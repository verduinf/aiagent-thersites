"""
Dual-Loop Agentic Orchestrator & Ollama Client for AI Agent Thersites
Handles prompt assembly, Turn-1 telemetry, fuzzy JSON parsing, subagent pipelines, and inner/outer execution loops.
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
    MAX_INNER_LOOP_TURNS, SCRATCHPAD_PATH, SANDBOX_DIR
)
from database import (
    get_pinned_messages, get_rolling_messages, add_message,
    add_scratch_message, execute_user_sql_query
)
from warden import inspect_and_authorize
from console_logger import (
    log_main, log_subagent, log_telemetry, log_performance,
    INDICATOR_DONE, INDICATOR_THINKING, INDICATOR_BLOCKED
)

SYSTEM_CONTRACT = """You are Thersites, a contextually-challenged, error-prone, but deeply enthusiastic AI Intern.
You work under "The Boss" and must ALWAYS respond with a structured JSON object containing your internal thoughts, user-facing content, and an array of actions.

CRITICAL FORMATTING RULE: You MUST output valid JSON matching this exact structure:

{
  "thought": "<your internal junior dev reasoning>",
  "content": "<what you say to The Boss>",
  "actions": [
    {
      "id": "act_1",
      "tool": "<tool_name_or_none>",
      "params": {}
    }
  ]
}

Available Tools:
1. `web_fetch`: params `{"url": "https://nu.nl"}`. (Fetches URL and auto-summarizes content. ONLY whitelisted URL is nu.nl).
2. `write_to_file`: params `{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt", "content": "..."}`.
3. `read_file`: params `{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt"}`.
4. `delete_file`: params `{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt"}`.
5. `list_sandbox`: params `{"dirpath": "C:/Dev/aiagent-thersites/sandbox"}`.
6. `write_to_scratchpad`: params `{"filepath": "scratchpad.md", "content": "..."}`.
7. `sqlite_query_executor`: params `{"query": "SELECT * FROM thersites_scratchpad;"}`. (Read-only on project data tables, Full CRUD allowed ONLY on table 'thersites_scratchpad').
8. `none` or empty actions `[]`: Signal that you have finished your work and are ready to deliver your final answer.

CONTEXT RECOVERY RULE: If you sense you are missing specific file paths, requirements, or details mentioned earlier that might be outside your active 20k rolling context buffer, politely ask The Boss in your 'content' message to pin that earlier message or repeat the detail (e.g., "Boss, I feel like you mentioned a specific file path earlier outside my 20k rolling window. Could you pin that earlier message for me?").
"""

def extract_fuzzy_json(raw_text: str) -> Dict[str, Any]:
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in response.")
        
    json_str = match.group(0)
    data = json.loads(json_str)
    
    thought = data.get("thought", "Processing...")
    content = data.get("content", "")
    actions = data.get("actions", [])
    
    if not isinstance(actions, list):
        if isinstance(data.get("action"), dict):
            actions = [data["action"]]
        else:
            actions = []
            
    return {"thought": thought, "content": content, "actions": actions}

def prewarm_ollama_model() -> bool:
    """Pre-warms local Ollama model into VRAM during server startup."""
    native_url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": "ping"}],
        "keep_alive": KEEP_AI_ALIVE,
        "options": {"num_ctx": NUM_CTX},
        "stream": False
    }
    try:
        log_main(f"Pre-warming model '{MODEL_NAME}' in VRAM (keep_alive: {KEEP_AI_ALIVE}, num_ctx: {NUM_CTX})...", INDICATOR_THINKING)
        start_t = time.time()
        resp = requests.post(native_url, json=payload, timeout=120)
        elapsed = round(time.time() - start_t, 2)
        if resp.status_code == 200:
            log_main(f"Model '{MODEL_NAME}' pre-warmed successfully in {elapsed}s!", INDICATOR_DONE)
            return True
    except Exception as e:
        log_main(f"Model pre-warm warning: {e}", INDICATOR_BLOCKED)
    return False

def query_ollama(messages: List[Dict[str, str]], model: str = MODEL_NAME) -> Tuple[str, Dict[str, Any]]:
    base = OLLAMA_BASE_URL.rstrip('/')
    native_url = f"{base}/api/chat"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "keep_alive": KEEP_AI_ALIVE,
        "options": {
            "num_ctx": NUM_CTX
        },
        "stream": False
    }
    
    start_t = time.time()
    perf_metrics = {
        "tok_per_sec": 0.0,
        "latency_sec": 0.0,
        "eval_count": 0
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
                "eval_count": eval_count
            }
            log_performance(perf_metrics["tok_per_sec"], perf_metrics["latency_sec"], perf_metrics["eval_count"])
            return raw_content, perf_metrics
        else:
            raise RuntimeError(f"Ollama returned HTTP {response.status_code}: {response.text}")
    except Exception as e:
        log_main(f"Ollama connection error: {e}", INDICATOR_BLOCKED)
        raise RuntimeError(f"Ollama connection error: {str(e)}")

def run_subagent_summarizer(raw_text: str) -> str:
    log_subagent("HTML Summarizer", "Spawning secondary transient context...", INDICATOR_THINKING)
    sub_messages = [
        {"role": "system", "content": "You are a concise summarization subagent. Compress the input text into a clean 300-word markdown summary focusing on key factual points."},
        {"role": "user", "content": f"Summarize this content:\n\n{raw_text[:15000]}"}
    ]
    summary, _ = query_ollama(sub_messages)
    log_subagent("HTML Summarizer", f"Compressed raw text -> {len(summary)} chars", INDICATOR_DONE)
    return summary

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
            resp = requests.get(url, timeout=10)
            raw_html = resp.text
            summary = run_subagent_summarizer(raw_html)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": summary}
            
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
            llm_messages.append({"role": "assistant", "content": json.dumps(s)})
            
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
            yield {
                "type": "scratch_step",
                "turn": turn,
                "action": "ollama_error",
                "status": "error",
                "details": err_msg
            }
            final_response = err_msg
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
            log_main(f"JSON Parse Error: {json_err}. Triggering self-correction retry.", INDICATOR_BLOCKED)
            scratch_history.append({"error": f"JSON Parse Error: {str(json_err)}. Output raw valid JSON only."})
            add_scratch_message(session_id, turn, "json_parse_error", str(json_err))
            yield {
                "type": "scratch_step",
                "turn": turn,
                "action": "json_retry",
                "status": "error",
                "details": f"JSON Parse Error: {str(json_err)}"
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
        
    final_msg = add_message(session_id, "assistant", final_response)
    log_main(f"Outer Loop Complete. Message #{final_msg['sequence_id']} saved.", INDICATOR_DONE)
    
    yield {
        "type": "final_response",
        "message": final_msg
    }
    
    return final_response
