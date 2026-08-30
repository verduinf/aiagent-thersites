"""
Tado Climate API Client for Local Intern Thersites
Handles OAuth2 token exchange with in-memory caching (10-min lifecycle),
home discovery, and room temperature/humidity extraction.
"""
import os
import time
import requests
from typing import Dict, Any, Optional

from config import BASE_DIR

# Load credentials from environment
TADO_USERNAME = os.environ.get("TADO_USERNAME", os.environ.get("TADO_EMAIL", ""))
TADO_PASSWORD = os.environ.get("TADO_PASSWORD", "")

# In-memory Token & Home Cache
_CACHED_ACCESS_TOKEN: Optional[str] = None
_TOKEN_EXPIRES_AT: float = 0.0
_CACHED_HOME_ID: Optional[int] = None
_CACHED_ZONES_MAP: Dict[int, str] = {}
_ZONES_MAP_EXPIRES_AT: float = 0.0

def set_tado_credentials(username: str, password: str):
    """Programmatically set or update Tado credentials."""
    global TADO_USERNAME, TADO_PASSWORD, _CACHED_ACCESS_TOKEN, _TOKEN_EXPIRES_AT
    TADO_USERNAME = username
    TADO_PASSWORD = password
    _CACHED_ACCESS_TOKEN = None
    _TOKEN_EXPIRES_AT = 0.0

def get_valid_access_token() -> str:
    """
    Exchanges Tado credentials for an OAuth2 bearer token.
    Reuses cached token if valid (Tado tokens expire in 10 minutes / 600s).
    """
    global _CACHED_ACCESS_TOKEN, _TOKEN_EXPIRES_AT
    now = time.time()
    
    # Return cached token if valid for at least 60 more seconds
    if _CACHED_ACCESS_TOKEN and now < (_TOKEN_EXPIRES_AT - 60):
        return _CACHED_ACCESS_TOKEN
        
    username = TADO_USERNAME or os.environ.get("TADO_USERNAME") or os.environ.get("TADO_EMAIL", "")
    password = TADO_PASSWORD or os.environ.get("TADO_PASSWORD", "")
    
    if not username or not password:
        raise ValueError("Tado credentials not configured. Please set TADO_USERNAME and TADO_PASSWORD in .env")
        
    token_url = "https://my.tado.com/oauth/token"
    payload = {
        "client_id": "tado-webapp",
        "grant_type": "password",
        "scope": "home.user",
        "username": username,
        "password": password,
    }
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent-Thersites"}
    resp = requests.post(token_url, data=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    
    data = resp.json()
    _CACHED_ACCESS_TOKEN = data["access_token"]
    expires_in = int(data.get("expires_in", 599))
    _TOKEN_EXPIRES_AT = now + expires_in
    
    return _CACHED_ACCESS_TOKEN

def get_home_id() -> int:
    """Fetches and caches the user's primary Home ID."""
    global _CACHED_HOME_ID
    if _CACHED_HOME_ID is not None:
        return _CACHED_HOME_ID
        
    token = get_valid_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Agent-Thersites"
    }
    resp = requests.get("https://my.tado.com/api/v2/me", headers=headers, timeout=15)
    resp.raise_for_status()
    
    data = resp.json()
    _CACHED_HOME_ID = int(data["homeId"])
    return _CACHED_HOME_ID

def get_zones_map(home_id: int) -> Dict[int, str]:
    """Fetches and caches zone_id -> room name mapping (e.g. 1: 'Living Room')."""
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
    _CACHED_ZONES_MAP = {int(z["id"]): z["name"] for z in zones if "id" in z and "name" in z}
    _ZONES_MAP_EXPIRES_AT = now + 3600  # Cache zone names for 1 hour
    return _CACHED_ZONES_MAP

def get_room_temperatures() -> Dict[str, Any]:
    """
    Fetches the live temperature, target temperature, and humidity for all rooms.
    Returns a clean structured dictionary and human-readable text summary.
    """
    try:
        home_id = get_home_id()
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
        summary_lines = [f"Tado Climate Status (Home ID: {home_id}):"]
        
        for zid_str, state in zone_states.items():
            zid = int(zid_str)
            room_name = zones_map.get(zid, f"Room {zid}")
            
            # Extract sensor readings
            sensor_dp = state.get("sensorDataPoints", {})
            temp_dp = sensor_dp.get("insideTemperature")
            humidity_dp = sensor_dp.get("humidity")
            
            current_temp = temp_dp.get("celsius") if temp_dp else None
            humidity = humidity_dp.get("percentage") if humidity_dp else None
            
            # Extract target settings
            setting = state.get("setting", {})
            power = setting.get("power", "OFF")
            target_temp_obj = setting.get("temperature")
            target_temp = target_temp_obj.get("celsius") if target_temp_obj else None
            
            # Extract heating activity
            activity_dp = state.get("activityDataPoints", {})
            heating_power = activity_dp.get("heatingPower", {}).get("percentage", 0.0) if activity_dp else 0.0
            
            room_info = {
                "current_temperature_celsius": current_temp,
                "target_temperature_celsius": target_temp,
                "humidity_percentage": humidity,
                "heating_power_percentage": heating_power,
                "power_state": power
            }
            rooms[room_name] = room_info
            
            curr_str = f"{current_temp:.1f}?C" if current_temp is not None else "N/A"
            targ_str = f"{target_temp:.1f}?C" if target_temp is not None else "OFF"
            hum_str = f"{humidity:.0f}%" if humidity is not None else "N/A"
            heat_str = f"{heating_power:.0f}%" if heating_power is not None else "0%"
            
            summary_lines.append(f"- {room_name}: {curr_str} (Target: {targ_str}, Humidity: {hum_str}, Heating: {heat_str})")
            
        return {
            "status": "success",
            "home_id": home_id,
            "rooms": rooms,
            "summary_text": "\n".join(summary_lines)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "summary_text": f"Error fetching Tado room temperatures: {e}"
        }
