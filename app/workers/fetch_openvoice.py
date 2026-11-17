"""Setup only: download everything the OpenVoice worker needs into models\\.
Each step is skipped when already done, and every error is written in full to
models\\fetch_openvoice.log so a failed download can be diagnosed."""
import os
import sys
import traceback

MODELS = os.environ["VOICESTUDIO_MODELS"]
os.environ["HF_HOME"] = os.path.join(MODELS, "hf_cache")
os.environ["NLTK_DATA"] = os.path.join(MODELS, "nltk_data")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ.pop("HF_HUB_OFFLINE", None)
os.environ.pop("TRANSFORMERS_OFFLINE", None)

ov = os.path.join(MODELS, "openvoice")
melo = os.path.join(MODELS, "melo", "EN")
nltk_dir = os.environ["NLTK_DATA"]
for d in (ov, melo, nltk_dir):
    os.makedirs(d, exist_ok=True)
LOG = os.path.join(MODELS, "fetch_openvoice.log")
failed = []


def step(title, fn):
    print(title, flush=True)
    try:
        fn()
        return
    except Exception:
        first = traceback.format_exc()
    try:                       # one more try: downloads resume where they stopped
        print("  retrying once", flush=True)
        fn()
    except Exception:
        failed.append(title)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n===== {title}\n{first}\n--- second try\n{traceback.format_exc()}\n")
        print(f"  FAILED: {title}. Details in {LOG}", flush=True)
        traceback.print_exc()


def converter():
    from huggingface_hub import hf_hub_download
    for f in ["converter/config.json", "converter/checkpoint.pth"] + \
            [f"base_speakers/ses/{n}.pth" for n in ["en-us", "en-br", "en-au", "en-default", "en-india"]]:
        if not os.path.exists(os.path.join(ov, f)):
            hf_hub_download("myshell-ai/OpenVoiceV2", f, local_dir=ov)


def melo_voices():
    from huggingface_hub import hf_hub_download
    for f in ["config.json", "checkpoint.pth"]:
        if not os.path.exists(os.path.join(melo, f)):
            hf_hub_download("myshell-ai/MeloTTS-English", f, local_dir=melo)


def bert():
    # loaded the same way MeloTTS loads it, so exactly the needed files are cached
    from transformers import AutoModelForMaskedLM, AutoTokenizer
    AutoTokenizer.from_pretrained("bert-base-uncased")
    AutoModelForMaskedLM.from_pretrained("bert-base-uncased")


def watermark():
    # loaded the same way OpenVoice loads it
    import wavmark
    wavmark.load_model()


def pronunciation():
    import nltk
    for pkg, where in [("averaged_perceptron_tagger", "taggers/averaged_perceptron_tagger"), ("cmudict", "corpora/cmudict")]:
        if not os.path.isdir(os.path.join(nltk_dir, *where.split("/"))):
            if not nltk.download(pkg, download_dir=nltk_dir, quiet=True):
                raise RuntimeError(f"NLTK could not download {pkg}")


step("OpenVoice tone colour converter (131 MB)", converter)
step("MeloTTS English voices (208 MB)", melo_voices)
step("English text model bert-base-uncased (440 MB)", bert)
step("OpenVoice watermark model", watermark)
step("Pronunciation data", pronunciation)
if failed:
    print("Not finished: " + "; ".join(failed))
    sys.exit(1)
print("OpenVoice model files are in place.")
sys.exit(0)
