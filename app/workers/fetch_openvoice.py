"""Setup only: download everything the OpenVoice worker needs into models\\."""
import os
import sys

MODELS = os.environ["VOICESTUDIO_MODELS"]
os.environ["HF_HOME"] = os.path.join(MODELS, "hf_cache")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
from huggingface_hub import hf_hub_download, snapshot_download  # noqa: E402

ov = os.path.join(MODELS, "openvoice")
melo = os.path.join(MODELS, "melo", "EN")
nltk_dir = os.path.join(MODELS, "nltk_data")
for d in (ov, melo, nltk_dir):
    os.makedirs(d, exist_ok=True)

print("OpenVoice tone colour converter", flush=True)
for f in ["converter/config.json", "converter/checkpoint.pth"] + \
        [f"base_speakers/ses/{n}.pth" for n in ["en-us", "en-br", "en-au", "en-default", "en-india"]]:
    if not os.path.exists(os.path.join(ov, f)):
        hf_hub_download("myshell-ai/OpenVoiceV2", f, local_dir=ov)
print("MeloTTS English voices", flush=True)
for f in ["config.json", "checkpoint.pth"]:
    if not os.path.exists(os.path.join(melo, f)):
        hf_hub_download("myshell-ai/MeloTTS-English", f, local_dir=melo)
print("English text model (bert-base-uncased)", flush=True)
snapshot_download("bert-base-uncased", allow_patterns=["config.json", "tokenizer*", "vocab.txt", "model.safetensors"])
print("OpenVoice watermark model", flush=True)
snapshot_download("M4869/WavMark")
print("Pronunciation data", flush=True)
import nltk  # noqa: E402
for pkg in ["averaged_perceptron_tagger", "cmudict"]:
    nltk.download(pkg, download_dir=nltk_dir, quiet=True)
print("OpenVoice model files are in place.")
sys.exit(0)
