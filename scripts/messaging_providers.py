"""
Standalone Reference Implementation for Agent Messaging Providers
Contains clean, reusable functions for:
1. Pushover (Native push alerts with image attachments, priority, tap URLs)
2. CallMeBot Signal (Free Signal alerts with image URL attachments)
3. CallMeBot WhatsApp (Free WhatsApp text alerts)
4. Twilio WhatsApp (Enterprise WhatsApp API)
"""
import os
import json
import urllib.parse
import urllib.request
import requests
from typing import Tuple, Optional

# ==============================================================================
# 1. PUSHOVER NOTIFICATION PROVIDER (Recommended - Private, No Ads, Direct Media)
# ==============================================================================
def send_pushover_notification(
    user_key: str,
    api_token: str,
    message: str,
    title: str = "AI Agent Notification",
    image_path: Optional[str] = None,
    click_url: Optional[str] = "http://localhost:8000",
    url_title: Optional[str] = "Open Agent Dashboard",
    priority: int = 0,
    sound: str = "magic"
) -> Tuple[bool, str]:
    if not user_key or not api_token:
        return False, "Missing user_key or api_token."
        
    payload = {
        "token": api_token,
        "user": user_key,
        "title": title,
        "message": message,
        "priority": priority,
        "url": click_url,
        "url_title": url_title,
        "sound": sound
    }
    
    files = None
    file_handle = None
    if image_path and os.path.exists(image_path):
        file_handle = open(image_path, "rb")
        files = {"attachment": (os.path.basename(image_path), file_handle)}
        
    try:
        resp = requests.post("https://api.pushover.net/1/messages.json", data=payload, files=files, timeout=15)
        if file_handle:
            file_handle.close()
        if resp.status_code == 200:
            return True, "Successfully dispatched Pushover alert."
        else:
            return False, f"Pushover HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        if file_handle:
            file_handle.close()
        return False, f"Pushover dispatch error: {str(e)}"


# ==============================================================================
# 2. CALLMEBOT SIGNAL PROVIDER (Free Signal messages + Image URL support)
# ==============================================================================
def send_callmebot_signal(
    phone: str,
    apikey: str,
    message: str,
    image_url: Optional[str] = None
) -> Tuple[bool, str]:
    if not phone or not apikey:
        return False, "Missing phone or apikey."
        
    encoded_message = urllib.parse.quote(message)
    if image_url:
        encoded_image = urllib.parse.quote(image_url)
        url = f"https://signal.callmebot.com/signal/send.php?phone={phone}&apikey={apikey}&image={encoded_image}&text={encoded_message}"
    else:
        url = f"https://signal.callmebot.com/signal/send.php?phone={phone}&apikey={apikey}&text={encoded_message}"
        
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AI-Agent"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status == 200:
                return True, "Successfully dispatched Signal message."
            return False, f"Signal gateway HTTP {resp.status}: {body}"
    except Exception as e:
        return False, f"Signal dispatch error: {str(e)}"


# ==============================================================================
# 3. CALLMEBOT WHATSAPP PROVIDER (Free WhatsApp text messages)
# ==============================================================================
def send_callmebot_whatsapp(
    phone: str,
    apikey: str,
    message: str
) -> Tuple[bool, str]:
    if not phone or not apikey:
        return False, "Missing phone or apikey."
        
    encoded_message = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_message}&apikey={apikey}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AI-Agent"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status == 200:
                return True, "Successfully dispatched WhatsApp message."
            return False, f"WhatsApp gateway HTTP {resp.status}: {body}"
    except Exception as e:
        return False, f"WhatsApp dispatch error: {str(e)}"
