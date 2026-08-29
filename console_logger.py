"""
Colorized ANSI Terminal Logger for AI Agent Thersites
Provides visual indicators for main loop operations, subagents, telemetry, and performance.
"""
import sys
from config import VERBOSE

INDICATOR_DONE = "🟢 [DONE]"
INDICATOR_THINKING = "🟡 [THINKING/RUNNING]"
INDICATOR_BLOCKED = "🔴 [BLOCKED/ERROR]"

def log_main(message: str, indicator: str = INDICATOR_DONE):
    color = "\033[92m" if "DONE" in indicator else ("\033[93m" if "THINKING" in indicator else "\033[91m")
    reset = "\033[0m"
    print(f"{color}🟢 [MAIN AGENT] {indicator} {message}{reset}")
    sys.stdout.flush()

def log_subagent(agent_name: str, message: str, indicator: str = INDICATOR_DONE):
    color = "\033[92m" if "DONE" in indicator else ("\033[93m" if "THINKING" in indicator else "\033[91m")
    reset = "\033[0m"
    print(f"\033[94m│   ├── [SUBAGENT: {agent_name}] {color}{indicator} {message}{reset}")
    sys.stdout.flush()

def log_telemetry(turn: int, max_turns: int, rolling_chars: int, max_chars: int):
    reset = "\033[0m"
    cyan = "\033[96m"
    print(f"{cyan}📊 [TELEMETRY] Turn {turn}/{max_turns} | Rolling Buffer: {rolling_chars:,} / {max_chars:,} chars{reset}")
    sys.stdout.flush()

def log_performance(tok_per_sec: float, latency_sec: float, eval_count: int):
    magenta = "\033[95m"
    reset = "\033[0m"
    print(f"{magenta}⚡ [PERFORMANCE] {tok_per_sec} tok/s | Total Latency: {latency_sec}s | Output Tokens: {eval_count}{reset}")
    sys.stdout.flush()

def log_verbose(title: str, text: str):
    """Prints raw verbose output in subtle dimmed cyan ANSI text when VERBOSE flag is enabled."""
    if VERBOSE:
        clean = text.replace("\n", " ").strip()
        if len(clean) > 250:
            clean = clean[:247] + "..."
        print(f"\033[96m│   ├── [VERBOSE {title}]: \"{clean}\"\033[0m")
        sys.stdout.flush()
