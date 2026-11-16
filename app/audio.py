"""Audio helpers on plain numpy arrays (mono float32, -1..1)."""
import numpy as np

TARGET_SR = 48000
TARGET_LUFS = -16.0
PEAK_CEILING = 10 ** (-1.0 / 20)   # -1 dBFS


def mono(a) -> np.ndarray:
    a = np.asarray(a, dtype=np.float32)
    if a.ndim > 1:
        a = a.reshape(-1) if 1 in a.shape else a.mean(axis=0 if a.shape[0] < a.shape[1] else 1)
    return np.nan_to_num(a)


def silence(ms: float, sr: int) -> np.ndarray:
    return np.zeros(max(0, int(sr * ms / 1000)), dtype=np.float32)


def resample(a: np.ndarray, sr: int, target: int) -> np.ndarray:
    if sr == target or a.size == 0:
        return a
    try:
        import soxr
        return soxr.resample(a, sr, target, quality="VHQ").astype(np.float32)
    except ImportError:
        pass
    try:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(sr, target)
        return resample_poly(a, target // g, sr // g).astype(np.float32)
    except ImportError:
        n = int(round(a.size * target / sr))
        return np.interp(np.linspace(0, a.size - 1, n), np.arange(a.size), a).astype(np.float32)


def trim(a: np.ndarray, sr: int, db: float = -45.0, keep_ms: float = 40) -> np.ndarray:
    """Remove silence at both ends so the gap controls decide the spacing."""
    if a.size == 0:
        return a
    thr = 10 ** (db / 20)
    win = max(1, sr // 100)
    n = a.size // win
    if n < 3:
        return a
    env = np.abs(a[: n * win]).reshape(n, win).max(axis=1)
    loud = np.nonzero(env > thr)[0]
    if loud.size == 0:
        return a
    keep = int(sr * keep_ms / 1000)
    start = max(0, loud[0] * win - keep)
    end = min(a.size, (loud[-1] + 1) * win + keep)
    return a[start:end]


def fade(a: np.ndarray, sr: int, ms: float = 6) -> np.ndarray:
    n = min(int(sr * ms / 1000), a.size // 2)
    if n < 2:
        return a
    a = a.copy()
    ramp = np.linspace(0, 1, n, dtype=np.float32)
    a[:n] *= ramp
    a[-n:] *= ramp[::-1]
    return a


def stretch(a: np.ndarray, rate: float):
    """Change speed without changing pitch. Returns (audio, applied)."""
    if abs(rate - 1.0) < 0.01 or a.size < 2048:
        return a, True
    try:
        import librosa
        return librosa.effects.time_stretch(a.astype(np.float32), rate=float(rate)).astype(np.float32), True
    except Exception:
        return a, False


def loudness(a: np.ndarray, sr: int):
    try:
        import pyloudnorm
        if a.size < int(sr * 0.5):
            return None
        v = float(pyloudnorm.Meter(sr).integrated_loudness(a.astype(np.float64)))
        return v if np.isfinite(v) else None
    except Exception:
        return None


def normalize(a: np.ndarray, sr: int, target: float = TARGET_LUFS):
    """Gain to the target loudness, then make sure peaks stay under -1 dBFS.
    Returns (audio, info)."""
    info = {"target_lufs": target, "before_lufs": None, "after_lufs": None, "limited": False}
    if a.size == 0:
        return a, info
    before = loudness(a, sr)
    info["before_lufs"] = before
    peak = float(np.abs(a).max()) or 1e-9
    gain = 10 ** ((target - before) / 20) if before is not None else (10 ** (-3 / 20)) / peak
    out = a * gain
    peak = float(np.abs(out).max())
    if peak > PEAK_CEILING:
        # soft-knee limiter: only the part above the knee is compressed
        knee = PEAK_CEILING * 0.8
        over = np.abs(out) > knee
        span = PEAK_CEILING - knee
        out = out.copy()
        out[over] = np.sign(out[over]) * (knee + span * np.tanh((np.abs(out[over]) - knee) / span))
        info["limited"] = True
    after = loudness(out, sr)
    info["after_lufs"] = after
    return out.astype(np.float32), info


def write_wav(path, a: np.ndarray, sr: int):
    import soundfile as sf
    sf.write(str(path), np.clip(a, -1, 1), sr, subtype="PCM_16")


def read_wav(path):
    import soundfile as sf
    a, sr = sf.read(str(path), dtype="float32", always_2d=False)
    return mono(a), sr


def write_mp3(path, a: np.ndarray, sr: int, kbps: int = 192):
    import lameenc
    enc = lameenc.Encoder()
    enc.set_bit_rate(kbps)
    enc.set_in_sample_rate(sr)
    enc.set_channels(1)
    enc.set_quality(2)
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes()
    data = enc.encode(pcm) + enc.flush()
    with open(path, "wb") as f:
        f.write(data)


def mp3_available() -> bool:
    try:
        import lameenc  # noqa: F401
        return True
    except ImportError:
        return False
