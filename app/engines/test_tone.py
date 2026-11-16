"""Test engines (only loaded when VOICESTUDIO_TEST=1). They make beeps instead
of speech so the app can be tested without a GPU or an Azure account."""
import time

import numpy as np

from .base import Engine


def _tone(text, sr, f0):
    n = int(sr * max(0.5, 0.33 * len(text.split())))
    t = np.arange(n) / sr
    a = 0.25 * np.sin(2 * np.pi * (f0 + 12 * len(text) % 90) * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    pad = np.zeros(sr // 5)
    return np.concatenate([pad, a, pad]).astype(np.float32)


class TestLocal(Engine):
    id = "testlocal"
    name = "Test tone (local)"
    kind = "local"
    voices = [{"id": "low", "label": "Low", "note": "test"}, {"id": "high", "label": "High", "note": "test"}]

    def synth(self, text, voice, *, rate=1.0, variation=False):
        time.sleep(0.15)
        return _tone(text, 24000, 330 if voice == "high" else 180), 24000


ENGINE = TestLocal()
