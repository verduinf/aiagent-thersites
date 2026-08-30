"""
The Warden — Guardrail Security & Scope Enforcer for AI Agent Thersites
Enforces sandbox enclosure, domain whitelisting, and SQL table mutation rules.
"""
import os
import re
from pathlib import Path
from config import SANDBOX_DIR, URL_DOMAIN_WHITELIST

from typing import Tuple, Dict, Any, List, Optional

def enforce_single_action_rule(actions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Enforces the Single-Action Invariant per turn.
    If multiple actions are emitted, truncates execution strictly to the first actionable tool call
    and defers the rest to subsequent turns to prevent multi-step hallucinations.
    """
    if not actions or len(actions) <= 1:
        return actions, None
        
    first_action = actions[0]
    deferred_count = len(actions) - 1
    deferred_tools = [a.get("tool", a.get("name", "tool")) for a in actions[1:]]
    
    warden_notice = (
        f"[WARDEN ENFORCEMENT]: Single-Action Rule Active. Executing strictly 1st action ('{first_action.get('tool')}'). "
        f"Deferred {deferred_count} bundled action(s) ({', '.join(deferred_tools)}) to the next turn to ensure step-by-step observation."
    )
    return [first_action], warden_notice

class WardenViolation(Exception):
    """Raised when a tool action violates safety or sandbox boundaries."""
    pass

def validate_url(url: str) -> Tuple[bool, str]:
    if not url or not isinstance(url, str):
        return False, "Invalid or missing URL parameter."
        
    for domain in URL_DOMAIN_WHITELIST:
        pattern = rf"^https?://(?:[a-zA-Z0-9-]+\.)*{re.escape(domain)}(?:/.*)?$"
        if re.match(pattern, url, re.IGNORECASE):
            return True, f"Domain '{domain}' authorized by The Warden."
            
    return False, f"Unauthorized domain '{url}'. URL must be in whitelist: {URL_DOMAIN_WHITELIST}"

def validate_write_path(filepath: str) -> Tuple[bool, str]:
    if not filepath or not isinstance(filepath, str):
        return False, "Invalid or missing filepath parameter."
        
    try:
        resolved = Path(filepath).resolve()
        sandbox_resolved = SANDBOX_DIR.resolve()
        
        if resolved.exists() and resolved.is_dir():
            return False, f"Target path '{filepath}' is a directory. Please specify a file name inside the sandbox (e.g., '{filepath}/bus_story.txt')."
            
        if resolved == sandbox_resolved or sandbox_resolved in resolved.parents:
            return True, f"Path '{filepath}' within sandbox enclosure."
        else:
            return False, f"Path sandbox violation. Target path '{filepath}' resolves outside '{SANDBOX_DIR}'"
    except Exception as e:
        return False, f"Invalid file path structure: {str(e)}"

def validate_sql_query(query: str) -> Tuple[bool, str]:
    if not query or not isinstance(query, str):
        return False, "Invalid or missing SQL query."
        
    clean_q = query.strip()
    is_select = clean_q.upper().startswith("SELECT")
    
    if is_select:
        return True, "Read-only SELECT query authorized by The Warden."
        
    forbidden_tables = ["messages", "sessions", "scratch_messages"]
    for table in forbidden_tables:
        if re.search(rf"\b{table}\b", clean_q, re.IGNORECASE):
            return False, f"SQL Write/Delete/Modification statements are restricted strictly to table 'thersites_scratchpad'. System tables ({', '.join(forbidden_tables)}) are read-only."
            
    if "thersites_scratchpad" in clean_q.lower():
        return True, "SQL mutation authorized on table 'thersites_scratchpad'."
        
    return False, "SQL mutations allowed ONLY on table 'thersites_scratchpad'."

def inspect_and_authorize(tool_name: str, params: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    if tool_name == "web_fetch":
        url = params.get("url", "")
        ok, msg = validate_url(url)
        return ok, msg, params
        
    elif tool_name == "download_image":
        url = params.get("url", "")
        filepath = params.get("filepath", "")
        url_ok, url_msg = validate_url(url)
        if not url_ok:
            return False, url_msg, params
        path_ok, path_msg = validate_write_path(filepath)
        if not path_ok:
            return False, path_msg, params
        return True, "Image download authorized by The Warden.", params
        
    elif tool_name in ("write_to_file", "read_file", "delete_file"):
        filepath = params.get("filepath", "")
        ok, msg = validate_write_path(filepath)
        return ok, msg, params
        
    elif tool_name == "list_sandbox":
        dirpath = params.get("dirpath", str(SANDBOX_DIR))
        ok, msg = validate_write_path(dirpath)
        if not ok and os.path.exists(dirpath):
            ok = True
            msg = "Sandbox directory listing authorized."
        return ok, msg, params
        
    elif tool_name == "sqlite_query_executor":
        query = params.get("query", "")
        ok, msg = validate_sql_query(query)
        return ok, msg, params
        
    elif tool_name in ("send_message", "send_pushover_alert", "send_notification", "send_push_notification"):
        msg = params.get("message", params.get("text", ""))
        if not msg:
            return False, "Missing required 'message' parameter.", params
        return True, "Pushover notification authorized by The Warden.", params
        
    elif tool_name in ("write_to_scratchpad", "none", "finish", ""):
        return True, "Authorized action.", params
        
    return True, f"Action '{tool_name}' allowed.", params
