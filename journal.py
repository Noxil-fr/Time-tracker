"""
Journal local des sessions de jeux non suivis (pas encore ajoutés).
Permet de récupérer le temps joué quand le jeu est ajouté après coup.
Stocké uniquement sur ce PC — jamais synchronisé.
"""
import json
import os
import threading
from datetime import datetime, timedelta

from data_manager import _DATA_DIR

JOURNAL_FILE = _DATA_DIR / "untracked_sessions.json"
ACTIVE_FILE  = _DATA_DIR / "untracked_active.json"

_RETENTION_DAYS = 30
_MERGE_GAP      = 120   # secondes — deux sessions séparées de moins sont fusionnées


def _write_atomic(path, data) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _read(path, default):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _matches(s: dict, proc: str, exe: str) -> bool:
    """Même exe (chemin) ; à défaut d'exe d'un côté, même nom de process."""
    s_exe = (s.get("exe") or "").lower()
    exe   = (exe or "").lower()
    if s_exe and exe:
        return s_exe == exe
    return s.get("process", "") == (proc or "").lower()


class UntrackedJournal:
    def __init__(self):
        self._lock = threading.Lock()
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._sessions: list = _read(JOURNAL_FILE, {}).get("sessions", [])
            self._purge()

    # ── Persistance ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            _write_atomic(JOURNAL_FILE, {"sessions": self._sessions})
        except Exception:
            pass

    def _purge(self) -> None:
        limit = (datetime.now() - timedelta(days=_RETENTION_DAYS)).isoformat()
        before = len(self._sessions)
        self._sessions = [s for s in self._sessions if s.get("end", "") >= limit]
        if len(self._sessions) != before:
            self._save()

    # ── Écriture ──────────────────────────────────────────────────────────────

    def add(self, proc: str, exe: str, game: str | None,
            start: datetime, end: datetime, peak_mb: int) -> None:
        duration = int((end - start).total_seconds())
        with self._lock:
            # Fusion avec la session précédente du même exe si la coupure est courte
            for s in reversed(self._sessions):
                if not _matches(s, proc, exe):
                    continue
                gap = (start - datetime.fromisoformat(s["end"])).total_seconds()
                if 0 <= gap < _MERGE_GAP:
                    s["end"]      = end.isoformat()
                    s["duration"] = s["duration"] + duration
                    s["peak_mb"]  = max(s.get("peak_mb", 0), peak_mb)
                    if game and not s.get("game"):
                        s["game"] = game
                    self._save()
                    return
                break
            self._sessions.append({
                "process":  proc.lower(),
                "exe":      exe,
                "game":     game or "",
                "start":    start.isoformat(),
                "end":      end.isoformat(),
                "duration": duration,
                "peak_mb":  peak_mb,
            })
            self._purge()
            self._save()

    def forget(self, proc: str) -> None:
        """Oublie toutes les sessions d'un process (« Ne plus proposer »)."""
        with self._lock:
            self._sessions = [s for s in self._sessions if s.get("process") != proc.lower()]
            self._save()

    def claim(self, proc: str, exe: str) -> list:
        """Retire et retourne les sessions correspondant à ce jeu (ajouté entre-temps)."""
        with self._lock:
            taken = [s for s in self._sessions if _matches(s, proc, exe)]
            if taken:
                self._sessions = [s for s in self._sessions if not _matches(s, proc, exe)]
                self._save()
            return taken

    # ── Lecture ───────────────────────────────────────────────────────────────

    def summary(self, proc: str, exe: str) -> dict:
        with self._lock:
            found = [s for s in self._sessions if _matches(s, proc, exe)]
        return {"count": len(found), "seconds": sum(s["duration"] for s in found)}

    # ── Sessions non suivies en cours (récupération après crash / redémarrage) ─

    def save_active(self, active: dict, now: datetime) -> None:
        data = {
            name: {
                "exe":        info["exe"],
                "start":      info["start"].isoformat(),
                "checkpoint": now.isoformat(),
                "peak_mb":    info["peak_mb"],
                "game":       info.get("game") or "",
            }
            for name, info in active.items()
        }
        try:
            if data:
                _write_atomic(ACTIVE_FILE, data)
            elif ACTIVE_FILE.exists():
                ACTIVE_FILE.unlink()
        except Exception:
            pass

    def pop_active(self) -> dict:
        """Lit puis supprime le fichier des sessions non suivies en cours."""
        data = _read(ACTIVE_FILE, {})
        try:
            if ACTIVE_FILE.exists():
                ACTIVE_FILE.unlink()
        except Exception:
            pass
        return data
