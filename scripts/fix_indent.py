from pathlib import Path
p = Path(r"C:\Dev\ai-chatbot\models\ollama_client.py")
content = p.read_text(encoding="utf-8")
bad = """    }
        if NUM_GPU is not None and NUM_GPU != -1:
        payload["options"]["num_gpu"] = NUM_GPU
    if is_granite:"""
good = """    }
    if NUM_GPU is not None and NUM_GPU != -1:
        payload["options"]["num_gpu"] = NUM_GPU
    if is_granite:"""
content = content.replace(bad, good)
p.write_text(content, encoding="utf-8")
print("[OK] Fixed ollama_client.py indent")
