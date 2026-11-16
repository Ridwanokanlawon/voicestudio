"""Template for a new voice engine.

1. Copy this file to a new name in this folder WITHOUT the leading underscore,
   for example  piper_engine.py
2. Fill in the class below.
3. Restart Voice Studio. The engine shows up in the Engine list by itself.

Rules the app enforces for you:
- kind = "local": the app calls synth() once per sentence and may batch freely.
- kind = "cloud": the app calls synth_script() ONCE per Generate click, never
  retries, waits at least 3 seconds between requests and runs the voice-safe
  check first. Keep keys in Credential Manager via app.settings.get_secret().
"""
import numpy as np

from .base import Engine, EngineError  # noqa: F401


class MyEngine(Engine):
    id = "myengine"                 # used in file names
    name = "My Engine"
    kind = "local"                  # or "cloud"
    badge = "Local, no account"     # or "Cloud"
    voices = [{"id": "voice1", "label": "Voice 1", "note": "female"}]
    rate_note = ""

    def load(self):
        """Load models once here (runs in the background at startup)."""

    def status(self):
        return {"state": "ready", "detail": ""}

    def synth(self, text, voice, *, rate=1.0, variation=False):
        """Return (mono float32 numpy array in -1..1, sample_rate) for one sentence."""
        sr = 24000
        return np.zeros(sr, dtype=np.float32), sr


ENGINE = MyEngine()
