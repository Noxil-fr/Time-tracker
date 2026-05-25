import json
from datetime import datetime
from pathlib import Path

DATA_FILE       = Path(__file__).parent / "data" / "games.json"
CHECKPOINT_FILE = Path(__file__).parent / "data" / "active_sessions.json"
SETTINGS_FILE   = Path(__file__).parent / "data" / "settings.json"

_MIN_RECOVERY_SECONDS = 10  # sessions < 10s ignorées à la récupération


class DataManager:
    def __init__(self):
        DATA_FILE.parent.mkdir(exist_ok=True)
        self._data = self._load()
        self._recover_checkpoints()

    def _load(self) -> dict:
        if DATA_FILE.exists():
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"games": {}}

    def _save(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

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
        self._save()
        return True

    def delete_game(self, name: str) -> bool:
        if name in self._data["games"]:
            del self._data["games"][name]
            self._save()
            return True
        return False

    def set_game_flag(self, name: str, flag: str, value) -> bool:
        if name not in self._data.get("games", {}):
            return False
        self._data["games"][name][flag] = value
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

    def set_games(self, games: dict) -> None:
        self._data["games"] = games
        self._save()

    def merge_games(self, remote_games: dict) -> int:
        """Fusionne les jeux distants dans les données locales (union des sessions).
        Retourne le nombre de jeux modifiés ou ajoutés."""
        merged = 0
        for name, remote in remote_games.items():
            if name not in self._data["games"]:
                self._data["games"][name] = remote
                merged += 1
            else:
                local = self._data["games"][name]
                local_starts = {s["start"] for s in local.get("sessions", [])}
                added = 0
                for s in remote.get("sessions", []):
                    if s["start"] not in local_starts:
                        local.setdefault("sessions", []).append(s)
                        added += 1
                if added:
                    local["total_seconds"] = sum(
                        s["duration"] for s in local["sessions"]
                    )
                    merged += 1
        if merged:
            self._save()
        return merged

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
        """{nom_jeu: secondes_à_ajouter} — incrémente total_seconds sans créer de sessions."""
        for name, added in updates.items():
            if name in self._data["games"] and added > 0:
                self._data["games"][name]["total_seconds"] += added
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
