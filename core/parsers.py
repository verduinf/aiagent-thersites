"""
Robust JSON, HTML, and RSS/Atom feed parsing utilities for AI Agent Thersites.
"""
import re
import json
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
from config import WEB_FETCH_CHAR_LIMIT

def extract_fuzzy_json(raw_text: str) -> Dict[str, Any]:
    """
    Fuzzy JSON extractor that safely handles markdown fences, embedded code blocks,
    unescaped control characters/newlines, unescaped quotes in content,
    and extracts contract-compliant thought/content/actions JSON objects.
    """
    clean_text = raw_text.strip()
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\s*```$", "", clean_text)
        
    decoder = json.JSONDecoder(strict=False)
    idx = 0
    valid_candidates = []
    
    # Pass 1: Standard raw_decode with strict=False
    while idx < len(clean_text):
        pos = clean_text.find('{', idx)
        if pos == -1:
            break
        try:
            obj, end = decoder.raw_decode(clean_text, pos)
            if isinstance(obj, dict):
                valid_candidates.append(obj)
                idx = end
                continue
        except json.JSONDecodeError:
            pass
        idx = pos + 1
        
    data = None
    for candidate in valid_candidates:
        if "thought" in candidate or "actions" in candidate:
            data = candidate
            break
            
    if not data and valid_candidates:
        data = valid_candidates[0]

    # Pass 2: Fallback Regex Extraction for unescaped multiline XML/SVG/quotes
    if not data:
        thought = "Processing..."
        content = ""
        actions = []

        thought_m = re.search(r'"thought"\s*:\s*"((?:[^"\\]|\\.)*)"', clean_text, re.DOTALL)
        if thought_m:
            raw_t = thought_m.group(1)
            thought = raw_t.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')

        actions_m = re.search(r'"actions"\s*:\s*(\[[^\]]*\])', clean_text, re.DOTALL)
        if actions_m:
            try:
                actions = json.loads(actions_m.group(1), strict=False)
            except Exception:
                actions = []

        content_m = re.search(r'"content"\s*:\s*"(.*?)",?\s*(?:"actions"|\}\s*$)', clean_text, re.DOTALL)
        if not content_m:
            content_m = re.search(r'"content"\s*:\s*"(.*)', clean_text, re.DOTALL)
        if content_m:
            raw_c = content_m.group(1).rstrip('"} \n\r\t')
            content = raw_c.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')

        if thought_m or content_m or actions_m:
            data = {"thought": thought, "content": content, "actions": actions}
        
    if not data:
        raise ValueError("No valid contract JSON object found in response. You MUST wrap your response in valid JSON matching the contract schema.")
        
    thought = data.get("thought", "Processing...")
    content = data.get("content", "")
    actions = data.get("actions", [])
    
    if not isinstance(actions, list):
        if isinstance(data.get("action"), dict):
            actions = [data["action"]]
        else:
            actions = []
            
    return {"thought": thought, "content": content, "actions": actions}

def extract_structured_feed(raw_text: str, max_items: int = 15) -> Optional[str]:
    """
    Parses XML/RSS/Atom feeds into structured numbered item lists with titles, dates, links, and summaries.
    """
    clean_str = raw_text.lstrip('\ufeff').strip()
    lower_text = clean_str[:500].lower()
    
    if "<rss" in lower_text or "<feed" in lower_text or ("<channel" in lower_text and "<item" in lower_text) or "<?xml" in lower_text:
        try:
            root = ET.fromstring(clean_str.encode('utf-8'))
            
            feed_title = root.findtext(".//channel/title") or root.findtext(".//title") or "RSS Feed"
            feed_title = re.sub(r'<[^>]+>', '', feed_title).strip()
            
            items = root.findall(".//item") or root.findall(".//entry")
            if not items:
                return None
                
            formatted_items = []
            for i, it in enumerate(items[:max_items]):
                title = (it.findtext("title") or "No Title").strip()
                title = re.sub(r'<[^>]+>', '', title).strip()
                
                link = (it.findtext("link") or "").strip()
                if not link:
                    for child in it:
                        if child.tag.endswith("link"):
                            link = child.attrib.get("href", (child.text or "").strip())
                            if link:
                                break
                                
                desc = it.findtext("description") or it.findtext("summary") or it.findtext("content") or ""
                desc_clean = re.sub(r'<[^>]+>', ' ', desc)
                desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()
                if len(desc_clean) > 220:
                    desc_clean = desc_clean[:220] + "..."
                    
                pub_date = (it.findtext("pubDate") or it.findtext("updated") or "").strip()
                
                img_url = ""
                for child in it:
                    if child.tag.endswith("enclosure") and child.attrib.get("type", "").startswith("image/"):
                        img_url = child.attrib.get("url", "")
                        break
                    elif child.tag.endswith("content") and "url" in child.attrib:
                        img_url = child.attrib.get("url", "")
                        break
                    elif "image" in child.tag.lower() and "url" in child.attrib:
                        img_url = child.attrib.get("url", "")
                        break
                        
                if not img_url:
                    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc)
                    if img_match:
                        img_url = img_match.group(1)
                
                img_tag = f" [IMAGE: {img_url}]" if img_url else ""
                date_tag = f" ({pub_date})" if pub_date else ""
                
                formatted_items.append(f"[{i+1}] {title}{date_tag}\n    URL: {link}\n    Summary: {desc_clean}{img_tag}")
                
            return f"--- {feed_title} ({len(formatted_items)} items) ---\n\n" + "\n\n".join(formatted_items)
        except Exception:
            pass
    return None

def clean_html_to_text(html_content: str, max_chars: Optional[int] = None, base_url: str = "") -> str:
    """
    Robust HTML and RSS feed stripper prioritizing structured feed items or <main> / <article> blocks.
    Resolves relative links and images against base_url.
    """
    limit = max_chars if max_chars is not None else WEB_FETCH_CHAR_LIMIT
    feed_text = extract_structured_feed(html_content, max_items=15)
    if feed_text:
        return feed_text[:limit]
        
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<svg[^>]*>.*?</svg>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    main_matches = re.findall(r'<(main|article)[^>]*>(.*?)</\1>', text, flags=re.DOTALL | re.IGNORECASE)
    if main_matches:
        text = " ".join([m[1] for m in main_matches])
    else:
        text = re.sub(r'<(header|nav|footer)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<div[^>]*(header|nav|menu|footer)[^>]*>.*?</div>', '', text, flags=re.DOTALL | re.IGNORECASE)

    NAV_KEYWORDS = {'voorpagina', 'net binnen', 'binnenland', 'buitenland', 'politiek', 'economie', 'sport', 
                    'formule 1', 'wielrennen', 'inloggen', 'zoeken', 'menu', 'tv-gids', 'weer', 'spellen', 'shop'}

    def link_replacer(match):
        href = match.group(1)
        anchor_text = re.sub(r'<[^>]+>', ' ', match.group(2)).strip()
        
        if base_url:
            href = urllib.parse.urljoin(base_url, href)
        elif href.startswith("/"):
            href = f"https://nu.nl{href}"
            
        lower_anchor = anchor_text.lower()
        if lower_anchor in NAV_KEYWORDS or len(anchor_text) < 12 or href.endswith(('.css', '.js', '.png', '.jpg', '.svg', '.gif')):
            return f" {anchor_text} "
            
        return f" [{anchor_text}]({href}) "

    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', link_replacer, text, flags=re.DOTALL | re.IGNORECASE)
    
    def img_replacer(match):
        src = match.group(1)
        if base_url:
            src = urllib.parse.urljoin(base_url, src)
        elif src.startswith("/"):
            src = f"https://nu.nl{src}"
        if not src.endswith((".svg", ".gif", ".ico")) and ("media" in src or "images" in src or src.endswith((".jpg", ".png", ".webp"))):
            return f" [IMAGE: {src}] "
        return " "

    text = re.sub(r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*>', img_replacer, text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<enclosure\s+[^>]*url=["\']([^"\']+)["\'][^>]*>', r' [IMAGE: \1] ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return "[PAGE CONTENT]: No direct textual body extracted (page may require JavaScript rendering). Try fetching category feeds like https://www.nu.nl/rss/Algemeen or https://www.nu.nl/rss/Binnenland."
    return text[:limit]
