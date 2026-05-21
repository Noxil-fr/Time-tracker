import threading
import time
from datetime import datetime
from typing import Callable

import psutil

_CHECKPOINT_INTERVAL = 60   # secondes entre chaque sauvegarde de checkpoint


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
        on_suggestion: Callable[[str, str], None] | None = None,
    ):
        self._dm = data_manager
        self._on_start = on_game_start
        self._on_stop = on_game_stop
        self._on_suggestion = on_suggestion
        self._active: dict[str, datetime] = {}  # {nom_jeu: heure_debut}
        self._suggested: set[str] = set()
        self._known_games = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Arrête le tracker et flush toutes les sessions actives."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)

        # Sauvegarder les sessions encore actives au moment du Quitter
        now = datetime.now()
        with self._lock:
            for name, start in list(self._active.items()):
                duration = int((now - start).total_seconds())
                if duration >= 10:
                    try:
                        self._dm.record_session(name, start, now)
                        self._on_stop(name, start, now)
                    except Exception:
                        pass
            self._active.clear()

        self._dm.clear_all_checkpoints()

    def get_active(self) -> dict:
        with self._lock:
            return dict(self._active)

    def get_snapshot(self) -> set:
        """Retourne l'ensemble des processus actuellement en cours (noms en minuscules)."""
        return set(_get_processes().keys())

    def _loop(self):
        # Construire la base de jeux connus en parallèle pour ne pas retarder le tracking
        if self._on_suggestion:
            def _build():
                try:
                    from game_library import build_known_games
                    self._known_games = build_known_games()
                except Exception:
                    pass
            threading.Thread(target=_build, daemon=True).start()

        elapsed_since_checkpoint = 0
        prev_procs: set[str] = set()

        while self._running:
            running = {}
            try:
                running = _get_processes()
                self._check(running)
            except Exception:
                pass

            if self._on_suggestion and self._known_games:
                try:
                    self._check_suggestions(running, prev_procs)
                except Exception:
                    pass
            prev_procs = set(running.keys())

            elapsed_since_checkpoint += 2
            if elapsed_since_checkpoint >= _CHECKPOINT_INTERVAL:
                elapsed_since_checkpoint = 0
                with self._lock:
                    if self._active:
                        self._dm.save_checkpoint(dict(self._active))

            time.sleep(2)

    def _check_suggestions(self, running: dict, prev_procs: set[str]):
        """Détecte les nouveaux processus qui correspondent à des jeux connus non suivis."""
        process_map = self._dm.get_process_map()
        tracked = set(process_map.keys())

        for name_lower, exe in running.items():
            if name_lower in prev_procs:
                continue
            if name_lower in tracked or name_lower in self._suggested:
                continue
            if not exe:
                continue
            game_name = self._known_games.lookup(exe)
            if game_name:
                self._suggested.add(name_lower)
                self._on_suggestion(game_name, exe)

    def _check(self, running: dict):
        process_map = self._dm.get_process_map()
        if not process_map:
            return

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
                    self._dm.clear_checkpoint(name)
                    self._dm.record_session(name, start, end)
                    self._on_stop(name, start, end)
