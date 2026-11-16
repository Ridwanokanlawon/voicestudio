"""The contract every voice engine follows. To add an engine, copy
_template.py to a new file in this folder, fill it in and restart the app."""
import numpy as np


class EngineError(Exception):
    """Raise with a message that is safe and useful to show in the UI."""


class Engine:
    id = ""                 # short id used in file names, e.g. "chatterbox"
    name = ""               # shown in the UI
    kind = "local"          # "local" (runs on this PC) or "cloud" (sends text to a service)
    badge = "Local, no account"
    voices: list = []       # [{"id": "abeo", "label": "Abeo", "note": "male"}]
    uses_profiles = False   # True: the voices are the user's own voice profiles
    extra_voices: list = [] # fixed voices offered next to the profiles
    params: list = []       # extra controls, see _template.py
    rate_note = ""          # one line shown under the speaking-rate slider
    native_rate = False     # True if the engine changes speed itself
    self_timed = False      # True if the engine adds its own pauses (cloud SSML engines)

    def status(self) -> dict:
        """{'state': 'ready' | 'idle' | 'loading' | 'error' | 'unconfigured' | 'missing', 'detail': str}"""
        return {"state": "ready", "detail": ""}

    def load(self):
        """Load models. Called when the engine is selected. Only one local
        engine is kept loaded at a time (8 GB graphics memory)."""

    def unload(self):
        """Free the graphics memory. Called when another local engine is selected."""

    def synth(self, text: str, voice: str, *, rate: float = 1.0, variation: bool = False,
              params: dict = None, ref: str = None):
        """Local engines: one sentence -> (mono float32 numpy array, sample_rate).
        variation=True means 'give me a different take' (used by Regenerate).
        ref is the voice profile's reference WAV when uses_profiles is True."""
        raise NotImplementedError

    def synth_script(self, items: list, voice: str, *, rate: float = 1.0, pause_ms: int = 700,
                     params: dict = None):
        """Cloud engines: the whole script in ONE request.
        items = [{'text': str, 'pause_after': bool}, ...]
        -> (list of mono float32 arrays, one per item, sample_rate)"""
        raise NotImplementedError

    def voice_list(self) -> list:
        if not self.uses_profiles:
            return list(self.voices)
        from .. import profiles
        mine = [{"id": "p:" + p["id"], "label": p["name"], "note": "voice profile"} for p in profiles.all_profiles()]
        return mine + list(self.extra_voices)

    def describe(self) -> dict:
        return {"id": self.id, "name": self.name, "kind": self.kind, "badge": self.badge,
                "voices": self.voice_list(), "uses_profiles": self.uses_profiles, "params": self.params,
                "rate_note": self.rate_note, "status": self.status()}


def f32(a) -> np.ndarray:
    return np.asarray(a, dtype=np.float32).reshape(-1)
