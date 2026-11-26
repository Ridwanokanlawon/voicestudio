"""Command-line access to the Voice Studio app that is already running.

  voicestudio-cli status
  voicestudio-cli presets
  voicestudio-cli generate --preset "WCGW - Harry" --in script.txt --episode EP22
  voicestudio-cli generate --preset "WCGW - George" --in episodes.md --all-episodes

It talks to the app on this PC (127.0.0.1) and nothing else, and prints one
JSON object. Every safety rule of the app applies unchanged, because the work
is done by the app itself: a cloud voice gets exactly one request per run, is
never retried, has to wait 3 seconds after the previous cloud request, and the
voice-safe check runs first. If that check has warnings for a cloud voice,
nothing is sent unless --accept-warnings is given.

Exit codes: 0 done, 1 failed, 2 app not running, 3 stopped by the voice-safe check.
"""
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = f"http://127.0.0.1:{os.environ.get('VOICESTUDIO_PORT', '8765')}"
_open = urllib.request.build_opener(urllib.request.ProxyHandler({}))     # never through a proxy: local only


class Stop(Exception):
    def __init__(self, code, **out):
        self.code, self.out = code, out


def call(path, body=None, method=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with _open.open(req, timeout=120) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read() or b"{}").get("detail", "")
        except Exception:
            detail = ""
        raise Stop(1, error=detail or f"The app answered with error {e.code}.")
    except Exception:
        raise Stop(2, error="Voice Studio is not running. Start it (Start menu or Desktop shortcut), then run this again.")


def loose(name):
    n = re.sub(r"[‐-―−-]+", "-", name or "").lower()
    return re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", n)).strip()


def read_script(path):
    if not os.path.isfile(path):
        raise Stop(1, error=f"File not found: {path}")
    raw = open(path, "rb").read()
    if path.lower().endswith(".docx"):
        r = call("/api/parse", {"name": os.path.basename(path), "b64": base64.b64encode(raw).decode()})
    else:
        r = call("/api/parse", {"name": os.path.basename(path), "text": raw.decode("utf-8-sig", errors="replace")})
    return r["text"].replace("\r", ""), r["episodes"]


def wait(job, quiet):
    last = ""
    while True:
        j = call("/api/jobs/" + job["id"])
        if not quiet and j.get("message") and j["message"] != last:
            last = j["message"]
            print(last, file=sys.stderr, flush=True)
        if j["status"] != "running":
            return j
        time.sleep(1.0)


def cmd_status(a):
    st = call("/api/state")
    return {"ok": True, "version": st["version"], "busy": st["busy"], "folder": st.get("root"), "data": st.get("data"),
            "video_folder": st.get("chunks_dir", ""),
            "engines": [{"id": e["id"], "name": e["name"], "kind": e["kind"], "state": e["status"]["state"],
                         "voices": [v["id"] for v in e["voices"]]} for e in st["engines"]]}


def cmd_presets(a):
    r = call("/api/presets")
    return {"ok": True, "last": r["last"], "presets": r["presets"]}


def cmd_generate(a):
    st = call("/api/state")
    presets = call("/api/presets")["presets"]
    p = next((x for x in presets if loose(x["name"]) == loose(a.preset)), None)
    if not p:
        raise Stop(1, error=f"No preset named '{a.preset}'.", presets=[x["name"] for x in presets])
    eng = next((e for e in st["engines"] if e["id"] == p["engine"]), None)
    if not eng:
        raise Stop(1, error=f"The preset uses the engine '{p['engine']}', which this copy of the app does not have.")
    text, episodes = read_script(a.infile)
    mp3 = p.get("mp3", False) if a.mp3 is None else a.mp3
    common = {"engine": p["engine"], "voice": p["voice"], "rate": p.get("rate", 1.0), "pause_ms": p.get("pause_ms", 700),
              "gap_ms": p.get("gap_ms", 150), "mp3": mp3, "params": p.get("params") or {}}
    base = {"preset": p["name"], "engine": eng["name"], "engine_kind": eng["kind"], "voice": p["voice"]}

    if a.all_episodes:
        if eng["kind"] != "local":
            raise Stop(1, error="Cloud safety rule: cloud voices are one episode per run. --all-episodes works with local engines only.", **base)
        if not episodes:
            raise Stop(1, error="This file has no '## EPxx | Title' episode blocks.", **base)
        job = wait(call("/api/generate_all", dict(common, text=text, deliver=not a.no_copy)), a.quiet)
        res = job.get("results") or []
        ok = job["status"] == "done" and all(r["state"] == "done" for r in res)
        return dict(base, ok=ok, message=job.get("message") or job.get("error"),
                    episodes=[{"episode": r["episode"], "state": r["state"], "wav": r.get("wav"), "mp3": r.get("mp3"),
                               "srt": r.get("srt"), "duration": r.get("duration"), "copied_to": (r.get("delivery") or {}).get("path"),
                               "error": r.get("error")} for r in res])

    episode = a.episode or ""
    label = re.sub(r"\.[^.]+$", "", os.path.basename(a.infile))
    if episodes:                                    # a file with episode blocks: speak only the chosen one
        pick = next((e for e in episodes if e["id"].lower() == episode.lower()), None)
        if not pick:
            raise Stop(1, error="This file holds several episodes. Choose one with --episode, or use --all-episodes (local engines).",
                       episodes=[e["id"] for e in episodes], **base)
        text, label, episode = pick["text"], pick["id"], pick["id"]
    elif episode:
        label = episode
    check = call("/api/check", {"text": text})      # the voice-safe check always runs first
    warnings = [{"sentence": w["index"] + 1, "reason": w["reason"], "text": w["sentence"]} for w in check["warnings"]]
    if warnings and eng["kind"] == "cloud" and not a.accept_warnings:
        raise Stop(3, error="The voice-safe check has warnings and this is a cloud voice, so nothing was sent. "
                            "Edit the script, or run again with --accept-warnings to send it as it is.",
                   warnings=warnings, **base)
    est = call("/api/estimate", dict(common, text=text, target=a.target if a.target is not None else p.get("target", "")))
    body = dict(common, text=text, label=label, episode="" if a.no_copy else episode, if_exists=a.if_exists)
    job = wait(call("/api/generate", body), a.quiet)        # exactly one generate request, never repeated here
    s = job.get("session") or {}
    f = s.get("final") or {}
    d = s.get("delivery") or {}
    if job["status"] != "done" or not f:
        raise Stop(1, error=job.get("error") or job.get("message") or "No file was produced.", warnings=warnings, **base)
    return dict(base, ok=True, episode=episode, wav=f["wav"], mp3=f.get("mp3"), srt=f.get("srt"),
                srt_words=f.get("srt_words"), captions=f.get("captions"), duration=f["duration"], lufs=f.get("lufs"),
                estimated=est.get("seconds"), fit=est.get("fit"), note=est.get("message"),
                copied_to=d.get("path"), copy_status=d.get("status"), copy_note=d.get("why") or d.get("suggest"),
                sentences=len(s.get("sentences") or []), message=job.get("message"), warnings=warnings)


def main():
    ap = argparse.ArgumentParser(prog="voicestudio-cli", description="Drive the running Voice Studio app from the command line.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="is the app running, which engines and voices are available")
    sub.add_parser("presets", help="list the saved presets")
    g = sub.add_parser("generate", help="generate a voiceover with a saved preset")
    g.add_argument("--preset", required=True, help='preset name, for example "WCGW - Harry"')
    g.add_argument("--in", dest="infile", required=True, help="script file: .txt, .md or .docx")
    g.add_argument("--episode", help="episode code, for example EP22. Picks that episode from a file with several, and names the copy in the video folder")
    g.add_argument("--all-episodes", action="store_true", help="every episode in the file, one after another (local engines only)")
    g.add_argument("--target", help='target length in seconds, for example 45 or 40-50 (only reported, nothing is changed)')
    g.add_argument("--if-exists", choices=["version", "skip", "overwrite"], default="version",
                   help="when EPxx_audio.wav is already in the video folder: keep it and save as _v2 (default), skip the copy, or overwrite")
    g.add_argument("--no-copy", action="store_true", help="do not copy to the video folder")
    g.add_argument("--mp3", dest="mp3", action="store_true", default=None, help="also save an MP3")
    g.add_argument("--no-mp3", dest="mp3", action="store_false", help="do not save an MP3")
    g.add_argument("--accept-warnings", action="store_true", help="send to a cloud voice even if the voice-safe check has warnings")
    g.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
    a = ap.parse_args()
    try:
        out, code = {"status": cmd_status, "presets": cmd_presets, "generate": cmd_generate}[a.cmd](a), 0
        if not out.get("ok", True):
            code = 1
    except Stop as e:
        out, code = dict(ok=False, **e.out), e.code
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
