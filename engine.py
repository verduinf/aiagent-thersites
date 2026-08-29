"""
Dual-Loop Agentic Orchestrator & Ollama Client for AI Agent Thersites
Handles prompt assembly, Turn-1 telemetry, fuzzy JSON parsing, fast HTML text extraction with link preservation, and inner/outer execution loops.
"""
import os
import re
import json
import time
import requests
from pathlib import Path
from typing import Dict, Any, List, Generator, Tuple
from config import (
    OLLAMA_BASE_URL, MODEL_NAME, KEEP_AI_ALIVE, NUM_CTX,
    ROLLING_BUFFER_CHAR_LIMIT, PINNED_CONTEXT_CHAR_LIMIT,
    MAX_INNER_LOOP_TURNS, SCRATCHPAD_PATH, SANDBOX_DIR, VERBOSE
)
from database import (
    get_pinned_messages, get_rolling_messages, add_message,
    add_scratch_message, execute_user_sql_query
)
from warden import inspect_and_authorize
from console_logger import (
    log_main, log_subagent, log_telemetry, log_performance, log_verbose,
    INDICATOR_DONE, INDICATOR_THINKING, INDICATOR_BLOCKED
)

SYSTEM_CONTRACT = f"""You are Thersites, an enthusiastic junior AI intern for "The Boss".
Always output RAW JSON matching this exact structure:

{{
  "thought": "<internal junior dev reasoning>",
  "content": "<message to The Boss>",
  "actions": [
    {{
      "id": "act_1",
      "tool": "<tool_name_or_none>",
      "params": {{}}
    }}
  ]
}}

Available Tools (Restricted strictly to C:/Dev/aiagent-thersites/sandbox):
- `web_fetch`: {{"url": "https://nu.nl"}} (Fetches any whitelisted nu.nl page or article URL)
- `write_to_file`: {{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt", "content": "..."}}
- `read_file`: {{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt"}}
- `delete_file`: {{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt"}}
- `list_sandbox`: {{"dirpath": "C:/Dev/aiagent-thersites/sandbox"}}
- `write_to_scratchpad`: {{"content": "..."}}
- `sqlite_query_executor`: {{"query": "SELECT * FROM thersites_scratchpad;"}} (Full CRUD on thersites_scratchpad only)
- `none` or empty actions []: Signal work completion.

Plan-First Multi-Turn Workflow:
1. For multi-step tasks (or when asked to check pinned instructions), use `write_to_scratchpad` on Turn 1 to outline your Step Plan (you have up to {MAX_INNER_LOOP_TURNS} turns, so keep your plan to 5-6 steps max).
2. Execute one tool step per turn so you can inspect tool results before taking the next action.
3. Signal completion of all steps by outputting empty "actions": [] when all steps are executed successfully.
4. If the prompt asks to check pinned instructions, inspect PINNED CONTEXT ANCHORS for active directives and execute them.
"""

def extract_fuzzy_json(raw_text: str) -> Dict[str, Any]:
    clean_text = raw_text.strip()
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\s*```$", "", clean_text)
        
    decoder = json.JSONDecoder()
    idx = 0
    valid_candidates = []
    
    while idx < len(clean_text):
        pos = clean_text.find('{', idx)
        if pos == -1:
            break
        try:
            obj, end = decoder.raw_decode(clean_text, pos)
            if isinstance(obj, dict):
                valid_candidates.append(obj)
                idx = end
                continue
        except json.JSONDecodeError:
            pass
        idx = pos + 1
        
    data = None
    for candidate in valid_candidates:
        if "thought" in candidate or "actions" in candidate:
            data = candidate
            break
            
    if not data and valid_candidates:
        data = valid_candidates[0]
        
    if not data:
        raise ValueError("No valid contract JSON object found in response.")
        
    thought = data.get("thought", "Processing...")
    content = data.get("content", "")
    actions = data.get("actions", [])
    
    if not isinstance(actions, list):
        if isinstance(data.get("action"), dict):
            actions = [data["action"]]
        else:
            actions = []
            
    return {"thought": thought, "content": content, "actions": actions}

def clean_html_to_text(html_content: str, max_chars: int = 4000) -> str:
    """Robust HTML stripper prioritizing <main> / <article> blocks and filtering nav noise."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<svg[^>]*>.*?</svg>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    main_matches = re.findall(r'<(main|article)[^>]*>(.*?)</\1>', text, flags=re.DOTALL | re.IGNORECASE)
    if main_matches:
        text = " ".join([m[1] for m in main_matches])
    else:
        text = re.sub(r'<(header|nav|footer)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<div[^>]*(header|nav|menu|footer)[^>]*>.*?</div>', '', text, flags=re.DOTALL | re.IGNORECASE)

    NAV_KEYWORDS = {'voorpagina', 'net binnen', 'binnenland', 'buitenland', 'politiek', 'economie', 'sport', 
                    'formule 1', 'wielrennen', 'inloggen', 'zoeken', 'menu', 'tv-gids', 'weer', 'spellen', 'shop'}

    def link_replacer(match):
        href = match.group(1)
        anchor_text = re.sub(r'<[^>]+>', ' ', match.group(2)).strip()
        
        if href.startswith("/"):
            href = f"https://nu.nl{href}"
            
        lower_anchor = anchor_text.lower()
        if lower_anchor in NAV_KEYWORDS or len(anchor_text) < 12 or href.endswith(('.css', '.js', '.png', '.jpg', '.svg', '.gif')):
            return f" {anchor_text} "
            
        return f" [{anchor_text}]({href}) "

    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', link_replacer, text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_chars]

def prewarm_ollama_model() -> bool:
    """Pre-loads model into VRAM on startup using empty messages array (2s)."""
    native_url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": [],
        "keep_alive": KEEP_AI_ALIVE,
        "options": {
            "num_ctx": 2048,
            "num_thread": 8
        },
        "stream": False
    }
    try:
        log_main(f"Pre-warming model '{MODEL_NAME}' in VRAM (keep_alive: {KEEP_AI_ALIVE}, num_ctx: 2048)...", INDICATOR_THINKING)
        start_t = time.time()
        resp = requests.post(native_url, json=payload, timeout=60)
        elapsed = round(time.time() - start_t, 2)
        if resp.status_code == 200:
            log_main(f"Model '{MODEL_NAME}' pre-warmed into VRAM in {elapsed}s!", INDICATOR_DONE)
            return True
    except Exception as e:
        log_main(f"Model pre-warm warning: {e}", INDICATOR_BLOCKED)
    return False

def query_ollama(messages: List[Dict[str, str]], model: str = MODEL_NAME) -> Tuple[str, Dict[str, Any]]:
    base = OLLAMA_BASE_URL.rstrip('/')
    native_url = f"{base}/api/chat"
    headers = {"Content-Type": "application/json"}
    
    total_chars = sum(len(m.get("content", "")) for m in messages)
    dynamic_num_ctx = 2048 if total_chars < 5000 else 4096
    
    payload = {
        "model": model,
        "messages": messages,
        "keep_alive": KEEP_AI_ALIVE,
        "options": {
            "num_ctx": dynamic_num_ctx,
            "num_thread": 8,
            "temperature": 0.7
        },
        "stream": False
    }
    
    start_t = time.time()
    perf_metrics = {
        "tok_per_sec": 0.0,
        "latency_sec": 0.0,
        "eval_count": 0,
        "dynamic_num_ctx": dynamic_num_ctx
    }
    
    try:
        response = requests.post(native_url, headers=headers, json=payload, timeout=120)
        wall_time = time.time() - start_t
        if response.status_code == 200:
            data = response.json()
            raw_content = data["message"]["content"]
            
            eval_count = data.get("eval_count", len(raw_content) // 4)
            eval_duration_ns = data.get("eval_duration", 0)
            total_duration_ns = data.get("total_duration", 0)
            
            if eval_duration_ns > 0:
                tok_per_sec = (eval_count / eval_duration_ns) * 1e9
            else:
                tok_per_sec = eval_count / wall_time if wall_time > 0 else 0
                
            latency_sec = (total_duration_ns / 1e9) if total_duration_ns > 0 else wall_time
            
            perf_metrics = {
                "tok_per_sec": round(tok_per_sec, 1),
                "latency_sec": round(latency_sec, 2),
                "eval_count": eval_count,
                "dynamic_num_ctx": dynamic_num_ctx
            }
            log_performance(perf_metrics["tok_per_sec"], perf_metrics["latency_sec"], perf_metrics["eval_count"])
            return raw_content, perf_metrics
        else:
            raise RuntimeError(f"Ollama returned HTTP {response.status_code}: {response.text}")
    except Exception as e:
        log_main(f"Ollama connection error: {e}", INDICATOR_BLOCKED)
        raise RuntimeError(f"Ollama connection error: {str(e)}")

def execute_tool_call(action: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = action.get("tool", action.get("name", "none"))
    params = action.get("params", {})
    action_id = action.get("id", "act_1")
    
    authorized, warden_msg, sanitized_params = inspect_and_authorize(tool_name, params)
    if not authorized:
        return {"id": action_id, "tool": tool_name, "status": "blocked", "result": warden_msg}
        
    try:
        if tool_name == "web_fetch":
            url = sanitized_params["url"]
            log_subagent("Web Fetcher", f"Fetching '{url}'...", INDICATOR_THINKING)
            resp = requests.get(url, timeout=10)
            raw_html = resp.text
            clean_text = clean_html_to_text(raw_html, max_chars=4000)
            log_subagent("Web Fetcher", f"Extracted {len(clean_text)} chars of text with article URLs in 0.01s", INDICATOR_DONE)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": clean_text}
            
        elif tool_name == "write_to_file":
            filepath = sanitized_params["filepath"]
            content = sanitized_params.get("content", "")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Successfully written to '{filepath}'"}
            
        elif tool_name == "read_file":
            filepath = sanitized_params["filepath"]
            if not os.path.exists(filepath):
                return {"id": action_id, "tool": tool_name, "status": "error", "result": f"File not found: '{filepath}'"}
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return {"id": action_id, "tool": tool_name, "status": "success", "result": content}
            
        elif tool_name == "delete_file":
            filepath = sanitized_params["filepath"]
            if not os.path.exists(filepath):
                return {"id": action_id, "tool": tool_name, "status": "error", "result": f"File not found: '{filepath}'"}
            os.remove(filepath)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Successfully deleted '{filepath}'"}
            
        elif tool_name == "list_sandbox":
            dirpath = sanitized_params.get("dirpath", str(SANDBOX_DIR))
            items = os.listdir(dirpath)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Sandbox items in '{dirpath}': {items}"}
            
        elif tool_name == "write_to_scratchpad":
            content = sanitized_params.get("content", "")
            with open(SCRATCHPAD_PATH, "w", encoding="utf-8") as f:
                f.write(content)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Scratchpad updated at '{SCRATCHPAD_PATH.name}'"}
            
        elif tool_name == "sqlite_query_executor":
            query = sanitized_params["query"]
            sql_results = execute_user_sql_query(query)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": sql_results}
            
        elif tool_name in ("none", "finish", ""):
            return {"id": action_id, "tool": "none", "status": "success", "result": "Inner loop finished."}
            
        else:
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Executed tool '{tool_name}'"}
            
    except Exception as e:
        return {"id": action_id, "tool": tool_name, "status": "error", "result": f"Execution error: {str(e)}"}

def run_agent_inner_loop(session_id: str, user_prompt: str) -> Generator[Dict[str, Any], None, str]:
    log_main(f"Starting Inner Loop for session '{session_id}' prompt: '{user_prompt[:50]}...'", INDICATOR_THINKING)
    add_message(session_id, "user", user_prompt)
    
    scratch_history = []
    final_response = ""
    is_error_response = False
    
    for turn in range(1, MAX_INNER_LOOP_TURNS + 1):
        pinned_msgs = get_pinned_messages(session_id, PINNED_CONTEXT_CHAR_LIMIT)
        rolling_msgs = get_rolling_messages(session_id, ROLLING_BUFFER_CHAR_LIMIT)
        
        pinned_text = "\n".join([f"[PINNED ANCHOR Msg #{m['sequence_id']}]: {m['content']}" for m in pinned_msgs])
        rolling_char_count = sum(len(m["content"]) for m in rolling_msgs)
        
        telemetry_tag = f"[TELEMETRY: Turn {turn} of {MAX_INNER_LOOP_TURNS} | Rolling Buffer: {rolling_char_count:,} / {ROLLING_BUFFER_CHAR_LIMIT:,} chars]"
        log_telemetry(turn, MAX_INNER_LOOP_TURNS, rolling_char_count, ROLLING_BUFFER_CHAR_LIMIT)
        
        sys_content = f"{SYSTEM_CONTRACT}\n\n{telemetry_tag}"
        if pinned_text:
            sys_content += f"\n\n--- PINNED CONTEXT ANCHORS ---\n{pinned_text}"
            
        llm_messages = [{"role": "system", "content": sys_content}]
        
        for m in rolling_msgs:
            llm_messages.append({"role": m["role"], "content": m["content"]})
            
        for s in scratch_history:
            if "results" in s:
                res_summary = "\n".join([f"[TOOL RESULT '{r.get('tool')}']: {str(r.get('result'))[:4000]}" for r in s.get("results", [])])
                llm_messages.append({"role": "user", "content": res_summary})
            elif "error" in s:
                llm_messages.append({"role": "user", "content": f"[SYSTEM ERROR]: {s['error']}"})
            
        if turn >= MAX_INNER_LOOP_TURNS - 1:
            llm_messages.append({
                "role": "user",
                "content": f"[LOOP GUARDRAIL]: Turn {turn} of {MAX_INNER_LOOP_TURNS}. Wrap up your tool calls and set actions: [] on your next response."
            })
            
        yield {
            "type": "telemetry",
            "turn": turn,
            "max_turns": MAX_INNER_LOOP_TURNS,
            "char_count": rolling_char_count,
            "max_chars": ROLLING_BUFFER_CHAR_LIMIT,
            "active_rolling_ids": [m["id"] for m in rolling_msgs],
            "status": "thinking"
        }
        
        try:
            raw_output, perf = query_ollama(llm_messages)
        except Exception as query_err:
            log_main(f"Ollama Connection Error: {query_err}", INDICATOR_BLOCKED)
            err_msg = f"[OLLAMA ERROR]: Local model 'qwen3.5:9b' is offline or unreachable ({str(query_err)})."
            add_scratch_message(session_id, turn, "ollama_error", err_msg)
            is_error_response = True
            final_response = err_msg
            yield {
                "type": "scratch_step",
                "turn": turn,
                "action": "ollama_error",
                "status": "error",
                "details": err_msg
            }
            break
            
        yield {
            "type": "performance",
            "tok_per_sec": perf["tok_per_sec"],
            "latency_sec": perf["latency_sec"],
            "eval_count": perf["eval_count"]
        }
        
        try:
            parsed = extract_fuzzy_json(raw_output)
            thought = parsed["thought"]
            content = parsed["content"]
            actions = parsed["actions"]
            final_response = content or thought
        except Exception as json_err:
            scratch_entry = add_scratch_message(session_id, turn, "json_parse_error", raw_output)
            scratch_id = scratch_entry.get("id", "N/A")
            
            log_main(f"JSON Parse Error (Scratch Msg #{scratch_id}): {json_err}. Triggering self-correction retry.", INDICATOR_BLOCKED)
            log_verbose(f"RAW LLM OUTPUT (Scratch Msg #{scratch_id})", raw_output)
            
            scratch_history.append({"error": f"JSON Parse Error: {str(json_err)}. Output raw valid JSON only matching schema."})
            yield {
                "type": "scratch_step",
                "turn": turn,
                "action": "json_retry",
                "status": "error",
                "details": f"JSON Parse Error (Scratch Msg #{scratch_id}): {str(json_err)}"
            }
            continue
            
        yield {
            "type": "scratch_step",
            "turn": turn,
            "thought": thought,
            "content": content,
            "actions": actions,
            "status": "executed"
        }
        
        if not actions or all(a.get("tool", "") in ("none", "finish", "") for a in actions):
            log_main(f"Inner Loop Terminated cleanly on Turn {turn}.", INDICATOR_DONE)
            break
            
        action_results = []
        for act in actions:
            res = execute_tool_call(act)
            action_results.append(res)
            add_scratch_message(session_id, turn, res.get("tool", "unknown"), json.dumps(res))
            
        scratch_history.append({"actions_executed": actions, "results": action_results})
        
    if not is_error_response:
        final_msg = add_message(session_id, "assistant", final_response)
        log_main(f"Outer Loop Complete. Message #{final_msg['sequence_id']} saved.", INDICATOR_DONE)
        yield {
            "type": "final_response",
            "message": final_msg
        }
    else:
        log_main("Outer Loop Terminated with error. Error message omitted from outer context history.", INDICATOR_BLOCKED)
        yield {
            "type": "final_response",
            "message": {"id": -1, "sequence_id": -1, "role": "assistant", "content": final_response, "created_at": "now"}
        }
        
    return final_response
