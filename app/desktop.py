"""Voice Studio as a standalone window (no browser tab, no console).

Start with:  runtime\\Scripts\\pythonw.exe -m app.desktop
The same local server runs inside this process; the window is Windows' own
Edge WebView showing it. If the window component is missing, the app falls
back to opening in the browser."""
import os
import sys
import threading
import time

if sys.stdout is None:                      # pythonw has no console streams
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from . import server  # noqa: E402
from .paths import ASSETS  # noqa: E402

URL = f"http://{server.HOST}:{server.PORT}/"
APP_ID = "VoiceStudio.App"


def _serve():
    import uvicorn
    cfg = uvicorn.Config(server.app, host=server.HOST, port=server.PORT, log_level="warning", log_config=None)
    srv = uvicorn.Server(cfg)
    srv.install_signal_handlers = lambda: None
    srv.run()


def _set_icon(window):
    """Give the window and taskbar button the Voice Studio icon."""
    try:
        import ctypes
        ico = str(ASSETS / "voicestudio.ico")
        hwnd = int(window.native.Handle.ToInt64())
        u = ctypes.windll.user32
        u.LoadImageW.restype = ctypes.c_void_p
        u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        for size, which in ((32, 1), (16, 0)):
            h = u.LoadImageW(None, ico, 1, size, size, 0x10)      # IMAGE_ICON, LR_LOADFROMFILE
            if h:
                u.SendMessageW(hwnd, 0x80, which, h)              # WM_SETICON
    except Exception:
        server.log.info("Could not set the window icon", exc_info=True)


def main():
    server.harden_console()
    try:
        import webview
    except ImportError:
        server.log.warning("Window component (pywebview) is not installed; opening in the browser instead.")
        return server.main()
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    owner = not server.already_running()
    if owner:
        server.prepare()
        threading.Thread(target=_serve, daemon=True).start()
        for _ in range(100):
            if server.already_running():
                break
            time.sleep(0.1)
    server.log.info("Voice Studio %s window starting (%s)", server.version(), "own server" if owner else "joining running app")
    window = webview.create_window("Voice Studio", URL, width=1360, height=920, min_size=(980, 640),
                                   background_color="#1A1A1A", text_select=True)
    window.events.shown += lambda: _set_icon(window)
    test_out = os.environ.get("VOICESTUDIO_WINDOW_TEST")
    if test_out:                                 # used by the automated Windows test
        def probe():
            time.sleep(6)
            try:
                title = window.evaluate_js("document.title + '|' + document.querySelectorAll('.engine').length")
            except Exception as e:
                title = f"ERROR {e}"
            open(test_out, "w", encoding="utf-8").write(str(title))
            window.destroy()
        window.events.loaded += lambda: threading.Thread(target=probe, daemon=True).start()
    try:
        webview.start(private_mode=False, storage_path=str(server.DATA / "webview"))
    finally:
        if owner:
            server.engines.shutdown()
    os._exit(0)


if __name__ == "__main__":
    main()
