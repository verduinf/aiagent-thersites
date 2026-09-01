"""
Memory capsule (Paycheck Capsule) tools for episodic and bookmarked knowledge.
"""
from typing import Dict, Any
from core.database import save_clue, delete_clue, get_clues_by_type
from console_logger import log_subagent, INDICATOR_DONE

def handle_remember(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    key = params.get("key", "")
    clue = params.get("clue", params.get("value", ""))
    entry_type = params.get("type", "memory")
    res = save_clue(key, clue, entry_type=entry_type)
    log_subagent("Memory Capsule", f"Saved [{res['type']}] '{res['key']}': '{res['value']}'", INDICATOR_DONE)
    return {"id": action_id, "tool": "remember", "status": "success", "result": f"Clue saved to Paycheck Capsule [{res['type']}]: [{res['key']}] -> {res['value']}"}

def handle_forget(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    key = params.get("key", "")
    deleted = delete_clue(key)
    status_msg = f"Clue '{key}' deleted from Paycheck Capsule" if deleted else f"Clue '{key}' not found in Paycheck Capsule"
    log_subagent("Memory Capsule", status_msg, INDICATOR_DONE)
    return {"id": action_id, "tool": "forget", "status": "success", "result": status_msg}

def handle_list_favorites(params: Dict[str, Any], action_id: str = "act_1") -> Dict[str, Any]:
    favs = get_clues_by_type("url_fav", limit=20)
    fav_map = {f['key']: f['value'] for f in favs}
    log_subagent("Memory Capsule", f"Retrieved {len(fav_map)} bookmarked internet favorites", INDICATOR_DONE)
    return {"id": action_id, "tool": "list_internet_fav", "status": "success", "result": f"Bookmarked Internet Favorites: {fav_map}"}
