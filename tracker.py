import threading
import time
from datetime import datetime
from typing import Callable

import psutil


def _get_processes() -> dict:
    """Retourne {nom_process.lower(): exe_path} pour tous les processus actifs."""
    procs = {}
    for p in psutil.process_iter(["name", "exe"]):
        try:
            name = p.info["name"]
            if name:
                procs[name.lower()] = p.info.get("exe") or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return procs


class ProcessTracker:
    def __init__(
        self,
        data_manager,
        on_game_start: Callable[[str], None],
        on_game_stop: Callable[[str, datetime, datetime], None],
    ):
        self._dm = data_manager
        self._on_start = on_game_start
        self._on_stop = on_game_stop
        self._active: dict[str, datetime] = {}  # {nom_jeu: heure_debut}
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def get_active(self) -> dict:
        with self._lock:
            return dict(self._active)

    def get_snapshot(self) -> set:
        """Retourne l'ensemble des processus actuellement en cours (noms en minuscules)."""
        return set(_get_processes().keys())

    def _loop(self):
        while self._running:
            try:
                self._check()
            except Exception:
                pass
            time.sleep(2)

    def _check(self):
        process_map = self._dm.get_process_map()
        if not process_map:
            return

        running = _get_processes()

        with self._lock:
            # Jeux nouvellement lancés
            for proc, name in process_map.items():
                if proc in running and name not in self._active:
                    self._active[name] = datetime.now()
                    self._on_start(name)
                    exe = running[proc]
                    if exe:
                        self._dm.batch_update_exe_paths({name: exe})

            # Jeux fermés
            for name in list(self._active):
                proc = next(
                    (p for p, n in process_map.items() if n == name), None
                )
                if proc and proc not in running:
                    start = self._active.pop(name)
                    end = datetime.now()
                    self._dm.record_session(name, start, end)
                    self._on_stop(name, start, end)
