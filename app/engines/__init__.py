"""Engine registry. Any .py file in this folder that defines ENGINE (an Engine
instance) is picked up automatically. Files starting with '_' are skipped."""
import importlib
import logging
import os
import pkgutil

from .base import Engine, EngineError  # noqa: F401

log = logging.getLogger("voicestudio")
_engines = {}


def discover():
    _engines.clear()
    for mod in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if mod.name.startswith("_") or mod.name == "base":
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
    order = {"yarn": 0, "azure": 1}
    return dict(sorted(_engines.items(), key=lambda kv: order.get(kv[0], 9)))


def all_engines():
    order = {"yarn": 0, "azure": 1}
    return [e for _, e in sorted(_engines.items(), key=lambda kv: order.get(kv[0], 9))]


def get(engine_id: str) -> Engine:
    if engine_id not in _engines:
        raise EngineError(f"Unknown engine '{engine_id}'")
    return _engines[engine_id]
