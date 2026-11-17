"""OpenVoice v2 worker. Runs in envs\\openvoice.

1. MeloTTS speaks the sentence with an English base voice (the accent).
2. The OpenVoice tone colour converter gives it the tone of the voice profile.
OpenVoice's own audio watermark is left switched on."""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proto  # noqa: E402

MODELS = os.environ["VOICESTUDIO_MODELS"]
_proto.offline(MODELS)
OV = os.path.join(MODELS, "openvoice")
MELO = os.path.join(MODELS, "melo", "EN")
# accent id -> (MeloTTS speaker name, OpenVoice base speaker embedding file)
ACCENTS = {"EN-US": "en-us", "EN-BR": "en-br", "EN-AU": "en-au", "EN-Default": "en-default", "EN_INDIA": "en-india"}
S = {"tts": None, "conv": None, "se": {}, "src": {}}


def _english_only_melo():
    """MeloTTS imports every language at start-up (Japanese, Korean, Chinese...),
    each with heavy extra packages and downloads. Only English is used here, so
    the other language modules are replaced by empty stand-ins."""
    import melo.text as mt

    def distribute_phone(n_phone, n_word):
        per = [0] * n_word
        for _ in range(n_phone):
            per[per.index(min(per))] += 1
        return per

    for name in ["chinese", "japanese", "chinese_mix", "korean", "french", "spanish",
                 "chinese_bert", "japanese_bert", "spanish_bert", "french_bert"]:
        mod = types.ModuleType(f"melo.text.{name}")
        mod.get_bert_feature = None
        mod.distribute_phone = distribute_phone
        sys.modules[f"melo.text.{name}"] = mod
        setattr(mt, name, mod)


def _light_text_helpers():
    """OpenVoice imports 'unidecode' for its older V1 text front end, which is
    not used here (MeloTTS handles the text). A pass-through stand-in avoids
    installing that extra package."""
    if "unidecode" not in sys.modules:
        try:
            import unidecode  # noqa: F401
        except ImportError:
            mod = types.ModuleType("unidecode")
            mod.unidecode = lambda s: s
            sys.modules["unidecode"] = mod


def load(req):
    import torch
    _light_text_helpers()
    for p in [os.path.join(OV, "converter", "checkpoint.pth"), os.path.join(MELO, "checkpoint.pth")]:
        if not os.path.exists(p):
            raise RuntimeError("OpenVoice model files are missing. Run Setup.bat.")
    _english_only_melo()
    from melo.api import TTS
    from openvoice.api import ToneColorConverter
    dev = _proto.device()
    _proto.step("melo and openvoice imported; " + _proto.gpu_note())
    S["tts"] = TTS(language="EN", device=dev, config_path=os.path.join(MELO, "config.json"),
                   ckpt_path=os.path.join(MELO, "checkpoint.pth"))
    _proto.step("MeloTTS loaded")
    S["conv"] = ToneColorConverter(os.path.join(OV, "converter", "config.json"), device=dev)
    S["conv"].load_ckpt(os.path.join(OV, "converter", "checkpoint.pth"))
    for acc, f in ACCENTS.items():
        S["src"][acc] = torch.load(os.path.join(OV, "base_speakers", "ses", f + ".pth"), map_location=dev)
    _proto.step("converter loaded; " + _proto.gpu_note())
    return {"detail": f"Warm on {_proto.device_name()}", "sr": int(S["tts"].hps.data.sampling_rate),
            "accents": list(S["tts"].hps.data.spk2id.keys())}


def _target_se(ref):
    """Tone colour of the voice profile, worked out once per reference file."""
    key = (ref, os.path.getmtime(ref))
    if key not in S["se"]:
        S["se"].clear()
        S["se"][key] = S["conv"].extract_se([ref])
    return S["se"][key]


def synth(req):
    import torch
    tts, conv = S["tts"], S["conv"]
    acc = req.get("accent") or "EN-US"
    if acc not in ACCENTS:
        raise RuntimeError(f"Unknown accent {acc}")
    spk = tts.hps.data.spk2id[acc]
    out = req["out"]
    ref = req.get("ref") or None
    base = out + ".base.wav" if ref else out
    with torch.inference_mode():
        tts.tts_to_file(req["text"], spk, base, speed=float(req.get("speed", 1.0)), quiet=True)
        if ref:
            conv.convert(audio_src_path=base, src_se=S["src"][acc], tgt_se=_target_se(ref),
                         output_path=out, message="@MyShell")
            os.remove(base)
            return {"sr": int(conv.hps.data.sampling_rate)}
    return {"sr": int(tts.hps.data.sampling_rate)}


if __name__ == "__main__":
    _proto.serve({"load": load, "synth": synth})
