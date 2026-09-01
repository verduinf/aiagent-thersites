"""
Context and thinking budget calculations for multi-model runtime.
"""
from typing import Dict, Any, List, Tuple
from config import (
    NUM_CTX, THINK_BUDGET_LOW, THINK_BUDGET_DEEP, DEFAULT_THINK_MODE
)

def estimate_dynamic_context(messages: List[Dict[str, str]], floor: int = 2048, headroom: int = 1024) -> int:
    """
    Ultra-lean dynamic context scaling: lean baseline, expanding dynamically with prompt + headroom up to NUM_CTX.
    """
    total_chars = sum(len(m.get("content", "")) for m in messages)
    estimated_prompt_tokens = int(total_chars / 3.2) + 200
    return min(NUM_CTX, max(floor, estimated_prompt_tokens + headroom))

def resolve_thinking_parameters(model: str, think_mode: Any = DEFAULT_THINK_MODE) -> Tuple[Any, str, int]:
    """
    Normalizes think mode and resolves (think_val, reasoning_effort, predict_budget)
    for model-specific reasoning implementations (e.g. Granite vs Qwen).
    """
    if isinstance(think_mode, bool):
        mode_str = "deep" if think_mode else "off"
    else:
        mode_str = str(think_mode or DEFAULT_THINK_MODE).lower().strip()
        if mode_str not in ("off", "low", "deep"):
            mode_str = "off"
            
    is_granite = "granite" in model.lower()
    
    if mode_str == "off":
        think_val = False
        reasoning_effort = "none"
        predict_budget = 1536
    elif mode_str == "low":
        think_val = "low" if is_granite else True
        reasoning_effort = "low"
        predict_budget = 1536 + THINK_BUDGET_LOW
    else:  # deep
        think_val = True
        reasoning_effort = "high"
        predict_budget = 2048 + THINK_BUDGET_DEEP
        
    return think_val, reasoning_effort, predict_budget
