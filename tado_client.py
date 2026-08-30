import threading
"""
Tado Climate API Client for Local Intern Thersites
Handles OAuth2 PKCE token exchange with active access probing, 
in-memory caching (10-min lifecycle), home discovery, and room telemetry extraction.
"""
import os
import re
import time
import base64
import hashlib
import secrets
import requests
from typing import Dict, Any, Optional

# In-memory Token & Home Cache (10-minute lifecycle)
_CACHED_ACCESS_TOKEN: Optional[str] = None
_TOKEN_EXPIRES_AT: float = 0.0
_CACHED_HOME_ID: Optional[int] = None
_CACHED_HOME_NAME: str = "Home"
_CACHED_ZONES_MAP: Dict[int, Dict[str, Any]] = {}
_ZONES_MAP_EXPIRES_AT: float = 0.0
_TOKEN_LOCK = threading.Lock()

def load_credentials():
    """Loads Tado credentials from environment or .env file."""
    username = os.environ.get("TADO_USERNAME") or os.environ.get("TADO_EMAIL", "")
    password = os.environ.get("TADO_PASSWORD", "")
    
    if not username or not password:
        try:
            with open(".env", "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"\'').strip()
                        if k in ("TADO_USERNAME", "TADO_EMAIL") and not username:
                            username = v
                        elif k == "TADO_PASSWORD" and not password:
                            password = v
        except Exception:
            pass
            
    return username, password

def set_tado_credentials(username: str, password: str):
    """Programmatically set or update Tado credentials."""
    global _CACHED_ACCESS_TOKEN, _TOKEN_EXPIRES_AT
    os.environ["TADO_USERNAME"] = username
    os.environ["TADO_PASSWORD"] = password
    _CACHED_ACCESS_TOKEN = None
    _TOKEN_EXPIRES_AT = 0.0

def is_cached_token_alive() -> bool:
    """
    Probes the Tado API with the current cached token to verify if we still have access.
    Returns True if the token is valid and active (HTTP 200), avoiding unnecessary re-auth.
    """
    global _CACHED_ACCESS_TOKEN, _TOKEN_EXPIRES_AT
    if not _CACHED_ACCESS_TOKEN:
        return False
        
    now = time.time()
    # If locally expired beyond lifecycle timestamp, do not probe
    if now >= (_TOKEN_EXPIRES_AT - 15):
        return False
        
    try:
        headers = {
            "Authorization": f"Bearer {_CACHED_ACCESS_TOKEN}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent-Thersites"
        }
        probe_r = requests.get("https://my.tado.com/api/v2/me", headers=headers, timeout=5)
        if probe_r.status_code == 200:
            return True
    except Exception:
        pass
        
    return False

def get_valid_access_token() -> str:
    """
    Returns a verified valid OAuth2 Bearer token with thread-safe concurrency locking.
    Prior to requesting a new token via OAuth, checks if existing cached access is still alive.
    """
    global _CACHED_ACCESS_TOKEN, _TOKEN_EXPIRES_AT
    
    # 1. Fast path: check prior access before acquiring lock
    if is_cached_token_alive():
        return _CACHED_ACCESS_TOKEN
        
    with _TOKEN_LOCK:
        # Re-check under lock in case another thread refreshed it
        if is_cached_token_alive():
            return _CACHED_ACCESS_TOKEN
        
    username, password = load_credentials()
    if not username or not password:
        raise ValueError("Tado credentials not found. Please configure TADO_USERNAME and TADO_PASSWORD in .env")
        
    now = time.time()
    
    # 2. Perform PKCE Authorization Exchange
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode('utf-8')
    challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b'=').decode('utf-8')
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    })
    
    client_id = "af44f89e-ae86-4ebe-905f-6bf759cf6473"
    redirect_uri = "https://app.tado.com/en/auth/authorize"
    
    auth_url = (
        f"https://login.tado.com/oauth2/authorize?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"scope=home.user&"
        f"redirect_uri={redirect_uri}&"
        f"code_challenge={code_challenge}&"
        f"code_challenge_method=S256"
    )
    
    r1 = session.get(auth_url, timeout=15)
    r1.raise_for_status()
    
    hidden_inputs = dict(re.findall(r'<input[^>]+type=["\']hidden["\'][^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']', r1.text))
    action_match = re.search(r'action=["\']([^"\']+)["\']', r1.text)
    action_url = f"https://login.tado.com{action_match.group(1)}" if action_match else auth_url
    
    login_payload = {
        **hidden_inputs,
        "loginId": username,
        "password": password
    }
    
    r2 = session.post(action_url, data=login_payload, allow_redirects=True, timeout=15)
    
    code_match = re.search(r'code=([^&]+)', r2.url)
    if not code_match:
        for resp in r2.history:
            loc = resp.headers.get("Location", "")
            if "code=" in loc:
                code_match = re.search(r'code=([^&]+)', loc)
                break
                
    if not code_match:
        raise ValueError("Failed to obtain OAuth authorization code from Tado login. Please verify credentials.")
        
    auth_code = code_match.group(1)
    
    # 3. Exchange Code for Bearer Access Token
    token_payload = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier
    }
    tok_resp = session.post("https://login.tado.com/oauth2/token", data=token_payload, timeout=15)
    tok_resp.raise_for_status()
    
    tok_data = tok_resp.json()
    _CACHED_ACCESS_TOKEN = tok_data["access_token"]
    expires_in = int(tok_data.get("expires_in", 599))
    _TOKEN_EXPIRES_AT = now + expires_in
    
    return _CACHED_ACCESS_TOKEN

def get_home_info() -> Dict[str, Any]:
    """Fetches and caches the user's primary Home ID and Name."""
    global _CACHED_HOME_ID, _CACHED_HOME_NAME
    if _CACHED_HOME_ID is not None and is_cached_token_alive():
        return {"id": _CACHED_HOME_ID, "name": _CACHED_HOME_NAME}
        
    token = get_valid_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent-Thersites"
    }
    resp = requests.get("https://my.tado.com/api/v2/me", headers=headers, timeout=15)
    resp.raise_for_status()
    
    data = resp.json()
    _CACHED_HOME_ID = int(data.get("homeId") or data.get("homes", [{}])[0].get("id"))
    _CACHED_HOME_NAME = data.get("homes", [{}])[0].get("name", "Home")
    return {"id": _CACHED_HOME_ID, "name": _CACHED_HOME_NAME}

def get_zones_map(home_id: int) -> Dict[int, Dict[str, Any]]:
    """Fetches and caches zone metadata (ID -> name, type)."""
    global _CACHED_ZONES_MAP, _ZONES_MAP_EXPIRES_AT
    now = time.time()
    if _CACHED_ZONES_MAP and now < _ZONES_MAP_EXPIRES_AT:
        return _CACHED_ZONES_MAP
        
    token = get_valid_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent-Thersites"
    }
    resp = requests.get(f"https://my.tado.com/api/v2/homes/{home_id}/zones", headers=headers, timeout=15)
    resp.raise_for_status()
    
    zones = resp.json()
    _CACHED_ZONES_MAP = {
        int(z["id"]): {"name": z.get("name", f"Zone {z.get('id')}"), "type": z.get("type", "HEATING")}
        for z in zones if "id" in z
    }
    _ZONES_MAP_EXPIRES_AT = now + 3600  # Cache zone metadata for 1 hour
    return _CACHED_ZONES_MAP

def get_room_temperatures() -> Dict[str, Any]:
    """
    Fetches live temperatures, target settings, humidity, and heating states for all rooms.
    Returns structured room data and a human-readable summary.
    """
    try:
        home_info = get_home_info()
        home_id = home_info["id"]
        home_name = home_info["name"]
        
        zones_map = get_zones_map(home_id)
        token = get_valid_access_token()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent-Thersites"
        }
        
        resp = requests.get(f"https://my.tado.com/api/v2/homes/{home_id}/zoneStates", headers=headers, timeout=15)
        resp.raise_for_status()
        
        zone_states = resp.json().get("zoneStates", {})
        rooms = {}
        summary_lines = [f"Tado Climate Status ({home_name}):"]
        
        for zid, meta in zones_map.items():
            zid_str = str(zid)
            room_name = meta["name"]
            room_type = meta["type"]
            state = zone_states.get(zid_str, {})
            
            # Extract sensor readings
            sensor = state.get("sensorDataPoints") or {}
            temp_obj = sensor.get("insideTemperature") or {}
            hum_obj = sensor.get("humidity") or {}
            
            current_temp = temp_obj.get("celsius")
            humidity = hum_obj.get("percentage")
            
            # Extract target settings
            setting = state.get("setting") or {}
            power = setting.get("power", "OFF")
            target_temp_obj = setting.get("temperature") or {}
            target_temp = target_temp_obj.get("celsius")
            
            # Extract heating power
            activity = state.get("activityDataPoints") or {}
            heat_obj = activity.get("heatingPower") or {}
            heating_power = heat_obj.get("percentage", 0.0)
            
            room_info = {
                "name": room_name,
                "type": room_type,
                "current_temperature_celsius": current_temp,
                "target_temperature_celsius": target_temp,
                "humidity_percentage": humidity,
                "heating_power_percentage": heating_power,
                "power_state": power
            }
            rooms[room_name] = room_info
            
            curr_str = f"{current_temp:.1f}?C" if current_temp is not None else "N/A"
            targ_str = f"{target_temp:.1f}?C" if (power == "ON" and target_temp is not None) else "OFF"
            hum_str = f"{humidity:.0f}%" if humidity is not None else "N/A"
            heat_str = f"{heating_power:.0f}%" if heating_power is not None else "0%"
            
            summary_lines.append(f"- {room_name}: Current: {curr_str} (Target: {targ_str}, Humidity: {hum_str}, Heating: {heat_str})")
            
        return {
            "status": "success",
            "home_id": home_id,
            "home_name": home_name,
            "rooms": rooms,
            "summary_text": "\n".join(summary_lines)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "summary_text": f"Error fetching Tado room temperatures: {e}"
        }
