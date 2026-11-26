"""Qwen3-TTS worker (Alibaba Qwen, Apache-2.0). Runs in envs\\qwen. Uses the
CustomVoice model: nine preset voices, with an optional delivery instruction.
On an NVIDIA graphics card it runs in half precision (about 5 GB of graphics
memory for the 1.7B model); without one it runs on the CPU, slowly."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _proto  # noqa: E402

MODELS = os.environ["VOICESTUDIO_MODELS"]
_proto.offline(MODELS)
REPO = os.environ.get("VOICESTUDIO_QWEN_MODEL") or "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
VOICES = ["ryan", "aiden", "serena", "vivian", "uncle_fu", "sohee", "ono_anna", "dylan", "eric"]
S = {"model": None}


def local_dir():
    """The model folder inside models\\hf_cache (never the network at run time)."""
    from huggingface_hub import snapshot_download
    return snapshot_download(REPO, local_files_only=True)


def load(req):
    _proto.step("importing torch and qwen_tts; " + _proto.gpu_note())
    import torch
    from qwen_tts import Qwen3TTSModel
    cuda = torch.cuda.is_available()
    kw = {"device_map": "cuda:0", "dtype": torch.bfloat16} if cuda else {"device_map": "cpu", "dtype": torch.float32}
    _proto.step(f"loading {REPO} on {'the graphics card' if cuda else 'the CPU'}")
    S["model"] = Qwen3TTSModel.from_pretrained(local_dir(), **kw)
    _proto.step("qwen3-tts loaded; " + _proto.mem_note() + "; " + _proto.gpu_note())
    return {"detail": f"Ready on {_proto.device_name()}", "sr": 24000}


def synth(req):
    import numpy as np
    import soundfile as sf
    voice = (req.get("voice") or "ryan").lower()
    if voice not in VOICES:
        raise RuntimeError(f"Unknown Qwen3-TTS voice {voice}")
    words = max(1, len(req["text"].split()))
    # The model writes 12.5 audio tokens per second. Cap the length by the text, so a sentence that
    # fails to stop cannot run for minutes and exhaust memory (the default limit is 164 seconds).
    kw = {"text": req["text"], "language": "English", "speaker": voice,
          "max_new_tokens": int(12.5 * (6 + 1.1 * words))}
    if req.get("instruct"):
        kw["instruct"] = req["instruct"]
    wavs, sr = S["model"].generate_custom_voice(**kw)
    a = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
    if not a.size:
        raise RuntimeError("Qwen3-TTS returned no audio for this sentence.")
    sf.write(req["out"], a, int(sr), subtype="PCM_16")
    return {"sr": int(sr)}


if __name__ == "__main__":
    _proto.serve({"load": load, "synth": synth})
