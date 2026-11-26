"""Qwen3-TTS (Alibaba Qwen, Apache-2.0): a large model with clear, natural
preset voices and a delivery instruction. Runs on this PC in its own
environment (envs\\qwen); an NVIDIA graphics card with 8 GB makes it usable."""
import os

from .worker import WorkerEngine

REPO = os.environ.get("VOICESTUDIO_QWEN_MODEL") or "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
STYLES = {
    "none": "",
    "clear": "Speak clearly and evenly, like a calm professional narrator.",
    "warm": "Speak in a warm, friendly, reassuring tone.",
    "serious": "Speak in a serious, measured tone, as if giving an important warning.",
    "lively": "Speak with energy and a quick, engaging rhythm.",
}


class Qwen(WorkerEngine):
    id = "qwen"
    name = "Qwen3-TTS"
    kind = "local"
    badge = "Local, heavy"
    env_name = "qwen"
    worker = "qwen_worker.py"
    fetch = "fetch_qwen.py"
    needs = ["qwen/" + REPO.split("/")[-1] + ".ok"]
    min_free_gb = 7.0
    load_timeout = 1200
    synth_timeout = 900
    rate_note = "Qwen3-TTS has no speed setting, so the speed is changed after generation (pitch is kept)."
    voices = [
        {"id": "ryan", "label": "Ryan", "note": "male, English, dynamic"},
        {"id": "aiden", "label": "Aiden", "note": "male, American, clear"},
        {"id": "serena", "label": "Serena", "note": "female, warm; Chinese native, accented English"},
        {"id": "vivian", "label": "Vivian", "note": "female, bright; Chinese native, accented English"},
        {"id": "uncle_fu", "label": "Uncle Fu", "note": "male, low; Chinese native, accented English"},
        {"id": "sohee", "label": "Sohee", "note": "female, warm; Korean native, accented English"},
        {"id": "ono_anna", "label": "Ono Anna", "note": "female, light; Japanese native, accented English"},
        {"id": "dylan", "label": "Dylan", "note": "male, young; Beijing native, accented English"},
        {"id": "eric", "label": "Eric", "note": "male, lively; Sichuan native, accented English"},
    ]
    params = [{"id": "style", "label": "Delivery", "type": "select", "default": "none",
               "options": [{"id": "none", "label": "As the voice comes"}, {"id": "clear", "label": "Clear narrator"},
                           {"id": "warm", "label": "Warm and friendly"}, {"id": "serious", "label": "Serious warning"},
                           {"id": "lively", "label": "Lively"}]}]

    def synth(self, text, voice, *, rate=1.0, variation=False, params=None, ref=None):
        style = STYLES.get((params or {}).get("style", "none"), "")
        return self.request(text=text, voice=voice, instruct=style)


ENGINE = Qwen()
