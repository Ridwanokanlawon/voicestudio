"""Presets, length estimates, the video-folder copy, hidden voices and the
removal of files left behind by engines that are no longer part of the app."""
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from . import pron, settings, textproc
from .paths import DATA, MODELS, ROOT

PRESETS = DATA / "presets.json"
STATS = DATA / "speed.json"
_lock = threading.Lock()
EPISODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,29}$")
RATE_MIN, RATE_MAX = 0.8, 1.2          # the speaking-rate slider
TYPICAL_CPS = {"azure": 13.5}          # characters spoken per second at 100%, before anything is measured
DEFAULT_CPS = 14.5


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- presets
def loose(name: str) -> str:
    """'WCGW – Harry', 'wcgw - harry' and 'WCGW-Harry' are the same preset name."""
    n = re.sub(r"[\u2010-\u2015\u2212-]+", "-", name or "").lower()
    return re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", n)).strip()


def presets() -> list:
    return [p for p in _read(PRESETS, []) if isinstance(p, dict) and p.get("name")]


def find_preset(name: str):
    return next((p for p in presets() if loose(p["name"]) == loose(name)), None)


def save_preset(p: dict) -> dict:
    name = re.sub(r"\s+", " ", str(p.get("name", ""))).strip()[:60]
    if not name:
        raise ValueError("Give the preset a name.")
    item = {"name": name, "engine": str(p.get("engine", "")), "voice": str(p.get("voice", "")),
            "rate": float(p.get("rate", 1.0)), "pause_ms": int(p.get("pause_ms", 700)),
            "gap_ms": int(p.get("gap_ms", 150)), "mp3": bool(p.get("mp3", False)),
            "params": p.get("params") if isinstance(p.get("params"), dict) else {},
            "target": str(p.get("target", ""))[:20]}
    with _lock:
        rest = [x for x in presets() if loose(x["name"]) != loose(name)]
        rest.append(item)
        rest.sort(key=lambda x: x["name"].lower())
        _write(PRESETS, rest[:200])
    settings.set_prefs(last_preset=name)
    return item


def delete_preset(name: str):
    with _lock:
        _write(PRESETS, [x for x in presets() if loose(x["name"]) != loose(name)])
    if loose(settings.prefs().get("last_preset", "")) == loose(name):
        settings.set_prefs(last_preset="")


# ---------------------------------------------------------------- hidden voices
def hidden() -> dict:
    h = settings.prefs().get("hidden_voices")
    return {k: [str(x) for x in v] for k, v in h.items() if isinstance(v, list)} if isinstance(h, dict) else {}


def is_hidden(engine_id: str, voice: str) -> bool:
    return voice in hidden().get(engine_id, [])


# ---------------------------------------------------------------- length estimate
def learn(engine_id, voice, chars, speech_s, rate_eff):
    """Remember how fast this voice really speaks (characters per second at 100%)."""
    if chars < 60 or speech_s < 3:
        return
    cps = chars / (speech_s * max(0.1, rate_eff))
    if not 6 <= cps <= 30:
        return
    with _lock:
        st = _read(STATS, {})
        e = st.get(f"{engine_id}:{voice}") or {"cps": cps, "n": 0}
        e["cps"] = round(cps if not e["n"] else 0.6 * e["cps"] + 0.4 * cps, 3)
        e["n"] = int(e["n"]) + 1
        st[f"{engine_id}:{voice}"] = e
        _write(STATS, st)


def speed(engine_id, voice):
    e = _read(STATS, {}).get(f"{engine_id}:{voice}")
    if e and e.get("n"):
        return float(e["cps"]), int(e["n"])
    return TYPICAL_CPS.get(engine_id, DEFAULT_CPS), 0


def parse_target(text: str):
    """'45' -> about 45 s; '40-50' or '40 to 50' -> between 40 and 50 s."""
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")][:2]
    nums = [n for n in nums if 1 <= n <= 3600]
    if not nums:
        return None
    if len(nums) == 1:
        return {"lo": nums[0] * 0.97, "hi": nums[0] * 1.03, "mid": nums[0], "text": f"about {nums[0]:g} s"}
    lo, hi = min(nums), max(nums)
    return {"lo": lo, "hi": hi, "mid": (lo + hi) / 2, "text": f"{lo:g} to {hi:g} s"}


def _mmss(s):
    s = max(0, int(round(s)))
    return f"{s // 60}:{s % 60:02d}"


def estimate(text, eng, voice, vlabel, rate, pause_ms, gap_ms, target):
    items = textproc.split_script(text)
    sent = [it["text"] for it in items if it["type"] == "s"]
    if not sent:
        return {"empty": True}
    table = pron.table()
    chars = sum(len(pron.apply(t, table)[0]) for t in sent)
    words = sum(len(t.split()) for t in sent)
    n_pause = sum(1 for it in items if it["type"] == "pause")
    cps, n = speed(eng.id, voice)
    fixed = bool(eng.rate_fixed(voice))
    silence = n_pause * pause_ms / 1000.0
    if not eng.self_timed:
        silence += max(0, len(sent) - 1 - n_pause) * gap_ms / 1000.0
    speech1 = chars / cps                                   # seconds of speech at 100%
    est = speech1 / (1.0 if fixed else rate) + silence
    basis = (f"measured from {n} earlier take{'s' if n != 1 else ''} with this voice" if n
             else "typical speed for this engine; it sharpens after the first full take with this voice")
    out = {"seconds": round(est, 1), "words": words, "fixed_rate": fixed, "basis": basis, "measured": n,
           "suggest_rate": None, "fit": None,
           "message": f"Estimated length with {vlabel}: {_mmss(est)} ({basis})."}
    t = parse_target(target)
    if not t:
        if fixed:
            out["message"] += f" {vlabel} ignores the speaking rate."
        return out
    out["target"] = t["text"]
    per_word = speech1 / max(1, words)

    def edit(seconds):                                      # how many words to cut or add to reach the target
        d = abs(seconds - t["mid"])
        return max(1, int(round(d / per_word)))
    if t["lo"] <= est <= t["hi"]:
        out["fit"] = "ok"
        out["message"] = f"Estimated {_mmss(est)} with {vlabel}: inside the target of {t['text']} ({basis})."
        if fixed:
            out["message"] += f" {vlabel} ignores the speaking rate."
        return out
    out["fit"] = "long" if est > t["hi"] else "short"
    change = "cut" if est > t["hi"] else "add"
    if fixed:
        out["message"] = (f"{vlabel} ignores the speaking rate, so only the script can change its length. "
                          f"Estimated {_mmss(est)} against a target of {t['text']}: {change} about {edit(est)} words ({basis}).")
        return out
    room = t["mid"] - silence
    need = speech1 / room if room > 1 else 99
    if RATE_MIN <= need <= RATE_MAX:
        need = round(need, 2)
        out["suggest_rate"] = need
        out["message"] = (f"Estimated {_mmss(est)} with {vlabel} at {round(rate * 100)}%. To land on {t['text']}, "
                          f"set the speaking rate to {round(need * 100)}% ({basis}).")
    else:
        lim = RATE_MAX if need > RATE_MAX else RATE_MIN
        at_lim = speech1 / lim + silence
        out["suggest_rate"] = lim
        out["message"] = (f"Estimated {_mmss(est)} with {vlabel}. Even at {round(lim * 100)}% it runs about {_mmss(at_lim)}, "
                          f"outside the target of {t['text']}: also {change} about {edit(at_lim)} words ({basis}).")
    return out


# ---------------------------------------------------------------- copy for the video pipeline
def chunks_dir() -> str:
    return str(settings.prefs().get("chunks_dir", "") or "")


def set_chunks_dir(value: str) -> str:
    value = (value or "").strip().strip('"')
    if value and not os.path.isabs(value):
        raise ValueError("Give the full path of the folder, for example C:\\Videos\\Renders\\_chunks")
    settings.set_prefs(chunks_dir=value)
    return value


def _next_free(folder: Path, ep: str) -> Path:
    n = 2
    while (folder / f"{ep}_audio_v{n}.wav").exists():
        n += 1
    return folder / f"{ep}_audio_v{n}.wav"


def deliver(wav: str, episode: str, mode: str = "ask") -> dict:
    """Copy the finished WAV to <video folder>\\<EPxx>_audio.wav.
    mode: ask (never replaces: reports that the file exists), version (keep the
    old file, save as _v2, _v3...), overwrite (only when the user chose it), skip."""
    folder = chunks_dir()
    if not episode:
        return {"status": "off", "why": "No episode code was given."}
    if not folder:
        return {"status": "off", "why": "No video folder is set (Settings, Folders)."}
    if not EPISODE.match(episode):
        return {"status": "error", "why": "The episode code may contain only letters, digits, - and _."}
    if not wav or not os.path.exists(wav):
        return {"status": "error", "why": "The finished WAV is no longer on disk."}
    try:
        d = Path(folder)
        d.mkdir(parents=True, exist_ok=True)
        target = d / f"{episode}_audio.wav"
        replaced = False
        if target.exists():
            if mode == "skip":
                return {"status": "skipped", "target": str(target)}
            if mode == "ask":
                return {"status": "exists", "target": str(target), "suggest": _next_free(d, episode).name}
            if mode == "version":
                target = _next_free(d, episode)
            elif mode == "overwrite":
                replaced = True
            else:
                return {"status": "error", "why": "Unknown choice."}
        tmp = target.with_name(target.name + ".part")
        shutil.copyfile(wav, tmp)
        if replaced:
            os.replace(tmp, target)
        else:
            try:
                os.rename(tmp, target)             # fails rather than replaces if a file appeared meanwhile
            except OSError:
                if os.name == "nt" or target.exists():
                    tmp.unlink(missing_ok=True)
                    return {"status": "exists", "target": str(target), "suggest": _next_free(d, episode).name}
                raise
        return {"status": "copied", "path": str(target), "replaced": replaced}
    except Exception as e:
        return {"status": "error", "why": f"Could not copy to the video folder: {e}"}


# ---------------------------------------------------------------- leftovers of removed engines
POCKET_PACKAGES = ["pocket-tts", "einops", "sentencepiece", "fastapi", "starlette", "uvicorn", "python-multipart",
                   "opentelemetry-api"]        # in envs\\lite only Pocket TTS used these; Kokoro runs without them


def _real_files(path: Path) -> set:
    """Every real file a folder leads to (the model cache links to files kept elsewhere)."""
    out = set()
    if path.is_file():
        return {path.resolve()}
    for d, _, files in os.walk(path):
        for f in files:
            try:
                out.add(Path(os.path.join(d, f)).resolve())
            except OSError:
                pass
    return out


def _size(path: Path) -> int:
    total = 0
    for f in _real_files(path):
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total


def _lite_python() -> Path:
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return ROOT / "envs" / "lite" / sub[0] / sub[1]


def _lite_site() -> Path:
    env = ROOT / "envs" / "lite"
    if os.name == "nt":
        return env / "Lib" / "site-packages"
    hits = sorted(env.glob("lib/python*/site-packages"))
    return hits[0] if hits else env / "lib" / "site-packages"


def leftovers() -> dict:
    """What Pocket TTS (removed in 0.5.0) left on this PC."""
    items = []
    hub = MODELS / "hf_cache" / "hub"
    if hub.exists():
        for d in hub.glob("models--kyutai--pocket-tts*"):
            items.append({"path": str(d), "what": "Pocket TTS model files", "bytes": _size(d), "kind": "dir"})
    for f in (MODELS / "lite" / "pocket.ok", ROOT / "app" / "engines" / "pocket_engine.py",
              ROOT / "app" / "workers" / "pocket_worker.py"):
        if f.exists():
            items.append({"path": str(f), "what": "Pocket TTS program file", "bytes": _size(f), "kind": "file"})
    site = _lite_site()
    if (site / "pocket_tts").exists():
        dirs = ["pocket_tts", "einops", "sentencepiece", "fastapi", "starlette", "uvicorn", "multipart",
                "python_multipart", "opentelemetry"]
        size = sum(_size(site / d) for d in dirs if (site / d).exists())
        items.append({"path": str(site / "pocket_tts"), "what": "Pocket TTS and the packages only it used, in envs\\lite",
                      "bytes": size, "kind": "packages"})
    return {"items": [dict(i, mb=round(i["bytes"] / 2 ** 20, 1)) for i in items],
            "total_mb": round(sum(i["bytes"] for i in items) / 2 ** 20, 1)}


def remove_leftovers() -> dict:
    """Delete them. Only ever started by the button in the Engines screen."""
    done, failed = [], []
    hf = (MODELS / "hf_cache").resolve()
    for it in leftovers()["items"]:
        p = Path(it["path"])
        try:
            if it["kind"] == "packages":
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                r = subprocess.run([str(_lite_python()), "-m", "pip", "uninstall", "-y", *POCKET_PACKAGES],
                                   capture_output=True, text=True, timeout=300, creationflags=flags)
                if r.returncode != 0:
                    raise RuntimeError((r.stderr or r.stdout).strip()[-200:])
            elif it["kind"] == "dir":
                # The cache keeps big files in a shared place and links to them. Delete only the
                # ones that no other model uses.
                others = set()
                for d in p.parent.glob("models--*"):
                    if d.resolve() != p.resolve():
                        others |= _real_files(d)
                for real in _real_files(p) - others:
                    if hf in real.parents and real.exists():
                        real.unlink()
                shutil.rmtree(p, ignore_errors=True)
                if p.exists():
                    raise RuntimeError("some files are in use")
            else:
                p.unlink()
            done.append(it["path"])
        except Exception as e:
            failed.append(f"{it['path']}: {e}")
    return {"removed": done, "failed": failed, "left": leftovers()}
