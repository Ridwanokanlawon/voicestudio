"""Chatterbox (Resemble AI): voice cloning from a voice profile. Runs on this
PC in its own environment (envs\\chatterbox). Its audio watermark stays on."""
from .worker import WorkerEngine


class Chatterbox(WorkerEngine):
    id = "chatterbox"
    name = "Chatterbox"
    kind = "local"
    badge = "Local, no account"
    env_name = "chatterbox"
    worker = "chatterbox_worker.py"
    needs = ["chatterbox/t3_cfg.safetensors", "chatterbox/s3gen.safetensors", "chatterbox/ve.safetensors",
             "chatterbox/tokenizer.json", "chatterbox/conds.pt"]
    min_free_gb = 10.0
    uses_profiles = True
    extra_voices = [{"id": "builtin", "label": "Built-in voice", "note": "Chatterbox default"}]
    rate_note = "Chatterbox has no speed setting, so the speed is changed after generation (pitch is kept). The Pacing control also affects speed."
    params = [
        {"id": "exaggeration", "label": "Expressiveness", "type": "range", "min": 0.25, "max": 1.5, "step": 0.05,
         "default": 0.5, "hint": "Higher is more dramatic. 0.5 is neutral."},
        {"id": "cfg_weight", "label": "Pacing", "type": "range", "min": 0.0, "max": 1.0, "step": 0.05,
         "default": 0.5, "hint": "Lower is slower and more deliberate. 0.5 is the default."},
    ]

    def synth(self, text, voice, *, rate=1.0, variation=False, params=None, ref=None):
        p = params or {}
        return self.request(text=text, ref=ref, exaggeration=float(p.get("exaggeration", 0.5)),
                            cfg_weight=float(p.get("cfg_weight", 0.5)))


ENGINE = Chatterbox()
