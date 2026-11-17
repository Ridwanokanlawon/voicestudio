"""Tiny line protocol between Voice Studio and an engine worker process.

The main app writes one JSON object per line to the worker's stdin and reads
one JSON object per line back. Audio travels as WAV files on disk, never
through the pipe. Libraries that print to stdout are redirected to stderr so
they cannot corrupt the protocol. Workers use only their own environment."""
import json
import os
import sys
import traceback


def step(msg):
    """Progress line in the worker log, so a crash shows how far loading got."""
    import datetime
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def gpu_note():
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            return f"GPU {torch.cuda.get_device_name(0)}: {free / 2**30:.1f} GB free of {total / 2**30:.1f} GB"
        return "no CUDA GPU visible to this environment"
    except Exception as e:
        return f"GPU check failed: {e}"


def serve(handlers):
    """handlers: {'cmd': function(request_dict) -> result_dict}"""
    import faulthandler
    faulthandler.enable(file=sys.stderr, all_threads=True)   # a hard crash leaves a trace in the worker log
    step(f"worker started (python {sys.version.split()[0]})")
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)                      # anything else printed goes to the worker log
    sys.stdout = sys.stderr
    out.write(json.dumps({"ok": True, "hello": True}) + "\n")
    out.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("cmd") == "quit":
                out.write(json.dumps({"ok": True}) + "\n")
                out.flush()
                return
            res = handlers[req["cmd"]](req) or {}
            res["ok"] = True
        except Exception as e:
            traceback.print_exc()
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        out.write(json.dumps(res) + "\n")
        out.flush()


def offline(models_dir):
    """Models are loaded from the app folder only; no network at run time."""
    os.environ["HF_HOME"] = os.path.join(models_dir, "hf_cache")
    os.environ["TORCH_HOME"] = os.path.join(models_dir, "torch_cache")
    os.environ["NLTK_DATA"] = os.path.join(models_dir, "nltk_data")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    if os.environ.get("VOICESTUDIO_FETCH") != "1":
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"


def device():
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def device_name():
    import torch
    return torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU (slow, no NVIDIA GPU found)"
