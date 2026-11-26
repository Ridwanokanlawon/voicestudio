"""Kokoro worker. Runs in envs\\lite on the CPU: small (82M parameters), loads
in seconds and leaves the graphics card and most of the PC's memory free.
Preset voices only (no voice cloning)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proto  # noqa: E402

MODELS = os.environ["VOICESTUDIO_MODELS"]
_proto.offline(MODELS)
REPO = "hexgrad/Kokoro-82M"
VOICES = ["af_heart", "af_bella", "af_nicole", "af_sarah", "am_michael", "am_fenrir", "am_puck", "am_adam",
          "bf_emma", "bf_isabella", "bm_george", "bm_fable", "bm_lewis"]
S = {"pipes": {}}


def _pipe(lang):
    if lang not in S["pipes"]:
        from kokoro import KPipeline
        S["pipes"][lang] = KPipeline(lang_code=lang, repo_id=REPO, device="cpu")
    return S["pipes"][lang]


def load(req):
    _proto.step("importing kokoro")
    _pipe("a")
    _proto.step("kokoro loaded; " + _proto.mem_note())
    return {"detail": "Ready on the CPU (no graphics memory used)", "sr": 24000}


def synth(req):
    import numpy as np
    import soundfile as sf
    voice = req.get("voice") or "af_heart"
    if voice not in VOICES:
        raise RuntimeError(f"Unknown Kokoro voice {voice}")
    pipe = _pipe("b" if voice[0] == "b" else "a")       # British voices use British pronunciation
    parts = [r.audio.detach().cpu().numpy() for r in pipe(req["text"], voice=voice, speed=float(req.get("speed", 1.0)))
             if r.audio is not None]
    if not parts:
        raise RuntimeError("Kokoro returned no audio for this sentence.")
    sf.write(req["out"], np.concatenate(parts), 24000, subtype="PCM_16")
    return {"sr": 24000}


if __name__ == "__main__":
    _proto.serve({"load": load, "synth": synth})
