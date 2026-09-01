"""
OpenVINO Image Generation Tool for AI Agent Thersites.
Supports both fast, lightweight SD 1.5 INT8 and high-fidelity FLUX.1-schnell INT4 on Intel GPU/CPU.
Provides ephemeral memory lifecycle (loads on-demand, generates, logs hardware telemetry, and immediately releases VRAM).
"""
import os
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from config import (
    SANDBOX_DIR, SD_MODEL_DIR, FLUX_MODEL_DIR, SD_DEVICE,
    SD_PYTHON_PATH, SD_CACHE_DIR, SD_DEFAULT_STEPS,
    IMAGE_GEN_METADATA_RECEIPT, IMAGE_MAX_DIMENSION
)
from console_logger import log_main, INDICATOR_DONE, INDICATOR_THINKING, INDICATOR_BLOCKED

def _generate_via_subprocess(
    prompt: str,
    target_path: Path,
    metadata_path: Optional[Path] = None,
    model_type: str = "sd1.5",
    negative_prompt: str = "blurry, low quality, distorted, bad anatomy",
    steps: Optional[int] = None,
    seed: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    device: str = "GPU",
    save_metadata: bool = True
) -> Dict[str, Any]:
    """
    Executes the OpenVINO generation in a dedicated Python subprocess targeting SD_PYTHON_PATH.
    Guarantees 100% immediate OS memory reclamation upon completion and writes a metadata receipt.
    """
    # Model selection and defaults
    is_flux = "flux" in str(model_type).lower()
    selected_model_path = str(FLUX_MODEL_DIR) if is_flux else str(SD_MODEL_DIR)
    
    final_steps = steps if steps is not None else (4 if is_flux else SD_DEFAULT_STEPS)
    final_width = width if width is not None else (768 if is_flux else 512)
    final_height = height if height is not None else (768 if is_flux else 512)
    final_seed = int(seed) if seed is not None else 42

    py_code = f"""
import sys
import time
import json
import os
from datetime import datetime
from pathlib import Path
import psutil
from PIL import Image
import openvino_genai as ov

model_path = r"{selected_model_path}"
cache_dir = r"{SD_CACHE_DIR}"
device = "{device}"
target_path = r"{target_path}"
metadata_path = r"{metadata_path}"
prompt = {json.dumps(prompt)}
negative_prompt = {json.dumps(negative_prompt)}
steps = {final_steps}
seed = {final_seed}
width = {final_width}
height = {final_height}
is_flux = {is_flux}

process = psutil.Process(os.getpid())

def get_ram_gb():
    try:
        return process.memory_info().rss / (1024 ** 3)
    except Exception:
        return 0.0

def get_gpu_memory_stats():
    try:
        core = ov.Core()
        return str(core.get_property(device, "GPU_MEMORY_STATISTICS"))
    except Exception:
        return "unavailable"

try:
    start_dt = datetime.now()
    t0 = time.time()
    ram_before_load = get_ram_gb()

    try:
        if is_flux:
            pipe = ov.Text2ImagePipeline(model_path, device)
        else:
            pipe = ov.Text2ImagePipeline(model_path, device, CACHE_DIR=cache_dir)
    except Exception:
        # Fallback to CPU if target device fails compilation
        pipe = ov.Text2ImagePipeline(model_path, "CPU")

    load_time = time.time() - t0
    ram_after_load = get_ram_gb()
    t1 = time.time()

    gen_kwargs = {{
        "width": width,
        "height": height,
        "num_inference_steps": steps,
        "rng_seed": seed
    }}
    if not is_flux:
        gen_kwargs["guidance_scale"] = 7.5
        gen_kwargs["negative_prompt"] = negative_prompt

    result = pipe.generate(prompt, **gen_kwargs)
    gen_time = time.time() - t1
    end_dt = datetime.now()
    ram_after_gen = get_ram_gb()

    image_array = result.data
    image = Image.fromarray(image_array[0])
    image.save(target_path)
    ram_after_save = get_ram_gb()

    gpu_stats = get_gpu_memory_stats()

    save_metadata = {save_metadata}

    # Write metadata receipt sidecar if enabled
    if save_metadata and metadata_path:
        receipt = f\"\"\"OpenVINO Image Generation Receipt
============================================================
Image File       : {{Path(target_path).name}}
Model Type       : {{'FLUX.1-schnell INT4' if is_flux else 'Stable Diffusion 1.5 INT8'}}
Model Path       : {{model_path}}
Device           : {{device}}
Resolution       : {{width}}x{{height}}
Steps            : {{steps}}
Seed             : {{seed}}

Prompt:
{{prompt}}

Generation Start : {{start_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}}
Generation Stop  : {{end_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}}
Load Time        : {{load_time:.2f}}s
Inference Time   : {{gen_time:.2f}}s
Total Time       : {{time.time() - t0:.2f}}s

RAM (Process RSS):
- Before Load    : {{ram_before_load:.2f}} GB
- After Load     : {{ram_after_load:.2f}} GB
- After Gen      : {{ram_after_gen:.2f}} GB
- After Save     : {{ram_after_save:.2f}} GB

GPU Memory Stats : {{gpu_stats}}
============================================================
\"\"\"
        with open(metadata_path, "w", encoding="utf-8") as f:
            f.write(receipt)

    print(json.dumps({{
        "status": "success",
        "model": "flux" if is_flux else "sd1.5",
        "load_time_sec": round(load_time, 2),
        "gen_time_sec": round(gen_time, 2),
        "total_time_sec": round(time.time() - t0, 2),
        "ram_peak_gb": round(max(ram_after_load, ram_after_gen, ram_after_save), 2),
        "seed": seed,
        "width": width,
        "height": height
    }}))

except Exception as e:
    print(json.dumps({{
        "status": "error",
        "error": str(e)
    }}))
    sys.exit(1)
"""
    python_exe = str(SD_PYTHON_PATH) if SD_PYTHON_PATH.exists() else sys.executable
    cmd = [python_exe, "-c", py_code]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=300
    )

    if proc.returncode != 0 or not target_path.exists():
        err_msg = proc.stderr.strip() or proc.stdout.strip() or "Subprocess failed to generate image."
        return {"status": "error", "error": err_msg}

    try:
        lines = [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
        for line in reversed(lines):
            if line.startswith("{") and line.endswith("}"):
                return json.loads(line)
        return {"status": "success", "total_time_sec": 0}
    except Exception:
        return {"status": "success", "total_time_sec": 0}


def handle_generate_image(params: Dict[str, Any], action_id: str) -> Dict[str, Any]:
    """
    Handles image generation requests from Thersites's inner cognitive loop.
    Supports model="sd1.5" (default) or model="flux".
    Respects config toggles for telemetry receipts and resolution/filesize guardrails.
    """
    prompt = params.get("prompt", params.get("description", "")).strip()
    if not prompt:
        return {
            "id": action_id,
            "tool": "generate_image",
            "status": "error",
            "result": "Missing required 'prompt' parameter describing the image to generate."
        }

    filename = params.get("filename") or params.get("filepath")
    if not filename:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"image_{timestamp}.png"

    clean_name = os.path.basename(str(filename))
    if not clean_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        clean_name += ".png"

    target_path = SANDBOX_DIR / clean_name
    metadata_name = Path(clean_name).stem + ".txt"
    metadata_path = SANDBOX_DIR / metadata_name if IMAGE_GEN_METADATA_RECEIPT else None

    relative_path = f"sandbox/{clean_name}"
    web_url = f"/sandbox/{clean_name}"

    model_type = str(params.get("model", "sd1.5")).lower()
    is_flux = "flux" in model_type
    steps = params.get("steps", params.get("num_inference_steps"))
    steps = int(steps) if steps is not None else None

    seed = params.get("seed", params.get("rng_seed"))
    if seed is not None:
        try:
            seed = int(seed)
        except Exception:
            seed = None

    # Enforce safe dimension limits
    raw_width = params.get("width")
    width = min(int(raw_width), IMAGE_MAX_DIMENSION) if raw_width is not None else (768 if is_flux else 512)

    raw_height = params.get("height")
    height = min(int(raw_height), IMAGE_MAX_DIMENSION) if raw_height is not None else (768 if is_flux else 512)

    negative_prompt = params.get("negative_prompt", "blurry, low quality, distorted, bad anatomy")
    device = str(params.get("device", SD_DEVICE)).upper()

    engine_label = "FLUX.1-schnell" if is_flux else "Stable Diffusion 1.5"
    log_main(f"[SUBAGENT: Image Generator] {INDICATOR_THINKING} Generating {engine_label} image ({width}x{height}) on {device} for: '{prompt[:60]}...'")

    try:
        res = _generate_via_subprocess(
            prompt=prompt,
            target_path=target_path,
            metadata_path=metadata_path,
            model_type=model_type,
            negative_prompt=negative_prompt,
            steps=steps,
            seed=seed,
            width=width,
            height=height,
            device=device,
            save_metadata=IMAGE_GEN_METADATA_RECEIPT
        )

        if res.get("status") != "success" or not target_path.exists():
            err = res.get("error", "Failed to generate image file.")
            log_main(f"[SUBAGENT: Image Generator] {INDICATOR_BLOCKED} Generation error: {err}")
            return {
                "id": action_id,
                "tool": "generate_image",
                "status": "error",
                "result": f"Image generation failed: {err}"
            }

        file_size_kb = round(os.path.getsize(target_path) / 1024, 1)
        tot_time = res.get("total_time_sec", "N/A")
        peak_ram = res.get("ram_peak_gb", "N/A")
        used_seed = res.get("seed", seed or 42)

        meta_info = f" with metadata in 'sandbox/{metadata_name}'" if IMAGE_GEN_METADATA_RECEIPT else ""
        result_msg = (
            f"Successfully generated {engine_label} image ({file_size_kb} KB in {tot_time}s, peak RAM: {peak_ram} GB, seed: {used_seed}) for: '{prompt}'. "
            f"Saved to '{relative_path}'{meta_info}. Web URL: '{web_url}'."
        )
        log_main(f"[SUBAGENT: Image Generator] {INDICATOR_DONE} {result_msg}")

        out_dict = {
            "id": action_id,
            "tool": "generate_image",
            "status": "success",
            "result": result_msg,
            "filepath": str(target_path).replace("\\", "/"),
            "url": web_url,
            "markdown": f"![{prompt}]({web_url})"
        }
        if IMAGE_GEN_METADATA_RECEIPT and metadata_path:
            out_dict["metadata_path"] = str(metadata_path).replace("\\", "/")

        return out_dict

    except Exception as e:
        log_main(f"[SUBAGENT: Image Generator] {INDICATOR_BLOCKED} Exception: {str(e)}")
        return {
            "id": action_id,
            "tool": "generate_image",
            "status": "error",
            "result": f"Image generator error: {str(e)}"
        }
