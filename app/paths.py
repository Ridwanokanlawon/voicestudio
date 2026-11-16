"""All folders the app uses. Everything is relative to the app folder, so the
whole folder can be moved or zipped and still work."""
import datetime
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SESSIONS = DATA / "sessions"
MODELS = ROOT / "models"
VENDOR = ROOT / "vendor"
STATIC = Path(__file__).resolve().parent / "static"
ASSETS = ROOT / "assets"


def version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def out_root() -> Path:
    """C:\\Temp on Windows (override with VOICESTUDIO_OUT for testing)."""
    env = os.environ.get("VOICESTUDIO_OUT")
    if env:
        return Path(env)
    return Path(r"C:\Temp") if os.name == "nt" else Path.home() / "VoiceStudio_out"


def stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def new_out_dir() -> Path:
    d = out_root() / f"VoiceStudio_{stamp()}"
    n = 1
    while d.exists():
        n += 1
        d = out_root() / f"VoiceStudio_{stamp()}-{n}"
    d.mkdir(parents=True)
    return d


def log_dir() -> Path:
    d = out_root() / "VoiceStudio_logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


for _d in (DATA, SESSIONS):
    _d.mkdir(parents=True, exist_ok=True)
