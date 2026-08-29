"""
Therp 🦜 Benchmark & Performance Tuning Script
Pesters local Ollama (qwen3.5:9b) with diagnostic prompts across context sizes,
evaluates tokens/sec speed, latency, and JSON schema accuracy (100-point rubric).
"""
import sys
import json
import time
import requests
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen3.5:9b"

SYSTEM_CONTRACT = """You are Thersites, a contextually-challenged, error-prone, but deeply enthusiastic AI Intern.
You work under "The Boss" and must ALWAYS respond with a structured JSON object.

JSON Schema Required:
{
  "thought": "<internal junior dev reasoning>",
  "content": "<what you say to The Boss>",
  "actions": [
    {
      "id": "act_1",
      "tool": "<tool_name_or_none>",
      "params": {}
    }
  ]
}
"""

TEST_PROMPTS = [
    "Hello Thersites! Introduce yourself and list your available tools.",
    "Fetch news from nu.nl and write a short summary to sandbox/summary.txt.",
    "Query the thersites_scratchpad table and check if there are any notes saved."
]

def run_benchmark_pass(prompt: str, num_ctx: int = 8192, keep_alive: str = "5m") -> dict:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_CONTRACT},
            {"role": "user", "content": prompt}
        ],
        "keep_alive": keep_alive,
        "options": {
            "num_ctx": num_ctx,
            "temperature": 0.7
        },
        "stream": False
    }
    
    start_t = time.time()
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        wall_time = time.time() - start_t
        if resp.status_code == 200:
            data = resp.json()
            raw_text = data["message"]["content"]
            
            eval_count = data.get("eval_count", len(raw_text) // 4)
            eval_duration_ns = data.get("eval_duration", 0)
            total_duration_ns = data.get("total_duration", 0)
            
            tok_per_sec = (eval_count / eval_duration_ns) * 1e9 if eval_duration_ns > 0 else (eval_count / wall_time)
            latency_sec = (total_duration_ns / 1e9) if total_duration_ns > 0 else wall_time
            
            # Evaluate JSON Schema
            has_json = "{" in raw_text and "}" in raw_text
            has_thought = '"thought"' in raw_text
            has_content = '"content"' in raw_text
            has_actions = '"actions"' in raw_text
            
            score = 0
            if has_json: score += 40
            if has_thought: score += 20
            if has_content: score += 20
            if has_actions: score += 20
            
            return {
                "status": "success",
                "num_ctx": num_ctx,
                "latency_sec": round(latency_sec, 2),
                "tok_per_sec": round(tok_per_sec, 1),
                "eval_count": eval_count,
                "schema_score": f"{score}/100",
                "raw_preview": raw_text[:120].replace("\n", " ") + "..."
            }
        else:
            return {"status": "error", "error": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def run_full_suite():
    print(f"[Therp Benchmark] Testing Local Model '{MODEL_NAME}'")
    results = []
    
    for ctx in [8192]:
        print(f"\n--- Testing num_ctx: {ctx} ---")
        for i, prompt in enumerate(TEST_PROMPTS, 1):
            print(f"Test #{i}: '{prompt[:40]}...' ", end="", flush=True)
            res = run_benchmark_pass(prompt, num_ctx=ctx)
            if res["status"] == "success":
                print(f"-> 🟢 {res['tok_per_sec']} tok/s | Latency: {res['latency_sec']}s | Score: {res['schema_score']}")
            else:
                print(f"-> 🔴 Error: {res.get('error')}")
            results.append(res)
            
    print("\n[Therp Benchmark Complete] Summary Report")
    avg_speed = sum(r.get("tok_per_sec", 0) for r in results if r["status"] == "success") / max(1, len(results))
    print(f"Average Inference Generation Speed: {avg_speed:.1f} tok/s")

if __name__ == "__main__":
    run_full_suite()
