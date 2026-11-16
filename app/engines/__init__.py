"""Engine registry. Any .py file in this folder that defines ENGINE (an Engine
instance) is picked up automatically. Files starting with '_' are skipped."""
import importlib
import logging
import os
import pkgutil
import threading

from .base import Engine, EngineError  # noqa: F401

log = logging.getLogger("voicestudio")
_engines = {}
_load_lock = threading.Lock()
ORDER = {"chatterbox": 0, "openvoice": 1, "azure": 2}
REMOVED = {"yarngpt_engine"}          # retired engines: ignored even if the file is still on disk
SKIP = {"base", "worker"}


def discover():
    _engines.clear()
    for mod in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if mod.name.startswith("_") or mod.name in SKIP or mod.name in REMOVED:
            continue
        if mod.name.startswith("test_") and os.environ.get("VOICESTUDIO_TEST") != "1":
            continue
        try:
            m = importlib.import_module(f"{__name__}.{mod.name}")
            eng = getattr(m, "ENGINE", None)
            if eng is not None and eng.id:
                _engines[eng.id] = eng
        except Exception:
            log.exception("Engine %s failed to import", mod.name)


def all_engines():
    return [e for _, e in sorted(_engines.items(), key=lambda kv: ORDER.get(kv[0], 9))]


def get(engine_id: str) -> Engine:
    if engine_id not in _engines:
        raise EngineError(f"Unknown engine '{engine_id}'")
    return _engines[engine_id]


def ensure_loaded(eng: Engine):
    """Make this the one loaded local engine: unload the others first."""
    if eng.kind != "local":
        return
    with _load_lock:
        for other in all_engines():
            if other is not eng and other.kind == "local":
                try:
                    other.unload()
                except Exception:
                    log.exception("Could not unload %s", other.id)
        if eng.status()["state"] != "ready":
            log.info("Loading engine %s", eng.id)
            eng.load()
        st = eng.status()
        log.info("Engine %s: %s", eng.id, st)
        if st["state"] != "ready":
            raise EngineError(f"{eng.name} is not ready: {st['detail']}")


def activate_async(eng: Engine):
    if getattr(eng, "_state", None) in ("idle", "error"):      # show "Loading" straight away,
        eng._state, eng._detail = "loading", "Loading engine..."   # even while another engine unloads

    def run():
        try:
            ensure_loaded(eng)
        except Exception as e:
            log.warning("Activate %s: %s", eng.id, e)
    threading.Thread(target=run, daemon=True).start()


def shutdown():
    for e in all_engines():
        try:
            e.unload()
        except Exception:
            pass
