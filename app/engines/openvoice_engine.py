"""OpenVoice v2 (MyShell) with MeloTTS base voices: a chosen English accent,
then the tone of a voice profile. Runs in its own environment (envs\\openvoice)."""
from .worker import WorkerEngine


class OpenVoice(WorkerEngine):
    id = "openvoice"
    name = "OpenVoice v2"
    kind = "local"
    badge = "Local, no account"
    env_name = "openvoice"
    worker = "openvoice_worker.py"
    needs = ["openvoice/converter/checkpoint.pth", "melo/EN/checkpoint.pth",
             "hf_cache/hub/models--bert-base-uncased", "hf_cache/hub/models--M4869--WavMark",
             "nltk_data/corpora/cmudict", "nltk_data/taggers/averaged_perceptron_tagger"]
    min_free_gb = 6.0
    uses_profiles = True
    extra_voices = [{"id": "base", "label": "Base voice only", "note": "accent without my tone"}]
    native_rate = True
    rate_note = "Sent to MeloTTS as the speaking speed."
    params = [
        {"id": "accent", "label": "Accent", "type": "select", "default": "EN-US", "options": [
            {"id": "EN-US", "label": "American (EN-US)"}, {"id": "EN-BR", "label": "British (EN-BR)"},
            {"id": "EN-AU", "label": "Australian (EN-AU)"}, {"id": "EN-Default", "label": "Default (EN-Default)"},
            {"id": "EN_INDIA", "label": "Indian (EN-India)"}]},
    ]

    def synth(self, text, voice, *, rate=1.0, variation=False, params=None, ref=None):
        p = params or {}
        return self.request(text=text, ref=ref, accent=p.get("accent", "EN-US"), speed=float(rate))


ENGINE = OpenVoice()
