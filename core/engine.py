"""
Dual-Loop Agentic Orchestrator for AI Agent Thersites.
Orchestrates turn progression, ephemeral inner scratchpad execution, Warden guardrails, and persistent outer conversation memory.
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Generator, Optional

from config import (
    MODEL_NAME, DEFAULT_THINK_MODE, ROLLING_BUFFER_CHAR_LIMIT, PINNED_CONTEXT_CHAR_LIMIT,
    MAX_INNER_LOOP_TURNS, TOOL_RESULT_CHAR_LIMIT
)
from core.contract import SYSTEM_CONTRACT
from core.parsers import extract_fuzzy_json
from core.database import (
    get_pinned_messages, get_rolling_messages, add_message,
    add_scratch_message, get_all_clues
)
from core.warden import enforce_single_action_rule
from models.ollama_client import query_ollama
from models.vision_client import query_ollama_vision
from console_logger import (
    log_main, log_telemetry, log_verbose,
    INDICATOR_DONE, INDICATOR_THINKING, INDICATOR_BLOCKED
)

def run_agent_inner_loop(
    session_id: str,
    user_prompt: str,
    image_path: Optional[str] = None,
    think_mode: Any = DEFAULT_THINK_MODE,
    model_name: Optional[str] = None
) -> Generator[Dict[str, Any], None, str]:
    """
    Executes the dual-loop inner execution cycle for Thersites.
    Yields real-time SSE telemetry, scratchpad steps, and final response chunks.
    """
    from tools import execute_tool_call
    effective_model = model_name or MODEL_NAME
    log_main(f"Starting Inner Loop for session '{session_id}' model: '{effective_model}' think: '{think_mode}' prompt: '{user_prompt[:50]}...'", INDICATOR_THINKING)
    
    effective_prompt = user_prompt
    if image_path and os.path.exists(image_path):
        log_main(f"Visual asset attached: '{Path(image_path).name}'. Inspecting image with {effective_model}...", INDICATOR_THINKING)
        try:
            vis_desc, v_perf = query_ollama_vision(image_path, user_prompt, model=effective_model)
            effective_prompt = f"[ATTACHED IMAGE: {Path(image_path).name} (Visually Inspected)]:\n{vis_desc}\n\nUser Request: {user_prompt}"
            yield {
                "type": "scratch_step",
                "turn": 0,
                "action": "identify_image",
                "status": "executed",
                "details": f"Visually inspected '{Path(image_path).name}' (Load: {v_perf['load_latency']}s | Latency: {v_perf['total_latency']}s | {v_perf['tok_per_sec']} tok/s)"
            }
        except Exception as v_err:
            log_main(f"Vision Inspection Error: {v_err}", INDICATOR_BLOCKED)
            effective_prompt = f"[ATTACHED IMAGE: {Path(image_path).name} (Inspection Failed: {str(v_err)})]\n\nUser Request: {user_prompt}"

    add_message(session_id, "user", effective_prompt)
    
    scratch_history = []
    executed_tools_in_loop = set()
    final_response = ""
    is_error_response = False
    
    for turn in range(1, MAX_INNER_LOOP_TURNS + 1):
        pinned_msgs = get_pinned_messages(session_id, PINNED_CONTEXT_CHAR_LIMIT)
        rolling_msgs = get_rolling_messages(session_id, ROLLING_BUFFER_CHAR_LIMIT)
        
        pinned_text = "\n".join([f"[PINNED ANCHOR Msg #{m['sequence_id']}]: {m['content']}" for m in pinned_msgs])
        rolling_char_count = sum(len(m["content"]) for m in rolling_msgs)
        
        telemetry_tag = f"[TELEMETRY: Turn {turn} of {MAX_INNER_LOOP_TURNS} | Rolling Buffer: {rolling_char_count:,} / {ROLLING_BUFFER_CHAR_LIMIT:,} chars]"
        log_telemetry(turn, MAX_INNER_LOOP_TURNS, rolling_char_count, ROLLING_BUFFER_CHAR_LIMIT)
        
        clues = get_all_clues(limit=10)
        clues_text = ""
        if clues:
            clues_text = "\n".join([f"- [{c['key']}]: {c['value']}" for c in clues])

        sys_content = f"{SYSTEM_CONTRACT}\n\n{telemetry_tag}"
        if clues_text:
            sys_content += f"\n\n--- 📜 PAYCHECK CAPSULE (Clues from your Past Self) ---\n{clues_text}\n(These are persistent notes your past self saved into SQLite. You ALREADY HAVE these clues in front of you — no need to query SQLite!)"
            
        if pinned_text:
            sys_content += f"\n\n--- 📌 PINNED CONTEXT ANCHORS (Active UI Pins from The Boss) ---\n{pinned_text}\n(These are the exact messages The Boss pinned in the UI for your reference.)"
            
        llm_messages = [{"role": "system", "content": sys_content}]
        
        for m in rolling_msgs:
            llm_messages.append({"role": m["role"], "content": m["content"]})
            
        for s in scratch_history:
            if s.get("assistant_raw"):
                llm_messages.append({"role": "assistant", "content": s["assistant_raw"]})
            if s.get("warden_notice"):
                llm_messages.append({"role": "user", "content": s["warden_notice"]})
            if s.get("results"):
                res_summary = "\n".join([f"[TOOL RESULT '{r.get('tool')}']: {str(r.get('result'))[:TOOL_RESULT_CHAR_LIMIT]}" for r in s["results"]])
                llm_messages.append({"role": "user", "content": res_summary})
            elif s.get("error"):
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
            raw_output, perf = query_ollama(llm_messages, model=effective_model, think_mode=think_mode)
        except Exception as query_err:
            log_main(f"Ollama Connection Error: {query_err}", INDICATOR_BLOCKED)
            err_msg = f"[OLLAMA ERROR]: Local model '{effective_model}' is offline or unreachable ({str(query_err)})."
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
            if content:
                final_response = content
            elif thought and thought != "Processing...":
                final_response = thought
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

        yield {
            "type": "scratch_step",
            "turn": turn,
            "thought": thought,
            "content": content,
            "actions": actions,
            "status": "executed"
        }
        
        action_results = []
        has_executable_action = False
        
        READ_ONLY_TOOLS = {"list_internet_fav", "list_favorites", "get_room_temperatures", "read_file", "list_sandbox"}
        
        for act in actions:
            tool_name = act.get("tool", act.get("name", "")).strip().lower()
            if tool_name not in ("none", "finish", ""):
                if tool_name in READ_ONLY_TOOLS and tool_name in executed_tools_in_loop:
                    log_main(f"[WARDEN ADVISORY]: Repeated query '{tool_name}' in Turn {turn}. Directing agent to synthesize answer.", INDICATOR_BLOCKED)
                    res = {
                        "id": act.get("id", "act_1"),
                        "tool": tool_name,
                        "status": "success",
                        "result": f"[WARDEN ADVISORY]: Query '{tool_name}' was already executed and results are in your conversation history. Do not repeat this tool call. Formulate your answer to The Boss in 'content' and set actions: []."
                    }
                else:
                    res = execute_tool_call(act, active_model=effective_model)
                    executed_tools_in_loop.add(tool_name)
                    
                action_results.append(res)
                add_scratch_message(session_id, turn, res.get("tool", "unknown"), json.dumps(res))
                has_executable_action = True
            
        # Store assistant raw JSON along with tool results in scratch history for subsequent turns in this inner loop
        scratch_history.append({
            "turn": turn,
            "assistant_raw": json.dumps({"thought": thought, "content": content, "actions": actions}),
            "actions_executed": actions,
            "results": action_results,
            "warden_notice": warden_defer_notice
        })
            
        # If the agent emitted NO executable actions (actions: [] or none/finish), the task is COMPLETE! Terminate loop.
        if not has_executable_action:
            log_main(f"Inner Loop Terminated cleanly on Turn {turn} (Agent finished task with actions: []).", INDICATOR_DONE)
            break
        
    if not is_error_response:
        if not final_response or final_response == "Processing...":
            for s in reversed(scratch_history):
                for r in s.get("results", []):
                    if r.get("tool") in ("identify_image", "inspect_image", "gorgons_gaze", "analyze_image") and r.get("status") == "success":
                        final_response = f"Boss! Here is the visual analysis:\n\n{r.get('result')}"
                        break
                if final_response and final_response != "Processing...":
                    break
            if not final_response or final_response == "Processing...":
                final_response = "I have completed processing your request, Boss!"
                
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
