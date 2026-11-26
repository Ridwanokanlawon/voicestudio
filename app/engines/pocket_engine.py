"""Pocket TTS (Kyutai; code MIT, weights CC BY 4.0): a 100M-parameter engine
that runs on the CPU in the shared light environment (envs\\lite). Preset
voices only for now; every voice offered is CC0 or CC BY 4.0."""
from .worker import WorkerEngine

_V = [("alba", "Alba", "female"), ("marius", "Marius", "male"), ("javert", "Javert", "male"),
      ("anna", "Anna", "female"), ("vera", "Vera", "female"), ("fantine", "Fantine", "female"),
      ("charles", "Charles", "male"), ("paul", "Paul", "male"), ("eponine", "Eponine", "female"),
      ("azelma", "Azelma", "female"), ("george", "George", "male"), ("mary", "Mary", "female"),
      ("jane", "Jane", "female"), ("michael", "Michael", "male"), ("eve", "Eve", "female"),
      ("bill_boerst", "Bill", "male, narrator"), ("peter_yearsley", "Peter", "male, narrator"),
      ("stuart_bell", "Stuart", "male, narrator"), ("caro_davy", "Caro", "female, narrator")]


class Pocket(WorkerEngine):
    id = "pocket"
    name = "Pocket TTS"
    kind = "local"
    badge = "Local, light"
    env_name = "lite"
    worker = "pocket_worker.py"
    fetch = "fetch_lite.py"
    needs = ["lite/pocket.ok"]
    min_free_gb = 2.0
    rate_note = "Pocket TTS has no speed setting, so the speed is changed after generation (pitch is kept)."
    voices = [{"id": i, "label": l, "note": n} for i, l, n in _V]

    def synth(self, text, voice, *, rate=1.0, variation=False, params=None, ref=None):
        return self.request(text=text, voice=voice)


ENGINE = Pocket()
