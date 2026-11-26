"""Memory facts about this PC (Windows): how much is free, and which apps are
using the most, so the app can say what to close when an engine cannot load."""
import csv
import io
import os
import re
import subprocess


def _status():
    import ctypes

    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
            (n, ctypes.c_ulonglong) for n in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile",
                                              "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual",
                                              "ullAvailExtendedVirtual")]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m


def memory_free():
    """(free RAM GB, free commit GB) on Windows, else (None, None)."""
    try:
        if os.name == "nt":
            m = _status()
            return m.ullAvailPhys / 2 ** 30, m.ullAvailPageFile / 2 ** 30
    except Exception:
        pass
    return None, None


def memory_note():
    """Free memory on this PC, to tell an out-of-memory stop from a real crash."""
    try:
        if os.name == "nt":
            m, g = _status(), 2 ** 30
            return (f"Memory: {m.ullAvailPhys / g:.1f} GB of {m.ullTotalPhys / g:.1f} GB RAM free, "
                    f"{m.ullAvailPageFile / g:.1f} GB of {m.ullTotalPageFile / g:.1f} GB commit free.")
    except Exception:
        pass
    return ""


NICE = {"chrome": "Google Chrome", "msedge": "Microsoft Edge", "msedgewebview2": "Edge WebView (apps built on Edge, Voice Studio's window included)",
        "firefox": "Firefox", "code": "VS Code", "teams": "Microsoft Teams", "ms-teams": "Microsoft Teams",
        "blender": "Blender", "resolve": "DaVinci Resolve", "claude": "Claude", "outlook": "Outlook", "olk": "Outlook",
        "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "onedrive": "OneDrive", "slack": "Slack",
        "discord": "Discord", "spotify": "Spotify", "explorer": "Windows Explorer", "vmmem": "Virtual machines (WSL, Docker or VirtualBox)",
        "vmmemwsl": "WSL (Linux on Windows)", "unrealeditor": "Unreal Editor", "ollama": "Ollama", "lm studio": "LM Studio",
        "python": "Python (may be a Voice Studio engine)", "pythonw": "Python (may be Voice Studio itself)",
        "msmpeng": "Windows Defender", "memory compression": "Windows memory compression", "dwm": "Windows desktop",
        "virtualboxvm": "VirtualBox", "photoshop": "Photoshop", "afterfx": "After Effects", "clo": "CLO"}
SKIP = {"system idle process", "system", "registry", "secure system"}


def parse_tasklist(text: str, n: int = 5):
    """`tasklist /FO CSV /NH` output -> [{"name", "gb", "count"}], biggest first.
    Processes with the same program name are added together (a browser is many)."""
    total = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 5:
            continue
        name = row[0].strip()
        digits = re.sub(r"[^0-9]", "", row[4])
        if not name or not digits or name.lower() in SKIP:
            continue
        key = re.sub(r"\.exe$", "", name, flags=re.I)
        t = total.setdefault(key.lower(), {"name": key, "kb": 0, "count": 0})
        t["kb"] += int(digits)
        t["count"] += 1
    top = sorted(total.values(), key=lambda t: t["kb"], reverse=True)[:n]
    return [{"name": NICE.get(t["name"].lower(), t["name"]), "gb": round(t["kb"] / 2 ** 20, 1), "count": t["count"]}
            for t in top if t["kb"] >= 150 * 1024]


def top_apps(n: int = 5):
    """The programs using the most memory right now. Empty off Windows or on any problem."""
    if os.name != "nt":
        return []
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=15,
                           errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        return parse_tasklist(r.stdout, n)
    except Exception:
        return []


def free_up_hint(n: int = 5) -> str:
    apps = top_apps(n)
    if not apps:
        return "Close other heavy apps (Task Manager, Memory column, shows which) or restart the PC."
    lst = ", ".join(f"{a['name']} {a['gb']:.1f} GB" for a in apps)
    return f"Free up memory: the biggest users right now are {lst}. Close the ones you do not need."
