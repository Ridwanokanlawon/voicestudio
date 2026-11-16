"""Pretend cloud engine (only loaded when VOICESTUDIO_TEST=1) used to test the
cloud safety rules without calling any real service."""
import numpy as np

from .base import Engine
from .test_tone import _tone

CALLS = []


class TestCloud(Engine):
    id = "testcloud"
    name = "Test tone (cloud rules)"
    kind = "cloud"
    badge = "Cloud"
    self_timed = True
    voices = [{"id": "beep", "label": "Beep", "note": "test"}]

    def synth_script(self, items, voice, *, rate=1.0, pause_ms=700):
        CALLS.append(len(items))
        out = []
        for it in items:
            a = _tone(it["text"], 48000, 440)
            if it.get("pause_after"):
                a = np.concatenate([a, np.zeros(int(48000 * pause_ms / 1000), dtype=np.float32)])
            out.append(a)
        return out, 48000


ENGINE = TestCloud()
