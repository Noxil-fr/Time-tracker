import ctypes
import os
import sys

# ── Instance unique — AVANT tout import lourd (webview, tracker…) ─────────────
_MUTEX_NAME = "TimeTracker_SingleInstance_Mutex"
_mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    ctypes.windll.user32.MessageBoxW(
        0,
        "Time Tracker est déjà en cours d'exécution.\n"
        "Consultez l'icône dans la barre des tâches.",
        "Time Tracker",
        0x40,
    )
    sys.exit(0)

import webview

from api import Api
from data_manager import DataManager
from sync import SyncManager
from tracker import ProcessTracker
from tray import TrayManager, acquire_single_instance_lock, set_autostart, is_autostart_enabled, _is_frozen


def _resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def main():
    # acquire_single_instance_lock déjà effectué au niveau module — pas de double check

    start_hidden = "--minimized" in sys.argv

    dm      = DataManager()
    sync    = SyncManager(dm)
    api_obj = Api(dm, sync)

    tracker = ProcessTracker(
        dm,
        on_game_start = api_obj.on_game_start,
        on_game_stop  = api_obj.on_game_stop,
        on_suggestion = api_obj.on_suggestion,
    )
    api_obj.set_tracker(tracker)

    window = webview.create_window(
        "Time Tracker",
        url              = _resource_path("web/index.html"),
        js_api           = api_obj,
        width            = 700,
        height           = 1097,
        min_size         = (600, 500),
        background_color = "#11111b",
    )

    _quitting = [False]

    def _quit():
        _quitting[0] = True
        window.destroy()

    tray = TrayManager(window, quit_callback=_quit)

    def setup(w):
        def _on_closing():
            if _quitting[0]:
                return True  # laisser la fenêtre se fermer
            w.hide()
            return False  # bloquer la fermeture, réduire dans le tray

        w.events.closing += _on_closing

        tracker.start()
        tray.start()
        api_obj.set_tray(tray)

        if start_hidden:
            w.hide()

        if _is_frozen() and not is_autostart_enabled():
            set_autostart(True)

    webview.start(setup, window)
    tracker.stop()


if __name__ == "__main__":
    main()
