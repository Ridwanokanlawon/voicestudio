"""The contract every voice engine follows. To add an engine, copy
_template.py to a new file in this folder, fill it in and restart the app."""
import numpy as np


class EngineError(Exception):
    """Raise with a message that is safe and useful to show in the UI."""


class Engine:
    id = ""                 # short id used in file names, e.g. "yarn"
    name = ""               # shown in the UI
    kind = "local"          # "local" (runs on this PC) or "cloud" (sends text to a service)
    badge = "Local, no account"
    voices: list = []       # [{"id": "idera", "label": "Idera", "note": "female"}]
    rate_note = ""          # one line shown under the speaking-rate slider
    self_timed = False      # True if the engine adds its own pauses (cloud SSML engines)

    def status(self) -> dict:
        """{'state': 'ready' | 'loading' | 'error' | 'unconfigured', 'detail': str}"""
        return {"state": "ready", "detail": ""}

    def load(self):
        """Called once in the background at startup. Local engines load models here."""

    def synth(self, text: str, voice: str, *, rate: float = 1.0, variation: bool = False):
        """Local engines: one sentence -> (mono float32 numpy array, sample_rate).
        variation=True means 'give me a different take' (used by Regenerate)."""
        raise NotImplementedError

    def synth_script(self, items: list, voice: str, *, rate: float = 1.0, pause_ms: int = 700):
        """Cloud engines: the whole script in ONE request.
        items = [{'text': str, 'pause_after': bool}, ...]
        -> (list of mono float32 arrays, one per item, sample_rate)"""
        raise NotImplementedError

    def describe(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind, "badge": self.badge,
                "voices": self.voices, "rate_note": self.rate_note, "status": self.status()}


def f32(a) -> np.ndarray:
    return np.asarray(a, dtype=np.float32).reshape(-1)
