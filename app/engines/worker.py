"""Base class for engines that run in their own Python environment as a
separate worker process (see app/workers). This keeps engines with clashing
package versions apart, and unloading an engine is simply ending its process."""
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import uuid

from .. import audio
from ..paths import DATA, MODELS, ROOT, log_dir
from .base import Engine, EngineError

log = logging.getLogger("voicestudio")
TMP = DATA / "tmp"


def memory_free():
    """(free RAM GB, free commit GB) on Windows, else (None, None)."""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                    (n, ctypes.c_ulonglong) for n in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile",
                                                      "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual",
                                                      "ullAvailExtendedVirtual")]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullAvailPhys / 2 ** 30, m.ullAvailPageFile / 2 ** 30
    except Exception:
        pass
    return None, None


def memory_note():
    """Free memory on this PC, to tell an out-of-memory stop from a real crash."""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                    (n, ctypes.c_ulonglong) for n in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile",
                                                      "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual",
                                                      "ullAvailExtendedVirtual")]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            g = 2 ** 30
            return (f"Memory: {m.ullAvailPhys / g:.1f} GB of {m.ullTotalPhys / g:.1f} GB RAM free, "
                    f"{m.ullAvailPageFile / g:.1f} GB of {m.ullTotalPageFile / g:.1f} GB commit free.")
    except Exception:
        pass
    return ""


class WorkerEngine(Engine):
    env_name = ""           # folder under envs\
    worker = ""             # file under app\workers\
    needs: list = []        # model files (relative to models\) that must exist
    min_free_gb = 6.0       # free memory (commit) needed to load; below this the load is refused
    load_timeout = 900
    synth_timeout = 600

    def __init__(self):
        self._proc = None
        self._q = None
        self._state = "idle"
        self._detail = "Loads when selected"
        self._io = threading.Lock()

    # ---- where things are
    def python(self):
        sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
        return ROOT / "envs" / self.env_name / sub[0] / sub[1]

    def installed(self):
        return self.python().exists() and all((MODELS / n).exists() for n in self.needs)

    def status(self):
        if not self.python().exists():
            return {"state": "missing", "detail": "Not installed. Close Voice Studio, run Setup.bat and choose this engine."}
        if not self.installed():
            return {"state": "missing", "detail": "Its download did not finish. Close Voice Studio and run Setup.bat again; it only fetches what is missing."}
        if self._proc is not None and self._proc.poll() is not None and self._state == "ready":
            self._state, self._detail = "error", "The engine process stopped. Select the engine again to restart it."
        return {"state": self._state, "detail": self._detail}

    # ---- process handling
    def _reader(self, proc, q):
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("{"):
                q.put(line)
        q.put(None)

    def _call(self, req, timeout):
        with self._io:
            if self._proc is None or self._proc.poll() is not None:
                raise EngineError(f"{self.name} is not running. Select the engine again.")
            self._proc.stdin.write(json.dumps(req) + "\n")
            self._proc.stdin.flush()
            try:
                line = self._q.get(timeout=timeout)
            except queue.Empty:
                self._kill()
                raise EngineError(f"{self.name} took too long and was stopped.")
            if line is None:
                raise EngineError(self._death_note())
            res = json.loads(line)
            if not res.get("ok"):
                raise EngineError(f"{self.name}: {res.get('error', 'unknown error')}")
            return res

    def _death_note(self):
        """Why did the worker process end? Exit code, memory and its last log line."""
        code = None
        try:
            code = self._proc.wait(timeout=5)
        except Exception:
            pass
        known = {0xC0000005: "access violation (a crash inside a library)", 0xC0000409: "the library aborted",
                 0xC000001D: "illegal instruction (the processor lacks a feature the library needs)",
                 0xC0000135: "a required DLL was not found", 0xC0000142: "a DLL failed to start",
                 0xC00000FD: "stack overflow", 0xC0000017: "not enough memory", 1: "Python error",
                 -9: "killed, usually out of memory", 137: "killed, usually out of memory"}
        u = code & 0xFFFFFFFF if isinstance(code, int) and code < 0 and os.name == "nt" else code
        why = known.get(u, known.get(code, "unknown reason"))
        last = ""
        try:
            lines = [l.strip() for l in (log_dir() / f"worker_{self.id}.log").read_text(
                encoding="utf-8", errors="replace").splitlines() if l.strip()]
            last = lines[-1][:160] if lines else ""
        except Exception:
            pass
        note = (f"{self.name} stopped while working (exit code {u if u is None else hex(u) if u > 255 else u}: {why}). "
                f"{memory_note()} Last log line: {last or 'none'}")
        log.error(note)
        return note

    def _kill(self):
        p, self._proc = self._proc, None
        if p is not None:
            try:
                p.kill()
            except Exception:
                pass

    def load(self):
        if not self.installed():
            return
        ram, commit = memory_free()
        if commit is not None and commit < self.min_free_gb:
            # loading now would crash this engine, and possibly the app with it
            self._state = "error"
            self._detail = (f"This PC is almost out of memory: {commit:.1f} GB free, and {self.name} needs about "
                            f"{self.min_free_gb:.0f} GB. Close other heavy apps (check Task Manager, Memory column) "
                            f"or restart the PC, then select the engine again.")
            log.warning("%s not loaded: %s", self.id, memory_note())
            return
        self._state, self._detail = "loading", "Loading engine..."
        log.info("Starting %s worker. %s", self.id, memory_note())
        try:
            self._kill()
            TMP.mkdir(parents=True, exist_ok=True)
            env = dict(os.environ, VOICESTUDIO_MODELS=str(MODELS), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            env.pop("PYTHONPATH", None)
            errlog = open(log_dir() / f"worker_{self.id}.log", "a", encoding="utf-8", errors="replace")
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._proc = subprocess.Popen(
                [str(self.python()), "-u", str(ROOT / "app" / "workers" / self.worker)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errlog, text=True, encoding="utf-8",
                cwd=str(ROOT), env=env, creationflags=flags)
            self._q = queue.Queue()
            threading.Thread(target=self._reader, args=(self._proc, self._q), daemon=True).start()
            if self._q.get(timeout=120) is None:
                raise EngineError("The engine process could not start.")
            res = self._call({"cmd": "load"}, self.load_timeout)
            self._state, self._detail = "ready", res.get("detail", "Ready")
        except Exception as e:
            self._kill()
            self._state = "error"
            self._detail = str(e) if isinstance(e, EngineError) else f"{type(e).__name__}: {e}"
            log.exception("%s failed to load", self.id)

    def unload(self):
        if self._proc is None:
            if self._state in ("ready", "loading", "error"):
                self._state, self._detail = "idle", "Loads when selected"
            return
        try:
            with self._io:
                self._proc.stdin.write('{"cmd": "quit"}\n')
                self._proc.stdin.flush()
            self._proc.wait(timeout=8)
        except Exception:
            pass
        self._kill()
        self._state, self._detail = "idle", "Loads when selected"

    def request(self, **req):
        """Ask the worker for one sentence; returns (audio, sample_rate)."""
        if self._state != "ready":
            raise EngineError(f"{self.name} is not ready: {self._detail}")
        out = TMP / f"{uuid.uuid4().hex}.wav"
        try:
            self._call(dict(req, cmd="synth", out=str(out)), self.synth_timeout)
            return audio.read_wav(out)
        finally:
            try:
                out.unlink()
            except OSError:
                pass
