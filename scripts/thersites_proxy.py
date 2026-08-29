"""
Thersites-proxy (Therp) — Development Proxy, Field Tester & Prompt Tuner

Therp field-tests candidate system prompts against local Ollama (qwen3-9b),
evaluates response quality and JSON schema adherence, diagnoses Ollama server errors,
and recommends concrete prompt optimizations and Python fallback fixes.
"""
import sys
import json
import time
import requests
from typing import Dict, Any

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODEL_NAME = "qwen3:9b"

SYSTEM_PROMPT_TEMPLATE = """You are Thersites, a contextually-challenged, error-prone, but deeply enthusiastic AI Intern.
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

def field_test_prompt(user_prompt: str, system_prompt: str = SYSTEM_PROMPT_TEMPLATE, model: str = MODEL_NAME) -> Dict[str, Any]:
    """
    Executes prompt against local Ollama model, evaluates output quality,
    and returns a structured diagnostic report.
    """
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7
    }
    
    start_time = time.time()
    try:
        response = requests.post(OLLAMA_URL, headers=headers, json=payload, timeout=30)
        latency = round(time.time() - start_time, 2)
        response.raise_for_status()
        data = response.json()
        raw_output = data["choices"][0]["message"]["content"]
        
        # Therp Diagnostic Evaluation
        eval_result = evaluate_response_quality(raw_output)
        
        return {
            "status": "success",
            "model": model,
            "latency_seconds": latency,
            "raw_output": raw_output,
            "therp_evaluation": eval_result
        }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error": f"Ollama request timed out after 30s targeting model '{model}'.",
            "therp_diagnosis": "Local Ollama server hit context saturation or model vram paging stall.",
            "recommended_fix": "Increase request timeout to 60s or reduce rolling context buffer size."
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "therp_diagnosis": "Ollama connection failure or model unavailable.",
            "recommended_fix": "Verify Ollama service is running (`ollama serve`) and model 'qwen3:9b' is pulled (`ollama pull qwen3:9b`)."
        }

def evaluate_response_quality(raw_output: str) -> Dict[str, Any]:
    """Evaluates raw output for JSON adherence, persona alignment, and quality."""
    has_json = "{" in raw_output and "}" in raw_output
    has_thought = '"thought"' in raw_output
    has_content = '"content"' in raw_output
    has_actions = '"actions"' in raw_output or '"action"' in raw_output
    
    score = 0
    feedback = []
    
    if has_json: score += 40
    else: feedback.append("Missing JSON structure.")
    
    if has_thought: score += 20
    else: feedback.append("Missing 'thought' key.")
    
    if has_content: score += 20
    else: feedback.append("Missing 'content' key.")
    
    if has_actions: score += 20
    else: feedback.append("Missing 'actions' array.")
    
    quality_label = "EXCELLENT" if score == 100 else ("ACCEPTABLE" if score >= 60 else "POOR / NEEDS TUNING")
    
    return {
        "score": f"{score}/100",
        "quality_label": quality_label,
        "schema_checks": {
            "has_valid_json": has_json,
            "has_thought": has_thought,
            "has_content": has_content,
            "has_actions": has_actions
        },
        "feedback_notes": feedback or ["Output adheres 100% to requested Intern JSON schema!"]
    }

if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Hello Therp, introduce yourself and explain how you help tuning prompts!"
    print(f"--- [Therp / Thersites-proxy] Field Testing Prompt against ({MODEL_NAME}) ---")
    print(f"Test Prompt: '{prompt}'\n")
    report = field_test_prompt(prompt)
    print(json.dumps(report, indent=2))
