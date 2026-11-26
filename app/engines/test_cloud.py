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
    voices = [{"id": "beep", "label": "Beep", "note": "test"},
              {"id": "plain", "label": "Plain", "note": "one piece, word timings, ignores rate"},
              {"id": "plainq", "label": "Plain quiet", "note": "one piece, no word timings"}]
    last_words = None

    def rate_fixed(self, voice):
        return voice.startswith("plain")

    def synth_script(self, items, voice, *, rate=1.0, pause_ms=700, params=None):
        CALLS.append(len(items))
        out, words, at = [], [], 0.0
        for it in items:
            a = _tone(it["text"], 48000, 440)
            ws, n = [], len(it["text"].split())
            for k, w in enumerate(it["text"].split()):          # pretend each word takes an equal share of the tone
                span = (a.size / 48000 - 0.4) / n
                ws.append([0.2 + k * span, 0.2 + (k + 1) * span, w])
            if it.get("pause_after"):
                a = np.concatenate([a, np.zeros(int(48000 * pause_ms / 1000), dtype=np.float32)])
            out.append(a)
            words.append(ws)
        self.last_words = words
        if voice.startswith("plain") and len(items) > 1:      # like the HD voices: everything comes back as one clip
            flat, at = [], 0.0
            for a, ws in zip(out, words):
                flat += [[at + w[0], at + w[1], w[2]] for w in ws]
                at += a.size / 48000
            self.last_words = [flat] + [[] for _ in out[1:]] if voice == "plain" else None
            return [np.concatenate(out)] + [np.zeros(0, dtype=np.float32)] * (len(out) - 1), 48000
        if voice == "plainq":
            self.last_words = None
        return out, 48000


ENGINE = TestCloud()
