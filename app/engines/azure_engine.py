"""Azure AI Speech (official SDK). One request per call, never retried here.
The whole script goes in a single SSML request; bookmarks tell us where each
sentence starts so the sentence editor still works."""
import html
import json
import threading
import urllib.error
import urllib.request

import numpy as np

from .. import settings
from .base import Engine, EngineError

# plain=True: Dragon HD and MAI voices accept only a small part of SSML (no
# speaking rate, no sentence bookmarks), so they are sent plainly and come back
# as one piece. speed: the speed picked for that voice after listening; the
# rate slider is applied on top of it.
VOICES = {
    "leah":      {"name": "en-ZA-LeahNeural", "lang": "en-ZA", "plain": False, "speed": 1.05},
    "asilia":    {"name": "en-KE-AsiliaNeural", "lang": "en-KE", "plain": False, "speed": 1.025},
    "sonia":     {"name": "en-GB-SoniaNeural", "lang": "en-GB", "plain": False, "speed": 1.0},
    "ryan":      {"name": "en-GB-RyanNeural", "lang": "en-GB", "plain": False, "speed": 1.0},
    "harry":     {"name": "en-GB-Harry:MAI-Voice-2.1", "lang": "en-GB", "plain": True, "speed": 1.0},
    "harper":    {"name": "en-US-Harper:MAI-Voice-2.1", "lang": "en-US", "plain": True, "speed": 1.0},
    "emma_hd":   {"name": "en-US-Emma:DragonHDLatestNeural", "lang": "en-US", "plain": True, "speed": 1.0},
    "andrew_hd": {"name": "en-US-Andrew:DragonHDLatestNeural", "lang": "en-US", "plain": True, "speed": 1.0},
    "abeo":      {"name": "en-NG-AbeoNeural", "lang": "en-NG", "plain": False, "speed": 1.0},
    "ezinne":    {"name": "en-NG-EzinneNeural", "lang": "en-NG", "plain": False, "speed": 1.0},
}
SR = 48000


def creds():
    return settings.get_secret("azure_key"), settings.get_secret("azure_region")


def build_ssml(items, v, rate, pause_ms):
    parts = []
    for i, it in enumerate(items):
        mark = "" if v["plain"] else f'<bookmark mark="s{i}"/>'
        parts.append(mark + html.escape(it["text"]))
        if it.get("pause_after"):
            parts.append(f'<break time="{int(pause_ms)}ms"/>')
    body = " ".join(parts)
    pct = (rate * v["speed"] - 1.0) * 100
    if not v["plain"] and abs(pct) >= 0.05:
        body = f'<prosody rate="{pct:+.1f}%">{body}</prosody>'
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{v["lang"]}">'
            f'<voice name="{v["name"]}">{body}</voice></speak>')


class Azure(Engine):
    id = "azure"
    name = "Azure AI Speech"
    kind = "cloud"
    badge = "Cloud"
    self_timed = True
    rate_note = ("Leah is already set 5% faster and Asilia 2.5% faster; this slider is applied on top. "
                 "Harry, Harper, Emma HD and Andrew HD ignore the rate and come back as one piece, "
                 "so their sentences cannot be redone one at a time.")
    voices = [
        {"id": "leah", "label": "Leah", "note": "female, South African, +5%"},
        {"id": "asilia", "label": "Asilia", "note": "female, Kenyan, +2.5%"},
        {"id": "sonia", "label": "Sonia", "note": "female, British"},
        {"id": "ryan", "label": "Ryan", "note": "male, British"},
        {"id": "harry", "label": "Harry", "note": "male, British, MAI"},
        {"id": "harper", "label": "Harper", "note": "female, US, MAI"},
        {"id": "emma_hd", "label": "Emma HD", "note": "female, US, HD"},
        {"id": "andrew_hd", "label": "Andrew HD", "note": "male, US, HD"},
        {"id": "abeo", "label": "Abeo", "note": "male, Nigerian"},
        {"id": "ezinne", "label": "Ezinne", "note": "female, Nigerian"},
    ]

    def __init__(self):
        self._lock = threading.Lock()

    def status(self):
        key, region = creds()
        if not key or not region:
            return {"state": "unconfigured", "detail": "Add your Azure key and region in Settings"}
        return {"state": "ready", "detail": f"Region {region}"}

    def synth_script(self, items, voice, *, rate=1.0, pause_ms=700, params=None):
        key, region = creds()
        if not key or not region:
            raise EngineError("Azure is not set up. Add your key and region in Settings.")
        if voice not in VOICES:
            raise EngineError(f"Unknown Azure voice '{voice}'")
        try:
            import azure.cognitiveservices.speech as sdk
        except ImportError:
            raise EngineError("The Azure Speech package is not installed. Run Setup.bat.")
        ssml = build_ssml(items, VOICES[voice], rate, pause_ms)
        cfg = sdk.SpeechConfig(subscription=key, region=region)
        cfg.set_speech_synthesis_output_format(sdk.SpeechSynthesisOutputFormat.Raw48Khz16BitMonoPcm)
        marks = {}
        with self._lock:
            synth = sdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
            synth.bookmark_reached.connect(lambda e: marks.__setitem__(e.text, e.audio_offset))
            r = synth.speak_ssml_async(ssml).get()          # exactly one request
        if r.reason != sdk.ResultReason.SynthesizingAudioCompleted:
            d = r.cancellation_details
            raise EngineError(f"Azure refused or failed: {d.reason}. {d.error_details or ''}".strip())
        audio = np.frombuffer(r.audio_data, dtype="<i2").astype(np.float32) / 32768.0
        # bookmark offsets are in 100-nanosecond ticks
        cuts = [int(marks.get(f"s{i}", -1) * SR / 10_000_000) if f"s{i}" in marks else -1
                for i in range(len(items))]
        if len(items) == 1 or any(c < 0 for c in cuts) or cuts != sorted(cuts):
            if len(items) == 1:
                return [audio], SR
            # could not split: hand the whole take to the first sentence
            return [audio] + [np.zeros(0, dtype=np.float32)] * (len(items) - 1), SR
        cuts[0] = 0
        cuts.append(audio.size)
        return [audio[cuts[i]:cuts[i + 1]] for i in range(len(items))], SR

    def test(self, key=None, region=None):
        """Checks the key without sending any script text: asks for the voice list."""
        k, r = creds()
        key, region = key or k, region or r
        if not key or not region:
            raise EngineError("Enter a key and a region first.")
        if not region.replace("-", "").isalnum():
            raise EngineError("The region should look like 'eastus' or 'westeurope'.")
        req = urllib.request.Request(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
            headers={"Ocp-Apim-Subscription-Key": key})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                names = {v.get("ShortName") for v in json.loads(resp.read())}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise EngineError("Azure rejected the key for this region. Check both values.")
            raise EngineError(f"Azure answered with error {e.code}.")
        except Exception as e:
            raise EngineError(f"Could not reach Azure: {e}")
        have = {n.lower() for n in names if n}
        missing = [k for k, v in VOICES.items() if v["name"].lower() not in have]
        if missing:
            return ("Connected. Not listed for this region (they may still work, or need another region): "
                    + ", ".join(missing))
        return f"Connected. All {len(VOICES)} voices are available in this region."


ENGINE = Azure()
