"""
Thersites-proxy (Therp) — Development Proxy & Field Test Harness

Allows Helios, Athena, Argus, and the Boss to send test prompts directly to
the local Ollama instance (qwen3-9b) to field-test prompts, JSON action schemas,
and Bouncer rules in real-time during development.
"""
import sys
import json
import requests

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODEL_NAME = "qwen3:9b"  # Fallback to available local qwen model

SYSTEM_PROMPT = """You are Thersites, a contextually-challenged, error-prone, but deeply enthusiastic AI Intern.
You must ALWAYS respond with a structured JSON action array using the following schema:

{
  "thought": "<internal reasoning>",
  "content": "<message to the Boss>",
  "actions": [
    {
      "id": "act_1",
      "tool": "<tool_name_or_none>",
      "params": {}
    }
  ]
}
"""

def query_therp(user_prompt: str, model: str = MODEL_NAME) -> dict:
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(OLLAMA_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        raw_text = data["choices"][0]["message"]["content"]
        return {"status": "success", "raw_output": raw_text}
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Hello Therp, introduce yourself to the Boss!"
    print(f"--- [Therp / Thersites-proxy] Querying Ollama ({MODEL_NAME}) ---")
    print(f"Prompt: {prompt}\n")
    res = query_therp(prompt)
    print(json.dumps(res, indent=2))
