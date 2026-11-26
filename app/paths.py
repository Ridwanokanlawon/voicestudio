"""All folders the app uses. Program files, engines and models are relative to
the app folder, so the whole folder can be moved or zipped and still work.
The data folder is described at _data_dir below."""
import datetime
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def installed_copy():
    """The copy put in place by the installer (per user), or None."""
    local = os.environ.get("LOCALAPPDATA") if os.name == "nt" else os.environ.get("VOICESTUDIO_FAKE_INSTALL")
    if not local:
        return None
    inst = Path(local) / "VoiceStudio"
    return inst if (inst / "app" / "server.py").exists() else None


def _data_dir():
    """One place for profiles, history, presets and settings. When the app is
    installed on this PC, every copy (for example a source folder) uses the
    installed copy's data folder, so nothing ends up in two places. A copy on a
    PC without an installed app keeps its data in its own folder (portable).
    -> (folder, True if it is the installed copy's folder borrowed by another copy)"""
    env = os.environ.get("VOICESTUDIO_DATA")
    if env:
        return Path(env), False
    inst = installed_copy()
    if inst is not None and inst.resolve() != ROOT.resolve():
        return inst / "data", True
    return ROOT / "data", False


DATA, DATA_SHARED = _data_dir()
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
