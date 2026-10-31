import json
import os
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

# UNE seule source de données locale : DATA_FILE.
# Installé (frozen) : {exe}\data\ ; lancé depuis le code source : dossier de dev séparé,
# pour que le développement ne touche jamais aux vraies données.
if getattr(sys, "frozen", False):
    _DATA_DIR = Path(sys.executable).parent / "data"
else:
    _DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "TimeTracker-dev"

DATA_FILE       = _DATA_DIR / "games.json"
CHECKPOINT_FILE = _DATA_DIR / "active_sessions.json"
SETTINGS_FILE   = _DATA_DIR / "settings.json"
AUTH_FILE       = _DATA_DIR / "auth.json"
ARCHIVE_DIR     = _DATA_DIR / "archive"

_MIN_RECOVERY_SECONDS = 10  # sessions < 10s ignorées à la récupération


def _sessions_overlap(a: dict, b: dict) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def migrate_to_single_file(data_dir: Path = _DATA_DIR) -> dict | None:
    """Ancien format (games.json anonyme + games_<compte>.json) → un seul games.json.
    Le fichier du compte fait foi ; les sessions récupérées après crash qui étaient parties
    dans le fichier anonyme sont reprises si elles ne recoupent aucune session existante.
    Les anciens fichiers sont archivés (jamais supprimés sans copie). Retourne un résumé."""
    account_files = sorted(data_dir.glob("games_*.json"))
    if not account_files:
        return None

    data_file = data_dir / "games.json"
    owner = None
    try:
        owner = json.loads((data_dir / "auth.json").read_text(encoding="utf-8")).get("user_id")
    except Exception:
        pass
    chosen = next((f for f in account_files if owner and f.stem == f"games_{owner}"), None)
    if chosen is None:
        chosen = max(account_files, key=lambda f: f.stat().st_mtime)
        owner = chosen.stem[len("games_"):]

    data = json.loads(chosen.read_text(encoding="utf-8"))
    games = data.setdefault("games", {})

    # Sessions récupérées après crash écrites par erreur dans le fichier anonyme
    recovered, skipped = 0, 0
    if data_file.exists():
        try:
            anon = json.loads(data_file.read_text(encoding="utf-8")).get("games", {})
        except Exception:
            anon = {}
        all_sessions = [s for g in games.values() for s in g.get("sessions", [])]
        for name, g in anon.items():
            for s in g.get("sessions", []):
                if not s.get("recovered") or name not in games:
                    continue
                if any(_sessions_overlap(s, o) for o in all_sessions):
                    skipped += 1
                    continue
                games[name].setdefault("sessions", []).append(s)
                games[name]["sessions"].sort(key=lambda x: x["start"])
                games[name]["total_seconds"] = games[name].get("total_seconds", 0) + s["duration"]
                all_sessions.append(s)
                recovered += 1

    # 1. Copie d'archive  2. écriture atomique du fichier unique  3. retrait des anciens.
    # Un arrêt à n'importe quelle étape laisse les anciens fichiers : la migration se relance.
    archive = data_dir / "archive" / f"migration_{datetime.now():%Y%m%d_%H%M%S}"
    archive.mkdir(parents=True, exist_ok=True)
    for f in [data_file, *account_files]:
        if f.exists():
            shutil.copy2(f, archive / f.name)

    data["owner"] = owner
    data.setdefault("deleted", {})
    tmp = data_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, data_file)
    for f in account_files:
        f.unlink()

    return {"owner": owner, "games": len(games), "recovered": recovered,
            "skipped_overlap": skipped, "archive": str(archive)}


class DataManager:
    def __init__(self):
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._data_file = DATA_FILE
        self._save_lock = threading.Lock()
        try:
            self.migration = migrate_to_single_file()
        except Exception:
            self.migration = None   # anciens fichiers intacts : nouvel essai au prochain lancement
        self._data = self._load()
        self._data.setdefault("games", {})
        self._data.setdefault("deleted", {})
        self._data.setdefault("owner", None)
        self._recover_checkpoints()

    def _load(self) -> dict:
        if self._data_file.exists():
            with open(self._data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"owner": None, "games": {}, "deleted": {}}

    def _save(self):
        """Écriture atomique : le fichier est soit l'ancien, soit le nouveau, jamais à moitié écrit."""
        with self._save_lock:
            text = json.dumps(self._data, indent=2, ensure_ascii=False)
            tmp = self._data_file.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self._data_file)

    # ── Propriétaire des données (compte) ─────────────────────────────────────

    @property
    def owner(self) -> str | None:
        return self._data.get("owner")

    def bind_owner(self, user_id: str) -> bool:
        """Associe les données locales au compte. Refuse si elles appartiennent à un autre compte :
        on ne mélange jamais les données de deux comptes."""
        current = self._data.get("owner")
        if current and current != user_id:
            return False
        if current != user_id:
            self._data["owner"] = user_id
            self._save()
        return True

    # ── Récupération après crash ───────────────────────────────────────────────

    def _recover_checkpoints(self):
        """Lit active_sessions.json et injecte les sessions interrompues."""
        if not CHECKPOINT_FILE.exists():
            return
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                checkpoints = json.load(f)
            recovered = 0
            for name, info in checkpoints.items():
                if name not in self._data["games"]:
                    continue
                start    = datetime.fromisoformat(info["start"])
                end      = datetime.fromisoformat(info["checkpoint"])
                duration = int((end - start).total_seconds())
                if duration < _MIN_RECOVERY_SECONDS:
                    continue
                self._data["games"][name]["total_seconds"] += duration
                self._data["games"][name]["sessions"].append({
                    "start":     start.isoformat(),
                    "end":       end.isoformat(),
                    "duration":  duration,
                    "recovered": True,
                })
                recovered += 1
            if recovered:
                self._save()
        except Exception:
            pass
        finally:
            try:
                CHECKPOINT_FILE.unlink()
            except Exception:
                pass

    # ── Checkpoints périodiques ────────────────────────────────────────────────

    def save_checkpoint(self, active: dict) -> None:
        """Écrit {nom: {start, checkpoint}} pour toutes les sessions actives."""
        if not active:
            self.clear_all_checkpoints()
            return
        now = datetime.now().isoformat()
        data = {
            name: {"start": start.isoformat(), "checkpoint": now}
            for name, start in active.items()
        }
        try:
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def clear_checkpoint(self, name: str) -> None:
        """Retire un jeu du fichier de checkpoint (arrêt normal)."""
        try:
            if not CHECKPOINT_FILE.exists():
                return
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.pop(name, None)
            if data:
                with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                CHECKPOINT_FILE.unlink()
        except Exception:
            pass

    def clear_all_checkpoints(self) -> None:
        try:
            if CHECKPOINT_FILE.exists():
                CHECKPOINT_FILE.unlink()
        except Exception:
            pass

    # ── API principale ─────────────────────────────────────────────────────────

    def get_games(self) -> dict:
        return self._data["games"]

    def game_exists(self, name: str) -> bool:
        return name in self._data["games"]

    def add_game(self, name: str, process: str, exe_path: str = ""):
        self._data["games"][name] = {
            "process": process,
            "exe_path": exe_path,
            "total_seconds": 0,
            "sessions": [],
        }
        self._data["deleted"].pop(name, None)
        self._save()

    def record_session(self, name: str, start: datetime, end: datetime) -> int:
        duration = max(1, int((end - start).total_seconds()))
        self._data["games"][name]["total_seconds"] += duration
        self._data["games"][name]["sessions"].append(
            {
                "start": start.isoformat(),
                "end":   end.isoformat(),
                "duration": duration,
            }
        )
        self._save()
        return duration

    def rename_game(self, old_name: str, new_name: str) -> bool:
        if old_name not in self._data["games"]:
            return False
        if new_name in self._data["games"]:
            return False
        self._data["games"][new_name] = self._data["games"].pop(old_name)
        # L'ancien nom existe encore dans le cloud : il ne doit pas revenir à la fusion
        self._data["deleted"][old_name] = datetime.now().isoformat()
        self._data["deleted"].pop(new_name, None)
        self._save()
        return True

    def delete_game(self, name: str) -> bool:
        if name in self._data["games"]:
            del self._data["games"][name]
            # Mémorisé pour que la fusion avec le cloud ne le fasse pas réapparaître
            self._data["deleted"][name] = datetime.now().isoformat()
            self._save()
            return True
        return False

    def set_game_time(self, name: str, seconds: int) -> bool:
        if name not in self._data.get("games", {}):
            return False
        self._data["games"][name]["total_seconds"] = max(0, seconds)
        self._data["games"][name]["time_edited"] = True
        self._save()
        return True

    def set_game_flag(self, name: str, flag: str, value) -> bool:
        if name not in self._data.get("games", {}):
            return False
        self._data["games"][name][flag] = value
        self._save()
        return True

    def set_game_tracking(self, name: str, enabled: bool) -> bool:
        """Arrête ou reprend la détection d'un jeu. L'historique est conservé ;
        le process et l'exe sont mis de côté pour pouvoir reprendre le suivi."""
        game = self._data["games"].get(name)
        if not game:
            return False
        if enabled:
            if "paused_process" not in game:
                return False
            game["process"]  = game.pop("paused_process")
            game["exe_path"] = game.pop("paused_exe_path", "")
        else:
            if not game.get("process"):
                return False
            game["paused_process"]  = game["process"]
            game["paused_exe_path"] = game.get("exe_path", "")
            game["process"]  = ""
            game["exe_path"] = ""
        self._save()
        return True

    def batch_update_exe_paths(self, updates: dict):
        """Persiste {nom: exe_path} pour les jeux sans exe_path. Un seul _save()."""
        changed = False
        for name, exe in updates.items():
            if name in self._data["games"] and exe:
                if not self._data["games"][name].get("exe_path"):
                    self._data["games"][name]["exe_path"] = exe
                    changed = True
        if changed:
            self._save()

    def get_process_map(self) -> dict:
        """Retourne {process_lower: nom_du_jeu} — ignore les jeux sans process."""
        return {
            v["process"].lower(): k
            for k, v in self._data["games"].items()
            if v.get("process")
        }

    def reset_all_local_data(self) -> None:
        """Vide les données de jeux locales (après archivage) et les détache du compte."""
        if self._data["games"]:
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(self._data_file,
                             ARCHIVE_DIR / f"reset_{datetime.now():%Y%m%d_%H%M%S}.json")
            except Exception:
                pass
        self._data = {"owner": None, "games": {}, "deleted": {}}
        self._save()

    def merge_remote(self, remote_games: dict) -> int:
        """Fusionne les données du cloud dans les données locales. Ne supprime JAMAIS rien :
        - jeu absent en local → ajouté, sauf s'il a été supprimé/renommé ici ;
        - jeu présent des deux côtés → union des sessions (par heure de début).
        Le total n'est jamais recalculé : on ajoute seulement le temps des sessions reçues,
        ce qui préserve les temps modifiés à la main. Retourne le nombre de jeux modifiés."""
        changed = 0
        deleted = self._data["deleted"]
        for name, remote in remote_games.items():
            if not isinstance(remote, dict):
                continue
            local = self._data["games"].get(name)
            if local is None:
                if name in deleted:
                    continue
                self._data["games"][name] = remote
                changed += 1
                continue

            local_starts = {s["start"] for s in local.get("sessions", [])}
            added = [s for s in remote.get("sessions", []) if s["start"] not in local_starts]
            extra = sum(s["duration"] for s in added)

            remote_steam = remote.get("steam_seconds", 0)
            local_steam  = local.get("steam_seconds", 0)
            if remote_steam > local_steam:
                extra += remote_steam - local_steam
                local["steam_seconds"] = remote_steam

            if added:
                local.setdefault("sessions", []).extend(added)
                local["sessions"].sort(key=lambda s: s["start"])
            if extra:
                local["total_seconds"] = local.get("total_seconds", 0) + extra
            if added or extra:
                changed += 1
        if changed:
            self._save()
        return changed

    def import_sessions(self, name: str, sessions: list) -> int:
        """Ajoute des sessions récupérées (journal des non suivis). Retourne les secondes ajoutées."""
        game = self._data["games"].get(name)
        if not game:
            return 0
        existing = {s["start"] for s in game.get("sessions", [])}
        added = 0
        for s in sessions:
            if s["start"] in existing:
                continue
            game.setdefault("sessions", []).append({
                "start":     s["start"],
                "end":       s["end"],
                "duration":  s["duration"],
                "untracked": True,
            })
            added += s["duration"]
        if added:
            game["sessions"].sort(key=lambda s: s["start"])
            game["total_seconds"] = game.get("total_seconds", 0) + added
            self._save()
        return added

    def get_setting(self, key: str, default=None):
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f).get(key, default)
        except Exception:
            pass
        return default

    def get_ignored_procs(self) -> set[str]:
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return set(json.load(f).get("ignored_procs", []))
        except Exception:
            pass
        return set()

    def add_ignored_proc(self, proc_name: str) -> None:
        SETTINGS_FILE.parent.mkdir(exist_ok=True)
        try:
            existing = {}
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
        except Exception:
            pass
        procs = set(existing.get("ignored_procs", []))
        procs.add(proc_name.lower())
        existing["ignored_procs"] = sorted(procs)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

    def is_retro_dismissed(self, year: int) -> bool:
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return year in json.load(f).get("retro_dismissed_years", [])
        except Exception:
            pass
        return False

    def set_retro_dismissed(self, year: int) -> None:
        SETTINGS_FILE.parent.mkdir(exist_ok=True)
        try:
            existing = {}
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
        except Exception:
            pass
        dismissed = set(existing.get("retro_dismissed_years", []))
        dismissed.add(year)
        existing["retro_dismissed_years"] = sorted(dismissed)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

    def get_steam_config(self) -> dict:
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    s = json.load(f)
                return {"api_key": s.get("steam_api_key", ""),
                        "steam_id": s.get("steam_id", "")}
        except Exception:
            pass
        return {"api_key": "", "steam_id": ""}

    def save_steam_config(self, api_key: str, steam_id: str) -> None:
        SETTINGS_FILE.parent.mkdir(exist_ok=True)
        try:
            existing = {}
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
        except Exception:
            pass
        existing["steam_api_key"] = api_key
        existing["steam_id"]      = steam_id
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

    def apply_steam_import(self, updates: dict) -> None:
        """{nom_jeu: secondes_à_ajouter} — incrémente total_seconds et steam_seconds sans créer de sessions."""
        for name, added in updates.items():
            if name in self._data["games"] and added > 0:
                game = self._data["games"][name]
                game["steam_seconds"] = game.get("steam_seconds", 0) + added
                game["total_seconds"] += added
        self._save()

    def get_all_sessions_in_range(self, start_date: datetime, end_date: datetime) -> dict:
        """Retourne {nom_jeu: total_secondes} pour la période donnée."""
        totals = {}
        for name, data in self._data["games"].items():
            total = sum(
                s["duration"]
                for s in data["sessions"]
                if start_date <= datetime.fromisoformat(s["start"]) <= end_date
            )
            if total >= 900:
                totals[name] = total
        return totals
