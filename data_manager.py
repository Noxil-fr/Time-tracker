import json
from datetime import datetime
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "games.json"


class DataManager:
    def __init__(self):
        DATA_FILE.parent.mkdir(exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if DATA_FILE.exists():
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"games": {}}

    def _save(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

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
                "end": end.isoformat(),
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

    def delete_game(self, name: str):
        if name in self._data["games"]:
            del self._data["games"][name]
            self._save()

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
        """Retourne {exe_lower: nom_du_jeu}"""
        return {
            v["process"].lower(): k
            for k, v in self._data["games"].items()
        }

    def get_all_sessions_in_range(self, start_date: datetime, end_date: datetime) -> dict:
        """Retourne {nom_jeu: total_secondes} pour la période donnée."""
        totals = {}
        for name, data in self._data["games"].items():
            total = sum(
                s["duration"]
                for s in data["sessions"]
                if start_date <= datetime.fromisoformat(s["start"]) <= end_date
            )
            if total > 0:
                totals[name] = total
        return totals
