"""Secrets live in Windows Credential Manager (via keyring). Nothing secret is
ever written to a file. Non-secret choices go in data/prefs.json."""
import json
from .paths import DATA

SERVICE = "VoiceStudio"
PREFS = DATA / "prefs.json"


def _kr():
    import keyring
    return keyring


def get_secret(name: str):
    try:
        return _kr().get_password(SERVICE, name)
    except Exception:
        return None


def set_secret(name: str, value: str):
    _kr().set_password(SERVICE, name, value)


def delete_secret(name: str):
    try:
        _kr().delete_password(SERVICE, name)
    except Exception:
        pass


def keyring_ok() -> bool:
    try:
        kr = _kr()
        return "fail" not in type(kr.get_keyring()).__module__.lower()
    except Exception:
        return False


def prefs() -> dict:
    try:
        return json.loads(PREFS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def set_prefs(**kw) -> dict:
    p = prefs()
    p.update(kw)
    PREFS.write_text(json.dumps(p, indent=2), encoding="utf-8")
    return p
