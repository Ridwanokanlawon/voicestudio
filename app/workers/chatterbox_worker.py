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


def load(req):
    _proto.step("importing chatterbox")
    from chatterbox.tts import ChatterboxTTS
    d = os.path.join(MODELS, "chatterbox")
    missing = [f for f in FILES if not os.path.exists(os.path.join(d, f))]
    if missing:
        raise RuntimeError("Chatterbox model files are missing. Run Setup.bat.")
    _proto.step("chatterbox imported; " + _proto.gpu_note())
    S["model"] = ChatterboxTTS.from_local(d, _proto.device())
    S["default_conds"] = S["model"].conds
    _proto.step("model loaded; " + _proto.gpu_note())
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
