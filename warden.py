"""
The Warden — Guardrail Security & Scope Enforcer for AI Agent Thersites
Enforces sandbox enclosure, domain whitelisting, and SQL table mutation rules.
"""
import os
import re
from pathlib import Path
from typing import Tuple, Dict, Any
from config import SANDBOX_DIR, URL_DOMAIN_WHITELIST

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
        
    elif tool_name in ("send_pushover_alert", "send_notification", "send_push_notification"):
        msg = params.get("message", params.get("text", ""))
        if not msg:
            return False, "Missing required 'message' parameter.", params
        return True, "Pushover notification authorized by The Warden.", params
        
    elif tool_name in ("write_to_scratchpad", "none", "finish", ""):
        return True, "Authorized action.", params
        
    return True, f"Action '{tool_name}' allowed.", params
