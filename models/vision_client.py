"""
Vision inspection and image processing client for Ollama vision models.
"""
import io
import time
import base64
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import requests

from config import (
    OLLAMA_BASE_URL, VISION_MODEL_NAME, VISION_NUM_CTX, NUM_GPU, KEEP_AI_ALIVE, SANDBOX_DIR
)
from console_logger import log_subagent, INDICATOR_DONE

_VISION_SESSION = requests.Session()

def encode_image_to_base64(filepath: str) -> str:
    """
    Encodes an image to base64 with Lanczos scaling for large images to conserve VRAM,
    handling alpha transparency for .ico/PNG and RGB for JPEG/WEBP/BMP/TIFF.
    """
    try:
        from PIL import Image
        p = Path(filepath)
        suffix = p.suffix.lower()
        with Image.open(filepath) as img:
            if suffix == ".ico":
                buf = io.BytesIO()
                img.convert("RGBA").save(buf, format="PNG")
                return base64.b64encode(buf.getvalue()).decode("utf-8")
            
            img_rgb = img.convert("RGB")
            if max(img_rgb.size) > 1024:
                img_rgb.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            
            buf = io.BytesIO()
            img_rgb.save(buf, format="JPEG", quality=90)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

def query_ollama_vision(image_path: str, prompt: str = "Describe what is shown in this image.", model: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Queries Ollama vision model with image base64 and logs swap/inference telemetry.
    """
    effective_model = model or VISION_MODEL_NAME
    t0 = time.time()
    p = Path(image_path).resolve()
    if not p.exists():
        if (SANDBOX_DIR / Path(image_path).name).exists():
            p = (SANDBOX_DIR / Path(image_path).name).resolve()
        elif (SANDBOX_DIR / image_path).exists():
            p = (SANDBOX_DIR / image_path).resolve()
        else:
            raise FileNotFoundError(f"Image not found at '{image_path}'")
        
    img_b64 = encode_image_to_base64(str(p))
    
    payload = {
        "model": effective_model,
        "messages": [
            {
                "role": "user",
                "content": prompt or "Describe what you see in this image in clear detail.",
                "images": [img_b64]
            }
        ],
        "stream": False,
        "think": False,
        "options": {
            "num_ctx": VISION_NUM_CTX,
            "num_gpu": NUM_GPU,
            "num_predict": 384,
            "temperature": 0.2
        },
        "keep_alive": KEEP_AI_ALIVE
    }
    
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    resp = _VISION_SESSION.post(url, json=payload, timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama Vision API error ({resp.status_code}): {resp.text}")
        
    data = resp.json()
    content = data.get("message", {}).get("content", "").strip()
    
    total_duration_sec = data.get("total_duration", 0) / 1e9
    load_duration_sec = data.get("load_duration", 0) / 1e9
    eval_count = data.get("eval_count", 0)
    eval_duration_sec = data.get("eval_duration", 0) / 1e9
    tok_per_sec = (eval_count / eval_duration_sec) if eval_duration_sec > 0 else 0.0
    
    perf = {
        "total_latency": round(total_duration_sec or (time.time() - t0), 2),
        "load_latency": round(load_duration_sec, 2),
        "eval_count": eval_count,
        "tok_per_sec": round(tok_per_sec, 1)
    }
    
    log_subagent("Vision Inspection", f"Model '{effective_model}' load/swap: {perf['load_latency']}s | Inference: {perf['total_latency'] - perf['load_latency']:.2f}s ({perf['tok_per_sec']} tok/s)", INDICATOR_DONE)
    return content, perf
