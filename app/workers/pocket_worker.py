"""Pocket TTS worker (Kyutai). Runs in envs\\lite on the CPU: 100M parameters,
loads in a few seconds. Uses the preset voices whose licences allow commercial
use. Cloning a voice profile needs Kyutai's voice-cloning weights, which each
user has to accept on Hugging Face themselves, so it is not switched on here."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proto  # noqa: E402

MODELS = os.environ["VOICESTUDIO_MODELS"]
_proto.offline(MODELS)
# Only voices released as CC0 or CC BY 4.0 (the Expresso and EARS voices are non-commercial and left out).
VOICES = ["alba", "marius", "javert", "anna", "vera", "fantine", "charles", "paul", "eponine", "azelma", "george",
          "mary", "jane", "michael", "eve", "bill_boerst", "peter_yearsley", "stuart_bell", "caro_davy"]
S = {"model": None, "states": {}}


def load(req):
    _proto.step("importing pocket_tts")
    from pocket_tts import TTSModel
    S["model"] = TTSModel.load_model()
    _proto.step("pocket tts loaded; " + _proto.mem_note())
    return {"detail": "Ready on the CPU (no graphics memory used)", "sr": int(S["model"].sample_rate)}


def synth(req):
    import soundfile as sf
    m = S["model"]
    voice = req.get("voice") or "alba"
    if voice not in VOICES:
        raise RuntimeError(f"Unknown Pocket TTS voice {voice}")
    if voice not in S["states"]:
        S["states"][voice] = m.get_state_for_audio_prompt(voice)
    a = m.generate_audio(S["states"][voice], req["text"]).detach().cpu().numpy()
    sf.write(req["out"], a, int(m.sample_rate), subtype="PCM_16")
    return {"sr": int(m.sample_rate)}


if __name__ == "__main__":
    _proto.serve({"load": load, "synth": synth})
