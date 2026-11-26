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


from ..sysinfo import free_up_hint, memory_free, memory_note  # noqa: E402,F401


class WorkerEngine(Engine):
    env_name = ""           # folder under envs\
    worker = ""             # file under app\workers\
    needs: list = []        # model files (relative to models\) that must exist
    min_free_gb = 6.0       # free memory (commit) needed to load; below this the load is refused
    fetch = ""              # file under app\workers\ that downloads this engine's model files
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
            return {"state": "missing", "detail": "Not installed. Open Engines (top right) to download it."}
        if self._state == "loading":
            return {"state": "loading", "detail": self._detail}
        if not self.installed():
            why = f" Last attempt: {self._fetch_error}" if getattr(self, "_fetch_error", "") else ""
            return {"state": "missing", "repairable": bool(self.fetch),
                    "detail": "Some of its model files are not downloaded yet. Press Download missing files (needs internet)." + why}
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
            self._detail = (f"Not enough free memory to load {self.name}: {commit:.1f} GB free, about "
                            f"{self.min_free_gb:.0f} GB needed. {free_up_hint()} Then select the engine again.")
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

    def repair(self):
        """Download whatever model files are missing, using the engine's own
        environment. Started only by the Download button in the app."""
        if not self.python().exists() or not self.fetch or self._state == "loading":
            return
        self._state, self._detail, self._fetch_error = "loading", "Downloading missing model files...", ""
        logf = log_dir() / f"fetch_{self.id}.log"
        try:
            env = dict(os.environ, VOICESTUDIO_MODELS=str(MODELS), VOICESTUDIO_FETCH="1", PYTHONUTF8="1",
                       PYTHONIOENCODING="utf-8")
            for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "PYTHONPATH"):
                env.pop(k, None)
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            with open(logf, "a", encoding="utf-8", errors="replace") as out:
                r = subprocess.run([str(self.python()), "-u", str(ROOT / "app" / "workers" / self.fetch)],
                                   stdout=out, stderr=subprocess.STDOUT, cwd=str(ROOT), env=env,
                                   creationflags=flags, timeout=3600)
            if r.returncode != 0 or not self.installed():
                lines = [l.strip() for l in logf.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
                errs = [l for l in lines if "Error" in l or "FAILED" in l]
                self._fetch_error = (errs[-1] if errs else lines[-1] if lines else "unknown problem")[:220]
                log.error("Download for %s failed: %s", self.id, self._fetch_error)
        except Exception as e:
            self._fetch_error = f"{type(e).__name__}: {e}"[:220]
            log.exception("Download for %s failed", self.id)
        self._state, self._detail = "idle", "Loads when selected"

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
