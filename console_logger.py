"""
ANSI Color Telemetry & Console Logger for AI Agent Thersites
Provides visual terminal feedback with distinct colors for Main Agent, Subagents, Warden, and Telemetry.
"""
import sys

# Ensure Windows CMD handles UTF-8 output properly
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

COLOR_RESET = "\033[0m"
COLOR_MAIN = "\033[92m"      # Light Green
COLOR_SUBAGENT = "\033[93m"  # Light Yellow
COLOR_WARDEN = "\033[91m"    # Light Red / Magenta
COLOR_TELEMETRY = "\033[96m" # Light Cyan
COLOR_PERF = "\033[95m"      # Light Magenta / Violet

INDICATOR_DONE = "🟢 [DONE]"
INDICATOR_THINKING = "🟡 [THINKING/RUNNING]"
INDICATOR_BLOCKED = "🔴 [BLOCKED/ERROR]"

def log_main(msg: str, indicator: str = INDICATOR_THINKING):
    print(f"{COLOR_MAIN}🟢 [MAIN AGENT] {indicator} {msg}{COLOR_RESET}")

def log_subagent(name: str, msg: str, indicator: str = INDICATOR_THINKING):
    print(f"{COLOR_SUBAGENT}│   ├── [SUBAGENT: {name}] {indicator} {msg}{COLOR_RESET}")

def log_warden(action: str, allowed: bool, details: str):
    status = "ALLOWED" if allowed else "BLOCKED"
    indicator = INDICATOR_DONE if allowed else INDICATOR_BLOCKED
    print(f"{COLOR_WARDEN}🔴 [WARDEN: {status}] {indicator} Action '{action}': {details}{COLOR_RESET}")

def log_telemetry(turn: int, max_turns: int, rolling_chars: int, max_chars: int):
    print(f"{COLOR_TELEMETRY}📊 [TELEMETRY] Turn {turn}/{max_turns} | Rolling Buffer: {rolling_chars:,} / {max_chars:,} chars{COLOR_RESET}")

def log_performance(tok_per_sec: float, latency_sec: float, eval_count: int):
    print(f"{COLOR_PERF}⚡ [PERFORMANCE] {tok_per_sec:.1f} tok/s | Total Latency: {latency_sec:.2f}s | Output Tokens: {eval_count}{COLOR_RESET}")
