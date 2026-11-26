"""Caption files (.srt) written next to the exported audio.

<name>.srt        one caption per sentence, always written.
<name>.words.srt  one caption per word, only when the engine reported real
                  word timings (Azure). Local engines give sentence timings."""
import re


def _ts(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues) -> str:
    out = []
    for n, (a, b, text) in enumerate(cues, 1):
        if b <= a:
            b = a + 0.05
        out.append(f"{n}\n{_ts(a)} --> {_ts(b)}\n{text.strip()}\n")
    return "\n".join(out)


def _alnum(s: str) -> int:
    return len(re.sub(r"[^A-Za-z0-9]", "", s))


def split_by_words(texts, spoken, words, t0, t1):
    """One clip that holds several sentences (a cloud voice that comes back as
    one piece). words = [[start, end, text]] inside that clip. Returns one
    (start, end, written text) per sentence, or None if the words do not line
    up with the sentences."""
    need = [_alnum(s) for s in spoken]
    have = sum(_alnum(w[2]) for w in words)
    if not words or not sum(need) or abs(have - sum(need)) > 0.12 * sum(need) + 4:
        return None
    cues, i, used, goal = [], 0, 0, 0
    for n, text in enumerate(texts):
        goal += need[n]
        start = None
        end = None
        while i < len(words) and (used < goal or n == len(texts) - 1):
            w = words[i]
            i += 1
            if not _alnum(w[2]):                 # punctuation carries no time of its own
                continue
            if start is None:
                start = w[0]
            end = w[1]
            used += _alnum(w[2])
            if used >= goal and n < len(texts) - 1:
                break
        if start is None:
            return None
        cues.append((t0 + start, min(t1, t0 + end), text))
    return cues


def split_by_length(texts, spoken, t0, t1):
    """No timings at all for the sentences inside one clip: share the clip out
    by how long each sentence is. An estimate, marked as such by the caller."""
    need = [max(1, _alnum(s)) for s in spoken]
    total, at, cues = sum(need), t0, []
    for text, n in zip(texts, need):
        d = (t1 - t0) * n / total
        cues.append((at, at + d, text))
        at += d
    return cues


def split_by_pauses(texts, spoken, a, sr, t0):
    """Several sentences inside one clip and no word timings: start from each
    sentence's share of the clip by length, then move every boundary to the
    nearest real pause in the audio. Returns (cues, snapped: how many of the
    boundaries landed on a pause)."""
    import numpy as np
    dur = a.size / sr
    cues = split_by_length(texts, spoken, 0.0, dur)
    if len(texts) < 2 or a.size < sr:
        return [(t0 + x, t0 + y, t) for x, y, t in cues], 0
    hop = int(sr * 0.02)
    n = a.size // hop
    env = np.sqrt((a[:n * hop].astype(np.float64) ** 2).reshape(n, hop).mean(axis=1) + 1e-12)
    quiet = env < max(10 ** (-42 / 20), 0.06 * float(np.percentile(env, 95)))
    gaps, k = [], 0                                   # [(middle time, length)] of pauses of 160 ms or more
    while k < n:
        if quiet[k]:
            j = k
            while j < n and quiet[j]:
                j += 1
            if (j - k) * 0.02 >= 0.16 and k > 0 and j < n:
                gaps.append(((k + j) * 0.01, (j - k) * 0.02))
            k = j
        else:
            k += 1
    bounds, snapped, last = [], 0, 0.0
    for x, y, _ in cues[:-1]:
        near = [g for g in gaps if abs(g[0] - y) <= max(1.2, 0.35 * (y - x)) and g[0] > last + 0.3]
        if near:
            g = max(near, key=lambda g: g[1] - 0.25 * abs(g[0] - y))
            gaps.remove(g)
            y, snapped = g[0], snapped + 1
        y = max(y, last + 0.2)
        bounds.append(y)
        last = y
    edges = [0.0] + bounds + [dur]
    return [(t0 + edges[i], t0 + edges[i + 1], t) for i, t in enumerate(texts)], snapped


def pull_in(cues, timeline_end):
    """Captions never overlap and never run past the audio."""
    out = []
    for k, (a, b, t) in enumerate(cues):
        nxt = cues[k + 1][0] if k + 1 < len(cues) else timeline_end
        out.append((a, max(a + 0.05, min(b, nxt)), t))
    return out
