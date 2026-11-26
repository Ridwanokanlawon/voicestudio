"""Kokoro (hexgrad, Apache-2.0): a small, fast engine with preset American and
British voices. Runs on the CPU in the shared light environment (envs\\lite),
so it loads in seconds and does not need the graphics card."""
from .worker import WorkerEngine

_V = [("af_heart", "Heart", "female, American"), ("af_bella", "Bella", "female, American"),
      ("af_nicole", "Nicole", "female, American, soft"), ("af_sarah", "Sarah", "female, American"),
      ("am_michael", "Michael", "male, American"), ("am_fenrir", "Fenrir", "male, American"),
      ("am_puck", "Puck", "male, American"), ("am_adam", "Adam", "male, American"),
      ("bf_emma", "Emma", "female, British"), ("bf_isabella", "Isabella", "female, British"),
      ("bm_george", "George", "male, British"), ("bm_fable", "Fable", "male, British"),
      ("bm_lewis", "Lewis", "male, British")]


class Kokoro(WorkerEngine):
    id = "kokoro"
    name = "Kokoro"
    kind = "local"
    badge = "Local, light"
    env_name = "lite"
    worker = "kokoro_worker.py"
    fetch = "fetch_lite.py"
    needs = ["lite/kokoro.ok"]
    min_free_gb = 2.5
    native_rate = True
    rate_note = "Sent to Kokoro as the speaking speed."
    voices = [{"id": i, "label": l, "note": n} for i, l, n in _V]

    def synth(self, text, voice, *, rate=1.0, variation=False, params=None, ref=None):
        return self.request(text=text, voice=voice, speed=float(rate))


ENGINE = Kokoro()
