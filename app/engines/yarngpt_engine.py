"""YarnGPT: runs fully on this PC. The model is loaded once and kept warm.
Logic taken from the original tts.py."""
import importlib.util
import logging
import random
import sys
import threading

from ..paths import MODELS, ROOT, VENDOR
from .base import Engine, EngineError

log = logging.getLogger("voicestudio")
HF_ID = "saheedniyi/YarnGPT2"
CKPT = "wavtokenizer_large_speech_320_24k.ckpt"
YAML = "wavtokenizer_mediumdata_frame75_3s_nq1_code4096_dim512_kmeans200_attn.yaml"


def _import_yarngpt():
    for d in (VENDOR / "yarngpt", ROOT / "yarngpt", ROOT / "yarngpt-main"):
        if (d / "audiotokenizer.py").exists():
            spec = importlib.util.spec_from_file_location(
                "yarngpt", d / "__init__.py", submodule_search_locations=[str(d)])
            mod = importlib.util.module_from_spec(spec)
            sys.modules["yarngpt"] = mod
            spec.loader.exec_module(mod)
            return
    raise EngineError("YarnGPT code not found in vendor\\yarngpt. Run Setup.bat.")


class YarnGPT(Engine):
    id = "yarn"
    name = "YarnGPT"
    kind = "local"
    badge = "Local, no account"
    rate_note = "YarnGPT has no speed setting, so the speed is changed after generation (pitch is kept)."
    voices = [
        {"id": "idera", "label": "Idera", "note": "female"},
        {"id": "chinenye", "label": "Chinenye", "note": "female"},
        {"id": "jude", "label": "Jude", "note": "male"},
        {"id": "emma", "label": "Emma", "note": "male"},
        {"id": "umar", "label": "Umar", "note": "male"},
        {"id": "joke", "label": "Joke", "note": "female"},
        {"id": "zainab", "label": "Zainab", "note": "female"},
        {"id": "osagie", "label": "Osagie", "note": "male"},
        {"id": "remi", "label": "Remi", "note": "female"},
        {"id": "tayo", "label": "Tayo", "note": "male"},
    ]

    def __init__(self):
        self._state = "loading"
        self._detail = "Waiting to load"
        self._lock = threading.Lock()
        self.tok = None
        self.model = None

    def status(self):
        return {"state": self._state, "detail": self._detail}

    def load(self):
        try:
            self._detail = "Loading the YarnGPT model"
            ckpt, yaml = MODELS / CKPT, MODELS / YAML
            if not ckpt.exists() or not yaml.exists():
                raise EngineError("Model files are missing from the models folder. Run Setup.bat.")
            import torch
            _import_yarngpt()
            from transformers import AutoModelForCausalLM
            from yarngpt.audiotokenizer import AudioTokenizerV2
            local = MODELS / "hf" / "YarnGPT2"
            src = str(local) if (local / "config.json").exists() else HF_ID
            self.tok = AudioTokenizerV2(src, str(ckpt), str(yaml))
            self.model = AutoModelForCausalLM.from_pretrained(src, torch_dtype="auto").to(self.tok.device)
            self.model.eval()
            dev = str(self.tok.device)
            where = torch.cuda.get_device_name(0) if dev.startswith("cuda") else "CPU (slow, no NVIDIA GPU found)"
            self._state, self._detail = "ready", f"Warm on {where}"
        except Exception as e:  # shown in the UI, full trace in the log
            log.exception("YarnGPT failed to load")
            self._state = "error"
            self._detail = str(e) if isinstance(e, EngineError) else f"{type(e).__name__}: {e}"

    def synth(self, text, voice, *, rate=1.0, variation=False):
        if self._state != "ready":
            raise EngineError(f"YarnGPT is not ready: {self._detail}")
        import torch
        with self._lock, torch.inference_mode():
            tok = self.tok
            ids = tok.tokenize_prompt(tok.create_prompt(text, lang="english", speaker_name=voice))
            kw = dict(input_ids=ids, temperature=0.1, repetition_penalty=1.1, max_length=4000)
            if variation:
                # the first pass is repeatable; a redo needs sampling or it would
                # produce the same glitch again
                torch.manual_seed(random.randrange(2 ** 31))
                kw.update(do_sample=True, temperature=0.3)
            out = self.model.generate(**kw)
            codes = tok.get_codes(out)
            if not codes:
                raise EngineError("YarnGPT returned no audio for this sentence. Try Regenerate.")
            a = tok.get_audio(codes).detach().float().cpu().numpy().reshape(-1)
        return a, 24000


ENGINE = YarnGPT()
