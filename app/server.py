"""Voice Studio server. Local only: binds to 127.0.0.1 and nothing else.

Start with:  runtime\\Scripts\\python.exe -m app.server
"""
import os

# No telemetry and no surprise downloads: models are loaded from disk only.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")

import base64
import datetime
import json
import logging
import re
import socket
import threading
import time
import traceback
import uuid
import webbrowser
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audio, captions, engines, extras, profiles, pron, safecheck, settings, setup_runner, sysinfo, textproc, updater
from .engines.base import EngineError
from .paths import ASSETS, DATA, DATA_SHARED, ROOT, SESSIONS, STATIC, installed_copy, log_dir, new_out_dir, out_root, version

HOST = "127.0.0.1"
PORT = int(os.environ.get("VOICESTUDIO_PORT", "8765"))
CLOUD_MIN_GAP = 3.0            # seconds between cloud requests
HISTORY = DATA / "history.json"

log = logging.getLogger("voicestudio")
log.setLevel(logging.INFO)
_fh = logging.FileHandler(log_dir() / "voicestudio.log", encoding="utf-8")
_fh.setLevel(logging.INFO)
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
log.addHandler(_fh)
log.addHandler(logging.StreamHandler())

app = FastAPI(title="Voice Studio", docs_url=None, redoc_url=None, openapi_url=None)
jobs = {}
busy = threading.Lock()
_state_lock = threading.Lock()
_last_cloud = {"t": 0.0}


# ---------------------------------------------------------------- safety net
@app.middleware("http")
async def local_only(request: Request, call_next):
    """Refuse anything that is not this PC talking to itself (blocks other
    websites from poking the app through the browser)."""
    host = request.headers.get("host", "")
    ok = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
    if host not in ok:
        return JSONResponse({"detail": "Local access only"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in {f"http://{h}" for h in ok}:
        return JSONResponse({"detail": "Local access only"}, status_code=403)
    resp = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):
    log.error("Unhandled error on %s\n%s", request.url.path, traceback.format_exc())
    return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)


def fail(code, msg):
    raise HTTPException(code, msg)


# ---------------------------------------------------------------- sessions
SID = re.compile(r"^[0-9a-f]{12}$")
FNAME = re.compile(r"^(s\d{3}_r\d+|cmp_\d)\.wav$")


def sdir(sid):
    if not SID.match(sid):
        fail(404, "Unknown session")
    return SESSIONS / sid


def load_session(sid):
    p = sdir(sid) / "session.json"
    if not p.exists():
        fail(404, "This generation is no longer on disk")
    return json.loads(p.read_text(encoding="utf-8"))


def save_session(s):
    d = sdir(s["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "session.json").write_text(json.dumps(s, indent=2), encoding="utf-8")


def sents(s):
    return [it for it in s["items"] if it["type"] == "s"]


def public(s):
    out = []
    for i, it in enumerate(sents(s)):
        out.append({"index": i, "text": it["text"], "state": it.get("state", "pending"),
                    "dur": it.get("dur"), "flag": it.get("flag"), "error": it.get("error"),
                    "subs": it.get("subs") or [],
                    "url": f"/api/audio/{s['id']}/{it['file']}" if it.get("file") else None})
    return {"id": s["id"], "engine": s["engine"], "engine_kind": s["engine_kind"], "voice": s["voice"],
            "voice_label": s.get("voice_label", s["voice"]), "label": s["label"], "preview": s["preview"], "sentences": out, "final": s.get("final"),
            "merged": s.get("merged", False), "episode": s.get("episode", ""), "delivery": s.get("delivery")}


def read_history():
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return []


def write_history(entry):
    with _state_lock:
        h = [e for e in read_history() if e["id"] != entry["id"]]
        h.insert(0, entry)
        HISTORY.write_text(json.dumps(h[:300], indent=2), encoding="utf-8")


# ---------------------------------------------------------------- audio work
def glitch_flag(text, dur):
    words = max(1, len(text.split()))
    if dur < 0.12 * words + 0.15:
        return "Very short for this many words. Some words may be missing."
    if dur > 1.0 * words + 2.5:
        return "Very long for this many words. It may contain noise or repeats."
    return None


def store_sentence(s, it, index, a, sr, eng):
    """Clean up one sentence's audio and save it in the session folder."""
    a = audio.mono(a)
    flag = None
    if eng.kind == "local":
        a = audio.trim(a, sr)
        flag = glitch_flag(it["text"], a.size / sr)
        if not eng.native_rate:
            a, ok = audio.stretch(a, s["rate"])
            if not ok and not flag:
                flag = "Speed change is unavailable, so this was kept at normal speed."
        a = audio.fade(a, sr)
    it["rev"] = it.get("rev", 0) + 1
    it["file"] = f"s{index:03d}_r{it['rev']}.wav"
    it["sr"] = sr
    it["dur"] = round(a.size / sr, 2)
    it["flag"] = flag
    it["state"] = "done" if a.size else "merged"
    it["error"] = None
    if a.size:
        sdir(s["id"]).mkdir(parents=True, exist_ok=True)
        audio.write_wav(sdir(s["id"]) / it["file"], a, sr)
    else:
        it["file"] = None


def assemble(s, eng):
    """Join all sentences into one file and export it (WAV, optional MP3, captions)."""
    parts, prev = [], False
    sr = None
    pos = 0                          # samples so far, to time the captions
    groups = []                      # one per audio clip: {"t0", "t1", "items": [sentences inside it], "audio"}
    for it in s["items"]:
        if it["type"] == "pause":
            if not eng.self_timed and sr:
                parts.append(audio.silence(s["pause_ms"], sr))
                pos += parts[-1].size
            prev = False
            continue
        if not it.get("file"):
            if it.get("state") == "merged" and groups:
                groups[-1]["items"].append(it)
            continue
        a, sr = audio.read_wav(sdir(s["id"]) / it["file"])
        if prev and not eng.self_timed:
            parts.append(audio.silence(s["gap_ms"], sr))
            pos += parts[-1].size
        groups.append({"t0": pos / sr, "t1": (pos + a.size) / sr, "items": [it], "audio": a, "sr": sr})
        parts.append(a)
        pos += a.size
        prev = True
    if not parts:
        raise EngineError("There is no audio to join.")
    full = audio.resample(np.concatenate(parts), sr, audio.TARGET_SR)
    full, info = audio.normalize(full, audio.TARGET_SR)
    if not s.get("out_dir"):
        s["out_dir"] = str(new_out_dir())
    from pathlib import Path
    out = Path(s["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    s["version"] = s.get("version", 0) + 1
    vname = re.sub(r"[^A-Za-z0-9_-]+", "", s.get("voice_label", s["voice"]).replace(" ", "-"))[:30] or "voice"
    stem = f"{s['label']}_{s['engine']}-{vname}" + ("" if s["version"] == 1 else f"_v{s['version']}")
    wav = out / f"{stem}.wav"
    audio.write_wav(wav, full, audio.TARGET_SR, label=True)
    mp3 = None
    if s.get("mp3") and audio.mp3_available():
        mp3 = out / f"{stem}.mp3"
        audio.write_mp3(mp3, full, audio.TARGET_SR)
    duration = full.size / audio.TARGET_SR
    srt, srt_words, cap_note = write_captions(groups, out, stem, duration)
    s["final"] = {"wav": str(wav), "mp3": str(mp3) if mp3 else None, "name": wav.name,
                  "srt": srt, "srt_words": srt_words, "captions": cap_note,
                  "duration": round(duration, 2), "version": s["version"],
                  "lufs": None if info["after_lufs"] is None else round(info["after_lufs"], 1),
                  "limited": info["limited"], "out_dir": s["out_dir"],
                  "url": f"/api/sessions/{s['id']}/final?fmt=wav&v={s['version']}"}
    try:                             # remember this voice's real speed for the length estimate
        all_s = sents(s)
        chars = sum(len(it.get("spoken") or it["text"]) for it in all_s)
        n_pause = sum(1 for it in s["items"] if it["type"] == "pause")
        speech = (duration - n_pause * s["pause_ms"] / 1000.0) if eng.self_timed else sum(g["t1"] - g["t0"] for g in groups)
        if not any(it.get("state") == "error" for it in all_s):
            extras.learn(eng.id, s["voice"], chars, speech, 1.0 if eng.rate_fixed(s["voice"]) else s["rate"])
    except Exception:
        log.info("Could not record the speaking speed", exc_info=True)
    write_history({"id": s["id"], "date": datetime.datetime.now().isoformat(timespec="seconds"),
                   "excerpt": s["text"][:110], "label": s["label"], "engine": eng.name,
                   "engine_kind": eng.kind, "voice": s.get("voice_label", s["voice"]), "wav": str(wav),
                   "mp3": str(mp3) if mp3 else None, "out_dir": s["out_dir"],
                   "duration": s["final"]["duration"], "sentences": len(sents(s))})


def write_captions(groups, out, stem, duration):
    """-> (sentence .srt path, word .srt path or None, one line on how exact the timings are).
    A problem here never stops the audio export."""
    try:
        cues, word_cues, exact = [], [], True
        for g in groups:
            its = g["items"]
            words = [w for w in (its[0].get("words") or []) if re.search(r"[A-Za-z0-9]", str(w[2]))]
            for w in words:
                word_cues.append((g["t0"] + w[0], g["t0"] + w[1], str(w[2])))
            texts = [it["text"] for it in its]
            spoken = [it.get("spoken") or it["text"] for it in its]
            if len(its) == 1:
                a, b = (g["t0"] + words[0][0], g["t0"] + words[-1][1]) if words else (g["t0"], g["t1"])
                cues.append((a, max(b, a + 0.2), texts[0]))
                continue
            got = captions.split_by_words(texts, spoken, words, g["t0"], g["t1"]) if words else None
            if got is None:
                got, _ = captions.split_by_pauses(texts, spoken, g["audio"], g["sr"], g["t0"])
                exact = False
            cues.extend(got)
        if not cues:
            return None, None, ""
        srt = out / f"{stem}.srt"
        srt.write_text(captions.to_srt(captions.pull_in(cues, duration)), encoding="utf-8")
        wpath = None
        if word_cues:
            wpath = out / f"{stem}.words.srt"
            wpath.write_text(captions.to_srt(captions.pull_in(word_cues, duration)), encoding="utf-8")
        note = ("Captions: sentence and word timings from the voice service." if word_cues and exact
                else "Captions: sentence timings from each sentence's own clip." if exact
                else "Captions: this voice came back as one piece without timings, so sentence times were "
                     "placed on the pauses in the audio. Check them before using.")
        return str(srt), str(wpath) if wpath else None, note
    except Exception:
        log.error("Captions could not be written\n%s", traceback.format_exc())
        return None, None, "Captions could not be written (see the log)."


def cloud_gate():
    """No queue, no retry: a cloud request made too soon is simply refused."""
    wait = CLOUD_MIN_GAP - (time.time() - _last_cloud["t"])
    if wait > 0:
        fail(429, f"Cloud safety rule: wait {wait:.0f} more second(s) before the next request.")


def work(job, s, eng, targets, variation, note=""):
    """Synthesise the target sentences of one session and export it. Raises on failure."""
    all_s = sents(s)
    table = pron.table()
    for i in targets:                                # written text stays; this is what gets spoken
        all_s[i]["spoken"], all_s[i]["subs"] = pron.apply(all_s[i]["text"], table)
    if eng.kind == "cloud":
        _last_cloud["t"] = time.time()
        job["message"] = "Sending one request"
        items = []
        for i in targets:
            idx = s["items"].index(all_s[i])
            nxt = s["items"][idx + 1] if idx + 1 < len(s["items"]) else None
            items.append({"text": all_s[i]["spoken"], "pause_after": bool(nxt and nxt["type"] == "pause")})
        chunks, sr = eng.synth_script(items, s["voice"], rate=s["rate"], pause_ms=s["pause_ms"],
                                      params=s.get("params") or {})
        _last_cloud["t"] = time.time()
        words = getattr(eng, "last_words", None)
        for k, (i, a) in enumerate(zip(targets, chunks)):
            all_s[i]["words"] = words[k] if isinstance(words, list) and len(words) == len(targets) else None
            store_sentence(s, all_s[i], i, a, sr, eng)
        s["merged"] = any(it.get("state") == "merged" for it in all_s)
        job["done"] = len(targets)
    else:
        job["message"] = note + "Loading engine..."
        engines.ensure_loaded(eng)
        for n, i in enumerate(targets):
            it = all_s[i]
            it["state"] = "working"
            it["words"] = None
            job["current"] = i
            job["message"] = f"{note}Sentence {n + 1} of {len(targets)}"
            try:
                a, sr = eng.synth(it["spoken"], s["voice"], rate=s["rate"], variation=variation,
                                  params=s.get("params") or {}, ref=s.get("ref"))
                store_sentence(s, it, i, a, sr, eng)
            except EngineError as e:
                it["state"], it["error"] = "error", str(e)
            if not note:
                job["done"] = n + 1
            job["session"] = public(s)
    failed = [it for it in all_s if it.get("state") == "error"]
    if not s["preview"]:
        if any(it.get("state") in (None, "pending", "working") for it in all_s):
            pass
        elif failed and len(failed) == len(all_s):
            raise EngineError(failed[0]["error"])
        else:
            job["message"] = note + "Joining and normalising"
            assemble(s, eng)
            s["delivery"] = extras.deliver(s["final"]["wav"], s.get("episode", ""), s.get("if_exists", "ask"))
            if s["delivery"]["status"] in ("copied", "error"):
                log.info("Video folder copy for %s: %s", s.get("episode"), s["delivery"])
    save_session(s)
    job["session"] = public(s)
    return failed


def record_failure(s, e):
    msg = str(e) if isinstance(e, EngineError) else f"{type(e).__name__}: {e}"
    log.error("Generation failed (%s / %s): %s\n%s", s["engine"], s["voice"], msg, traceback.format_exc())
    try:
        if s.get("out_dir"):
            from pathlib import Path
            with open(Path(s["out_dir"]) / "errors.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat()} {msg}\n{traceback.format_exc()}\n")
        save_session(s)
    except Exception:
        pass
    return msg


def run_job(job, s, eng, targets, variation):
    """targets = sentence indexes to synthesise."""
    try:
        failed = work(job, s, eng, targets, variation)
        job["status"] = "done"
        job["message"] = (f"{len(failed)} sentence(s) failed. Use Regenerate on them." if failed else "Done")
    except Exception as e:
        job.update(status="error", error=record_failure(s, e), session=public(s))
    finally:
        busy.release()


def run_batch(job, sessions, eng):
    """Several episodes one after another. Local engines only (checked before this starts)."""
    try:
        for n, s in enumerate(sessions):
            res = job["results"][n]
            res["state"] = "working"
            job["current_episode"] = s["label"]
            try:
                failed = work(job, s, eng, list(range(len(sents(s)))), False,
                              note=f"{s['label']} ({n + 1} of {len(sessions)}): ")
                f = s.get("final") or {}
                res.update(state="done", id=s["id"], wav=f.get("wav"), mp3=f.get("mp3"), srt=f.get("srt"),
                           duration=f.get("duration"), delivery=s.get("delivery"),
                           note=f"{len(failed)} sentence(s) failed" if failed else "")
            except Exception as e:
                res.update(state="error", error=record_failure(s, e))
            job["done"] = n + 1
        bad = sum(1 for r in job["results"] if r["state"] == "error")
        job.update(status="done", session=None,
                   message=f"Finished. {bad} of {len(sessions)} episode(s) failed." if bad else f"All {len(sessions)} episodes are done.")
    except Exception as e:
        log.error("Batch stopped\n%s", traceback.format_exc())
        job.update(status="error", error=f"{type(e).__name__}: {e}")
    finally:
        busy.release()


def start_job(s, eng, targets, variation=False):
    if setup_runner.S["running"] and eng.kind == "local":
        fail(409, "Engines are being downloaded. Local engines are available again when that finishes.")
    if eng.kind == "cloud":
        cloud_gate()
    if not busy.acquire(blocking=False):
        fail(409, "A generation is already running. Wait for it to finish.")
    if eng.kind == "cloud":
        _last_cloud["t"] = time.time()
    job = {"id": uuid.uuid4().hex[:12], "status": "running", "total": len(targets), "done": 0,
           "current": None, "message": "Starting", "error": None, "session": public(s)}
    jobs[job["id"]] = job
    for k in list(jobs)[:-30]:
        jobs.pop(k, None)
    threading.Thread(target=run_job, args=(job, s, eng, targets, variation), daemon=True).start()
    return job


# ---------------------------------------------------------------- API models
class ParseBody(BaseModel):
    name: str = ""
    text: Optional[str] = None
    b64: Optional[str] = None


class CheckBody(BaseModel):
    text: str


class GenBody(BaseModel):
    text: str
    engine: str
    voice: str
    rate: float = 1.0
    pause_ms: int = 700
    gap_ms: int = 150
    preview: bool = False
    mp3: bool = False
    label: str = "script"
    params: dict = {}
    episode: str = ""
    if_exists: str = "ask"          # copy to the video folder when the file is already there: ask | version | overwrite | skip


class BatchBody(BaseModel):
    text: str                       # the whole file, with its '## EPxx | Title' blocks
    engine: str
    voice: str
    rate: float = 1.0
    pause_ms: int = 700
    gap_ms: int = 150
    mp3: bool = False
    params: dict = {}
    episodes: list[str] = []        # empty = every episode in the file
    deliver: bool = True


class EstimateBody(BaseModel):
    text: str
    engine: str
    voice: str = ""
    rate: float = 1.0
    pause_ms: int = 700
    gap_ms: int = 150
    target: str = ""


class PresetBody(BaseModel):
    name: str
    engine: str = ""
    voice: str = ""
    rate: float = 1.0
    pause_ms: int = 700
    gap_ms: int = 150
    mp3: bool = False
    params: dict = {}
    target: str = ""


class VoicesBody(BaseModel):
    hidden: dict = {}


class PronBody(BaseModel):
    rows: list = []


class FolderBody(BaseModel):
    chunks_dir: str = ""


class DeliverBody(BaseModel):
    mode: str = "ask"
    episode: Optional[str] = None


class LastPresetBody(BaseModel):
    name: str = ""


class CmpChoice(BaseModel):
    engine: str
    voice: str
    params: dict = {}


class CmpBody(BaseModel):
    text: str
    choices: list[CmpChoice]
    rate: float = 1.0
    pause_ms: int = 700
    gap_ms: int = 150


class ProfileCheckBody(BaseModel):
    b64: str


class ProfileBody(BaseModel):
    token: Optional[str] = None
    name: str = ""
    consent: bool = False


class SetupBody(BaseModel):
    packs: list[str] = []


class RegenBody(BaseModel):
    index: int
    text: Optional[str] = None


class AzureBody(BaseModel):
    key: Optional[str] = None
    region: Optional[str] = None


class UpdateBody(BaseModel):
    repo: Optional[str] = None
    auto_check: Optional[bool] = None
    auto_install: Optional[bool] = None
    token: Optional[str] = None


# ---------------------------------------------------------------- API
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    p = settings.prefs()
    inst = installed_copy()
    return {"version": version(), "engines": [e.describe() for e in engines.all_engines()],
            "out_root": str(out_root()), "mp3": audio.mp3_available(), "keyring": settings.keyring_ok(),
            "azure": {"configured": bool(settings.get_secret("azure_key")),
                      "region": settings.get_secret("azure_region") or ""},
            "update": {"repo": updater.repo(), "auto_check": p.get("auto_check", True),
                       "auto_install": p.get("auto_install", True),
                       "token": bool(settings.get_secret("github_token"))},
            "busy": busy.locked(), "cloud_gap": CLOUD_MIN_GAP, "pid": os.getpid(),
            "root": str(ROOT), "data": str(DATA), "data_shared": DATA_SHARED,
            "installed": str(inst) if inst else "", "is_installed_copy": bool(inst and inst.resolve() == ROOT.resolve()),
            "pronunciations": pron.table(), "chunks_dir": extras.chunks_dir(),
            "presets": extras.presets(), "last_preset": p.get("last_preset", ""),
            "profiles": {"passage": profiles.PASSAGE, "consent": profiles.CONSENT,
                         "min_s": profiles.MIN_S, "max_s": profiles.MAX_S}}


@app.post("/api/parse")
def parse(b: ParseBody):
    name = b.name.lower()
    if b.b64 is not None:
        raw = base64.b64decode(b.b64)
        if len(raw) > 20_000_000:
            fail(413, "That file is too large for a script.")
        if name.endswith(".docx"):
            try:
                text = textproc.docx_to_text(raw)
            except Exception:
                fail(400, "Could not read that .docx file.")
        else:
            text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = b.text or ""
    return {"text": text, "episodes": textproc.parse_episodes(text)}


@app.post("/api/check")
def check(b: CheckBody):
    items = textproc.split_script(b.text)
    n = [it for it in items if it["type"] == "s"]
    words = sum(len(it["text"].split()) for it in n)
    return {"warnings": safecheck.check(b.text), "sentences": len(n), "words": words,
            "pauses": sum(1 for it in items if it["type"] == "pause"),
            "first": n[0]["text"] if n else ""}


def usable(eng):
    """Local engines load on demand, so only 'not installed' or 'no key' stop a request."""
    st = eng.status()
    if st["state"] in ("missing", "unconfigured"):
        fail(409, f"{eng.name}: {st['detail']}")


def resolve_voice(eng, voice):
    """-> (label for file names and history, reference WAV path or None)"""
    match = next((v for v in eng.voice_list() if v["id"] == voice), None)
    if not match:
        fail(400, "Pick a voice for this engine." if not eng.uses_profiles
             else "Pick a voice profile for this engine (or create one under Voice profiles).")
    if extras.is_hidden(eng.id, voice):
        fail(400, f"The voice {match['label']} is hidden (Settings, Voices), so it is not used. Pick another voice or show it again.")
    if voice.startswith("p:"):
        try:
            return match["label"], str(profiles.ref_path(voice[2:]))
        except profiles.ProfileError as e:
            fail(400, str(e))
    return match["label"], None


def clean_params(eng, given):
    out = {}
    for p in eng.params:
        v = (given or {}).get(p["id"], p["default"])
        if p["type"] == "range":
            try:
                v = min(p["max"], max(p["min"], float(v)))
            except (TypeError, ValueError):
                v = p["default"]
        elif v not in {o["id"] for o in p["options"]}:
            v = p["default"]
        out[p["id"]] = v
    return out


def clamp(b):
    return (min(1.3, max(0.7, b.rate)), min(5000, max(0, b.pause_ms)), min(3000, max(0, b.gap_ms)))


def new_session(eng, b, text, label, vlabel, ref, preview=False, episode="", if_exists="ask"):
    items = textproc.split_script(text)
    if not any(it["type"] == "s" for it in items):
        fail(400, "There is no text to speak.")
    if preview:
        items = [next(it for it in items if it["type"] == "s")]
    label = re.sub(r"[^A-Za-z0-9_-]+", "", label)[:40] or "script"
    episode = (episode or "").strip()
    if episode and not extras.EPISODE.match(episode):
        fail(400, "The episode code may contain only letters, digits, - and _ (for example EP22).")
    if if_exists not in ("ask", "version", "overwrite", "skip"):
        fail(400, "Unknown choice for an existing file.")
    rate, pause_ms, gap_ms = clamp(b)
    return {"id": uuid.uuid4().hex[:12], "created": time.time(), "engine": eng.id, "engine_kind": eng.kind,
            "voice": b.voice, "voice_label": vlabel, "ref": ref, "params": clean_params(eng, b.params),
            "rate": rate, "pause_ms": pause_ms, "gap_ms": gap_ms, "preview": preview, "mp3": b.mp3,
            "label": label, "text": textproc.clean(text), "items": items,
            "episode": "" if preview else episode, "if_exists": if_exists}


@app.post("/api/generate")
def generate(b: GenBody):
    try:
        eng = engines.get(b.engine)
    except EngineError as e:
        fail(400, str(e))
    usable(eng)
    vlabel, ref = resolve_voice(eng, b.voice)
    s = new_session(eng, b, b.text, b.label, vlabel, ref, b.preview, b.episode, b.if_exists)
    return start_job(s, eng, list(range(len(sents(s)))))


@app.post("/api/generate_all")
def generate_all(b: BatchBody):
    """Every episode in a file, one after another. Local engines only."""
    try:
        eng = engines.get(b.engine)
    except EngineError as e:
        fail(400, str(e))
    if eng.kind != "local":
        fail(400, "Cloud safety rule: cloud voices are generated one episode per click. "
                  "Generate all episodes works with the engines that run on this PC.")
    usable(eng)
    vlabel, ref = resolve_voice(eng, b.voice)
    eps = textproc.parse_episodes(b.text.replace("\r", ""))
    if b.episodes:
        eps = [e for e in eps if e["id"] in set(b.episodes)]
    if not eps:
        fail(400, "No episodes found. Each one starts with a line like '## EP22 | Title' and its voiceover lines start with '> '.")
    if len(eps) > 60:
        fail(400, "That is more than 60 episodes in one go. Pick fewer.")
    if setup_runner.S["running"]:
        fail(409, "Engines are being downloaded. Local engines are available again when that finishes.")
    sessions = [new_session(eng, b, e["text"], e["id"], vlabel, ref, False,
                            e["id"] if b.deliver else "", "version") for e in eps]
    if not busy.acquire(blocking=False):
        fail(409, "A generation is already running. Wait for it to finish.")
    job = {"id": uuid.uuid4().hex[:12], "kind": "batch", "status": "running", "total": len(sessions), "done": 0,
           "current": None, "message": "Starting", "error": None, "session": None,
           "results": [{"episode": e["id"], "title": e["title"], "state": "pending"} for e in eps]}
    jobs[job["id"]] = job
    threading.Thread(target=run_batch, args=(job, sessions, eng), daemon=True).start()
    return job


@app.post("/api/estimate")
def estimate(b: EstimateBody):
    try:
        eng = engines.get(b.engine)
    except EngineError as e:
        fail(400, str(e))
    match = next((v for v in eng.voice_list() if v["id"] == b.voice), None)
    if not match:
        return {"empty": True}
    rate, pause_ms, gap_ms = clamp(b)
    return extras.estimate(b.text, eng, b.voice, match["label"], rate, pause_ms, gap_ms, b.target)


# ---------------------------------------------------------------- presets, voices, pronunciations, folders
@app.get("/api/presets")
def preset_list():
    return {"presets": extras.presets(), "last": settings.prefs().get("last_preset", "")}


@app.post("/api/presets")
def preset_save(b: PresetBody):
    try:
        return extras.save_preset(b.model_dump() if hasattr(b, "model_dump") else b.dict())
    except ValueError as e:
        fail(400, str(e))


@app.delete("/api/presets")
def preset_delete(name: str):
    extras.delete_preset(name)
    return {"deleted": True}


@app.post("/api/presets/last")
def preset_last(b: LastPresetBody):
    settings.set_prefs(last_preset=b.name)
    return {"saved": True}


@app.post("/api/settings/voices")
def voices_save(b: VoicesBody):
    known = {e.id: {v["id"] for v in e.voice_list()} for e in engines.all_engines()}
    clean = {}
    for eid, ids in (b.hidden or {}).items():
        if eid in known and isinstance(ids, list):
            keep = [str(i) for i in ids if str(i) in known[eid]]
            if keep:
                clean[eid] = sorted(set(keep))
    settings.set_prefs(hidden_voices=clean)
    return {"hidden": clean}


@app.post("/api/settings/pronunciations")
def pron_save(b: PronBody):
    return {"rows": pron.save(b.rows)}


@app.post("/api/settings/pronunciations/reset")
def pron_reset():
    return {"rows": pron.save(pron.DEFAULT)}


@app.post("/api/settings/folders")
def folders_save(b: FolderBody):
    try:
        return {"chunks_dir": extras.set_chunks_dir(b.chunks_dir)}
    except ValueError as e:
        fail(400, str(e))


@app.post("/api/sessions/{sid}/deliver")
def deliver(sid: str, b: DeliverBody):
    """Copy this take to the video folder. 'overwrite' only ever comes from the user's own choice."""
    s = load_session(sid)
    if not s.get("final"):
        fail(409, "This take has no finished file yet.")
    if b.episode is not None:
        ep = b.episode.strip()
        if ep and not extras.EPISODE.match(ep):
            fail(400, "The episode code may contain only letters, digits, - and _ (for example EP22).")
        s["episode"] = ep
    if b.mode not in ("ask", "version", "overwrite", "skip"):
        fail(400, "Unknown choice.")
    s["delivery"] = extras.deliver(s["final"]["wav"], s.get("episode", ""), b.mode)
    log.info("Video folder copy for %s (%s): %s", s.get("episode"), b.mode, s["delivery"])
    save_session(s)
    return public(s)


@app.get("/api/memory")
def memory():
    ram, commit = sysinfo.memory_free()
    return {"free_ram_gb": None if ram is None else round(ram, 1),
            "free_commit_gb": None if commit is None else round(commit, 1), "apps": sysinfo.top_apps(6)}


@app.get("/api/cleanup")
def cleanup_list():
    return extras.leftovers()


@app.post("/api/cleanup")
def cleanup_run():
    if busy.locked() or setup_runner.S["running"]:
        fail(409, "Wait for the current work to finish first.")
    engines.shutdown()                  # the light environment must not be in use while packages are removed
    return extras.remove_leftovers()


# ---------------------------------------------------------------- A/B compare
def run_compare(job, b, picks, items, cid):
    """The first two sentences with up to three engine/voice choices."""
    try:
        rate, pause_ms, gap_ms = clamp(b)
        d = SESSIONS / cid
        d.mkdir(parents=True, exist_ok=True)
        for n, (eng, voice, vlabel, ref, params) in enumerate(picks):
            res = job["results"][n]
            job["message"] = f"{eng.name}, {vlabel} ({n + 1} of {len(picks)})"
            try:
                if eng.kind == "cloud":
                    _last_cloud["t"] = time.time()
                    chunks, sr = eng.synth_script(items, voice, rate=rate, pause_ms=pause_ms, params=params)
                    _last_cloud["t"] = time.time()
                    full = np.concatenate([audio.mono(c) for c in chunks])
                else:
                    job["message"] = f"Loading {eng.name}..."
                    engines.ensure_loaded(eng)
                    job["message"] = f"{eng.name}, {vlabel} ({n + 1} of {len(picks)})"
                    parts = []
                    for k, it in enumerate(items):
                        a, sr = eng.synth(it["text"], voice, rate=rate, params=params, ref=ref)
                        a = audio.trim(audio.mono(a), sr)
                        if not eng.native_rate:
                            a, _ = audio.stretch(a, rate)
                        parts.append(audio.fade(a, sr))
                        if k + 1 < len(items):
                            parts.append(audio.silence(pause_ms if it.get("pause_after") else gap_ms, sr))
                    full = np.concatenate(parts)
                full, _ = audio.normalize(audio.resample(full, sr, audio.TARGET_SR), audio.TARGET_SR)
                audio.write_wav(d / f"cmp_{n}.wav", full, audio.TARGET_SR)
                res.update(state="done", url=f"/api/audio/{cid}/cmp_{n}.wav?t={int(time.time())}",
                           duration=round(full.size / audio.TARGET_SR, 1))
            except Exception as e:
                msg = str(e) if isinstance(e, EngineError) else f"{type(e).__name__}: {e}"
                log.error("Compare failed for %s: %s\n%s", eng.id, msg, traceback.format_exc())
                res.update(state="error", error=msg)
            job["done"] = n + 1
        job.update(status="done", message="Done")
    finally:
        busy.release()


@app.post("/api/compare")
def compare(b: CmpBody):
    if not 1 <= len(b.choices) <= 3:
        fail(400, "Choose one to three voices to compare.")
    sents2 = [it for it in textproc.split_script(b.text)]
    first, items = [], []
    for it in sents2:
        if it["type"] == "pause":
            if items:
                items[-1]["pause_after"] = True
            continue
        if len(items) == 2:
            break
        items.append({"text": pron.apply(it["text"])[0], "shown": it["text"], "pause_after": False})
    if not items:
        fail(400, "There is no text to speak.")
    if len(items) == 2:
        items[1]["pause_after"] = False
    picks = []
    for c in b.choices:
        try:
            eng = engines.get(c.engine)
        except EngineError as e:
            fail(400, str(e))
        usable(eng)
        vlabel, ref = resolve_voice(eng, c.voice)
        picks.append((eng, c.voice, vlabel, ref, clean_params(eng, c.params)))
    clouds = [p for p in picks if p[0].kind == "cloud"]
    if len(clouds) > 1:
        fail(400, "Cloud safety rule: a comparison can include only one cloud voice, because each click may send only one cloud request.")
    if clouds:
        cloud_gate()
    if not busy.acquire(blocking=False):
        fail(409, "A generation is already running. Wait for it to finish.")
    if clouds:
        _last_cloud["t"] = time.time()
    job = {"id": uuid.uuid4().hex[:12], "status": "running", "total": len(picks), "done": 0, "message": "Starting",
           "error": None, "session": None, "text": " ".join(i["shown"] for i in items),
           "results": [{"label": f"{p[0].name}: {p[2]}", "state": "pending"} for p in picks]}
    jobs[job["id"]] = job
    threading.Thread(target=run_compare, args=(job, b, picks, items, uuid.uuid4().hex[:12]), daemon=True).start()
    return job


# ---------------------------------------------------------------- engines and voice profiles
@app.post("/api/engines/{eid}/activate")
def activate(eid: str):
    try:
        eng = engines.get(eid)
    except EngineError as e:
        fail(404, str(e))
    if eng.kind == "local" and not busy.locked() and eng.status()["state"] in ("idle", "error"):
        engines.activate_async(eng)
    return eng.status()


@app.post("/api/engines/{eid}/repair")
def repair(eid: str):
    """Download an engine's missing model files (pressed by the user)."""
    try:
        eng = engines.get(eid)
    except EngineError as e:
        fail(404, str(e))
    if not hasattr(eng, "repair") or not eng.status().get("repairable"):
        fail(409, "Nothing to download for this engine. If it is not installed at all, run Setup.bat.")
    if busy.locked():
        fail(409, "Wait for the current generation to finish first.")
    threading.Thread(target=eng.repair, daemon=True).start()
    time.sleep(0.3)
    return eng.status()


@app.get("/api/setup")
def setup_status():
    return setup_runner.status()


@app.post("/api/setup")
def setup_start(b: SetupBody):
    if busy.locked():
        fail(409, "Wait for the current generation to finish first.")
    try:
        setup_runner.start(b.packs)
    except ValueError as e:
        fail(400, str(e))
    return setup_runner.status()


@app.get("/api/profiles")
def profile_list():
    return profiles.all_profiles()


@app.post("/api/profiles/check")
def profile_check(b: ProfileCheckBody):
    raw = base64.b64decode(b.b64)
    if len(raw) > 60_000_000:
        fail(413, "That recording is too large. Keep it between 10 and 30 seconds.")
    try:
        return profiles.check_upload(raw)
    except profiles.ProfileError as e:
        fail(400, str(e))


@app.post("/api/profiles")
def profile_create(b: ProfileBody):
    try:
        return profiles.create(b.token, b.name, b.consent)
    except profiles.ProfileError as e:
        fail(400, str(e))


@app.patch("/api/profiles/{pid}")
def profile_rename(pid: str, b: ProfileBody):
    try:
        return profiles.rename(pid, b.name)
    except profiles.ProfileError as e:
        fail(400, str(e))


@app.delete("/api/profiles/{pid}")
def profile_delete(pid: str):
    try:
        profiles.delete(pid)
    except profiles.ProfileError as e:
        fail(404, str(e))
    return {"deleted": True}


@app.get("/api/profiles/{pid}/audio")
def profile_audio(pid: str):
    try:
        return FileResponse(profiles.ref_path(pid), media_type="audio/wav")
    except profiles.ProfileError as e:
        fail(404, str(e))


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    if jid not in jobs:
        fail(404, "Unknown job")
    return jobs[jid]


@app.post("/api/sessions/{sid}/regenerate")
def regenerate(sid: str, b: RegenBody):
    s = load_session(sid)
    eng = engines.get(s["engine"])
    all_s = sents(s)
    if not 0 <= b.index < len(all_s):
        fail(400, "Unknown sentence")
    if s.get("merged"):
        fail(409, "This take came back as one piece, so single sentences cannot be redone. Generate again.")
    if b.text is not None and b.text.strip():
        all_s[b.index]["text"] = textproc.clean(b.text)
    usable(eng)
    if s.get("ref") and not os.path.exists(s["ref"]):
        fail(409, "The voice profile used for this take has been deleted, so it cannot be redone.")
    all_s[b.index]["state"] = "pending"
    return start_job(s, eng, [b.index], variation=True)


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    return public(load_session(sid))


@app.get("/api/audio/{sid}/{fname}")
def sentence_audio(sid: str, fname: str):
    if not FNAME.match(fname):
        fail(404, "Not found")
    p = sdir(sid) / fname
    if not p.exists():
        fail(404, "Not found")
    return FileResponse(p, media_type="audio/wav")


@app.get("/api/sessions/{sid}/final")
def final_audio(sid: str, fmt: str = "wav"):
    s = load_session(sid)
    key = {"mp3": "mp3", "srt": "srt", "words": "srt_words"}.get(fmt, "wav")
    f = (s.get("final") or {}).get(key)
    if not f or not os.path.exists(f):
        fail(404, "The exported file has been moved or deleted.")
    kind = {"mp3": "audio/mpeg", "wav": "audio/wav"}.get(key, "application/x-subrip")
    return FileResponse(f, media_type=kind, filename=os.path.basename(f))


@app.post("/api/sessions/{sid}/open")
def open_folder(sid: str):
    d = load_session(sid).get("out_dir")
    if not d or not os.path.isdir(d):
        fail(404, "That folder no longer exists.")
    if os.name == "nt":
        os.startfile(d)  # noqa: S606  (opens Explorer on the app's own output folder)
    return {"opened": d}


@app.get("/api/history")
def history():
    out = []
    for e in read_history():
        e = dict(e)
        e["exists"] = os.path.exists(e["wav"])
        e["editable"] = (SESSIONS / e["id"] / "session.json").exists()
        out.append(e)
    return out


@app.post("/api/settings/azure")
def azure_save(b: AzureBody):
    if not settings.keyring_ok():
        fail(500, "Windows Credential Manager is not available, so the key was not saved.")
    if b.key:
        settings.set_secret("azure_key", b.key.strip())
    if b.region:
        settings.set_secret("azure_region", b.region.strip().lower().replace(" ", ""))
    return {"saved": True}


@app.delete("/api/settings/azure")
def azure_forget():
    settings.delete_secret("azure_key")
    settings.delete_secret("azure_region")
    return {"removed": True}


@app.post("/api/settings/azure/test")
def azure_test(b: AzureBody):
    cloud_gate()
    _last_cloud["t"] = time.time()
    try:
        return {"ok": True, "message": engines.get("azure").test(b.key or None, b.region or None)}
    except EngineError as e:
        return {"ok": False, "message": str(e)}


@app.post("/api/update/settings")
def update_settings(b: UpdateBody):
    try:
        if b.repo is not None:
            updater.set_repo(b.repo)
        if b.auto_check is not None:
            settings.set_prefs(auto_check=b.auto_check)
        if b.auto_install is not None:
            settings.set_prefs(auto_install=b.auto_install)
        if b.token is not None:
            (settings.set_secret("github_token", b.token.strip()) if b.token.strip()
             else settings.delete_secret("github_token"))
    except updater.UpdateError as e:
        fail(400, str(e))
    return {"saved": True}


@app.get("/api/update/check")
def update_check(force: bool = False):
    if not force and not settings.prefs().get("auto_check", True):
        return {"configured": bool(updater.repo()), "current": version(), "skipped": True}
    try:
        return updater.check(force=force)
    except updater.UpdateError as e:
        return {"configured": True, "current": version(), "error": str(e)}


@app.post("/api/update/apply")
def update_apply():
    if busy.locked():
        fail(409, "Wait for the current generation to finish first.")
    try:
        return updater.apply()
    except updater.UpdateError as e:
        fail(400, str(e))


MODE = {"desktop": False}            # set by app.desktop: restart into the window, not the browser


@app.post("/api/restart")
def restart_app():
    """Start a fresh copy of the app (used after an update) and end this one."""
    if busy.locked() or setup_runner.S["running"]:
        fail(409, "Wait for the current work to finish first.")
    import subprocess
    import sys
    env = dict(os.environ, VOICESTUDIO_AFTER_RESTART="1", VOICESTUDIO_NO_BROWSER="1")
    flags = (0x00000008 | 0x00000200) if os.name == "nt" else 0          # detached, own process group
    subprocess.Popen([sys.executable, "-m", "app.desktop" if MODE["desktop"] else "app.server"], cwd=str(ROOT),
                     env=env, creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info("Restarting Voice Studio")

    def stop():
        engines.shutdown()
        os._exit(0)
    threading.Timer(0.6, stop).start()
    return {"restarting": True}


@app.post("/api/quit")
def quit_app():
    def stop():
        engines.shutdown()
        os._exit(0)
    threading.Timer(0.4, stop).start()
    return {"bye": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")
if ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")


def clear_previews():
    """Preview takes and A/B comparisons are throwaway: remove the ones left
    from earlier runs, plus any temporary worker files."""
    import shutil
    for d in SESSIONS.iterdir():
        try:
            f = d / "session.json"
            if not f.exists() or json.loads(f.read_text(encoding="utf-8")).get("preview"):
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
    shutil.rmtree(DATA / "tmp", ignore_errors=True)


class _Tee:
    """Copy everything printed in the console window into a log file too."""
    def __init__(self, stream, fh):
        self.stream, self.fh = stream, fh

    def write(self, data):
        for t in (self.stream, self.fh):
            try:
                t.write(data)
                t.flush()
            except Exception:
                pass
        return len(data)

    def flush(self):
        pass

    def isatty(self):
        return False


def harden_console():
    """Keep a record of console output and crashes, and stop a stray click in
    the console window from freezing the app (Windows 'QuickEdit' pause)."""
    import faulthandler
    import sys
    d = log_dir()
    fh = open(d / "console.log", "a", encoding="utf-8", errors="replace")
    fh.write(f"\n===== start {datetime.datetime.now().isoformat(timespec='seconds')} =====\n")
    sys.stdout, sys.stderr = _Tee(sys.stdout, fh), _Tee(sys.stderr, fh)
    faulthandler.enable(file=open(d / "crash.log", "a", encoding="utf-8"), all_threads=True)
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-10)
            mode = ctypes.c_uint()
            if k.GetConsoleMode(h, ctypes.byref(mode)):
                k.SetConsoleMode(h, (mode.value & ~0x0040) | 0x0080)
        except Exception:
            pass


def already_running():
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((HOST, PORT)) == 0


def _ask(path, post=False, timeout=3):
    import urllib.request
    req = urllib.request.Request(f"http://{HOST}:{PORT}{path}", data=b"{}" if post else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if post else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def claim():
    """Who answers on our port? -> (own: start our own server, problem: text to show or '').

    Nothing running: we start. The same version from the same folder: join it
    (a second window). Anything else, an older version or another copy, is
    asked to stop so this one takes over; if it is in the middle of a
    generation it is left alone and the user is told."""
    if os.environ.pop("VOICESTUDIO_AFTER_RESTART", "") == "1":      # we were started by the copy that is closing
        for _ in range(100):
            if not already_running():
                break
            time.sleep(0.2)
    if not already_running():
        return True, ""
    try:
        st = _ask("/api/state")
    except Exception:
        return False, (f"Something else on this PC is using port {PORT}, so Voice Studio cannot start. "
                       "Close that program, or restart the PC.")
    theirs, their_root = st.get("version", "?"), st.get("root", "")
    if theirs == version() and their_root and os.path.normcase(their_root) == os.path.normcase(str(ROOT)):
        return False, ""
    what = f"Voice Studio {theirs}" + (f" from {their_root}" if their_root else " (an older copy)")
    if st.get("busy"):
        log.warning("%s is running and busy; not taking over", what)
        return False, (f"{what} is still running and is in the middle of a generation. Let it finish, quit it "
                       f"(Quit button, top right), then start Voice Studio {version()} again.")
    log.info("%s is running; asking it to stop so %s from %s can start", what, version(), ROOT)
    try:
        _ask("/api/quit", post=True)
    except Exception:
        pass
    for _ in range(60):
        if not already_running():
            time.sleep(0.4)
            return True, ""
        time.sleep(0.25)
    return False, (f"{what} is still running and did not stop when asked. End it in Task Manager "
                   f"(python.exe or pythonw.exe), then start Voice Studio {version()} again.")


CLI_BAT = ('@echo off\r\nrem Command-line access to the running Voice Studio app. Example:\r\n'
           'rem   voicestudio-cli generate --preset "WCGW - Harry" --in script.txt --episode EP22\r\n'
           '"%~dp0runtime\\Scripts\\python.exe" "%~dp0tools\\voicestudio_cli.py" %*\r\n')


def prepare():
    """Everything that has to happen before the server starts answering."""
    import atexit
    engines.discover()
    clear_previews()
    atexit.register(engines.shutdown)
    try:                                # an update from an older version does not bring this file itself
        bat = ROOT / "voicestudio-cli.bat"
        if not bat.exists() and (ROOT / "tools" / "voicestudio_cli.py").exists():
            bat.write_bytes(CLI_BAT.encode("ascii"))
    except Exception:
        pass
    log.info("Engines: %s", {e.id: e.status()["state"] for e in engines.all_engines()})
    log.info("Voice Studio %s starting on http://%s:%s/ from %s (data: %s)", version(), HOST, PORT, ROOT, DATA)


def main():
    """Browser mode: a console window plus a browser tab."""
    harden_console()
    url = f"http://{HOST}:{PORT}/"
    own, problem = claim()
    if problem:
        print("\n  " + problem + "\n")
        log.warning(problem)
        if os.name == "nt":
            os.system("pause")
        return
    if not own:                                      # this same copy is already running: just show it
        webbrowser.open(url)
        return
    prepare()
    if os.environ.get("VOICESTUDIO_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    import uvicorn
    print(f"\n  Voice Studio {version()} is running at {url}\n  Close this window to stop it.\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
