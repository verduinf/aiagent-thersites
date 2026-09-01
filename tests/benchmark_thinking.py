import sys
import time

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from core.engine import run_agent_inner_loop

PROMPT = "Update the brief.txt file in the sandbox with top tech news headlines from NU.nl. If brief.txt does not exist yet, check the sandbox directory first before creating it."

def run_benchmark(think_mode: bool):
    label = "THINKING_ON (think: True)" if think_mode else "THINKING_OFF (think: False)"
    session_id = f"benchmark_think_{'on' if think_mode else 'off'}"
    
    print(f"\n============================================================")
    print(f"  STARTING BENCHMARK: {label}")
    print(f"============================================================")
    
    start_total_t = time.time()
    total_eval_tokens = 0
    turns_executed = 0
    actions_taken = []
    thoughts = []
    
    gen = run_agent_inner_loop(session_id, PROMPT, think_mode=think_mode)
    
    for event in gen:
        event_type = event.get("type")
        if event_type == "telemetry":
            turns_executed = event.get("turn")
        elif event_type == "scratch_step":
            turn = event.get("turn")
            thought = event.get("thought", "")
            thoughts.append(f"Turn {turn}: {thought}")
            actions = event.get("actions", [])
            if actions:
                actions_taken.append((turn, actions))
                print(f"  [Turn {turn}] Action: {actions}")
            else:
                print(f"  [Turn {turn}] No actions requested (Complete)")
        elif event_type == "performance":
            eval_cnt = event.get("eval_count", 0)
            latency = event.get("latency_sec", 0.0)
            total_eval_tokens += eval_cnt
            print(f"  [Turn Performance] Latency: {latency}s | Eval Tokens: {eval_cnt} | tok/s: {event.get('tok_per_sec')}")
        elif event_type == "final_response":
            print(f"  [Final Response Content Snippet]: {str(event.get('content', ''))[:120]}...")
            
    total_time = round(time.time() - start_total_t, 2)
    
    return {
        "label": label,
        "think_mode": think_mode,
        "total_time_sec": total_time,
        "total_eval_tokens": total_eval_tokens,
        "turns_executed": turns_executed,
        "actions_taken": actions_taken,
        "thoughts": thoughts
    }

if __name__ == "__main__":
    print("Running Side-by-Side Reasoning & Performance Benchmark...")
    
    res_off = run_benchmark(think_mode=False)
    res_on = run_benchmark(think_mode=True)
    
    print("\n============================================================")
    print("  SIDE-BY-SIDE BENCHMARK SUMMARY")
    print("============================================================")
    print(f"Condition A: {res_off['label']}")
    print(f"  - Total Latency: {res_off['total_time_sec']}s")
    print(f"  - Total Generated Tokens: {res_off['total_eval_tokens']}")
    print(f"  - Turns Executed: {res_off['turns_executed']}")
    print(f"  - Actions Sequence: {[a[1] for a in res_off['actions_taken']]}")
    
    print(f"\nCondition B: {res_on['label']}")
    print(f"  - Total Latency: {res_on['total_time_sec']}s")
    print(f"  - Total Generated Tokens: {res_on['total_eval_tokens']}")
    print(f"  - Turns Executed: {res_on['turns_executed']}")
    print(f"  - Actions Sequence: {[a[1] for a in res_on['actions_taken']]}")
    
    speedup = round(res_on['total_time_sec'] / max(res_off['total_time_sec'], 0.1), 1)
    token_ratio = round(res_on['total_eval_tokens'] / max(res_off['total_eval_tokens'], 1), 1)
    print(f"\nLatency Difference: THINKING_ON is {speedup}x slower than THINKING_OFF")
    print(f"Token Overhead: THINKING_ON generated {token_ratio}x more tokens")
