"""Maverick DevOS - Local Neural TTS Model Downloader.

Downloads Pocket TTS Indonesian (6-layer student model) and reference voice prompts
into the dedicated model cache: ~/.local/share/maverick/models/tts/pocket-tts-indonesian/
"""

import os
import sys
import time
import urllib.request

MODEL_DIR = os.path.expanduser("~/.local/share/maverick/models/tts/pocket-tts-indonesian")
VOICES_DIR = os.path.join(MODEL_DIR, "voices")

FILES = [
    ("indonesian_6l.yaml", "https://huggingface.co/anak10thn/pocket-tts-indonesian/raw/main/indonesian_6l.yaml"),
    ("tokenizer.model", "https://huggingface.co/anak10thn/pocket-tts-indonesian/resolve/main/tokenizer.model"),
    ("6l/model.safetensors", "https://huggingface.co/anak10thn/pocket-tts-indonesian/resolve/main/6l/model.safetensors"),
    ("voices/common_voice_id_19961910.mp3", "https://huggingface.co/anak10thn/pocket-tts-indonesian/resolve/main/voices/common_voice_id_19961910.mp3"),
    ("voices/common_voice_id_20954552.mp3", "https://huggingface.co/anak10thn/pocket-tts-indonesian/resolve/main/voices/common_voice_id_20954552.mp3"),
    ("voices/common_voice_id_20954811.mp3", "https://huggingface.co/anak10thn/pocket-tts-indonesian/resolve/main/voices/common_voice_id_20954811.mp3"),
    ("voices/common_voice_id_22918082.mp3", "https://huggingface.co/anak10thn/pocket-tts-indonesian/resolve/main/voices/common_voice_id_22918082.mp3"),
]


def download_file(rel_path: str, url: str) -> bool:
    dest_path = os.path.join(MODEL_DIR, rel_path)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        # Check if remote size matches
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                remote_size = int(resp.headers.get("Content-Length", 0))
                local_size = os.path.getsize(dest_path)
                if remote_size > 0 and local_size == remote_size:
                    print(f"[CACHE HIT] {rel_path} already complete ({local_size / (1024*1024):.1f} MB)")
                    return True
        except Exception:
            pass

    print(f"[DOWNLOADING] {rel_path} from {url}...")
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    tmp_path = dest_path + ".tmp"
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_path, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = (downloaded / total) * 100
                    mb = downloaded / (1024 * 1024)
                    tot_mb = total / (1024 * 1024)
                    print(f"\r  -> {rel_path}: {mb:.1f}/{tot_mb:.1f} MB ({pct:.1f}%)", end="", flush=True)

        os.replace(tmp_path, dest_path)
        elapsed = round(time.time() - t0, 1)
        print(f"\n[DONE] {rel_path} saved ({os.path.getsize(dest_path) / (1024*1024):.1f} MB in {elapsed}s)")
        return True
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"\n[ERROR] Failed to download {rel_path}: {e}")
        return False


def main():
    print(f"=== Downloading Pocket TTS Indonesian Model to {MODEL_DIR} ===")
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(VOICES_DIR, exist_ok=True)

    success_count = 0
    for rel_path, url in FILES:
        if download_file(rel_path, url):
            success_count += 1

    print(f"\nSummary: {success_count}/{len(FILES)} files ready in {MODEL_DIR}")
    return 0 if success_count == len(FILES) else 1


if __name__ == "__main__":
    sys.exit(main())

