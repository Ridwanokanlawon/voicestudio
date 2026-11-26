"""Pronunciation list: words that are written one way and should be said
another ("MFA" -> "M F A"). Applied to every engine just before speaking. The
script on screen, the captions and the voice-safe check keep the written form."""
import re

from . import settings

DEFAULT = [["Geeki", "geeky"], ["MFA", "M F A"], ["Intune", "in tune"], ["Entra", "en tra"],
           ["SharePoint", "share point"], ["ESU", "E S U"], ["2FA", "two factor"]]
MAX_ROWS = 300


def table() -> list:
    t = settings.prefs().get("pronunciations")
    return clean(t) if isinstance(t, list) else [list(r) for r in DEFAULT]


def clean(rows) -> list:
    out, seen = [], set()
    for r in rows or []:
        try:
            w, s = str(r[0]).strip(), str(r[1]).strip()
        except Exception:
            continue
        if not w or not s or len(w) > 60 or len(s) > 120 or w.lower() in seen:
            continue
        seen.add(w.lower())
        out.append([w, s])
    return out[:MAX_ROWS]


def save(rows) -> list:
    t = clean(rows)
    settings.set_prefs(pronunciations=t)
    return t


def _exact(word: str) -> bool:
    """Short forms in capitals (MFA, ESU, 2FA) match only as written; ordinary
    words (Geeki, Intune) match in any letter case."""
    return word.upper() == word and any(c.isalpha() for c in word)


def apply(text: str, rows=None):
    """-> (text to speak, [{"from": written, "to": said}] in the order found)"""
    rows = table() if rows is None else rows
    if not rows or not text:
        return text, []
    exact = {w: s for w, s in rows if _exact(w)}
    loose = {w.lower(): s for w, s in rows if not _exact(w)}
    words = sorted([w for w, _ in rows], key=len, reverse=True)
    pat = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(w) for w in words) + r")(?![A-Za-z0-9])", re.I)
    subs = []

    def rep(m):
        got = m.group(1)
        to = exact.get(got) if got in exact else loose.get(got.lower())
        if to is None:
            return got
        subs.append({"from": got, "to": to})
        return to
    return pat.sub(rep, text), subs
