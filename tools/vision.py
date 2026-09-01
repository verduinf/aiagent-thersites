"""
Visual inspection and image download tools.
"""
from pathlib import Path
import urllib.parse
import requests
from typing import Dict, Any, Optional
from config import SANDBOX_DIR, WEB_USER_AGENT, VISION_MODEL_NAME
from console_logger import log_subagent, INDICATOR_THINKING, INDICATOR_DONE
from models.vision_client import query_ollama_vision

def handle_identify_image(params: Dict[str, Any], action_id: str = "act_1", active_model: Optional[str] = None) -> Dict[str, Any]:
    filepath = params.get("filepath", params.get("image_path", params.get("path", params.get("url", ""))))
    prompt = params.get("prompt", "Describe this image in clear detail.")
    
    # If direct HTTP/HTTPS URL passed, auto-fetch to sandbox first
    if isinstance(filepath, str) and filepath.startswith(("http://", "https://")):
        url = filepath
        url_path = urllib.parse.urlparse(url).path
        fname = Path(url_path).name or "downloaded_image.jpg"
        if not any(fname.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
            fname = f"{fname}.jpg"
        local_path = SANDBOX_DIR / fname
        log_subagent("Image Downloader", f"Auto-fetching image URL '{url}' to '{local_path.name}'...", INDICATOR_THINKING)
        resp = requests.get(url, headers={"User-Agent": WEB_USER_AGENT}, timeout=15)
        if resp.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(resp.content)
            filepath = str(local_path)
            log_subagent("Image Downloader", f"Saved {round(len(resp.content)/1024, 1)} KB to '{local_path.name}'", INDICATOR_DONE)
        else:
            return {
                "id": action_id,
                "tool": "identify_image",
                "status": "error",
                "result": f"Failed to download image from '{url}': HTTP {resp.status_code}"
            }
            
    effective_vis_model = active_model or VISION_MODEL_NAME
    log_subagent("Vision Inspection", f"Inspecting visual asset '{Path(filepath).name}' with {effective_vis_model}...", INDICATOR_THINKING)
    description, v_perf = query_ollama_vision(filepath, prompt, model=effective_vis_model)
    return {
        "id": action_id,
        "tool": "identify_image",
        "status": "success",
        "result": f"Visual Inspection Analysis for '{Path(filepath).name}':\n{description}",
        "perf": v_perf
    }

def handle_download_image(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    url = params["url"]
    filepath = params["filepath"]
    log_subagent("Image Downloader", f"Fetching image '{url}'...", INDICATOR_THINKING)
    resp = requests.get(url, headers={"User-Agent": WEB_USER_AGENT}, timeout=15)
    if resp.status_code == 200:
        with open(filepath, "wb") as f:
            f.write(resp.content)
        size_kb = round(len(resp.content) / 1024, 1)
        log_subagent("Image Downloader", f"Saved {size_kb} KB to '{Path(filepath).name}'", INDICATOR_DONE)
        return {"id": action_id, "tool": "download_image", "status": "success", "result": f"Successfully downloaded image ({size_kb} KB) to '{filepath}'"}
    else:
        return {"id": action_id, "tool": "download_image", "status": "error", "result": f"HTTP {resp.status_code} while downloading image"}
