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


class WorkerEngine(Engine):
    env_name = ""           # folder under envs\
    worker = ""             # file under app\workers\
    needs: list = []        # model files (relative to models\) that must exist
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
        if not self.installed():
            return {"state": "missing", "detail": "Not installed. Run Setup.bat and choose this engine."}
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
                raise EngineError(f"{self.name} stopped unexpectedly. See worker_{self.id}.log in the log folder.")
            res = json.loads(line)
            if not res.get("ok"):
                raise EngineError(f"{self.name}: {res.get('error', 'unknown error')}")
            return res

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
        self._state, self._detail = "loading", "Loading engine..."
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
