"""Template for a new voice engine.

1. Copy this file to a new name in this folder WITHOUT the leading underscore,
   for example  piper_engine.py
2. Fill in the class below.
3. Restart Voice Studio. The engine shows up in the Engine list by itself.

Three ways to build an engine:
- Simple local engine: write synth() here. Use this only if its packages get
  along with the main runtime (runtime\\).
- Local engine with its own packages: subclass WorkerEngine (see
  chatterbox_engine.py and app\\workers\\chatterbox_worker.py). It runs in its own
  environment under envs\\ as a separate process, so versions never clash.
- Cloud engine: set kind = "cloud" and write synth_script() (see azure_engine.py).

Rules the app enforces for you:
- Local engines: only one is loaded at a time; load() and unload() are called
  when the user switches engine.
- Cloud engines: ONE request per click, never retried, at least 3 seconds
  between requests, voice-safe check first. Keep keys in Credential Manager via
  app.settings.get_secret().
- uses_profiles = True makes the voice list the user's own voice profiles and
  passes the profile's reference WAV to synth() as ref.
- params adds controls to the UI. Types: "range" (min, max, step, default) and
  "select" (options, default). The chosen values arrive in synth() as params.
"""
import numpy as np

from .base import Engine, EngineError  # noqa: F401


class MyEngine(Engine):
    id = "myengine"                 # used in file names
    name = "My Engine"
    kind = "local"                  # or "cloud"
    badge = "Local, no account"     # or "Cloud"
    voices = [{"id": "voice1", "label": "Voice 1", "note": "female"}]
    params = [{"id": "warmth", "label": "Warmth", "type": "range", "min": 0, "max": 1, "step": 0.05,
               "default": 0.5, "hint": "Shown under the slider."}]
    rate_note = ""

    def load(self):
        """Load models once here (called when the engine is selected)."""

    def unload(self):
        """Free memory here (called when another local engine is selected)."""

    def status(self):
        return {"state": "ready", "detail": ""}

    def synth(self, text, voice, *, rate=1.0, variation=False, params=None, ref=None):
        """Return (mono float32 numpy array in -1..1, sample_rate) for one sentence."""
        sr = 24000
        return np.zeros(sr, dtype=np.float32), sr


ENGINE = MyEngine()
