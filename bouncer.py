"""
The Bouncer — Programmatic Guardrail Enforcement Engine
Intercepts all tool calls and enforces absolute rules before hitting network or disk.
"""
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any, Tuple
from config import SANDBOX_DIR, SCRATCHPAD_PATH, URL_DOMAIN_WHITELIST
from console_logger import log_bouncer

class BouncerViolation(Exception):
    pass

def validate_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise BouncerViolation(f"[ERROR: Invalid URL structure: '{url}']")
        
    is_whitelisted = any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in URL_DOMAIN_WHITELIST
    )
    
    if not is_whitelisted:
        raise BouncerViolation(
            f"[ERROR: Unauthorized domain '{hostname}'. URL must be in whitelist: {URL_DOMAIN_WHITELIST}]"
        )
    return url

def validate_write_path(target_path_str: str) -> Path:
    target_path = Path(target_path_str).resolve()
    sandbox_resolved = SANDBOX_DIR.resolve()
    
    try:
        target_path.relative_to(sandbox_resolved)
    except ValueError:
        raise BouncerViolation(
            f"[ERROR: Path sandbox violation. Target path '{target_path_str}' resolves outside '{sandbox_resolved}']"
        )
    return target_path

def validate_scratchpad_path(target_path_str: str) -> Path:
    resolved = Path(target_path_str).resolve()
    expected = SCRATCHPAD_PATH.resolve()
    if resolved != expected:
        # Override target to exact scratchpad path
        log_bouncer("write_to_scratchpad", f"Overriding path '{target_path_str}' -> '{expected.name}'", is_allowed=True)
    return expected

def inspect_and_authorize(tool_name: str, params: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Intercepts tool calls and runs absolute programmatic rules.
    Returns (is_authorized, message, sanitized_params).
    """
    try:
        sanitized = dict(params)
        
        if tool_name == "web_fetch":
            url = params.get("url", "")
            validate_url(url)
            log_bouncer("web_fetch", f"Domain '{urlparse(url).hostname}' authorized by Bouncer.", is_allowed=True)
            return True, "URL authorized", sanitized
            
        elif tool_name == "write_to_file":
            filepath = params.get("filepath", "")
            validated_path = validate_write_path(filepath)
            sanitized["filepath"] = str(validated_path)
            log_bouncer("write_to_file", f"Path '{validated_path.name}' within sandbox enclosure.", is_allowed=True)
            return True, "Path authorized", sanitized
            
        elif tool_name == "write_to_scratchpad":
            filepath = params.get("filepath", "scratchpad.md")
            validated_path = validate_scratchpad_path(filepath)
            sanitized["filepath"] = str(validated_path)
            log_bouncer("write_to_scratchpad", f"Scratchpad path target enforced to '{validated_path.name}'", is_allowed=True)
            return True, "Scratchpad authorized", sanitized
            
        elif tool_name in ("sqlite_query_executor", "summarize_tool", "finish", "none"):
            log_bouncer(tool_name, "Safe utility action authorized.", is_allowed=True)
            return True, "Action authorized", sanitized
            
        else:
            raise BouncerViolation(f"[ERROR: Unknown or unauthorized tool '{tool_name}']")
            
    except BouncerViolation as e:
        msg = str(e)
        log_bouncer(tool_name, msg, is_allowed=False)
        return False, msg, params

if __name__ == "__main__":
    print("Testing Bouncer Guardrails...")
    ok, msg, p = inspect_and_authorize("web_fetch", {"url": "https://python.org/downloads"})
    print("Test 1 (Whitelisted URL):", ok, msg)
    
    ok, msg, p = inspect_and_authorize("web_fetch", {"url": "https://malicious-site.com/hacked"})
    print("Test 2 (Unauthorized URL):", ok, msg)
    
    ok, msg, p = inspect_and_authorize("write_to_file", {"filepath": str(SANDBOX_DIR / "test.txt")})
    print("Test 3 (Sandbox File):", ok, msg)
    
    ok, msg, p = inspect_and_authorize("write_to_file", {"filepath": "C:/Windows/System32/hacked.dll"})
    print("Test 4 (Sandbox Violation):", ok, msg)
