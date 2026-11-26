"""Self-update from GitHub Releases.

Only the app's own code is ever replaced. Models, the Python runtime, your
history, settings and scripts are never touched. The files being replaced are
copied to data/backups first, so an update can be undone by copying them back.

The only network calls are to api.github.com / github.com for the repository
named in update.json, and only when you press Check or leave the automatic
check switched on."""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

from . import settings
from .paths import DATA, ROOT, stamp, version

CONFIG = ROOT / "update.json"
UPDATABLE = ["app", "assets", "Setup.bat", "setup.ps1", "Voice Studio.bat", "Voice Studio (browser mode).bat",
             "Make Share Zip.bat", "make_share_zip.ps1", "requirements.txt", "requirements-chatterbox.txt",
             "requirements-openvoice.txt", "requirements-lite.txt", "installer", "tools", "voicestudio-cli.bat", "README.md", "LICENSES.md", "VERSION", ".gitignore"]
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_cache = {"at": 0, "result": None}


class UpdateError(Exception):
    pass


def repo() -> str:
    try:
        r = json.loads(CONFIG.read_text(encoding="utf-8")).get("repo", "").strip()
    except Exception:
        r = ""
    return r if REPO_RE.match(r) else ""


def set_repo(value: str):
    value = value.strip().removeprefix("https://github.com/").strip("/")
    if value and not REPO_RE.match(value):
        raise UpdateError("Use the form owner/repository, for example Ridwanokanlawon/voice-studio")
    CONFIG.write_text(json.dumps({"repo": value}, indent=2), encoding="utf-8")
    _cache["at"] = 0


def _ver(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4]) or (0,)


def _get(url: str, accept="application/vnd.github+json"):
    headers = {"User-Agent": "VoiceStudio-updater", "Accept": accept}
    token = settings.get_secret("github_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("No release found. The repository may be private, empty or misspelled.")
        if e.code in (403, 429):
            raise UpdateError("GitHub is asking to slow down. Try again in an hour.")
        raise UpdateError(f"GitHub answered with error {e.code}.")
    except Exception as e:
        raise UpdateError(f"Could not reach GitHub: {e}")


def check(force=False) -> dict:
    """At most one request every 6 hours unless the button is pressed."""
    r = repo()
    cur = version()
    if not r:
        return {"configured": False, "current": cur}
    if not force and _cache["result"] and time.time() - _cache["at"] < 6 * 3600:
        return _cache["result"]
    with _get(f"https://api.github.com/repos/{r}/releases/latest") as resp:
        rel = json.loads(resp.read())
    tag = rel.get("tag_name", "")
    res = {"configured": True, "repo": r, "current": cur, "latest": tag.lstrip("v"),
           "newer": _ver(tag) > _ver(cur), "notes": (rel.get("body") or "")[:1500],
           "page": rel.get("html_url", ""), "zip": rel.get("zipball_url", "")}
    _cache.update(at=time.time(), result=res)
    return res


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def apply() -> dict:
    info = check(force=True)
    if not info.get("newer"):
        return {"updated": False, "message": "You already have the latest version."}
    tmp = DATA / "updates" / f"{info['latest']}_{stamp()}"
    tmp.mkdir(parents=True)
    zpath = tmp / "update.zip"
    with _get(info["zip"], accept="application/octet-stream") as resp, open(zpath, "wb") as f:
        shutil.copyfileobj(resp, f)
    with zipfile.ZipFile(zpath) as z:
        base = (tmp / "x").resolve()
        for n in z.namelist():
            if not str((base / n).resolve()).startswith(str(base)):
                raise UpdateError("The update archive looks wrong. Nothing was changed.")
        z.extractall(base)
    tops = [d for d in base.iterdir() if d.is_dir()]
    if len(tops) != 1 or not (tops[0] / "app" / "server.py").exists():
        raise UpdateError("The release does not look like Voice Studio. Nothing was changed.")
    src = tops[0]
    backup = DATA / "backups" / f"{info['current']}_{stamp()}"
    backup.mkdir(parents=True)
    req_before = _sha(ROOT / "requirements.txt")
    for name in UPDATABLE:
        new, cur = src / name, ROOT / name
        if not new.exists():
            continue
        if cur.exists():                       # keep a copy of what is being replaced
            (shutil.copytree if cur.is_dir() else shutil.copy2)(cur, backup / name)
        if new.is_dir():
            shutil.copytree(new, cur, dirs_exist_ok=True)
        else:
            shutil.copy2(new, cur)
    pip = ""
    if _sha(ROOT / "requirements.txt") != req_before:
        p = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")],
                           capture_output=True, text=True)
        pip = "ok" if p.returncode == 0 else "failed: run Setup.bat"
    shutil.rmtree(tmp, ignore_errors=True)
    _cache["at"] = 0
    return {"updated": True, "from": info["current"], "to": info["latest"], "backup": str(backup),
            "packages": pip, "message": (f"Updated to {info['latest']}. Close Voice Studio and start it again."
                        + (" Then run Setup.bat once: this version needs a package that could not be installed automatically." if pip.startswith("failed") else ""))}
