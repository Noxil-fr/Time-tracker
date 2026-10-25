import threading
import time
from datetime import datetime
from typing import Callable

import psutil

_CHECKPOINT_INTERVAL = 60   # secondes entre chaque sauvegarde de checkpoint
_RAM_SAMPLE_INTERVAL = 30   # secondes entre deux relevés de RAM des processus non suivis
_SLEEP_GAP           = 60   # au-delà, un trou entre deux tours de boucle = mise en veille

_HELPER_PROCS = (
    "unitycrashandler",
    "crashreportclient",
    "unrealcefsubprocess",
    "easyanticheat",
    "battleye",
    "be_service",
    "gamelauncher",
    "gameoverlayui",
    "steam_api",
)

# Applications gourmandes en RAM qui ne sont pas des jeux (journal des non suivis)
_NOT_GAMES = {
    "timetracker.exe", "explorer.exe", "discord.exe", "qbittorrent.exe", "msmpeng.exe",
    "nvcontainer.exe", "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "vivaldi.exe", "code.exe", "devenv.exe", "idea64.exe", "pycharm64.exe",
    "rider64.exe", "photoshop.exe", "blender.exe", "obs64.exe", "docker desktop.exe",
    "vmmem", "vmmemwsl", "teams.exe", "ms-teams.exe", "slack.exe", "spotify.exe",
    "whatsapp.exe", "telegram.exe", "vlc.exe", "outlook.exe", "winword.exe",
    "excel.exe", "powerpnt.exe", "onedrive.exe", "claude.exe", "deepl.exe",
    "python.exe", "pythonw.exe", "node.exe", "steam.exe", "steamwebhelper.exe",
    "epicgameslauncher.exe", "epicwebhelper.exe", "galaxyclient.exe",
    "galaxyclient helper.exe", "battle.net.exe", "eadesktop.exe", "ealauncher.exe",
    "upc.exe", "ubisoftconnect.exe", "riotclientservices.exe", "riotclientux.exe",
    "steelseriesggclient.exe", "steelseriesgg.exe", "icue.exe", "greenshot.exe",
}

_NOT_GAME_DIRS = (
    "\\nvidia corporation\\",
    "\\windows defender\\",
    "\\microsoft\\edge",
    "\\microsoft onedrive\\",
    "\\common files\\",
)


def _scan() -> dict:
    """Retourne {nom_process.lower(): (exe_path, pid)} pour tous les processus actifs."""
    procs = {}
    for p in psutil.process_iter(["name", "exe"]):
        try:
            name = p.info["name"]
            if name:
                procs[name.lower()] = (p.info.get("exe") or "", p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return procs


def _get_processes() -> dict:
    """Retourne {nom_process.lower(): exe_path} pour tous les processus actifs."""
    return {name: exe for name, (exe, _) in _scan().items()}


def _is_untracked_candidate(name: str, exe: str) -> bool:
    """Process qui pourrait être un jeu : exe connu, hors Windows, pas une appli connue."""
    if not exe or name in _NOT_GAMES:
        return False
    low = exe.lower()
    if low[1:3] != ":\\":                     # pas un vrai chemin (MemCompression, Registry…)
        return False
    if low[1:].startswith(":\\windows\\"):
        return False
    if any(d in low for d in _NOT_GAME_DIRS):
        return False
    return not any(h in name for h in _HELPER_PROCS)


def _create_time(pid: int) -> datetime | None:
    try:
        return datetime.fromtimestamp(psutil.Process(pid).create_time())
    except Exception:
        return None


def _peak_mb(pid: int) -> int:
    try:
        mem = psutil.Process(pid).memory_info()
        return int(getattr(mem, "peak_wset", mem.rss) / 2**20)
    except Exception:
        return 0


class ProcessTracker:
    def __init__(
        self,
        data_manager,
        on_game_start: Callable[[str], None],
        on_game_stop: Callable[[str, datetime, datetime], None],
        on_suggestion: Callable[[str, str, str], None] | None = None,
        journal=None,
        on_untracked_closed: Callable[[str, str, str, int], None] | None = None,
        on_data_changed: Callable[[], None] | None = None,
    ):
        self._dm = data_manager
        self._on_start = on_game_start
        self._on_stop = on_game_stop
        self._on_suggestion = on_suggestion
        self._journal = journal
        self._on_untracked_closed = on_untracked_closed
        self._on_data_changed = on_data_changed
        self._active: dict[str, datetime] = {}  # {nom_jeu: heure_debut}
        # {process: {"exe", "pid", "start", "peak_mb", "game"}} — jeux potentiels non ajoutés
        self._untracked: dict[str, dict] = {}
        self._suggested: set[str] = set()        # process names déjà suggérés
        self._suggested_games: set[str] = set()  # game names déjà suggérés
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

            # Non suivis : conservés en checkpoint, repris ou journalisés au prochain lancement
            if self._journal:
                self._journal.save_active(self._untracked, now)

        self._dm.clear_all_checkpoints()

    def get_active(self) -> dict:
        with self._lock:
            return dict(self._active)

    def get_snapshot(self) -> set:
        """Retourne l'ensemble des processus actuellement en cours (noms en minuscules)."""
        return set(_get_processes().keys())

    def _loop(self):
        # Construire la base de jeux connus en parallèle pour ne pas retarder le tracking
        if self._on_suggestion or self._journal:
            def _build():
                try:
                    from game_library import build_known_games
                    self._known_games = build_known_games()
                except Exception:
                    pass
            threading.Thread(target=_build, daemon=True).start()

        elapsed_since_checkpoint = 0
        elapsed_since_ram = _RAM_SAMPLE_INTERVAL
        prev_procs: set[str] = set()
        last_tick = datetime.now()
        first = True

        while self._running:
            now = datetime.now()
            running = {}
            try:
                running = _scan()
                if first and self._journal:
                    self._recover_untracked(running)
                if (now - last_tick).total_seconds() > _SLEEP_GAP:
                    self._split_on_sleep(last_tick, now, running)
                self._check(running)
            except Exception:
                pass
            first = False
            last_tick = now

            if self._journal:
                try:
                    sample = elapsed_since_ram >= _RAM_SAMPLE_INTERVAL
                    if sample:
                        elapsed_since_ram = 0
                    self._check_untracked(running, sample)
                except Exception:
                    pass

            if self._on_suggestion and self._known_games:
                try:
                    self._check_suggestions(running, prev_procs)
                except Exception:
                    pass
            prev_procs = set(running.keys())

            elapsed_since_checkpoint += 2
            elapsed_since_ram += 2
            if elapsed_since_checkpoint >= _CHECKPOINT_INTERVAL:
                elapsed_since_checkpoint = 0
                with self._lock:
                    if self._active:
                        self._dm.save_checkpoint(dict(self._active))
                    if self._journal:
                        self._journal.save_active(self._untracked, datetime.now())

            time.sleep(2)

    def _check_suggestions(self, running: dict, prev_procs: set[str]):
        """Détecte les nouveaux processus qui correspondent à des jeux connus non suivis."""
        process_map = self._dm.get_process_map()
        tracked = set(process_map.keys())

        # game_name -> (score, proc_name, exe)
        candidates: dict[str, tuple[int, str, str]] = {}

        ignored = self._dm.get_ignored_procs()
        for name_lower, (exe, _) in running.items():
            if name_lower in prev_procs:
                continue
            if name_lower in tracked or name_lower in self._suggested:
                continue
            if name_lower in ignored:
                continue
            if not exe:
                continue
            if any(h in name_lower for h in _HELPER_PROCS):
                continue
            game_name = self._known_games.lookup(exe)
            if not game_name or game_name in self._dm.get_games():
                continue
            if game_name in self._suggested_games:
                continue
            # Score par similarité du nom de l'exe avec le nom du jeu
            stem = name_lower[:-4] if name_lower.endswith(".exe") else name_lower
            g = "".join(c for c in game_name.lower() if c.isalnum())
            s = "".join(c for c in stem if c.isalnum())
            score = 2 if s == g else (1 if g in s or s in g else 0)
            if score > candidates.get(game_name, (-1, "", ""))[0]:
                candidates[game_name] = (score, name_lower, exe)

        for game_name, (_, proc_name, exe) in candidates.items():
            self._suggested.add(proc_name)
            self._suggested_games.add(game_name)
            self._on_suggestion(game_name, proc_name, exe)

    def _check(self, running: dict):
        process_map = self._dm.get_process_map()
        if not process_map:
            return

        with self._lock:
            # Jeux nouvellement lancés
            for proc, name in process_map.items():
                if proc in running and name not in self._active:
                    # Jeu ajouté pendant qu'il tournait : on reprend depuis le vrai début
                    pending = self._untracked.pop(proc, None)
                    self._active[name] = pending["start"] if pending else datetime.now()
                    self._on_start(name)
                    exe = running[proc][0]
                    if exe:
                        self._dm.batch_update_exe_paths({name: exe})

            # Jeux fermés (ou supprimés pendant la partie)
            for name in list(self._active):
                proc = next(
                    (p for p, n in process_map.items() if n == name), None
                )
                if proc is None and not self._dm.game_exists(name):
                    self._active.pop(name)
                    self._dm.clear_checkpoint(name)
                elif proc and proc not in running:
                    start = self._active.pop(name)
                    end = datetime.now()
                    self._dm.clear_checkpoint(name)
                    self._dm.record_session(name, start, end)
                    self._on_stop(name, start, end)

    # ── Mise en veille ────────────────────────────────────────────────────────

    def rename_game(self, old_name: str, new_name: str) -> bool:
        """Renomme le jeu ; si une partie est en cours, la session continue sous le nouveau nom."""
        with self._lock:
            if not self._dm.rename_game(old_name, new_name):
                return False
            if old_name in self._active:
                self._active[new_name] = self._active.pop(old_name)
                self._dm.clear_checkpoint(old_name)
            return True

    def _split_on_sleep(self, last_tick: datetime, now: datetime, running: dict):
        """Le PC s'est mis en veille : on coupe les sessions au dernier tour avant la veille."""
        process_map = self._dm.get_process_map()
        with self._lock:
            for name, start in list(self._active.items()):
                if (last_tick - start).total_seconds() >= 10 and self._dm.game_exists(name):
                    self._dm.record_session(name, start, last_tick)
                proc = next((p for p, n in process_map.items() if n == name), None)
                if proc in running:
                    self._active[name] = now          # toujours lancé : nouvelle session
                else:
                    self._active.pop(name)            # fermé pendant la veille
                    self._dm.clear_checkpoint(name)
            for proc, info in list(self._untracked.items()):
                self._close_untracked(proc, info, last_tick, notify=False)
                if proc in running:
                    info["start"] = now
                else:
                    del self._untracked[proc]
        if self._on_data_changed:
            self._on_data_changed()

    # ── Jeux non suivis (journal local) ───────────────────────────────────────

    def _settings(self) -> tuple[int, int]:
        min_minutes = self._dm.get_setting("untracked_min_minutes", 5)
        min_ram_mb  = self._dm.get_setting("untracked_min_ram_mb", 500)
        return int(min_minutes) * 60, int(min_ram_mb)

    def _lookup_game(self, exe: str) -> str | None:
        return self._known_games.lookup(exe) if self._known_games else None

    def _check_untracked(self, running: dict, sample_ram: bool):
        tracked = set(self._dm.get_process_map().keys())
        ignored = self._dm.get_ignored_procs()

        with self._lock:
            # Nouveaux processus candidats
            for name, (exe, pid) in running.items():
                if name in self._untracked or name in tracked or name in ignored:
                    continue
                if not _is_untracked_candidate(name, exe):
                    continue
                self._untracked[name] = {
                    "exe":     exe,
                    "pid":     pid,
                    "start":   _create_time(pid) or datetime.now(),
                    "peak_mb": 0,
                    "game":    None,
                }

            # Relevé du pic de RAM (le pic ne redescend jamais, même après Alt-Tab)
            if sample_ram:
                for info in self._untracked.values():
                    info["peak_mb"] = max(info["peak_mb"], _peak_mb(info["pid"]))
                    if not info["game"]:
                        info["game"] = self._lookup_game(info["exe"])

            # Processus fermés
            now = datetime.now()
            for name in list(self._untracked):
                if name in tracked or name in ignored:
                    del self._untracked[name]
                elif name not in running:
                    info = self._untracked.pop(name)
                    self._close_untracked(name, info, now, notify=True)

    def _close_untracked(self, proc: str, info: dict, end: datetime, notify: bool):
        min_secs, min_ram = self._settings()
        duration = int((end - info["start"]).total_seconds())
        if duration < min_secs:
            return
        game = info.get("game") or self._lookup_game(info["exe"])
        # Jeu de launcher (Steam, GOG…) : toujours gardé ; sinon il faut assez de RAM
        if not game and info["peak_mb"] < min_ram:
            return
        self._journal.add(proc, info["exe"], game, info["start"], end, info["peak_mb"])
        if notify and game and self._on_untracked_closed and not self._dm.game_exists(game):
            self._on_untracked_closed(game, proc, info["exe"], duration)

    def _recover_untracked(self, running: dict):
        """Au démarrage : reprend les sessions non suivies encore en cours, journalise les autres."""
        saved = self._journal.pop_active()
        for proc, s in saved.items():
            try:
                start = datetime.fromisoformat(s["start"])
                info  = {"exe": s.get("exe", ""), "pid": 0, "start": start,
                         "peak_mb": s.get("peak_mb", 0), "game": s.get("game") or None}
                current = running.get(proc)
                if current and current[0] == info["exe"]:
                    created = _create_time(current[1])
                    if created and abs((created - start).total_seconds()) < 5:
                        info["pid"] = current[1]
                        with self._lock:
                            self._untracked[proc] = info
                        continue
                self._close_untracked(proc, info, datetime.fromisoformat(s["checkpoint"]),
                                      notify=False)
            except Exception:
                pass
