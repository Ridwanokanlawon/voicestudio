"""Chatterbox worker. Runs in envs\\chatterbox. Voice cloning from a reference
recording. The built-in Perth watermark is part of generate() and stays on."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proto  # noqa: E402

MODELS = os.environ["VOICESTUDIO_MODELS"]
_proto.offline(MODELS)
S = {"model": None, "default_conds": None, "ref": None, "ex": None}
FILES = ["ve.safetensors", "t3_cfg.safetensors", "s3gen.safetensors", "tokenizer.json", "conds.pt"]


def lean_load(d, dev):
    """Same result as ChatterboxTTS.from_local, but each weight file is read
    straight onto the target device and released before the next one, so the
    PC's memory never has to hold two copies of the model at once."""
    import gc
    from pathlib import Path

    import chatterbox.tts as ct
    import torch
    from safetensors.torch import load_file
    d = Path(d)

    def fill(module, name, strict=True):
        state = load_file(str(d / name), device=dev)
        if "model" in state:
            state = state["model"][0]
        module.load_state_dict(state, strict=strict, assign=True)
        del state
        gc.collect()
        return module.to(dev).eval()

    ve = fill(ct.VoiceEncoder(), "ve.safetensors")
    _proto.step("voice encoder ready; " + _proto.mem_note())
    t3 = fill(ct.T3(), "t3_cfg.safetensors")
    _proto.step("text model ready; " + _proto.mem_note())
    s3gen = fill(ct.S3Gen(), "s3gen.safetensors", strict=False)
    _proto.step("speech model ready; " + _proto.mem_note())
    tok = ct.EnTokenizer(str(d / "tokenizer.json"))
    conds = None
    if (d / "conds.pt").exists():
        conds = ct.Conditionals.load(d / "conds.pt", map_location=torch.device("cpu") if dev == "cpu" else None).to(dev)
    return ct.ChatterboxTTS(t3, s3gen, ve, tok, dev, conds=conds)


def load(req):
    _proto.step("importing chatterbox")
    from chatterbox.tts import ChatterboxTTS
    d = os.path.join(MODELS, "chatterbox")
    missing = [f for f in FILES if not os.path.exists(os.path.join(d, f))]
    if missing:
        raise RuntimeError("Chatterbox model files are missing. Run Setup.bat.")
    _proto.step("chatterbox imported; " + _proto.gpu_note())
    dev = _proto.device()
    if os.environ.get("VOICESTUDIO_PLAIN_LOAD") == "1":
        S["model"] = ChatterboxTTS.from_local(d, dev)
    else:
        try:
            S["model"] = lean_load(d, dev)
        except Exception as e:                  # fall back to the library's own loader
            _proto.step(f"lean load failed ({type(e).__name__}: {e}); using the standard loader")
            S["model"] = ChatterboxTTS.from_local(d, dev)
    S["default_conds"] = S["model"].conds
    _proto.step("model loaded; " + _proto.gpu_note() + "; " + _proto.mem_note())
    return {"detail": f"Warm on {_proto.device_name()}", "sr": S["model"].sr}


def synth(req):
    import soundfile as sf
    import torch
    m = S["model"]
    ex = float(req.get("exaggeration", 0.5))
    cfg = float(req.get("cfg_weight", 0.5))
    ref = req.get("ref") or None
    with torch.inference_mode():
        if ref:
            if ref != S["ref"] or ex != S["ex"]:      # only re-read the reference when it changes
                m.prepare_conditionals(ref, exaggeration=ex)
                S["ref"], S["ex"] = ref, ex
        else:
            m.conds = S["default_conds"]
            S["ref"] = None
        wav = m.generate(req["text"], exaggeration=ex, cfg_weight=cfg)   # watermark applied inside
    a = wav.squeeze().detach().cpu().numpy()
    sf.write(req["out"], a, m.sr, subtype="PCM_16")
    return {"sr": m.sr}


if __name__ == "__main__":
    _proto.serve({"load": load, "synth": synth})
