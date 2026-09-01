"""
Sandbox file management and scratchpad writing tools.
"""
import os
from typing import Dict, Any
from config import SANDBOX_DIR, SCRATCHPAD_PATH

def handle_write_file(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    filepath = params["filepath"]
    content = params.get("content", "")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return {"id": action_id, "tool": "write_to_file", "status": "success", "result": f"Successfully written to '{filepath}'"}

def handle_read_file(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    filepath = params["filepath"]
    if not os.path.exists(filepath):
        return {"id": action_id, "tool": "read_file", "status": "error", "result": f"File not found: '{filepath}'"}
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"id": action_id, "tool": "read_file", "status": "success", "result": content}

def handle_delete_file(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    filepath = params["filepath"]
    if not os.path.exists(filepath):
        return {"id": action_id, "tool": "delete_file", "status": "error", "result": f"File not found: '{filepath}'"}
    os.remove(filepath)
    return {"id": action_id, "tool": "delete_file", "status": "success", "result": f"Successfully deleted '{filepath}'"}

def handle_list_sandbox(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    dirpath = params.get("dirpath", str(SANDBOX_DIR))
    items = os.listdir(dirpath)
    return {"id": action_id, "tool": "list_sandbox", "status": "success", "result": f"Sandbox items in '{dirpath}': {items}"}

def handle_write_scratchpad(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    content = params.get("content", "")
    with open(SCRATCHPAD_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    return {"id": action_id, "tool": "write_to_scratchpad", "status": "success", "result": f"Scratchpad updated at '{SCRATCHPAD_PATH.name}'"}
