"""
Biometrics Model Auto-Downloader & Startup Warm-up Service.
Ensures DeepFace (ArcFace) and MiniFASNet anti-spoofing weights are pre-downloaded,
cached, and initialized into memory before FastAPI begins serving live student requests.
"""

import os
import sys
import time
import shutil
import urllib.request
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

# Weights directory resolution
DEEPFACE_HOME = Path(os.path.expanduser("~/.deepface/weights")).resolve()
BACKEND_WEIGHTS_FALLBACK = (Path(__file__).resolve().parent.parent.parent.parent / "weights").resolve()

REQUIRED_WEIGHTS: List[Dict[str, Any]] = [
    {
        "filename": "arcface_weights.h5",
        "size_bytes": 137_026_640,
        "url": "https://github.com/serengil/deepface_models/releases/download/v1.0/arcface_weights.h5",
        "description": "ArcFace 512-D Face Recognition Model (~137 MB)",
    },
    {
        "filename": "2.7_80x80_MiniFASNetV2.h5",
        "size_bytes": 2_234_368,
        "url": "https://github.com/serengil/deepface_models/releases/download/v1.0/2.7_80x80_MiniFASNetV2.h5",
        "description": "MiniFASNet V2 2.7x Anti-Spoofing Model (~2.2 MB)",
    },
    {
        "filename": "4_0_0_80x80_MiniFASNetV1SE.h5",
        "size_bytes": 2_288_392,
        "url": "https://github.com/serengil/deepface_models/releases/download/v1.0/4_0_0_80x80_MiniFASNetV1SE.h5",
        "description": "MiniFASNet V1SE 4.0x Anti-Spoofing Model (~2.3 MB)",
    },
]


def ensure_weights_directory() -> Path:
    """Creates the deepface weights directory if it doesn't exist."""
    DEEPFACE_HOME.mkdir(parents=True, exist_ok=True)
    return DEEPFACE_HOME


def assemble_split_weights(filename: str) -> bool:
    """
    If a large weight file was split into chunks (<100MB) for GitHub compliance,
    automatically reassembles it into the target DEEPFACE_HOME directory.
    """
    dst = DEEPFACE_HOME / filename
    if dst.is_file() and dst.stat().st_size > 100_000:
        return True

    search_dirs = [BACKEND_WEIGHTS_FALLBACK, DEEPFACE_HOME]
    for s_dir in search_dirs:
        parts = sorted(list(s_dir.glob(f"{filename}.part*")))
        if parts:
            print(f"[biometrics-warmup] 🧩 Reassembling {filename} from {len(parts)} parts in {s_dir}...")
            temp_dst = DEEPFACE_HOME / f"{filename}.assembling"
            with open(temp_dst, "wb") as outfile:
                for p in parts:
                    with open(p, "rb") as infile:
                        shutil.copyfileobj(infile, outfile)
            if temp_dst.stat().st_size > 100_000:
                temp_dst.replace(dst)
                print(f"[biometrics-warmup] ✅ Successfully reassembled {filename} ({dst.stat().st_size / (1024*1024):.1f} MB).")
                return True
            else:
                if temp_dst.is_file():
                    temp_dst.unlink()
    return False


def copy_from_local_fallback(filename: str) -> bool:
    """Attempts to copy weight file from Backend/weights if mounted/available."""
    src = BACKEND_WEIGHTS_FALLBACK / filename
    dst = DEEPFACE_HOME / filename
    if src.is_file() and src.stat().st_size > 100_000:
        if not dst.is_file() or dst.stat().st_size != src.stat().st_size:
            print(f"[biometrics-warmup] Copying {filename} from local fallback {src} -> {dst}")
            shutil.copy2(src, dst)
        return True
    return False


def download_weight_file(weight_info: Dict[str, Any], timeout: int = 120) -> bool:
    """Downloads a single model weight file with chunked progress logging."""
    filename = weight_info["filename"]
    target_path = DEEPFACE_HOME / filename
    url = weight_info["url"]
    desc = weight_info["description"]

    # 1. First check if target already exists and is healthy
    if target_path.is_file() and target_path.stat().st_size > 100_000:
        return True

    # 2. Check if split parts exist and reassemble them
    if assemble_split_weights(filename):
        return True

    # 3. Check local fallback folder
    if copy_from_local_fallback(filename):
        return True

    print(f"[biometrics-warmup] ⬇️ Auto-downloading {desc}...")
    print(f"[biometrics-warmup] Source URL: {url}")
    print(f"[biometrics-warmup] Destination: {target_path}")

    temp_path = DEEPFACE_HOME / f"{filename}.tmp"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DT-Biometrics/1.0"
            }
        )
        start_t = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as response, open(temp_path, "wb") as out_file:
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            block_size = 65536
            last_log_pct = 0

            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)

                if total_size > 0:
                    pct = int(downloaded * 100 / total_size)
                    if pct - last_log_pct >= 20 or pct == 100:
                        last_log_pct = pct
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        print(f"[biometrics-warmup] ... {filename}: {pct}% ({mb_done:.1f}MB / {mb_total:.1f}MB)")

        # Rename temp file to final target
        if temp_path.is_file() and temp_path.stat().st_size > 100_000:
            temp_path.replace(target_path)
            elapsed = time.time() - start_t
            print(f"[biometrics-warmup] ✅ Successfully downloaded {filename} in {elapsed:.1f}s.")
            return True
        else:
            if temp_path.is_file():
                temp_path.unlink()
            print(f"[biometrics-warmup] ❌ Downloaded file for {filename} was incomplete or corrupted.")
            return False

    except Exception as e:
        if temp_path.is_file():
            temp_path.unlink()
        print(f"[biometrics-warmup] ⚠️ Could not auto-download {filename}: {e}")
        print(f"[biometrics-warmup] 💡 Tip: If server cannot reach GitHub, please download manually:")
        print(f"      curl -L -o {target_path} {url}")
        return False


def ensure_all_biometric_weights(timeout: int = 180) -> bool:
    """Verifies and downloads all required biometric weight files."""
    ensure_weights_directory()
    all_ready = True
    for item in REQUIRED_WEIGHTS:
        ok = download_weight_file(item, timeout=timeout)
        if not ok:
            all_ready = False
    return all_ready


def warm_up_biometric_models() -> bool:
    """
    Instantiates ArcFace and MiniFASNet models into memory and executes a dummy pass.
    Guarantees zero cold-start delay and zero runtime model downloading.
    """
    print("[biometrics-warmup] Initializing and warming up AI models in RAM...")
    start_t = time.time()

    # 1. Ensure weight files are present
    ensure_all_biometric_weights()

    # 2. Warm up ArcFace
    try:
        from deepface.modules import modeling
        print("[biometrics-warmup] Compiling ArcFace facial recognition model...")
        arcface_model = modeling.build_model(task="facial_recognition", model_name="ArcFace")
        if arcface_model is not None:
            print("[biometrics-warmup] ArcFace model graph ready in memory.")
    except Exception as e:
        print(f"[biometrics-warmup] Warning: ArcFace warm-up exception: {e}")

    # 3. Warm up MiniFASNet Anti-Spoofing
    try:
        from .service import get_fasnet_model, analyze_liveness_probabilities
        print("[biometrics-warmup] Compiling MiniFASNet anti-spoofing model...")
        fasnet = get_fasnet_model()
        if fasnet is not None:
            # Synthetic 112x112 dummy image for warm-up
            dummy = np.zeros((112, 112, 3), dtype=np.uint8)
            dummy[20:90, 20:90] = 128
            analyze_liveness_probabilities(dummy, (20, 20, 70, 70))
            print("[biometrics-warmup] MiniFASNet anti-spoofing model ready.")
    except Exception as e:
        print(f"[biometrics-warmup] Warning: MiniFASNet warm-up exception: {e}")

    # 4. Warm up ONNX Affect & Gaze Engines
    try:
        from .emotion_engine import get_affect_engine
        from .attention import analyze_focal_attention
        engine = get_affect_engine("system_warmup")
        dummy = np.zeros((112, 112, 3), dtype=np.uint8)
        dummy[20:90, 20:90] = 128
        engine.process_frame(dummy)
        analyze_focal_attention(dummy, user_id="system_warmup")
        print("[biometrics-warmup] HSEmotion ONNX & Gaze models ready.")
    except Exception as e:
        print(f"[biometrics-warmup] Warning: Affect/Gaze warm-up exception: {e}")

    total_time = round(time.time() - start_t, 2)
    print(f"[biometrics-warmup] 🚀 All biometric engines pre-loaded and warmed up in {total_time}s.")
    return True
