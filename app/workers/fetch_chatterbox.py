"""Setup only: download the Chatterbox English weights into models\\chatterbox."""
import os
import sys

MODELS = os.environ["VOICESTUDIO_MODELS"]
from huggingface_hub import hf_hub_download  # noqa: E402

d = os.path.join(MODELS, "chatterbox")
os.makedirs(d, exist_ok=True)
for f in ["ve.safetensors", "t3_cfg.safetensors", "s3gen.safetensors", "tokenizer.json", "conds.pt"]:
    if not os.path.exists(os.path.join(d, f)):
        print("Downloading", f, flush=True)
        hf_hub_download("ResembleAI/chatterbox", f, local_dir=d)
print("Chatterbox model files are in place.")
sys.exit(0)
