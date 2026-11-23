"""Extract a release and verify its normal launcher with a loopback test page."""

import ctypes
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from zipfile import ZipFile

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local_models"))
from server import EPSILON, S42, epsilon_opening
from verify_offline import available_models, react_model, verify_ranked_recommendations, wait


class TestPage(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/login':
            self.server.visits.append(self.headers.get('Cookie', ''))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Set-Cookie", "training_session=retained; Max-Age=600; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(b"<title>Local login test</title><label>Login<input></label>")


def close_window(pid):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    windows = []

    @callback_type
    def collect(window, unused):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(window):
            window_class = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(window, window_class, len(window_class))
            if window_class.value == 'Tauri Window':
                windows.append(window)
        return True

    user32.EnumWindows(collect, 0)
    assert windows, "Client window not found"
    for window in windows:
        if not user32.PostMessageW(window, 0x0010, 0, 0):
            raise ctypes.WinError(ctypes.get_last_error())


def run(package, web, exercise_recovery):
    env = {k: v for k, v in os.environ.items() if k.upper() not in {
        "JAVA_HOME", "JDK_HOME", "PYTHONHOME", "PYTHONPATH", "DJL_CACHE_DIR", "ENGINE_CACHE_DIR"}}
    env["PATH"] = str(Path(os.environ["WINDIR"]) / "System32")
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = '--no-proxy-server --host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"'
    starting_visit = len(web.visits)
    launcher = subprocess.Popen([str(package / "Zheyou.exe")], cwd=package, env=env)
    parent = psutil.Process(launcher.pid)
    children = []

    try:
        wait(lambda: len(web.visits) > starting_visit, seconds=30)
        print("One-click launcher opened the local test page", flush=True)
        if exercise_recovery:
            wait(lambda: {EPSILON, S42} <= available_models(), seconds=60)
            verify_ranked_recommendations()
            worker = next(p for p in parent.children(recursive=True)
                          if p.name().lower() == "python.exe" and any("epsilon_worker.py" in a for a in p.cmdline()))
            worker.kill()
            worker.wait(timeout=8)
            try:
                react_model(EPSILON, 0, epsilon_opening())
            except HTTPError as error:
                assert error.code == 503
            def recovered():
                try:
                    return react_model(EPSILON, 0, epsilon_opening()).get("candidates")
                except HTTPError as error:
                    assert error.code == 503
            assert wait(recovered, seconds=35)
            print("Epsilon recovered after forced worker exit", flush=True)
        else:
            assert "training_session=retained" in web.visits[starting_visit:][0], web.visits
            print("WebView login cookie survived a normal close and relaunch", flush=True)
        children = [(p, p.name().lower()) for p in parent.children(recursive=True)]
        ui = next(p for p, name in children if name == "zheyouclient.exe")
        close_window(ui.pid)
        assert launcher.wait(timeout=20) == 0
        for process, name in children:
            if name in ("python.exe", "pythonw.exe", "zheyouclient.exe"):
                process.wait(timeout=10)
        print("One-click launcher exited and both model processes stopped", flush=True)
    except Exception:
        for name in ("launcher.log", "local-models.log", "epsilon.log"):
            log = package / "app/logs" / name
            if log.exists():
                print(name, "\n", "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]), flush=True)
        raise
    finally:
        if launcher.poll() is None:
            for process in reversed(parent.children(recursive=True)):
                try:
                    process.kill()
                except psutil.NoSuchProcess:
                    pass
            launcher.kill()
            launcher.wait(timeout=10)


def main(archive_path):
    with TemporaryDirectory(prefix="zheyou-test-") as directory, ThreadingHTTPServer(("127.0.0.1", 0), TestPage) as web:
        web.visits = []
        Thread(target=web.serve_forever, daemon=True).start()
        try:
            with ZipFile(archive_path) as archive:
                archive.extractall(directory)
            package = Path(directory) / "zheyou-majsoul-windows-x64"
            config = package / "app/defaults/config.toml"
            config.write_text(config.read_text(encoding="utf-8").replace("https://game.maj-soul.com/1/",
                f"http://127.0.0.1:{web.server_port}/login"), encoding="utf-8")
            run(package, web, exercise_recovery=True)
            run(package, web, exercise_recovery=False)
        finally:
            web.shutdown()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
