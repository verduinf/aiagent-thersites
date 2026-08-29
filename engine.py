"""
Dual-Loop Agentic Orchestrator & Ollama Client for AI Agent Thersites
Handles prompt assembly, Turn-1 telemetry, fuzzy JSON parsing, subagent pipelines, and inner/outer execution loops.
"""
import re
import json
import requests
from typing import Dict, Any, List, Generator
from config import (
    OLLAMA_BASE_URL, MODEL_NAME, ROLLING_BUFFER_CHAR_LIMIT,
    PINNED_CONTEXT_CHAR_LIMIT, MAX_INNER_LOOP_TURNS, SCRATCHPAD_PATH
)
from database import (
    get_pinned_messages, get_rolling_messages, add_message,
    add_scratch_message
)
from bouncer import inspect_and_authorize
from console_logger import log_main, log_subagent, log_telemetry, INDICATOR_DONE, INDICATOR_THINKING, INDICATOR_BLOCKED

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
1. `web_fetch`: params `{"url": "https://whitelisted-domain.com"}`. (Fetches URL and auto-summarizes content).
2. `write_to_file`: params `{"filepath": "C:/Dev/aiagent-thersites/sandbox/file.txt", "content": "..."}`.
3. `write_to_scratchpad`: params `{"filepath": "scratchpad.md", "content": "..."}`.
4. `sqlite_query_executor`: params `{"query": "SELECT * FROM ...;"}`.
5. `none` or empty actions `[]`: Signal that you have finished your work and are ready to deliver your final answer.
"""

def extract_fuzzy_json(raw_text: str) -> Dict[str, Any]:
    """Uses regex to extract outermost JSON object from raw LLM string output."""
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in response.")
        
    json_str = match.group(0)
    data = json.loads(json_str)
    
    # Normalize structure
    thought = data.get("thought", "Processing...")
    content = data.get("content", "")
    actions = data.get("actions", [])
    
    if not isinstance(actions, list):
        if isinstance(data.get("action"), dict):
            actions = [data["action"]]
        else:
            actions = []
            
    return {"thought": thought, "content": content, "actions": actions}

def query_ollama(messages: List[Dict[str, str]], model: str = MODEL_NAME) -> str:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        # Return fallback JSON payload if Ollama call fails or is offline
        log_main(f"Ollama connection error ({e}). Using Therp simulation mode.", INDICATOR_BLOCKED)
        return json.dumps({
            "thought": "Ollama local inference unavailable or starting up.",
            "content": f"[Therp Proxy Note]: Local Ollama model '{model}' is currently offline. Here is a simulated response to verify engine & UI workflow.",
            "actions": []
        })

def run_subagent_summarizer(raw_text: str) -> str:
    """Spawns a clean, transient subagent context to summarize raw HTML/text."""
    log_subagent("HTML Summarizer", "Spawning secondary transient context...", INDICATOR_THINKING)
    
    sub_messages = [
        {"role": "system", "content": "You are a concise summarization subagent. Compress the input text into a clean 300-word markdown summary focusing on key factual points."},
        {"role": "user", "content": f"Summarize this content:\n\n{raw_text[:15000]}"}
    ]
    
    summary = query_ollama(sub_messages, model=MODEL_NAME)
    log_subagent("HTML Summarizer", f"Compressed raw text -> {len(summary)} chars", INDICATOR_DONE)
    return summary

def execute_tool_call(action: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = action.get("tool", action.get("name", "none"))
    params = action.get("params", {})
    action_id = action.get("id", "act_1")
    
    # Pass through Bouncer guardrails
    authorized, bouncer_msg, sanitized_params = inspect_and_authorize(tool_name, params)
    if not authorized:
        return {"id": action_id, "tool": tool_name, "status": "blocked", "result": bouncer_msg}
        
    try:
        if tool_name == "web_fetch":
            url = sanitized_params["url"]
            resp = requests.get(url, timeout=10)
            raw_html = resp.text
            # Pipelined Subagent Summarization
            summary = run_subagent_summarizer(raw_html)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": summary}
            
        elif tool_name == "write_to_file":
            filepath = sanitized_params["filepath"]
            content = sanitized_params.get("content", "")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Successfully written to '{filepath}'"}
            
        elif tool_name == "write_to_scratchpad":
            content = sanitized_params.get("content", "")
            with open(SCRATCHPAD_PATH, "w", encoding="utf-8") as f:
                f.write(content)
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Scratchpad updated at '{SCRATCHPAD_PATH.name}'"}
            
        elif tool_name in ("none", "finish", ""):
            return {"id": action_id, "tool": "none", "status": "success", "result": "Inner loop finished."}
            
        else:
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Executed tool '{tool_name}'"}
            
    except Exception as e:
        return {"id": action_id, "tool": tool_name, "status": "error", "result": f"Execution error: {str(e)}"}

def run_agent_inner_loop(session_id: str, user_prompt: str) -> Generator[Dict[str, Any], None, str]:
    """
    Inner Loop (Agentic Execution).
    Yields SSE telemetry dictionaries for live web streaming.
    Returns final user-facing string.
    """
    log_main(f"Starting Inner Loop for session '{session_id}' prompt: '{user_prompt[:50]}...'", INDICATOR_THINKING)
    
    # Add User Prompt to Outer Loop DB
    add_message(session_id, "user", user_prompt)
    
    scratch_history = []
    final_response = ""
    
    for turn in range(1, MAX_INNER_LOOP_TURNS + 1):
        # 1. Assemble Context Stack
        pinned_msgs = get_pinned_messages(session_id, PINNED_CONTEXT_CHAR_LIMIT)
        rolling_msgs = get_rolling_messages(session_id, ROLLING_BUFFER_CHAR_LIMIT)
        
        pinned_text = "\n".join([f"[PINNED ANCHOR Msg #{m['sequence_id']}]: {m['content']}" for m in pinned_msgs])
        rolling_char_count = sum(len(m["content"]) for m in rolling_msgs)
        
        # Turn-1 Consistent Spatial Telemetry Header
        telemetry_tag = f"[TELEMETRY: Turn {turn} of {MAX_INNER_LOOP_TURNS} | Rolling Buffer: {rolling_char_count:,} / {ROLLING_BUFFER_CHAR_LIMIT:,} chars]"
        log_telemetry(turn, MAX_INNER_LOOP_TURNS, rolling_char_count, ROLLING_BUFFER_CHAR_LIMIT)
        
        # Build System & Message List
        sys_content = f"{SYSTEM_CONTRACT}\n\n{telemetry_tag}"
        if pinned_text:
            sys_content += f"\n\n--- PINNED CONTEXT ANCHORS ---\n{pinned_text}"
            
        llm_messages = [{"role": "system", "content": sys_content}]
        
        # Add rolling history
        for m in rolling_msgs:
            llm_messages.append({"role": m["role"], "content": m["content"]})
            
        # Add transient scratch history
        for s in scratch_history:
            llm_messages.append({"role": "assistant", "content": json.dumps(s)})
            
        # Deterministic Loop Guardrail at Turn 4/5
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
            "status": "thinking"
        }
        
        # 2. Query Model
        raw_output = query_ollama(llm_messages)
        
        # 3. Parse JSON Action Payload
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
            
        # Yield Scratch Step to UI
        yield {
            "type": "scratch_step",
            "turn": turn,
            "thought": thought,
            "content": content,
            "actions": actions,
            "status": "executed"
        }
        
        # 4. Check Exit Conditions
        if not actions or all(a.get("tool", "") in ("none", "finish", "") for a in actions):
            log_main(f"Inner Loop Terminated cleanly on Turn {turn}.", INDICATOR_DONE)
            break
            
        # 5. Execute Action Array via Bouncer
        action_results = []
        for act in actions:
            res = execute_tool_call(act)
            action_results.append(res)
            add_scratch_message(session_id, turn, res.get("tool", "unknown"), json.dumps(res))
            
        scratch_history.append({"actions_executed": actions, "results": action_results})
        
    # Outer Loop: Commit final content to `messages` table
    final_msg = add_message(session_id, "assistant", final_response)
    log_main(f"Outer Loop Complete. Message #{final_msg['sequence_id']} saved.", INDICATOR_DONE)
    
    yield {
        "type": "final_response",
        "message": final_msg
    }
    
    return final_response

if __name__ == "__main__":
    print("Testing Engine Dual-Loop Structure...")
    from database import init_db, create_session
    init_db()
    sess = create_session("Test Engine Session")
    for event in run_agent_inner_loop(sess["id"], "Hello Thersites! What can you do?"):
        print("SSE Event:", event)
