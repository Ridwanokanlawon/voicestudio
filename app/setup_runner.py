"""Runs setup.ps1 from inside the app (no PowerShell window) and reports its
progress, so engines can be added from the Engines screen."""
import collections
import os
import subprocess
import threading
import time

from . import engines
from .paths import MODELS, ROOT, log_dir

PACKS = [
    {"id": "lite", "name": "Kokoro", "size": "about 1.5 GB", "engines": ["kokoro"],
     "detail": "13 preset American and British voices. Light and quick: runs on any PC, no graphics card needed."},
    {"id": "qwen", "name": "Qwen3-TTS", "size": "about 9 GB", "engines": ["qwen"],
     "detail": "Large model with clear, natural preset voices and a delivery setting. Needs an NVIDIA graphics card "
               "with 8 GB to be usable, and about 7 GB of free memory to load."},
    {"id": "openvoice", "name": "OpenVoice v2", "size": "about 6 GB", "engines": ["openvoice"],
     "detail": "Your own voice tone with a choice of English accent."},
    {"id": "chatterbox", "name": "Chatterbox", "size": "about 8 GB", "engines": ["chatterbox"],
     "detail": "Clones a voice profile. Needs about 8 GB of free memory; an NVIDIA graphics card makes it fast."},
]
S = {"running": False, "packs": [], "step": "", "line": "", "started": 0.0, "ended": 0.0, "error": None,
     "done": False, "tail": collections.deque(maxlen=60)}
_size = {"at": 0.0, "gb": 0.0}


def _installed(pack):
    try:
        return all(engines.get(e).installed() for e in pack["engines"])
    except Exception:
        return False


def models_gb():
    if time.time() - _size["at"] > 4:
        total = 0
        for d, _, files in os.walk(MODELS):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(d, f))
                except OSError:
                    pass
        _size.update(at=time.time(), gb=round(total / 2 ** 30, 2))
    return _size["gb"]


def status():
    end = S["ended"] if not S["running"] and S["ended"] else time.time()
    return {"packs": [dict(p, installed=_installed(p)) for p in PACKS], "running": S["running"],
            "installing": S["packs"], "step": S["step"], "line": S["line"], "error": S["error"], "done": S["done"],
            "elapsed": int(end - S["started"]) if S["started"] else 0,
            "models_gb": models_gb() if S["running"] else None, "tail": list(S["tail"])[-12:]}


def _command(packs):
    if os.name == "nt":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "setup.ps1"),
                "-Yes", "-NoShortcut", "-Engines", ",".join(packs)]
    if os.environ.get("VOICESTUDIO_TEST") == "1":        # stand-in used when testing the screen off Windows
        import sys
        code = ("import time\nfor s in ['Light engines environment (envs/lite)', 'Kokoro model files']:\n"
                "    print('== ' + s, flush=True)\n    for i in range(4):\n        print(f'Downloading part {i + 1} of 4', flush=True); time.sleep(0.7)\n"
                "print('Setup finished.', flush=True)")
        return [sys.executable, "-c", code]
    return None


def _run(packs):
    logf = log_dir() / "setup_from_app.log"
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with open(logf, "a", encoding="utf-8", errors="replace") as out:
            out.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} engines: {packs}\n")
            env = dict(os.environ)
            for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "PYTHONPATH"):   # the app itself runs offline;
                env.pop(k, None)                                                 # setup has to reach the internet
            p = subprocess.Popen(_command(packs), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", cwd=str(ROOT), creationflags=flags, env=env)
            stopped = ""
            for raw in p.stdout:
                line = raw.strip()
                if not line:
                    continue
                out.write(line + "\n")
                out.flush()
                if line.startswith("== "):
                    S["step"], S["line"] = line[3:], ""
                elif line.startswith("SETUP STOPPED:"):
                    stopped = line[len("SETUP STOPPED:"):].strip()
                elif not line.startswith(("+", "At ", "Requirement already", "**", "CategoryInfo", "FullyQualified")):
                    S["line"] = line[:180]
                S["tail"].append(line[:200])
            rc = p.wait()
        if rc != 0:
            S["error"] = stopped or "Setup stopped before it finished. Details are in setup_from_app.log in the log folder."
    except Exception as e:
        S["error"] = f"{type(e).__name__}: {e}"
    S.update(running=False, done=True, ended=time.time(), step="" if S["error"] else "Finished")


def start(packs):
    valid = [p["id"] for p in PACKS]
    packs = [p for p in packs if p in valid]
    if not packs:
        raise ValueError("Tick at least one engine.")
    if S["running"]:
        raise ValueError("A download is already running.")
    if _command(packs) is None:
        raise ValueError("Engines can only be installed from the app on Windows.")
    engines.shutdown()                       # free the engines' files before they are updated
    S["tail"].clear()
    S.update(running=True, packs=packs, step="Starting", line="", started=time.time(), ended=0.0, error=None, done=False)
    threading.Thread(target=_run, args=(packs,), daemon=True).start()
