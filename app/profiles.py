"""Voice profiles: a short reference recording of the user's own voice (or a
voice they have written permission to use). Stored only on this PC, in
data\\profiles. Nothing here is ever uploaded or put in a share zip."""
import datetime
import json
import re
import shutil
import uuid

import numpy as np

from . import audio
from .paths import DATA

DIR = DATA / "profiles"
PENDING = DATA / "tmp"
MIN_S, MAX_S = 10.0, 30.0
PID = re.compile(r"^[0-9a-f]{12}$")
PASSAGE = ("Good morning. My name is Ridwan, and I help small businesses keep their cloud systems safe and "
           "simple. Every week I look at one thing that could go wrong, why it happens, and the three fixes "
           "that stop it. Clear steps, no jargon, and nothing you can't do today.")
CONSENT = "This is my voice, or I have the speaker's written permission"


class ProfileError(Exception):
    pass


def _db(x):
    return 20 * np.log10(max(float(x), 1e-9))


def check(path):
    """Look at a recording and explain any problem in plain words.
    Returns (trimmed_audio, sample_rate, report)."""
    a, sr = audio.read_wav(path)
    problems = []
    if a.size < sr:
        return a, sr, {"ok": False, "duration": 0, "problems": [
            "The recording is empty or under one second. Check that the right microphone is selected."]}
    peak = float(np.abs(a).max())
    win = max(1, int(sr * 0.02))
    n = a.size // win
    rms = np.sqrt((a[: n * win].reshape(n, win) ** 2).mean(axis=1) + 1e-12)
    noise, speech = float(np.percentile(rms, 5)), float(np.percentile(rms, 90))
    snr = _db(speech) - _db(noise)
    clipped = float((np.abs(a) >= 0.985).mean())
    trimmed = audio.trim(a, sr, db=max(-50.0, min(-30.0, _db(noise) + 10)), keep_ms=150)
    dur = trimmed.size / sr
    if peak < 0.05:
        problems.append("The recording is very quiet. Move closer to the microphone or raise its level in Windows sound settings.")
    if clipped > 0.0005:
        problems.append("The recording is too loud and distorts (clipping). Move back a little or lower the microphone level.")
    if dur < MIN_S:
        problems.append(f"Only {dur:.0f} seconds of speech were found. Read the whole passage: 10 to 30 seconds are needed.")
    elif dur > MAX_S:
        problems.append(f"The recording has {dur:.0f} seconds of speech. Keep it between 10 and 30 seconds: read the passage once.")
    if peak >= 0.05 and (snr < 20 or _db(noise) > -38):
        problems.append("There is too much background noise (fan, traffic, music or room echo). Record somewhere quieter, close to the microphone.")
    report = {"ok": not problems, "problems": problems, "duration": round(dur, 1),
              "peak_db": round(_db(peak), 1), "noise_db": round(_db(noise), 1), "snr_db": round(snr, 1),
              "trimmed_s": round((a.size - trimmed.size) / sr, 1)}
    return trimmed, sr, report


def check_upload(wav_bytes: bytes):
    PENDING.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    raw = PENDING / f"upload_{token}.wav"
    raw.write_bytes(wav_bytes)
    try:
        trimmed, sr, report = check(raw)
    except Exception:
        raise ProfileError("That file could not be read as audio.")
    finally:
        raw.unlink(missing_ok=True)
    for old in PENDING.glob("pending_*.wav"):          # only the latest take is kept
        old.unlink(missing_ok=True)
    if report["ok"]:
        audio.write_wav(PENDING / f"pending_{token}.wav", trimmed, sr)
        report["token"] = token
    return report


def all_profiles():
    out = []
    if DIR.exists():
        for d in DIR.iterdir():
            try:
                out.append(json.loads((d / "profile.json").read_text(encoding="utf-8")))
            except Exception:
                pass
    return sorted(out, key=lambda p: p["created"], reverse=True)


def get(pid):
    if not PID.match(pid or "") or not (DIR / pid / "profile.json").exists():
        raise ProfileError("That voice profile no longer exists.")
    return json.loads((DIR / pid / "profile.json").read_text(encoding="utf-8"))


def ref_path(pid):
    get(pid)
    return DIR / pid / "ref.wav"


def create(token, name, consent):
    if consent is not True:
        raise ProfileError("Tick the consent box first: profiles are only for your own voice, or a voice you have written permission to use.")
    name = re.sub(r"\s+", " ", name or "").strip()[:40]
    if not name:
        raise ProfileError("Give the profile a name.")
    src = PENDING / f"pending_{token}.wav"
    if not PID.match(token or "") or not src.exists():
        raise ProfileError("Record or import the voice again, then save.")
    pid = uuid.uuid4().hex[:12]
    d = DIR / pid
    d.mkdir(parents=True)
    shutil.move(str(src), d / "ref.wav")
    a, sr = audio.read_wav(d / "ref.wav")
    p = {"id": pid, "name": name, "created": datetime.datetime.now().isoformat(timespec="seconds"),
         "duration": round(a.size / sr, 1), "consent": CONSENT,
         "consent_at": datetime.datetime.now().isoformat(timespec="seconds")}
    (d / "profile.json").write_text(json.dumps(p, indent=2), encoding="utf-8")
    return p


def rename(pid, name):
    p = get(pid)
    name = re.sub(r"\s+", " ", name or "").strip()[:40]
    if not name:
        raise ProfileError("Give the profile a name.")
    p["name"] = name
    (DIR / pid / "profile.json").write_text(json.dumps(p, indent=2), encoding="utf-8")
    return p


def delete(pid):
    get(pid)
    shutil.rmtree(DIR / pid)
