"""
Climate and indoor sensor tools (Tado integration).
Provides clean separation between pure telemetry fetching and architectural heat map rendering.
"""
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional
from tools import tado_client
from config import SANDBOX_DIR, TEMPLATES_DIR
from console_logger import log_subagent, INDICATOR_THINKING, INDICATOR_DONE, INDICATOR_BLOCKED

def _get_temp_color(temp_c: Optional[float]) -> str:
    """Returns a visual color for temperature ranges."""
    if temp_c is None:
        return "#94a3b8"
    if temp_c < 18.5:
        return "#38bdf8"  # Cool / Blue
    elif temp_c <= 21.5:
        return "#4ade80"  # Ideal Comfort / Green
    else:
        return "#f97316"  # Warm / Orange

def generate_svg_floorplan_with_temperatures(rooms: Dict[str, Any]) -> Optional[str]:
    """
    Populates templates/floorplan_master.svg with live measured Tado temperatures.
    """
    master_svg_path = TEMPLATES_DIR / "floorplan_master.svg"
    if not master_svg_path.exists():
        # Fallback to sandbox if template is there
        master_svg_path = SANDBOX_DIR / "floorplan_master.svg"
        if not master_svg_path.exists():
            return None

    try:
        svg_content = master_svg_path.read_text(encoding="utf-8")

        # Map common room identifiers (supporting new English IDs and legacy IDs)
        id_mappings = {
            "temp-living": ["woonkamer", "living", "living room"],
            "temp-woonkamer": ["woonkamer", "living", "living room"],
            "temp-study": ["studeerkamer", "study", "slaapkamer 1", "bedroom 1", "kantoor", "workstation"],
            "temp-slaapkamer1": ["studeerkamer", "study", "slaapkamer 1", "bedroom 1", "kantoor", "workstation"],
            "temp-bedroom": ["slaapkamer", "slaapkamer 2", "bedroom", "bedroom 2", "master", "master bedroom"],
            "temp-slaapkamer2": ["slaapkamer", "slaapkamer 2", "bedroom", "bedroom 2", "master", "master bedroom"],
            "temp-kitchen": ["keuken", "kitchen"],
            "temp-keuken": ["keuken", "kitchen"],
            "temp-bathroom": ["badkamer", "bathroom", "bath"],
            "temp-badkamer": ["badkamer", "bathroom", "bath"],
            "temp-hallway": ["hal", "hallway", "gang", "hall"],
            "temp-hal": ["hal", "hallway", "gang", "hall"]
        }

        for svg_id, aliases in id_mappings.items():
            matched_temp = None
            for r_name, r_data in rooms.items():
                r_clean = r_name.strip().lower()
                if any(alias in r_clean for alias in aliases):
                    matched_temp = r_data.get("current_temperature_celsius")
                    break

            if matched_temp is not None:
                temp_str = f"{matched_temp:.1f}°C"
                color = _get_temp_color(matched_temp)
                # Replace the placeholder text in the matching SVG node
                pattern = rf'(id="{svg_id}"[^>]*>)[^<]*(</text>)'
                replacement = rf'\g<1>{temp_str}\g<2>'
                svg_content = re.sub(pattern, replacement, svg_content)
                # Also colorize the specific temp text element
                style_pattern = rf'(id="{svg_id}")'
                style_replacement = rf'\1 fill="{color}"'
                svg_content = re.sub(style_pattern, style_replacement, svg_content)

        return svg_content
    except Exception:
        return None

def handle_get_room_temperatures(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    """
    Pure telemetry query tool: returns live indoor temperature and humidity readings.
    """
    log_subagent("Tado Climate", "Querying Tado API for live room temperatures...", INDICATOR_THINKING)
    start_t = time.time()
    tado_res = tado_client.get_room_temperatures()
    elapsed = round(time.time() - start_t, 2)
    
    if tado_res.get("status") == "success":
        summary = tado_res.get("summary_text", "")
        rooms = tado_res.get("rooms", {})
        log_subagent("Tado Climate", f"Extracted live room readings in {elapsed}s", INDICATOR_DONE)
        return {
            "id": action_id,
            "tool": "get_room_temperatures",
            "status": "success",
            "result": summary,
            "rooms": rooms
        }
    else:
        err = tado_res.get("error", "Unknown error")
        log_subagent("Tado Climate", f"Error: {err}", INDICATOR_BLOCKED)
        return {
            "id": action_id,
            "tool": "get_room_temperatures",
            "status": "error",
            "result": f"Tado Error: {err}"
        }

def handle_get_heatmap(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    """
    Dedicated Heat Map tool: stamps live temperatures onto the architectural floorplan template
    and saves to sandbox/floorplan_live.svg.
    """
    log_subagent("Heat Map", "Rendering live temperature overlay on architectural floorplan...", INDICATOR_THINKING)
    start_t = time.time()
    tado_res = tado_client.get_room_temperatures()
    
    if tado_res.get("status") != "success":
        err = tado_res.get("error", "Unknown error fetching sensor telemetry")
        log_subagent("Heat Map", f"Error: {err}", INDICATOR_BLOCKED)
        return {
            "id": action_id,
            "tool": "get_heatmap",
            "status": "error",
            "result": f"Tado Error: {err}"
        }

    rooms = tado_res.get("rooms", {})
    summary = tado_res.get("summary_text", "")
    svg_blueprint = generate_svg_floorplan_with_temperatures(rooms)

    if not svg_blueprint:
        log_subagent("Heat Map", "Floorplan master template not found in templates/", INDICATOR_BLOCKED)
        return {
            "id": action_id,
            "tool": "get_heatmap",
            "status": "error",
            "result": "Floorplan template 'templates/floorplan_master.svg' was not found."
        }

    live_svg_path = SANDBOX_DIR / "floorplan_live.svg"
    try:
        live_svg_path.write_text(svg_blueprint, encoding="utf-8")
        elapsed = round(time.time() - start_t, 2)
        log_subagent("Heat Map", f"Generated live floorplan heat map in {elapsed}s -> sandbox/floorplan_live.svg", INDICATOR_DONE)
        return {
            "id": action_id,
            "tool": "get_heatmap",
            "status": "success",
            "result": f"Live architectural floorplan heat map generated and saved to 'sandbox/floorplan_live.svg'. Embed in your reply using: ![Live Heatmap](/sandbox/floorplan_live.svg)\n\n{summary}",
            "url": "/sandbox/floorplan_live.svg",
            "markdown": "![Live Heatmap](/sandbox/floorplan_live.svg)",
            "rooms": rooms
        }
    except Exception as e:
        log_subagent("Heat Map", f"Failed to save live floorplan: {e}", INDICATOR_BLOCKED)
        return {
            "id": action_id,
            "tool": "get_heatmap",
            "status": "error",
            "result": f"Failed to write live floorplan SVG: {e}"
        }
