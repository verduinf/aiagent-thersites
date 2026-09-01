"""
Push notifications and alert delivery (Pushover integration).
"""
import mimetypes
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import requests
from config import (
    PUSHOVER_USER_KEY, PUSHOVER_API_TOKEN, WEB_USER_AGENT, SANDBOX_DIR
)
from console_logger import log_subagent, INDICATOR_THINKING, INDICATOR_DONE, INDICATOR_BLOCKED

def dispatch_pushover_notification(message: str, title: str = "Thersites Agent", image_path: Optional[str] = None, priority: int = 0) -> Tuple[bool, str]:
    user_key = (PUSHOVER_USER_KEY or "").strip()
    api_token = (PUSHOVER_API_TOKEN or "").strip()
    
    if not user_key or not api_token:
        img_info = f" with image '{image_path}'" if image_path else ""
        sim_msg = f"[SIMULATION] PUSHOVER alert dispatched: \"{message}\"{img_info} (Configure PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN in config.json to enable live push delivery)."
        log_subagent("Pushover", sim_msg, INDICATOR_DONE)
        return True, sim_msg
        
    payload = {
        "token": api_token,
        "user": user_key,
        "title": title,
        "message": message,
        "priority": priority,
        "url": "http://localhost:8000",
        "url_title": "Open Thersites UI",
        "sound": "magic"
    }
    
    files = None
    if image_path:
        if isinstance(image_path, str) and image_path.startswith(("http://", "https://")):
            try:
                log_subagent("Pushover", f"Auto-fetching image URL '{image_path}' for attachment...", INDICATOR_THINKING)
                img_resp = requests.get(image_path, headers={"User-Agent": WEB_USER_AGENT}, timeout=15)
                if img_resp.status_code == 200:
                    local_img = SANDBOX_DIR / "photo.jpg"
                    with open(local_img, "wb") as f:
                        f.write(img_resp.content)
                    image_path = str(local_img)
            except Exception as dl_err:
                log_subagent("Pushover", f"Image URL download failed: {dl_err}", INDICATOR_BLOCKED)
                
        p = Path(image_path)
        if p.exists() and p.is_file():
            resolved_img = p
        elif (SANDBOX_DIR / p.name).exists() and (SANDBOX_DIR / p.name).is_file():
            resolved_img = SANDBOX_DIR / p.name
        elif (SANDBOX_DIR / image_path).exists() and (SANDBOX_DIR / image_path).is_file():
            resolved_img = SANDBOX_DIR / image_path
        else:
            resolved_img = None
            
        if resolved_img and resolved_img.exists() and resolved_img.is_file():
            mime_type = mimetypes.guess_type(resolved_img.name)[0] or "image/jpeg"
            files = {"attachment": (resolved_img.name, resolved_img.read_bytes(), mime_type)}
        else:
            log_subagent("Pushover", f"Image file '{image_path}' not found on disk. Sending text alert.", INDICATOR_THINKING)
            
    try:
        log_subagent("Pushover", f"Pushing alert '{title}' to The Boss's device...", INDICATOR_THINKING)
        resp = requests.post("https://api.pushover.net/1/messages.json", data=payload, files=files, timeout=15)
        if resp.status_code == 200:
            success_msg = "Successfully dispatched Pushover alert to The Boss's phone."
            log_subagent("Pushover", success_msg, INDICATOR_DONE)
            return True, success_msg
        else:
            fail_msg = f"Pushover HTTP {resp.status_code}: {resp.text}"
            log_subagent("Pushover", fail_msg, INDICATOR_BLOCKED)
            return False, fail_msg
    except Exception as e:
        err_msg = f"Failed to dispatch Pushover alert: {str(e)}"
        log_subagent("Pushover", err_msg, INDICATOR_BLOCKED)
        return False, err_msg

def handle_send_message(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    msg = params.get("message", params.get("text", "Task execution completed."))
    title = params.get("title", "Thersites Agent")
    img_path = params.get("image_path", params.get("image", None))
    priority = int(params.get("priority", 0))
    ok, dispatch_result = dispatch_pushover_notification(msg, title=title, image_path=img_path, priority=priority)
    status = "success" if ok else "error"
    return {"id": action_id, "tool": "send_message", "status": status, "result": dispatch_result}
