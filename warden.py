"""
The Warden — Guardrail Security & Scope Enforcer for AI Agent Thersites
Enforces sandbox enclosure, domain whitelisting, and SQL table mutation rules.
"""
import os
import re
from pathlib import Path
import ipaddress
import socket
import urllib.parse
from config import BASE_DIR, SANDBOX_DIR, UPLOADS_DIR, URL_DOMAIN_BLACKLIST

from typing import Tuple, Dict, Any, List, Optional

def enforce_single_action_rule(actions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Enforces the Single-Action Invariant per turn with Internal Memory Co-Action Exemption:
    - At most ONE external I/O action (web_fetch, download_image, get_room_temperatures, send_message, etc.)
    - At most ONE internal memory action (remember, unremember)
    Allows Thersites to record persistent notes/clues alongside an external tool execution or conclusion.
    """
    if not actions or len(actions) <= 1:
        return actions, None
        
    MEMORY_TOOLS = {"remember", "unremember", "forget", "list_internet_fav", "list_favorites"}
    PASSIVE_TOOLS = {"none", "finish", ""}
    
    external_actions = []
    memory_actions = []
    deferred_actions = []
    
    for a in actions:
        tool = a.get("tool", a.get("name", "")).strip().lower()
        if tool in MEMORY_TOOLS:
            if not memory_actions:
                memory_actions.append(a)
            else:
                deferred_actions.append(tool)
        elif tool not in PASSIVE_TOOLS:
            if not external_actions:
                external_actions.append(a)
            else:
                deferred_actions.append(tool)
                
    # Reassemble preserving original relative order
    filtered_actions = []
    for a in actions:
        if a in external_actions or a in memory_actions:
            if a not in filtered_actions:
                filtered_actions.append(a)
                
    if not filtered_actions:
        filtered_actions = [actions[0]]
        
    if deferred_actions:
        warden_notice = (
            f"[WARDEN ENFORCEMENT]: Single-Action Rule Active. Executing allowed action bundle ({', '.join(a.get('tool') for a in filtered_actions)}). "
            f"Deferred {len(deferred_actions)} bundled action(s) ({', '.join(deferred_actions)}) to subsequent turns."
        )
        return filtered_actions, warden_notice
        
    return filtered_actions, None

class WardenViolation(Exception):
    """Raised when a tool action violates safety or sandbox boundaries."""
    pass

def validate_url(url: str) -> Tuple[bool, str]:
    if not url or not isinstance(url, str):
        return False, "Invalid or missing URL parameter."
        
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Protocol '{parsed.scheme}' blocked. Only 'http://' and 'https://' are authorized."
            
        hostname = parsed.hostname
        if not hostname:
            return False, "URL missing valid hostname."
            
        hostname_clean = hostname.strip().lower()
        
        # 1. Check explicit domain blacklist
        for blocked_domain in URL_DOMAIN_BLACKLIST:
            if hostname_clean == blocked_domain.lower() or hostname_clean.endswith(f".{blocked_domain.lower()}"):
                return False, f"Access to '{hostname_clean}' blocked by Warden Security Policy (Blacklisted Domain)."
                
        # 2. Check SSRF / Private IP resolution
        try:
            ip_obj = ipaddress.ip_address(hostname_clean)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_unspecified:
                return False, f"Access to private/local IP '{ip_obj}' blocked by Warden SSRF Guardrail."
        except ValueError:
            try:
                resolved_ip = socket.gethostbyname(hostname_clean)
                ip_obj = ipaddress.ip_address(resolved_ip)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_unspecified:
                    return False, f"Domain '{hostname_clean}' resolves to private/local IP '{resolved_ip}' (Blocked by Warden SSRF Guardrail)."
            except Exception:
                if hostname_clean in ("localhost", "127.0.0.1", "0.0.0.0") or hostname_clean.startswith("192.168.") or hostname_clean.startswith("10."):
                    return False, f"Access to '{hostname_clean}' blocked by Warden SSRF Guardrail."
                    
        return True, f"URL '{url}' authorized for web access."
    except Exception as e:
        return False, f"URL validation error: {str(e)}"

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


VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".ico"}

def validate_image_path(filepath: str) -> Tuple[bool, str]:
    if not filepath or not isinstance(filepath, str):
        return False, "Missing or invalid image file path."
        
    # Direct HTTP/HTTPS URLs authorized via validate_url
    if filepath.startswith(("http://", "https://")):
        return validate_url(filepath)
        
    try:
        p = Path(filepath).resolve()
        sandbox_res = SANDBOX_DIR.resolve()
        base_res = BASE_DIR.resolve()
        
        # Check if exists directly or inside SANDBOX_DIR
        if not p.exists():
            if (SANDBOX_DIR / Path(filepath).name).exists():
                p = (SANDBOX_DIR / Path(filepath).name).resolve()
            elif (SANDBOX_DIR / filepath).exists():
                p = (SANDBOX_DIR / filepath).resolve()
            else:
                return False, f"Image file does not exist at '{filepath}'"
            
        if p.suffix.lower() not in VALID_IMAGE_EXTENSIONS:
            return False, f"File '{p.name}' has invalid image extension '{p.suffix}'. Must be one of: {', '.join(sorted(VALID_IMAGE_EXTENSIONS))}"
            
        # Allowed in sandbox, uploads, or project Images directory
        if sandbox_res in p.parents or p == sandbox_res or base_res in p.parents:
            return True, f"Image path '{filepath}' authorized for visual analysis."
        else:
            return False, f"Path violation. Target image '{filepath}' is outside project boundaries."
    except Exception as e:
        return False, f"Invalid image path structure: {str(e)}"

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
        
    elif tool_name == "remember":
        key = params.get("key", "")
        clue = params.get("clue", params.get("value", ""))
        entry_type = params.get("type", "memory")
        if not key or not clue:
            return False, "Missing required 'key' or 'clue' parameter for remember tool.", params
        if "url" in str(entry_type).lower():
            ok_url, msg_url = validate_url(clue)
            if not ok_url:
                return False, msg_url, params
        return True, f"Memory ({entry_type}) '{key}' authorized.", params

    elif tool_name in ("list_internet_fav", "list_favorites"):
        return True, "Listing bookmarked internet favorites authorized by The Warden.", params

    elif tool_name in ("unremember", "forget"):
        key = params.get("key", "")
        if not key:
            return False, f"Missing required 'key' parameter for {tool_name} tool.", params
        return True, f"Memory clue {tool_name} '{key}' authorized.", params

    elif tool_name in ("identify_image", "inspect_image", "gorgons_gaze", "analyze_image"):
        filepath = params.get("filepath", params.get("image_path", params.get("path", params.get("url", ""))))
        ok, msg = validate_image_path(filepath)
        return ok, msg, params

    elif tool_name in ("write_to_scratchpad", "none", "finish", ""):
        return True, "Authorized action.", params
        
    return True, f"Action '{tool_name}' allowed.", params
