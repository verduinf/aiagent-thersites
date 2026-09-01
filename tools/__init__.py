"""
Modular Agent Tools Package for AI Agent Thersites.
Inspects actions with The Warden and dispatches to specialized tool handlers.
"""
from typing import Dict, Any, Optional
from core.warden import inspect_and_authorize
from tools.climate import handle_get_room_temperatures, handle_get_heatmap
from tools.web import handle_web_fetch
from tools.vision import handle_identify_image, handle_download_image
from tools.files import handle_read_file, handle_write_file, handle_delete_file, handle_list_sandbox, handle_write_scratchpad
from tools.memory import handle_remember, handle_forget, handle_list_favorites
from tools.notifications import handle_send_message, dispatch_pushover_notification
from tools.sql import handle_sqlite_query_executor
from tools.image_gen import handle_generate_image

def execute_tool_call(action: Dict[str, Any], active_model: Optional[str] = None) -> Dict[str, Any]:
    """
    Validates tool execution with The Warden and dispatches to the corresponding modular tool handler.
    """
    tool_name = action.get("tool", action.get("name", "none")).strip()
    params = action.get("params", {})
    action_id = action.get("id", "act_1")
    
    authorized, warden_msg, sanitized_params = inspect_and_authorize(tool_name, params)
    if not authorized:
        return {"id": action_id, "tool": tool_name, "status": "blocked", "result": warden_msg}
        
    try:
        if tool_name == "get_room_temperatures":
            return handle_get_room_temperatures(sanitized_params, action_id)

        elif tool_name in ("get_heatmap", "get_heat_map", "render_floorplan", "get_floorplan_heatmap", "get_floorplan"):
            return handle_get_heatmap(sanitized_params, action_id)

        elif tool_name == "web_fetch":
            return handle_web_fetch(sanitized_params, action_id)

        elif tool_name in ("identify_image", "inspect_image", "gorgons_gaze", "analyze_image"):
            return handle_identify_image(sanitized_params, action_id, active_model=active_model)

        elif tool_name == "download_image":
            return handle_download_image(sanitized_params, action_id)

        elif tool_name == "write_to_file":
            return handle_write_file(sanitized_params, action_id)
            
        elif tool_name == "read_file":
            return handle_read_file(sanitized_params, action_id)
            
        elif tool_name == "delete_file":
            return handle_delete_file(sanitized_params, action_id)
            
        elif tool_name == "list_sandbox":
            return handle_list_sandbox(sanitized_params, action_id)
            
        elif tool_name == "write_to_scratchpad":
            return handle_write_scratchpad(sanitized_params, action_id)

        elif tool_name == "remember":
            return handle_remember(sanitized_params, action_id)

        elif tool_name in ("unremember", "forget"):
            return handle_forget(sanitized_params, action_id)

        elif tool_name in ("list_internet_fav", "list_favorites"):
            return handle_list_favorites(sanitized_params, action_id)

        elif tool_name == "sqlite_query_executor":
            return handle_sqlite_query_executor(sanitized_params, action_id)

        elif tool_name in ("send_message", "send_pushover_alert", "send_notification", "send_push_notification"):
            return handle_send_message(sanitized_params, action_id)

        elif tool_name in ("generate_image", "create_image", "draw_image"):
            return handle_generate_image(sanitized_params, action_id)
            
        elif tool_name in ("none", "finish", ""):
            return {"id": action_id, "tool": "none", "status": "success", "result": "Inner loop finished."}
            
        else:
            return {"id": action_id, "tool": tool_name, "status": "success", "result": f"Executed tool '{tool_name}'"}
            
    except Exception as e:
        return {"id": action_id, "tool": tool_name, "status": "error", "result": f"Execution error: {str(e)}"}

__all__ = [
    "execute_tool_call",
    "dispatch_pushover_notification",
    "handle_get_room_temperatures",
    "handle_web_fetch",
    "handle_identify_image",
    "handle_download_image",
    "handle_generate_image",
    "handle_read_file",
    "handle_write_file",
    "handle_delete_file",
    "handle_list_sandbox",
    "handle_write_scratchpad",
    "handle_remember",
    "handle_forget",
    "handle_list_favorites",
    "handle_sqlite_query_executor",
    "handle_send_message"
]
