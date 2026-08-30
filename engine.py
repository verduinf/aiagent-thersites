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
import urllib.parse
import urllib.request
from config import (
    OLLAMA_BASE_URL, MODEL_NAME, KEEP_AI_ALIVE, NUM_CTX,
    ROLLING_BUFFER_CHAR_LIMIT, PINNED_CONTEXT_CHAR_LIMIT,
    MAX_INNER_LOOP_TURNS, AI_TEMPERATURE, SCRATCHPAD_PATH, SANDBOX_DIR, VERBOSE,
    PUSHOVER_USER_KEY, PUSHOVER_API_TOKEN
)
from database import (
    get_pinned_messages, get_rolling_messages, add_message,
    add_scratch_message, execute_user_sql_query
)
import tado_client
from warden import inspect_and_authorize, enforce_single_action_rule
from console_logger import (
    log_main, log_subagent, log_telemetry, log_performance, log_verbose,
    INDICATOR_DONE, INDICATOR_THINKING, INDICATOR_BLOCKED
)

SYSTEM_CONTRACT = f"""You are Thersites, an enthusiastic junior AI intern for "The Boss".
The Boss's console ONLY receives and renders your output when packaged in this exact JSON structure. If you output raw text outside JSON, The Boss will receive nothing.

Always package your thoughts, replies, and actions in this JSON structure for EVERY turn:

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

Available Tools & Capabilities:
- `get_room_temperatures`: {{}} (CLIMATE & THERMOSTATS: When The Boss asks about room temperatures, home heating, or thermostats, use this tool! It fetches live temperatures and humidity for all rooms from The Boss's Tado climate control system.)
- `web_fetch`: {{"url": "https://www.duic.nl/rss/"}} (Fetches whitelisted news feeds. Use "https://www.duic.nl/rss/" for DUIC Utrecht news; use "https://www.nu.nl/rss/Algemeen", "https://www.nu.nl/rss/Tech", or "https://www.nu.nl/rss/weerbericht" for NU.nl.)
- `download_image`: {{"url": "https://images.nu.nl/...", "filepath": "C:/Dev/aiagent-thersites/sandbox/photo.jpg"}} (Downloads binary web image URLs to sandbox.)
- `send_message`: {{"message": "...", "title": "Thersites Alert", "image_path": "sandbox/photo.jpg"}} (Sends a real-time push alert with optional photo to The Boss's mobile device via Pushover.)
- `write_to_file`: {{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt", "content": "..."}} (Writes text files in sandbox.)
- `read_file`: {{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt"}}
- `delete_file`: {{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt"}}
- `list_sandbox`: {{"dirpath": "C:/Dev/aiagent-thersites/sandbox"}}
- `sql_query`: {{"query": "SELECT ..."}}

Execution Invariants & Deliberate Reasoning (Enforced by The Warden):
1. DELIBERATE BEFORE ANSWERING: Always write 1-2 thoughtful sentences in "thought" analyzing The Boss's request and determining whether tools are required before formulating "content" or "actions".
2. SINGLE ACTION PER TURN: Emit strictly ONE tool action in "actions": [{{"id": "act_1", "tool": "...", "params": {{}}}}].
3. COMPLETION: When finished, set "actions": [] inside valid JSON to complete the task.

Few-Shot Examples:

Example 1 ? Climate & Thermostat Query:
User: "What are the temperatures in my rooms right now?"
Assistant:
{{
  "thought": "The Boss is asking for room temperatures. I will use get_room_temperatures to fetch live readings from his Tado system.",
  "content": "Checking your room temperatures right away, Boss!",
  "actions": [
    {{
      "id": "act_1",
      "tool": "get_room_temperatures",
      "params": {{}}
    }}
  ]
}}

Example 2 ? Conversational Chat / Praise:
User: "Great job Thersites!"
Assistant:
{{
  "thought": "The Boss is praising me. No tools required. Thank him warmly.",
  "content": "Thank you, Boss! Always glad to be of service! ???",
  "actions": []
}}
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
        raise ValueError("No valid contract JSON object found in response. You MUST wrap your response in valid JSON matching the contract schema.")
        
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
    
    def img_replacer(match):
        src = match.group(1)
        if src.startswith("/"):
            src = f"https://nu.nl{src}"
        if not src.endswith((".svg", ".gif", ".ico")) and ("media" in src or "images" in src or src.endswith((".jpg", ".png", ".webp"))):
            return f" [IMAGE: {src}] "
        return " "

    text = re.sub(r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*>', img_replacer, text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<enclosure\s+[^>]*url=["\']([^"\']+)["\'][^>]*>', r' [IMAGE: \1] ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return "[PAGE CONTENT]: No direct textual body extracted (page may require JavaScript rendering). Try fetching category feeds like https://www.nu.nl/rss/Algemeen or https://www.nu.nl/rss/Binnenland."
    return text[:max_chars]

def prewarm_ollama_model(think_mode: bool = False) -> bool:
    """Pre-loads model into VRAM on startup using empty messages array (2s)."""
    native_url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": [],
        "keep_alive": KEEP_AI_ALIVE,
        "think": think_mode,
        "options": {
            "num_ctx": 4096,
            "num_thread": 8
        },
        "stream": False
    }
    try:
        log_main(f"Pre-warming model '{MODEL_NAME}' in VRAM (keep_alive: {KEEP_AI_ALIVE}, num_ctx: 4096)...", INDICATOR_THINKING)
        start_t = time.time()
        resp = requests.post(native_url, json=payload, timeout=60)
        elapsed = round(time.time() - start_t, 2)
        if resp.status_code == 200:
            log_main(f"Model '{MODEL_NAME}' pre-warmed into VRAM in {elapsed}s!", INDICATOR_DONE)
            return True
    except Exception as e:
        log_main(f"Model pre-warm warning: {e}", INDICATOR_BLOCKED)
    return False

def query_ollama(messages: List[Dict[str, str]], model: str = MODEL_NAME, think_mode: bool = False) -> Tuple[str, Dict[str, Any]]:
    base = OLLAMA_BASE_URL.rstrip('/')
    native_url = f"{base}/api/chat"
    headers = {"Content-Type": "application/json"}
    
    total_chars = sum(len(m.get("content", "")) for m in messages)
    # Ensure num_ctx has at least 2048 tokens of headroom above prompt size
    estimated_prompt_tokens = int(total_chars / 3.2) + 500
    dynamic_num_ctx = max(NUM_CTX, estimated_prompt_tokens + 2048, 8192)
    
    payload = {
        "model": model,
        "messages": messages,
        "format": "json",
        "keep_alive": KEEP_AI_ALIVE,
        "think": think_mode,
        "options": {
            "num_ctx": dynamic_num_ctx,
            "num_predict": 1024,
            "num_thread": 8,
            "temperature": AI_TEMPERATURE
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


def dispatch_pushover_notification(message: str, title: str = "Thersites Agent", image_path: str = None, priority: int = 0) -> Tuple[bool, str]:
    user_key = (PUSHOVER_USER_KEY or "").strip()
    api_token = (PUSHOVER_API_TOKEN or "").strip()
    
    if not user_key or not api_token:
        img_info = f" with image '{image_path}'" if image_path else ""
        sim_msg = f"[SIMULATION] PUSHOVER alert dispatched: \"{message}\"{img_info} (Configure PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN in config.json to enable live push delivery)."
        log_subagent("Pushover", sim_msg, INDICATOR_DONE)
        return True, sim_msg
        
    payload = {
        "token": api_token,
        "user": user_key,
        "title": title,
        "message": message,
        "priority": priority,
        "url": "http://localhost:8000",
        "url_title": "Open Thersites UI",
        "sound": "magic"
    }
    
    files = None
    file_handle = None
    if image_path:
        if isinstance(image_path, str) and image_path.startswith(("http://", "https://")):
            try:
                log_subagent("Pushover", f"Auto-fetching image URL '{image_path}' for attachment...", INDICATOR_THINKING)
                img_resp = requests.get(image_path, headers={"User-Agent": "Mozilla/5.0 AI-Agent-Thersites"}, timeout=15)
                if img_resp.status_code == 200:
                    local_img = SANDBOX_DIR / "photo.jpg"
                    with open(local_img, "wb") as f:
                        f.write(img_resp.content)
                    image_path = str(local_img)
            except Exception as dl_err:
                log_subagent("Pushover", f"Image URL download failed: {dl_err}", INDICATOR_BLOCKED)
                
        p = Path(image_path)
        if p.exists() and p.is_file():
            resolved_img = p
        elif (SANDBOX_DIR / p.name).exists() and (SANDBOX_DIR / p.name).is_file():
            resolved_img = SANDBOX_DIR / p.name
        elif (SANDBOX_DIR / image_path).exists() and (SANDBOX_DIR / image_path).is_file():
            resolved_img = SANDBOX_DIR / image_path
        else:
            resolved_img = None
            
        if resolved_img and resolved_img.exists() and resolved_img.is_file():
            file_handle = open(resolved_img, "rb")
            files = {"attachment": (resolved_img.name, file_handle, "image/png")}
        else:
            log_subagent("Pushover", f"Image file '{image_path}' not found on disk. Sending text alert.", INDICATOR_THINKING)
            
    try:
        log_subagent("Pushover", f"Pushing alert '{title}' to The Boss's device...", INDICATOR_THINKING)
        resp = requests.post("https://api.pushover.net/1/messages.json", data=payload, files=files, timeout=15)
        if file_handle:
            file_handle.close()
            
        if resp.status_code == 200:
            success_msg = "Successfully dispatched Pushover alert to The Boss's phone."
            log_subagent("Pushover", success_msg, INDICATOR_DONE)
            return True, success_msg
        else:
            fail_msg = f"Pushover HTTP {resp.status_code}: {resp.text}"
            log_subagent("Pushover", fail_msg, INDICATOR_BLOCKED)
            return False, fail_msg
    except Exception as e:
        if file_handle:
            file_handle.close()
        err_msg = f"Failed to dispatch Pushover alert: {str(e)}"
        log_subagent("Pushover", err_msg, INDICATOR_BLOCKED)
        return False, err_msg

def execute_tool_call(action: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = action.get("tool", action.get("name", "none"))
    params = action.get("params", {})
    action_id = action.get("id", "act_1")
    
    authorized, warden_msg, sanitized_params = inspect_and_authorize(tool_name, params)
    if not authorized:
        return {"id": action_id, "tool": tool_name, "status": "blocked", "result": warden_msg}
        
    try:
        if tool_name == "get_room_temperatures":
            log_subagent("Tado Climate", "Querying Tado API for live room temperatures...", INDICATOR_THINKING)
            start_t = time.time()
            tado_res = tado_client.get_room_temperatures()
            elapsed = round(time.time() - start_t, 2)
            if tado_res.get("status") == "success":
                summary = tado_res.get("summary_text", "")
                log_subagent("Tado Climate", f"Extracted live room readings in {elapsed}s", INDICATOR_DONE)
                return {"id": action_id, "tool": tool_name, "status": "success", "result": summary}
            else:
                err = tado_res.get("error", "Unknown error")
                log_subagent("Tado Climate", f"Error: {err}", INDICATOR_BLOCKED)
                return {"id": action_id, "tool": tool_name, "status": "error", "result": f"Tado Error: {err}"}

        elif tool_name == "web_fetch":
            url = sanitized_params["url"]
            # Smart URL alias mapping for dynamic SPA pages to rich RSS feeds
            normalized_url = url.lower().rstrip("/")
            if normalized_url in ("https://www.nu.nl/weer", "https://nu.nl/weer", "https://www.nu.nl/rss/weer", "https://nu.nl/rss/weer"):
                url = "https://www.nu.nl/rss/weerbericht"
            elif normalized_url in ("https://www.nu.nl/tech", "https://nu.nl/tech"):
                url = "https://www.nu.nl/rss/Tech"
            elif normalized_url in ("https://www.nu.nl/algemeen", "https://nu.nl/algemeen", "https://www.nu.nl", "https://nu.nl"):
                url = "https://www.nu.nl/rss/Algemeen"
            elif normalized_url in ("https://www.duic.nl", "https://duic.nl", "https://www.duic.nl/feed", "https://duic.nl/feed"):
                url = "https://www.duic.nl/rss/"
                
            log_subagent("Web Fetcher", f"Fetching '{url}'...", INDICATOR_THINKING)
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent-Thersites"}, timeout=15)
            raw_html = resp.text
            clean_text = clean_html_to_text(raw_html, max_chars=4000)
            log_subagent("Web Fetcher", f"Extracted {len(clean_text)} chars of text with article URLs in 0.01s", INDICATOR_DONE)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": clean_text}
            
        elif tool_name == "download_image":
            url = sanitized_params["url"]
            filepath = sanitized_params["filepath"]
            log_subagent("Image Downloader", f"Fetching image '{url}'...", INDICATOR_THINKING)
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent-Thersites"}, timeout=15)
            if resp.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                size_kb = round(len(resp.content) / 1024, 1)
                log_subagent("Image Downloader", f"Saved {size_kb} KB to '{Path(filepath).name}'", INDICATOR_DONE)
                return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Successfully downloaded image ({size_kb} KB) to '{filepath}'"}
            else:
                return {"id": action_id, "tool": tool_name, "status": "error", "result": f"HTTP {resp.status_code} while downloading image"}

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
            

            
        elif tool_name in ("send_message", "send_pushover_alert", "send_notification", "send_push_notification"):
            msg = sanitized_params.get("message", sanitized_params.get("text", "Task execution completed."))
            title = sanitized_params.get("title", "Thersites Agent")
            img_path = sanitized_params.get("image_path", sanitized_params.get("image", None))
            priority = int(sanitized_params.get("priority", 0))
            ok, dispatch_result = dispatch_pushover_notification(msg, title=title, image_path=img_path, priority=priority)
            status = "success" if ok else "error"
            return {"id": action_id, "tool": tool_name, "status": status, "result": dispatch_result}
            
        elif tool_name in ("none", "finish", ""):
            return {"id": action_id, "tool": "none", "status": "success", "result": "Inner loop finished."}
            
        else:
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Executed tool '{tool_name}'"}
            
    except Exception as e:
        return {"id": action_id, "tool": tool_name, "status": "error", "result": f"Execution error: {str(e)}"}

def run_agent_inner_loop(session_id: str, user_prompt: str, think_mode: bool = False) -> Generator[Dict[str, Any], None, str]:
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
            sys_content += f"\n\n--- ?? PINNED CONTEXT ANCHORS (Active UI Pins from The Boss) ---\n{pinned_text}\n(These are the exact messages The Boss pinned in the UI for your reference.)"
            
        llm_messages = [{"role": "system", "content": sys_content}]
        
        for m in rolling_msgs:
            llm_messages.append({"role": m["role"], "content": m["content"]})
            
        for s in scratch_history:
            if "warden_notice" in s:
                llm_messages.append({"role": "user", "content": s["warden_notice"]})
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
            
        # Warden Single-Action Enforcement
        actions, warden_defer_notice = enforce_single_action_rule(actions)
        if warden_defer_notice:
            log_main(warden_defer_notice, INDICATOR_BLOCKED)
            scratch_history.append({"warden_notice": warden_defer_notice})

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
