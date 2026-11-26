"""Setup only: download the Kokoro model files into models\\hf_cache by loading
the model and each offered voice once."""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
MODELS = os.environ["VOICESTUDIO_MODELS"]
os.environ["VOICESTUDIO_FETCH"] = "1"
import _proto  # noqa: E402

_proto.offline(MODELS)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.makedirs(os.path.join(MODELS, "lite"), exist_ok=True)
LOG = os.path.join(MODELS, "fetch_lite.log")
failed = []


def step(title, fn, marker):
    if os.path.exists(os.path.join(MODELS, "lite", marker)):
        print(title + ": already in place", flush=True)
        return
    print(title, flush=True)
    for attempt in (1, 2):
        try:
            fn()
            open(os.path.join(MODELS, "lite", marker), "w").write("ok")
            return
        except Exception:
            err = traceback.format_exc()
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(f"\n===== {title} (try {attempt})\n{err}\n")
    failed.append(title)
    print(f"  FAILED: {title}. Details in {LOG}", flush=True)
    print(err, flush=True)


def kokoro():
    import kokoro_worker as k
    for v in k.VOICES:
        pipe = k._pipe("b" if v[0] == "b" else "a")
        pipe.load_voice(v)
    list(k._pipe("a")("Ready.", voice="af_heart"))


step("Kokoro model and voices (about 330 MB)", kokoro, "kokoro.ok")
if failed:
    print("Not finished: " + "; ".join(failed))
    sys.exit(1)
print("Kokoro model files are in place.")
sys.exit(0)
