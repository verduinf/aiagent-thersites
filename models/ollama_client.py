"""
Ollama HTTP API Client with connection pooling and multi-model query dispatch.
"""
import time
import requests
from typing import Dict, Any, List, Tuple, Optional

from config import (
    OLLAMA_BASE_URL, MODEL_NAME, KEEP_AI_ALIVE, NUM_GPU, AI_TEMPERATURE, DEFAULT_THINK_MODE
)
from console_logger import log_main, log_performance, INDICATOR_DONE, INDICATOR_THINKING, INDICATOR_BLOCKED
from models.context import estimate_dynamic_context, resolve_thinking_parameters

_OLLAMA_SESSION = requests.Session()

def prewarm_ollama_model(model: str = MODEL_NAME, think_mode: bool = False) -> bool:
    """
    Pre-loads model into VRAM on startup using empty messages array.
    """
    native_url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [],
        "keep_alive": KEEP_AI_ALIVE,
        "think": think_mode,
        "options": {
            "num_ctx": 4096,
            "num_thread": 8
        },
        "stream": False
    }
    try:
        log_main(f"Pre-warming model '{model}' in VRAM (keep_alive: {KEEP_AI_ALIVE}, num_ctx: 4096)...", INDICATOR_THINKING)
        start_t = time.time()
        resp = _OLLAMA_SESSION.post(native_url, json=payload, timeout=60)
        elapsed = round(time.time() - start_t, 2)
        if resp.status_code == 200:
            log_main(f"Model '{model}' pre-warmed into VRAM in {elapsed}s!", INDICATOR_DONE)
            return True
    except Exception as e:
        log_main(f"Model pre-warm warning: {e}", INDICATOR_BLOCKED)
    return False

def query_ollama(messages: List[Dict[str, str]], model: str = MODEL_NAME, think_mode: Any = DEFAULT_THINK_MODE) -> Tuple[str, Dict[str, Any]]:
    """
    Executes a structured JSON query against the Ollama chat endpoint with dynamic context sizing.
    """
    base = OLLAMA_BASE_URL.rstrip('/')
    native_url = f"{base}/api/chat"
    headers = {"Content-Type": "application/json"}
    
    dynamic_num_ctx = estimate_dynamic_context(messages)
    think_val, reasoning_effort, predict_budget = resolve_thinking_parameters(model, think_mode)
    is_granite = "granite" in model.lower()
    
    payload = {
        "model": model,
        "messages": messages,
        "format": "json",
        "keep_alive": KEEP_AI_ALIVE,
        "think": think_val,
        "options": {
            "num_ctx": dynamic_num_ctx,
            "num_gpu": NUM_GPU,
            "num_predict": predict_budget,
            "num_thread": 8,
            "temperature": AI_TEMPERATURE
        },
        "stream": False
    }
    
    if is_granite:
        payload["options"]["reasoning_effort"] = reasoning_effort
        
    start_t = time.time()
    perf_metrics = {
        "tok_per_sec": 0.0,
        "latency_sec": 0.0,
        "eval_count": 0,
        "dynamic_num_ctx": dynamic_num_ctx
    }
    
    try:
        response = _OLLAMA_SESSION.post(native_url, headers=headers, json=payload, timeout=300)
        wall_time = time.time() - start_t
        if response.status_code == 200:
            data = response.json()
            raw_content = data["message"]["content"]
            
            eval_count = data.get("eval_count", len(raw_content) // 4)
            eval_duration_ns = data.get("eval_duration", 0)
            total_duration_ns = data.get("total_duration", 0)
            
            if eval_duration_ns > 0:
                tok_per_sec = (eval_count / eval_duration_ns) * 1e9
            else:
                tok_per_sec = eval_count / wall_time if wall_time > 0 else 0
                
            latency_sec = (total_duration_ns / 1e9) if total_duration_ns > 0 else wall_time
            
            perf_metrics = {
                "tok_per_sec": round(tok_per_sec, 1),
                "latency_sec": round(latency_sec, 2),
                "eval_count": eval_count,
                "dynamic_num_ctx": dynamic_num_ctx
            }
            log_performance(perf_metrics["tok_per_sec"], perf_metrics["latency_sec"], perf_metrics["eval_count"])
            return raw_content, perf_metrics
        else:
            raise RuntimeError(f"Ollama returned HTTP {response.status_code}: {response.text}")
    except Exception as e:
        log_main(f"Ollama connection error: {e}", INDICATOR_BLOCKED)
        raise RuntimeError(f"Ollama connection error: {str(e)}")
