"""Setup only: download the Qwen3-TTS model files into models\\hf_cache."""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
MODELS = os.environ["VOICESTUDIO_MODELS"]
os.environ["VOICESTUDIO_FETCH"] = "1"
import _proto  # noqa: E402

_proto.offline(MODELS)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
REPO = os.environ.get("VOICESTUDIO_QWEN_MODEL") or "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
d = os.path.join(MODELS, "qwen")
os.makedirs(d, exist_ok=True)
marker = os.path.join(d, REPO.split("/")[-1] + ".ok")
if os.path.exists(marker):
    print("Qwen3-TTS model files: already in place", flush=True)
    sys.exit(0)
from huggingface_hub import snapshot_download  # noqa: E402

err = ""
for attempt in (1, 2, 3):
    try:
        print(f"Downloading {REPO} (try {attempt})", flush=True)
        path = snapshot_download(REPO, allow_patterns=["*.json", "*.txt", "*.safetensors", "speech_tokenizer/*"])
        need = ["model.safetensors", os.path.join("speech_tokenizer", "model.safetensors"), "config.json"]
        missing = [n for n in need if not os.path.exists(os.path.join(path, n))]
        if missing:
            raise RuntimeError("files missing after download: " + ", ".join(missing))
        open(marker, "w").write("ok")
        print("Qwen3-TTS model files are in place.", flush=True)
        sys.exit(0)
    except Exception:
        err = traceback.format_exc()
        with open(os.path.join(MODELS, "fetch_qwen.log"), "a", encoding="utf-8") as f:
            f.write(f"\n===== try {attempt}\n{err}\n")
print("FAILED: the Qwen3-TTS model files did not download.", flush=True)
print(err, flush=True)
sys.exit(1)
