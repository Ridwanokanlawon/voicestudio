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

from . import audio, engines, safecheck, settings, textproc, updater
from .engines.base import EngineError
from .paths import ASSETS, DATA, SESSIONS, STATIC, log_dir, new_out_dir, out_root, version

HOST = "127.0.0.1"
PORT = int(os.environ.get("VOICESTUDIO_PORT", "8765"))
CLOUD_MIN_GAP = 3.0            # seconds between cloud requests
HISTORY = DATA / "history.json"

log = logging.getLogger("voicestudio")
log.setLevel(logging.INFO)
_fh = logging.FileHandler(log_dir() / "voicestudio.log", encoding="utf-8")
_fh.setLevel(logging.WARNING)
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
FNAME = re.compile(r"^s\d{3}_r\d+\.wav$")


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
                    "url": f"/api/audio/{s['id']}/{it['file']}" if it.get("file") else None})
    return {"id": s["id"], "engine": s["engine"], "engine_kind": s["engine_kind"], "voice": s["voice"],
            "label": s["label"], "preview": s["preview"], "sentences": out, "final": s.get("final"),
            "merged": s.get("merged", False)}


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
    """Join all sentences into one file and export it."""
    parts, prev = [], False
    sr = None
    for it in s["items"]:
        if it["type"] == "pause":
            if not eng.self_timed and sr:
                parts.append(audio.silence(s["pause_ms"], sr))
            prev = False
            continue
        if not it.get("file"):
            continue
        a, sr = audio.read_wav(sdir(s["id"]) / it["file"])
        if prev and not eng.self_timed:
            parts.append(audio.silence(s["gap_ms"], sr))
        parts.append(a)
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
    stem = f"{s['label']}_{s['engine']}-{s['voice']}" + ("" if s["version"] == 1 else f"_v{s['version']}")
    wav = out / f"{stem}.wav"
    audio.write_wav(wav, full, audio.TARGET_SR)
    mp3 = None
    if s.get("mp3") and audio.mp3_available():
        mp3 = out / f"{stem}.mp3"
        audio.write_mp3(mp3, full, audio.TARGET_SR)
    s["final"] = {"wav": str(wav), "mp3": str(mp3) if mp3 else None, "name": wav.name,
                  "duration": round(full.size / audio.TARGET_SR, 2), "version": s["version"],
                  "lufs": None if info["after_lufs"] is None else round(info["after_lufs"], 1),
                  "limited": info["limited"], "out_dir": s["out_dir"],
                  "url": f"/api/sessions/{s['id']}/final?fmt=wav&v={s['version']}"}
    write_history({"id": s["id"], "date": datetime.datetime.now().isoformat(timespec="seconds"),
                   "excerpt": s["text"][:110], "label": s["label"], "engine": eng.name,
                   "engine_kind": eng.kind, "voice": s["voice"], "wav": str(wav),
                   "mp3": str(mp3) if mp3 else None, "out_dir": s["out_dir"],
                   "duration": s["final"]["duration"], "sentences": len(sents(s))})


def cloud_gate():
    """No queue, no retry: a cloud request made too soon is simply refused."""
    wait = CLOUD_MIN_GAP - (time.time() - _last_cloud["t"])
    if wait > 0:
        fail(429, f"Cloud safety rule: wait {wait:.0f} more second(s) before the next request.")


def run_job(job, s, eng, targets, variation):
    """targets = sentence indexes to synthesise."""
    try:
        all_s = sents(s)
        if eng.kind == "cloud":
            _last_cloud["t"] = time.time()
            job["message"] = "Sending one request"
            items = []
            for i in targets:
                idx = s["items"].index(all_s[i])
                nxt = s["items"][idx + 1] if idx + 1 < len(s["items"]) else None
                items.append({"text": all_s[i]["text"], "pause_after": bool(nxt and nxt["type"] == "pause")})
            chunks, sr = eng.synth_script(items, s["voice"], rate=s["rate"], pause_ms=s["pause_ms"])
            _last_cloud["t"] = time.time()
            for i, a in zip(targets, chunks):
                store_sentence(s, all_s[i], i, a, sr, eng)
            s["merged"] = any(it.get("state") == "merged" for it in all_s)
            job["done"] = len(targets)
        else:
            for n, i in enumerate(targets):
                it = all_s[i]
                it["state"] = "working"
                job["current"] = i
                job["message"] = f"Sentence {n + 1} of {len(targets)}"
                try:
                    a, sr = eng.synth(it["text"], s["voice"], rate=s["rate"], variation=variation)
                    store_sentence(s, it, i, a, sr, eng)
                except EngineError as e:
                    it["state"], it["error"] = "error", str(e)
                job["done"] = n + 1
                job["session"] = public(s)
        failed = [it for it in all_s if it.get("state") == "error"]
        if not s["preview"]:
            if any(it.get("state") in (None, "pending", "working") for it in all_s):
                pass
            elif failed and len(failed) == len(all_s):
                raise EngineError(failed[0]["error"])
            else:
                job["message"] = "Joining and normalising"
                assemble(s, eng)
        save_session(s)
        job["session"] = public(s)
        job["status"] = "done"
        job["message"] = (f"{len(failed)} sentence(s) failed. Use Regenerate on them." if failed else "Done")
    except Exception as e:
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
        job.update(status="error", error=msg, session=public(s))
    finally:
        busy.release()


def start_job(s, eng, targets, variation=False):
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


class RegenBody(BaseModel):
    index: int
    text: Optional[str] = None


class AzureBody(BaseModel):
    key: Optional[str] = None
    region: Optional[str] = None


class UpdateBody(BaseModel):
    repo: Optional[str] = None
    auto_check: Optional[bool] = None
    token: Optional[str] = None


# ---------------------------------------------------------------- API
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    p = settings.prefs()
    return {"version": version(), "engines": [e.describe() for e in engines.all_engines()],
            "out_root": str(out_root()), "mp3": audio.mp3_available(), "keyring": settings.keyring_ok(),
            "azure": {"configured": bool(settings.get_secret("azure_key")),
                      "region": settings.get_secret("azure_region") or ""},
            "update": {"repo": updater.repo(), "auto_check": p.get("auto_check", True),
                       "token": bool(settings.get_secret("github_token"))},
            "busy": busy.locked(), "cloud_gap": CLOUD_MIN_GAP}


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


@app.post("/api/generate")
def generate(b: GenBody):
    try:
        eng = engines.get(b.engine)
    except EngineError as e:
        fail(400, str(e))
    if b.voice not in {v["id"] for v in eng.voices}:
        fail(400, "Pick a voice for this engine.")
    st = eng.status()
    if st["state"] != "ready":
        fail(409, f"{eng.name} is not ready: {st['detail']}")
    items = textproc.split_script(b.text)
    if not any(it["type"] == "s" for it in items):
        fail(400, "There is no text to speak.")
    if b.preview:
        items = [next(it for it in items if it["type"] == "s")]
    label = re.sub(r"[^A-Za-z0-9_-]+", "", b.label)[:40] or "script"
    s = {"id": uuid.uuid4().hex[:12], "created": time.time(), "engine": eng.id, "engine_kind": eng.kind,
         "voice": b.voice, "rate": min(1.3, max(0.7, b.rate)), "pause_ms": min(5000, max(0, b.pause_ms)),
         "gap_ms": min(3000, max(0, b.gap_ms)), "preview": b.preview, "mp3": b.mp3, "label": label,
         "text": textproc.clean(b.text), "items": items}
    return start_job(s, eng, list(range(len(sents(s)))))


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
    f = (s.get("final") or {}).get("mp3" if fmt == "mp3" else "wav")
    if not f or not os.path.exists(f):
        fail(404, "The exported file has been moved or deleted.")
    return FileResponse(f, media_type="audio/mpeg" if fmt == "mp3" else "audio/wav",
                        filename=os.path.basename(f))


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


@app.post("/api/quit")
def quit_app():
    threading.Timer(0.4, lambda: os._exit(0)).start()
    return {"bye": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")
if ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")


def clear_previews():
    """Preview takes are throwaway: remove the ones left from earlier runs."""
    import shutil
    for d in SESSIONS.iterdir():
        try:
            if json.loads((d / "session.json").read_text(encoding="utf-8")).get("preview"):
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def main():
    url = f"http://{HOST}:{PORT}/"
    with socket.socket() as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((HOST, PORT)) == 0:       # already running: just show it
            webbrowser.open(url)
            return
    engines.discover()
    clear_previews()

    def warm():
        for e in engines.all_engines():
            try:
                e.load()
            except Exception:
                log.exception("Engine %s failed to load", e.id)
    threading.Thread(target=warm, daemon=True).start()
    if os.environ.get("VOICESTUDIO_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    import uvicorn
    print(f"\n  Voice Studio {version()} is running at {url}\n  Close this window to stop it.\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
