"""
Multi-model LLM interfaces and clients for AI Agent Thersites.
"""
from models.ollama_client import query_ollama, prewarm_ollama_model
from models.vision_client import query_ollama_vision, encode_image_to_base64
from models.context import estimate_dynamic_context, resolve_thinking_parameters

__all__ = [
    "query_ollama",
    "prewarm_ollama_model",
    "query_ollama_vision",
    "encode_image_to_base64",
    "estimate_dynamic_context",
    "resolve_thinking_parameters"
]
