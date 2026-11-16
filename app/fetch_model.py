"""Used by Setup only: put the YarnGPT2 model inside this folder (models/hf) so
the app never needs the internet to load it. Reuses a copy already on this PC
when there is one; otherwise downloads it once from Hugging Face."""
import os
import shutil
import sys

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
from .paths import MODELS  # noqa: E402

HF_ID = "saheedniyi/YarnGPT2"
PATTERNS = ["*.json", "*.safetensors", "*.txt", "*.model"]


def have(d):
    return (d / "config.json").exists() and any(d.glob("*.safetensors"))


def main():
    dest = MODELS / "hf" / "YarnGPT2"
    if have(dest):
        print("YarnGPT2 model already in place.")
        return 0
    from huggingface_hub import snapshot_download
    dest.mkdir(parents=True, exist_ok=True)
    try:
        src = snapshot_download(HF_ID, local_files_only=True, allow_patterns=PATTERNS)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        if have(dest):
            print("Copied the YarnGPT2 model that was already on this PC.")
            return 0
    except Exception:
        pass
    print("Downloading the YarnGPT2 model from Hugging Face (about 750 MB, one time)...")
    snapshot_download(HF_ID, local_dir=str(dest), allow_patterns=PATTERNS)
    return 0 if have(dest) else 1


if __name__ == "__main__":
    sys.exit(main())
