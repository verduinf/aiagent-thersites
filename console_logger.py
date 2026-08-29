"""
Color-coded ANSI Console Telemetry Logger for AI Agent Thersites
Renders indented tree views, subagent actions, and stoplight indicators.
"""
import sys

# Ensure UTF-8 encoding for Windows console emojis
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ANSI Color Constants
COLOR_MAIN = "\033[92m"      # Light Green for Main Agent (Thersites)
COLOR_SUB = "\033[93m"       # Light Yellow for Subagents (Summarizer)
COLOR_BOUNCER = "\033[91m"   # Light Red for Bouncer Guardrail Intercepts
COLOR_INFO = "\033[96m"      # Light Cyan for System & Telemetry
COLOR_RESET = "\033[0m"

# Stoplights
INDICATOR_DONE = "🟢 [DONE]"
INDICATOR_THINKING = "🟡 [THINKING/RUNNING]"
INDICATOR_BLOCKED = "🔴 [BLOCKED/ERROR]"

def log_main(message: str, indicator: str = INDICATOR_THINKING):
    formatted = f"{COLOR_MAIN}🟢 [MAIN AGENT] {indicator} {message}{COLOR_RESET}"
    print(formatted, flush=True)

def log_subagent(subagent_name: str, message: str, indicator: str = INDICATOR_THINKING):
    formatted = f"{COLOR_SUB}🟡 │   ├── [SUBAGENT: {subagent_name}] {indicator} {message}{COLOR_RESET}"
    print(formatted, flush=True)

def log_bouncer(action_name: str, message: str, is_allowed: bool = True):
    status = "ALLOWED" if is_allowed else "BLOCKED"
    indicator = INDICATOR_DONE if is_allowed else INDICATOR_BLOCKED
    color = COLOR_INFO if is_allowed else COLOR_BOUNCER
    formatted = f"{color}🔴 [BOUNCER: {status}] {indicator} Action '{action_name}': {message}{COLOR_RESET}"
    print(formatted, flush=True)

def log_telemetry(turn: int, max_turns: int, char_count: int, max_chars: int):
    formatted = f"{COLOR_INFO}📊 [TELEMETRY] Turn {turn}/{max_turns} | Rolling Buffer: {char_count:,} / {max_chars:,} chars{COLOR_RESET}"
    print(formatted, flush=True)

if __name__ == "__main__":
    log_main("Starting Inner Loop for user prompt: 'Search Python docs'", INDICATOR_THINKING)
    log_telemetry(1, 5, 4200, 20000)
    log_bouncer("web_fetch", "URL 'https://docs.python.org' passed domain whitelist", is_allowed=True)
    log_subagent("HTML Summarizer", "Spawning secondary transient context...", INDICATOR_THINKING)
    log_subagent("HTML Summarizer", "Processed 48,000 chars HTML -> 420 chars summary", INDICATOR_DONE)
    log_main("Inner Loop Complete. Output pushed to messages table.", INDICATOR_DONE)
