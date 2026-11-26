"""End-to-end check used by the build workflow (and usable by hand):
  runtime\\Scripts\\python.exe tools\\smoke_test.py [--install lite,openvoice] kokoro pocket
Starts Voice Studio, generates a short script with each named engine and checks
the exported file. Exits with 1 if anything fails. Standard library only."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
VOICE = {"kokoro": "bm_george", "pocket": "alba", "chatterbox": "builtin", "openvoice": "base"}
TEXT = "Your email filter checked every link. [pause] But this link was a picture."
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def main():
    args = sys.argv[1:]
    install = []
    if "--install" in args:
        i = args.index("--install")
        install = [x for x in args[i + 1].split(",") if x]
        del args[i:i + 2]
    engines = args or ["kokoro", "pocket"]
    out = Path(tempfile.mkdtemp(prefix="vs_smoke_"))
    env = dict(os.environ, VOICESTUDIO_NO_BROWSER="1", VOICESTUDIO_OUT=str(out), VOICESTUDIO_PORT=str(PORT))
    srv = subprocess.Popen([sys.executable, "-m", "app.server"], cwd=str(ROOT), env=env)
    failed = []
    try:
        for _ in range(60):
            try:
                if call("/api/state")[0] == 200:
                    break
            except Exception:
                time.sleep(1)
        st = call("/api/state")[1]
        print("version", st["version"], {e["id"]: e["status"]["state"] for e in st["engines"]}, flush=True)
        if install:
            t = time.time()
            code, r = call("/api/setup", {"packs": install})
            print("install from the app:", install, code, r.get("detail", ""), flush=True)
            last = ""
            while code == 200:
                r = call("/api/setup")[1]
                if r["step"] != last:
                    last = r["step"]
                    print(f"   [{r['elapsed']}s] {last}", flush=True)
                if not r["running"]:
                    break
                if time.time() - t > 3000:
                    r["error"] = "timed out"
                    break
                time.sleep(3)
            if code != 200 or r.get("error"):
                print("FAIL install:", r.get("error") or r, flush=True)
                print("\n".join(r.get("tail", [])), flush=True)
                failed.append("install")
            else:
                print(f"OK   install took {time.time() - t:.0f}s;",
                      {p["id"]: p["installed"] for p in r["packs"]}, flush=True)
        for eng in engines:
            t = time.time()
            code, job = call("/api/generate", {"text": TEXT, "engine": eng, "voice": VOICE[eng], "label": "smoke"})
            if code != 200:
                print(f"FAIL {eng}: {job}", flush=True)
                failed.append(eng)
                continue
            while True:
                j = call("/api/jobs/" + job["id"])[1]
                if j["status"] != "running":
                    break
                if time.time() - t > 1500:
                    j = {"status": "error", "error": "timed out after 25 minutes"}
                    break
                time.sleep(2)
            final = (j.get("session") or {}).get("final")
            if j["status"] == "done" and final and os.path.exists(final["wav"]):
                with wave.open(final["wav"]) as w:
                    secs, sr = w.getnframes() / w.getframerate(), w.getframerate()
                ok = sr == 48000 and secs > 2
                print(f"{'OK  ' if ok else 'FAIL'} {eng}: {secs:.1f}s at {sr} Hz, {final['lufs']} LUFS, "
                      f"took {time.time() - t:.0f}s", flush=True)
                if not ok:
                    failed.append(eng)
            else:
                print(f"FAIL {eng}: {j.get('error') or j.get('message')}", flush=True)
                failed.append(eng)
    finally:
        try:
            call("/api/quit", {})
        except Exception:
            pass
        time.sleep(1)
        srv.kill()
        logs = out / "VoiceStudio_logs"
        for f in sorted(logs.glob("worker_*.log")) + [logs / "voicestudio.log"]:
            if f.exists():
                lines = [l for l in f.read_text(encoding="utf-8", errors="replace").splitlines()
                         if l.startswith("[") or "ERROR" in l or "WARNING" in l or "Error" in l]
                print(f"--- {f.name}\n" + "\n".join(lines[-25:]), flush=True)
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    main()
