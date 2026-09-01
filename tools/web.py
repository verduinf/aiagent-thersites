"""
Web fetching and structured HTML/RSS extraction tool.
"""
import urllib.parse
import requests
from typing import Dict, Any
from config import WEB_USER_AGENT, WEB_FETCH_CHAR_LIMIT
from console_logger import log_subagent, INDICATOR_THINKING, INDICATOR_DONE
from core.parsers import clean_html_to_text

def handle_web_fetch(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    url = params["url"]
    parsed_path = urllib.parse.urlparse(url).path.lower()
    if any(parsed_path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
        return {
            "id": action_id,
            "tool": "web_fetch",
            "status": "success",
            "result": f"[DIRECT IMAGE URL DETECTED]: '{url}' is a direct image file, not a web page. Use 'download_image' or 'identify_image' to inspect this image."
        }
        
    # Smart URL alias mapping for dynamic SPA pages to rich RSS feeds
    normalized_url = url.lower().rstrip("/")
    if normalized_url in ("https://www.nu.nl/weer", "https://nu.nl/weer", "https://www.nu.nl/rss/weer", "https://nu.nl/rss/weer"):
        url = "https://www.nu.nl/rss/weerbericht"
    elif normalized_url in ("https://www.nu.nl/tech", "https://nu.nl/tech"):
        url = "https://www.nu.nl/rss/Tech"
    elif normalized_url in ("https://www.nu.nl/algemeen", "https://nu.nl/algemeen", "https://www.nu.nl", "https://nu.nl"):
        url = "https://www.nu.nl/rss/Algemeen"
    elif normalized_url in ("https://www.duic.nl", "https://duic.nl", "https://www.duic.nl/feed", "https://duic.nl/feed"):
        url = "https://www.duic.nl/rss/"
        
    log_subagent("Web Fetcher", f"Fetching '{url}'...", INDICATOR_THINKING)
    resp = requests.get(url, headers={"User-Agent": WEB_USER_AGENT}, timeout=15)
    content_type = resp.headers.get("Content-Type", "").lower()
    if content_type.startswith("image/"):
        return {
            "id": action_id,
            "tool": "web_fetch",
            "status": "success",
            "result": f"[DIRECT IMAGE CONTENT DETECTED]: '{url}' returned an image ({content_type}). Use 'download_image' or 'identify_image' to inspect this image."
        }
    raw_html = resp.text
    clean_text = clean_html_to_text(raw_html, max_chars=WEB_FETCH_CHAR_LIMIT, base_url=url)
    log_subagent("Web Fetcher", f"Extracted {len(clean_text)} chars of text with article URLs in 0.01s", INDICATOR_DONE)
    return {"id": action_id, "tool": "web_fetch", "status": "success", "result": clean_text}
