"""
The Warden — Programmatic Security & Sandbox Guardrail Overseer
Enforces sandbox path enclosure in /sandbox/, URL domain checks (strictly nu.nl), and SQL query safety.
"""
from pathlib import Path
from urllib.parse import urlparse
from typing import Tuple, Dict, Any
from config import SANDBOX_DIR, URL_DOMAIN_WHITELIST, SCRATCHPAD_PATH
from console_logger import log_warden

class WardenViolation(Exception):
    """Exception raised when an action violates security guardrail policies."""
    pass

def validate_url(url: str) -> str:
    """Verifies target URL domain against whitelist."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    
    if not any(hostname == domain or hostname.endswith("." + domain) for domain in URL_DOMAIN_WHITELIST):
        err_msg = f"[ERROR: Unauthorized domain '{hostname}'. URL must be in whitelist: {URL_DOMAIN_WHITELIST}]"
        log_warden("web_fetch", allowed=False, details=err_msg)
        raise WardenViolation(err_msg)
        
    log_warden("web_fetch", allowed=True, details=f"Domain '{hostname}' authorized by The Warden.")
    return url

def validate_write_path(target_path: str) -> Path:
    """Enforces strict path resolution inside C:/Dev/aiagent-thersites/sandbox or scratchpad.md."""
    path_obj = Path(target_path).resolve()
    
    # Override/Allow scratchpad.md explicitly
    if path_obj == SCRATCHPAD_PATH.resolve():
        log_warden("write_to_scratchpad", allowed=True, details=f"Path '{path_obj.name}' authorized as scratchpad.")
        return path_obj
        
    sandbox_resolved = SANDBOX_DIR.resolve()
    try:
        path_obj.relative_to(sandbox_resolved)
    except ValueError:
        err_msg = f"[ERROR: Path sandbox violation. Target path '{target_path}' resolves outside '{sandbox_resolved}']"
        log_warden("write_to_file", allowed=False, details=err_msg)
        raise WardenViolation(err_msg)
        
    log_warden("write_to_file", allowed=True, details=f"Path '{path_obj.name}' within sandbox enclosure.")
    return path_obj

def validate_sql_query(query: str) -> str:
    """
    Enforces SQL Query Safety:
    - SELECT queries (Read-Only) allowed across all project data tables.
    - Write/Update/Delete/Modify queries allowed ONLY on table 'thersites_scratchpad'.
    """
    q_clean = query.strip().upper()
    
    if q_clean.startswith("SELECT") or q_clean.startswith("EXPLAIN") or q_clean.startswith("PRAGMA"):
        log_warden("sqlite_query_executor", allowed=True, details="Read-only SELECT query authorized by The Warden.")
        return query
        
    # Check if mutation target is strictly thersites_scratchpad
    if "THERSITES_SCRATCHPAD" in q_clean:
        log_warden("sqlite_query_executor", allowed=True, details="SQL mutation authorized on table 'thersites_scratchpad'.")
        return query
    else:
        err_msg = "[ERROR: SQL Write/Delete/Modification statements are restricted strictly to table 'thersites_scratchpad'. System tables (messages, sessions, scratch_messages) are read-only.]"
        log_warden("sqlite_query_executor", allowed=False, details=err_msg)
        raise WardenViolation(err_msg)

def inspect_and_authorize(tool_name: str, params: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """Programmatically inspects and authorizes tool calls before execution."""
    try:
        sanitized_params = dict(params)
        
        if tool_name == "web_fetch":
            url = params.get("url", "")
            sanitized_params["url"] = validate_url(url)
            
        elif tool_name in ("write_to_file", "read_file", "delete_file", "list_sandbox"):
            filepath = params.get("filepath", params.get("dirpath", str(SANDBOX_DIR)))
            validated_path = validate_write_path(filepath)
            sanitized_params["filepath"] = str(validated_path)
            
        elif tool_name == "write_to_scratchpad":
            sanitized_params["filepath"] = str(SCRATCHPAD_PATH)
            
        elif tool_name == "sqlite_query_executor":
            query = params.get("query", "")
            sanitized_params["query"] = validate_sql_query(query)
            
        return True, "Authorized by The Warden", sanitized_params
        
    except WardenViolation as e:
        return False, str(e), params
    except Exception as ex:
        err = f"Warden Inspection Exception: {str(ex)}"
        log_warden(tool_name, allowed=False, details=err)
        return False, err, params
