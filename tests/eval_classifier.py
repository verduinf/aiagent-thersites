import sys
import json
import re
import time
import hashlib

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from models.ollama_client import query_ollama

# Labeled Test Set (Ground Truth)
LABELED_TEST_SET = [
    {"id": 1, "prompt": "Fetch today's news from NU.nl and save to sandbox/news.txt", "ground_truth": False, "category": "Routine Fetch & Save"},
    {"id": 2, "prompt": "Check if brief.txt exists in the sandbox.", "ground_truth": False, "category": "Routine Status Check"},
    {"id": 3, "prompt": "Pick exactly 5 headlines from NU.nl, 1 per category, published in the last 3 hours, no duplicates.", "ground_truth": True, "category": "Strict Counting + Set Filtering"},
    {"id": 4, "prompt": "Write a summary of tech news under 100 words while preserving 3 article URLs.", "ground_truth": True, "category": "Competing Word-Count & Link Constraints"},
    {"id": 5, "prompt": "List all files in the sandbox directory.", "ground_truth": False, "category": "Routine Directory Listing"},
    {"id": 6, "prompt": "Reconcile the contents of file A and file B, finding contradictory facts across both.", "ground_truth": True, "category": "Semantic Cross-File Contradiction Detection"},
    {"id": 7, "prompt": "Delete think_test.txt from the sandbox.", "ground_truth": False, "category": "Routine File Deletion"},
    {"id": 8, "prompt": "Summarize the main points of news.txt in 3 bullet points.", "ground_truth": False, "category": "Routine Basic Summarization"},
    {"id": 9, "prompt": "Verify first that sandbox is writable, then write 'OK'.", "ground_truth": False, "category": "False-Positive Keyword Trap"},
    {"id": 10, "prompt": "Calculate the average word count of all text files in the sandbox.", "ground_truth": True, "category": "Arithmetic & Multi-File Aggregation"}
]

# Track A: Bare Zero-Shot Prompt
PROMPT_TRACK_A_ZERO_SHOT = """You are the Task Complexity Classifier for an AI Agent.
Your job is to evaluate a user prompt and decide if it requires DEEP REASONING (think: True) or ROUTINE EXECUTION (think: False).

Output RAW JSON matching this structure:
{
  "deep_reasoning": boolean,
  "reason": "<1-sentence explanation>"
}
"""

# Track B: Explicit Criteria & Few-Shot Prompt
PROMPT_TRACK_B_FEW_SHOT = """You are the Task Complexity Classifier for an AI Agent.
Evaluate the user prompt and decide if it requires DEEP REASONING (deep_reasoning: true) or ROUTINE EXECUTION (deep_reasoning: false).

Deep Reasoning (deep_reasoning: true) is required ONLY for:
1. Strict precise counting constraints (e.g. 'exactly N items', 'no duplicates').
2. Competing tradeoffs (e.g. strict word-count limits combined with mandatory content inclusions).
3. Complex math, temporal calculations, or cross-file contradiction analysis.

Routine Execution (deep_reasoning: false) is required for:
1. Standard web fetches, file reading, file writing, directory listing, or file deletion.
2. Routine multi-step sequencing (e.g. 'check if X exists, if not write Y').
3. Simple verification tasks (e.g. 'verify sandbox is writable').

Output RAW JSON matching this structure:
{
  "deep_reasoning": boolean,
  "reason": "<1-sentence explanation>"
}
"""

def compute_experiment_fingerprint(system_prompt: str, model_params: dict, tool_schema: dict):
    clean = system_prompt.strip()
    bundle = {
        "system_prompt": clean,
        "model_params": model_params,
        "tool_schema": tool_schema
    }
    canonical = json.dumps(bundle, sort_keys=True)
    exp_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"exp_sha256:{exp_hash}", len(clean)

def parse_classifier_json(raw_text: str):
    clean = raw_text.strip()
    if "```" in clean:
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if m:
        clean = m.group(0)
    data = json.loads(clean)
    return bool(data.get("deep_reasoning", False)), str(data.get("reason", "No reason provided"))

def run_eval_track(track_name: str, system_prompt: str, think_mode: bool = False):
    model_params = {"model": "qwen3.5:9b", "temperature": 0.0, "think": think_mode}
    tool_schema = {"classifier_schema": "v1.0"}
    p_hash, p_len = compute_experiment_fingerprint(system_prompt, model_params, tool_schema)
    print(f"\n============================================================")
    print(f"  RUNNING EVAL TRACK: {track_name}")
    print(f"  EXPERIMENT CONFIG FINGERPRINT: {p_hash} ({p_len} chars) | think: {think_mode}")
    print(f"============================================================")
    
    correct_count = 0
    false_positives = 0
    false_negatives = 0
    total_latency = 0.0
    results = []
    
    for item in LABELED_TEST_SET:
        p_id = item["id"]
        prompt = item["prompt"]
        expected = item["ground_truth"]
        category = item["category"]
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User Prompt: \"{prompt}\"\nDetermine if this prompt requires deep_reasoning."}
        ]
        
        start_t = time.time()
        raw_resp, perf = query_ollama(messages, think_mode=think_mode)
        latency = round(time.time() - start_t, 2)
        total_latency += latency
        
        try:
            pred, reason = parse_classifier_json(raw_resp)
        except Exception as e:
            pred = False
            reason = f"Parse Error: {e}"
            
        is_correct = (pred == expected)
        if is_correct:
            correct_count += 1
            status_icon = "?? PASS"
        else:
            status_icon = "?? FAIL"
            if pred and not expected:
                false_positives += 1
            elif not pred and expected:
                false_negatives += 1
                
        print(f"Test #{p_id:02d} [{status_icon}] ({latency}s) - {category}")
        print(f"  Prompt: \"{prompt}\"")
        print(f"  Expected: {expected} | Predicted: {pred}")
        print(f"  Reason: {reason}\n")
        
        results.append({
            "id": p_id,
            "category": category,
            "expected": expected,
            "predicted": pred,
            "reason": reason,
            "latency": latency
        })
        
    total = len(LABELED_TEST_SET)
    accuracy = round((correct_count / total) * 100, 1)
    avg_latency = round(total_latency / total, 2)
    
    return {
        "track_name": track_name,
        "exp_fingerprint": p_hash,
        "prompt_len": p_len,
        "think_mode": think_mode,
        "accuracy": accuracy,
        "correct_count": correct_count,
        "total": total,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "avg_latency": avg_latency,
        "results": results
    }

if __name__ == "__main__":
    print("=== AUTOMATED RIGOR EVALUATION: TRACK A vs TRACK B ===")
    
    track_a = run_eval_track("TRACK_A_ZERO_SHOT", PROMPT_TRACK_A_ZERO_SHOT, think_mode=False)
    track_b = run_eval_track("TRACK_B_FEW_SHOT", PROMPT_TRACK_B_FEW_SHOT, think_mode=False)
    
    print("\n==================================================================================")
    print("  SIDE-BY-SIDE CONFIG INVARIANCE AUDIT")
    print("==================================================================================")
    
    if track_a['exp_fingerprint'] == track_b['exp_fingerprint']:
        print("  [CONFIG INVARIANCE: IDENTICAL EXPERIMENTAL CONDITIONS]")
    else:
        print("  ??  WARNING: CONFIG BUNDLE MISMATCH DETECTED BETWEEN TRACKS!")
        print(f"  Track A Bundle: {track_a['exp_fingerprint']} ({track_a['prompt_len']} prompt chars)")
        print(f"  Track B Bundle: {track_b['exp_fingerprint']} ({track_b['prompt_len']} prompt chars)")
        print("  NOTICE: Results reflect multi-variable environmental changes, NOT an isolated baseline comparison.")
        print("----------------------------------------------------------------------------------")
        
    print(f"\n| {'Track':<18} | {'Fingerprint':<20} | {'Accuracy':<10} | {'FP':<5} | {'FN':<5} | {'Avg Latency':<12} |")
    print(f"|{'-'*20}|{'-'*22}|{'-'*12}|{'-'*7}|{'-'*7}|{'-'*14}|")
    print(f"| {track_a['track_name']:<18} | {track_a['exp_fingerprint']:<20} | {str(track_a['accuracy']) + '%':<10} | {track_a['false_positives']:<5} | {track_a['false_negatives']:<5} | {str(track_a['avg_latency']) + 's':<12} |")
    print(f"| {track_b['track_name']:<18} | {track_b['exp_fingerprint']:<20} | {str(track_b['accuracy']) + '%':<10} | {track_b['false_positives']:<5} | {track_b['false_negatives']:<5} | {str(track_b['avg_latency']) + 's':<12} |")
