import base64
import io
import threading
from datetime import datetime

import psutil

from data_manager import DataManager
from icon_cache import get_game_icon, get_pil_icon, ICON_DIR, _safe_filename
from notifications import NotificationManager
from tracker import ProcessTracker
from utils import format_duration

_SKIP_DIRS = (
    "\\windows\\system32\\",
    "\\windows\\syswow64\\",
    "\\windows\\winsxs\\",
)

_VERSION     = "1.4"
_GITHUB_REPO = "Noxil-fr/Time-tracker"


class Api:
    def __init__(self, dm: DataManager, sync=None):
        self._dm        = dm
        self._sync      = sync
        self._tracker: ProcessTracker | None = None
        self._tray      = None
        self._notif     = NotificationManager()
        self._events: list = []
        self._lock    = threading.Lock()
        self._version = 0
        self._quit_cb       = None
        self._pending_update = None   # {"version": ..., "url": ...} dès qu'une MAJ est trouvée

        self._notif.set_on_add_game(self._notif_add_game)
        self._notif.set_on_ignore_game(self._notif_ignore_game)

    def _notif_add_game(self, game_name: str, proc_name: str, exe_path: str) -> None:
        self.add_game(game_name, proc_name, exe_path)

    def _notif_ignore_game(self, proc_name: str) -> None:
        self._dm.add_ignored_proc(proc_name)

    def set_tracker(self, tracker: ProcessTracker):
        self._tracker = tracker

    def set_tray(self, tray) -> None:
        self._tray = tray

    def _bump(self):
        self._version += 1
        if self._sync:
            self._sync.schedule_push()

    # ── Poll — appelé chaque seconde par le JS ────────────────────────────────

    def poll(self) -> dict:
        games  = self._dm.get_games()
        active = {}

        if self._tracker:
            raw = self._tracker.get_active()
            now = datetime.now()
            for name, start_dt in raw.items():
                elapsed = int((now - start_dt).total_seconds())
                total   = games.get(name, {}).get("total_seconds", 0)
                active[name] = {"elapsed": elapsed, "total": total + elapsed}

        with self._lock:
            events = self._events[:]
            self._events.clear()

        return {
            "version": self._version,
            "games":   games,
            "active":  active,
            "events":  events,
            "update":  self._pending_update,
        }

    # ── Callbacks tracker ─────────────────────────────────────────────────────

    def on_game_start(self, name: str):
        with self._lock:
            self._events.append({"type": "start", "name": name})
        # Toujours tenter d'extraire l'icône depuis l'exe live au lancement
        threading.Thread(target=self._fetch_icon_bg, args=(name,), daemon=True).start()

    def _fetch_icon_bg(self, name: str) -> None:
        from icon_cache import _extract_from_exe, _mem_cache
        game_data = self._dm.get_games().get(name, {})
        exe_path  = game_data.get("exe_path", "") or ""
        proc_name = game_data.get("process", "").lower()

        # 1. Priorité absolue : extraire depuis l'exe du processus LIVE
        if proc_name:
            try:
                for p in psutil.process_iter(["name", "exe"]):
                    if p.info["name"] and p.info["name"].lower() == proc_name:
                        found = p.info.get("exe") or ""
                        if found and not any(d in found.lower() for d in _SKIP_DIRS):
                            img = _extract_from_exe(found, 32)
                            if img:
                                disk_path = ICON_DIR / (_safe_filename(name) + ".png")
                                ICON_DIR.mkdir(parents=True, exist_ok=True)
                                try:
                                    img.save(disk_path, "PNG")
                                    for k in [k for k in _mem_cache if k[0] == name]:
                                        del _mem_cache[k]
                                except Exception:
                                    pass
                                self._dm.batch_update_exe_paths({name: found})
                                with self._lock:
                                    self._events.append({"type": "icon_ready", "name": name})
                                return
                            exe_path = found or exe_path
                            self._dm.batch_update_exe_paths({name: found})
                        break
            except Exception:
                pass

        # 2. Icône déjà en cache disque et pas d'exe live → rien à faire
        disk_path = ICON_DIR / (_safe_filename(name) + ".png")
        if disk_path.exists():
            return

        # 3. Fallbacks : exe_path sauvegardé → Steam appid → recherche nom Steam → find_exe
        img = get_game_icon(name, exe_path, 32)

        if not img:
            steam_appid = game_data.get("steam_appid", 0)
            if steam_appid:
                from icon_cache import fetch_steam_icon
                img = fetch_steam_icon(name, steam_appid, game_data.get("steam_icon_hash", ""), 32)

        if not img:
            from icon_cache import fetch_steam_icon_by_name
            img = fetch_steam_icon_by_name(name, 32)

        if not img and not exe_path:
            from icon_cache import find_exe_by_process
            proc = game_data.get("process", "")
            if proc:
                found = find_exe_by_process(proc)
                if found:
                    self._dm.batch_update_exe_paths({name: found})
                    img = get_game_icon(name, found, 32)

        if img:
            with self._lock:
                self._events.append({"type": "icon_ready", "name": name})

    def on_game_stop(self, name: str, start, end):
        duration = int((end - start).total_seconds())
        total    = self._dm.get_games().get(name, {}).get("total_seconds", 0)
        with self._lock:
            self._events.append({
                "type": "stop", "name": name,
                "duration": duration, "total": total,
            })
        self._bump()

    def on_suggestion(self, game_name: str, proc_name: str, exe_path: str):
        with self._lock:
            self._events.append({
                "type":      "suggestion",
                "game_name": game_name,
                "proc_name": proc_name,
                "exe_path":  exe_path,
            })

    # ── Jeux ─────────────────────────────────────────────────────────────────

    def get_games(self) -> dict:
        return self._dm.get_games()

    def add_game(self, name: str, proc: str, exe: str) -> dict:
        if self._dm.game_exists(name):
            return {"ok": False, "error": f'"{name}" existe déjà.'}
        self._dm.add_game(name, proc, exe)
        if exe and not any(d in exe.lower() for d in _SKIP_DIRS):
            get_game_icon(name, exe, 32)  # pré-cache l'icône sur disque
        self._bump()
        return {"ok": True}

    def delete_game(self, name: str) -> bool:
        ok = self._dm.delete_game(name)
        if ok:
            self._bump()
        return ok

    def set_game_time(self, name: str, seconds: int) -> dict:
        ok = self._dm.set_game_time(name, int(seconds))
        if ok:
            self._bump()
        return {"ok": ok}

    def reset_local_data(self) -> dict:
        self._dm.reset_all_local_data()
        if self._sync:
            self._sync.clear_local_session()
        self._bump()
        return {"ok": True}

    def reset_cloud_data(self) -> dict:
        if not self._sync:
            return {"ok": False, "error": "Non connecté"}
        return self._sync.reset_cloud_data()

    def set_game_archived(self, name: str, archived: bool) -> dict:
        ok = self._dm.set_game_flag(name, "archived", bool(archived))
        if ok:
            self._bump()
        return {"ok": ok}

    def set_game_pinned(self, name: str, pinned: bool) -> dict:
        ok = self._dm.set_game_flag(name, "pinned", bool(pinned))
        if ok:
            self._bump()
        return {"ok": ok}

    def set_game_flag(self, name: str, flag: str, value) -> dict:
        ok = self._dm.set_game_flag(name, flag, value)
        if ok:
            self._bump()
        return {"ok": ok}

    def rename_game(self, old_name: str, new_name: str) -> dict:
        new_name = new_name.strip()
        if not new_name:
            return {"ok": False, "error": "Nom vide."}
        if not self._dm.rename_game(old_name, new_name):
            return {"ok": False, "error": f'"{new_name}" existe déjà.'}
        from icon_cache import rename_icon
        rename_icon(old_name, new_name)
        self._bump()
        return {"ok": True}

    def game_exists(self, name: str) -> bool:
        return self._dm.game_exists(name)

    def record_session(self, game_name: str, start_iso: str, end_iso: str):
        start = datetime.fromisoformat(start_iso)
        end   = datetime.fromisoformat(end_iso)
        self._dm.record_session(game_name, start, end)
        self._bump()

    # ── Historique ────────────────────────────────────────────────────────────

    def get_sessions(self, start_iso: str, end_iso: str,
                     game_filter: str | None = None) -> list:
        start = datetime.fromisoformat(start_iso)
        end   = datetime.fromisoformat(end_iso)
        result = []
        for name, data in self._dm.get_games().items():
            if game_filter and name != game_filter:
                continue
            for s in data.get("sessions", []):
                s_start = datetime.fromisoformat(s["start"])
                if start <= s_start <= end:
                    result.append({
                        "game":     name,
                        "start":    s["start"],
                        "end":      s["end"],
                        "duration": s["duration"],
                    })
        return sorted(result, key=lambda x: x["start"])

    # ── Statistiques ──────────────────────────────────────────────────────────

    def get_stats(self, start_iso: str, end_iso: str) -> dict:
        start = datetime.fromisoformat(start_iso)
        end   = datetime.fromisoformat(end_iso)
        return self._dm.get_all_sessions_in_range(start, end)

    def get_yearly_recap(self, year: int = None) -> dict:
        """Rétrospective de l'année (par défaut l'année précédente)."""
        now = datetime.now()
        if year is None:
            year = now.year - 1

        games = self._dm.get_games()
        game_stats: dict = {}
        monthly: dict    = {}
        longest          = {"game": "", "seconds": 0, "date": ""}

        for name, data in games.items():
            for s in data.get("sessions", []):
                try:
                    dt = datetime.fromisoformat(s["start"])
                except Exception:
                    continue
                if dt.year != year:
                    continue
                dur = s.get("duration", 0)
                if not dur:
                    continue
                if name not in game_stats:
                    game_stats[name] = {"seconds": 0, "sessions": 0}
                game_stats[name]["seconds"]  += dur
                game_stats[name]["sessions"] += 1
                m = dt.month
                monthly[m] = monthly.get(m, 0) + dur
                if dur > longest["seconds"]:
                    longest = {"game": name, "seconds": dur, "date": s["start"]}

        top_games = sorted(
            [{"name": n, "seconds": v["seconds"], "sessions": v["sessions"]}
             for n, v in game_stats.items()],
            key=lambda x: x["seconds"], reverse=True
        )[:5]

        best_month_num  = max(monthly, key=monthly.get) if monthly else None
        best_month_secs = monthly.get(best_month_num, 0) if best_month_num else 0

        return {
            "year":              year,
            "total_seconds":     sum(v["seconds"]  for v in game_stats.values()),
            "games_count":       len(game_stats),
            "sessions_count":    sum(v["sessions"] for v in game_stats.values()),
            "top_games":         top_games,
            "best_month_num":    best_month_num,
            "best_month_seconds": best_month_secs,
            "longest":           longest,
        }

    # ── Processus ────────────────────────────────────────────────────────────

    def get_all_processes(self) -> list:
        seen, result = set(), []
        for p in psutil.process_iter(["name", "exe"]):
            try:
                name = p.info["name"]
                key  = name.lower() if name else ""
                if key and key not in seen:
                    seen.add(key)
                    result.append({"name": name, "exe": p.info["exe"] or ""})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return sorted(result, key=lambda x: x["name"].lower())

    def get_snapshot(self) -> list:
        return list(self._tracker.get_snapshot()) if self._tracker else []

    def get_process_start(self, proc_name: str) -> str | None:
        proc_lower = proc_name.lower()
        for p in psutil.process_iter(["name", "create_time"]):
            try:
                if p.info["name"] and p.info["name"].lower() == proc_lower:
                    return datetime.fromtimestamp(p.info["create_time"]).isoformat()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return None

    # ── Icônes ────────────────────────────────────────────────────────────────

    def get_icon_b64(self, game_name: str, exe_path: str) -> str:
        if exe_path and any(d in exe_path.lower() for d in _SKIP_DIRS):
            return ""
        # Fallback : si pas d'exe_path, chercher le processus en cours
        if not exe_path:
            game_data = self._dm.get_games().get(game_name, {})
            proc_name = game_data.get("process", "").lower()
            if proc_name:
                for p in psutil.process_iter(["name", "exe"]):
                    try:
                        if p.info["name"] and p.info["name"].lower() == proc_name:
                            found = p.info.get("exe") or ""
                            if found and not any(d in found.lower() for d in _SKIP_DIRS):
                                exe_path = found
                                self._dm.batch_update_exe_paths({game_name: exe_path})
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        pil_img = get_game_icon(game_name, exe_path or "", 32)
        if not pil_img:
            game_data   = self._dm.get_games().get(game_name, {})
            steam_appid = game_data.get("steam_appid", 0)
            if steam_appid:
                steam_icon = game_data.get("steam_icon_hash", "")
                from icon_cache import fetch_steam_icon
                pil_img = fetch_steam_icon(game_name, steam_appid, steam_icon, 32)
        if not pil_img:
            from icon_cache import fetch_steam_icon_by_name
            pil_img = fetch_steam_icon_by_name(game_name, 32)
        if not pil_img and not exe_path:
            # Dernière chance : trouver l'exe sur disque et en extraire l'icône
            from icon_cache import find_exe_by_process
            proc = self._dm.get_games().get(game_name, {}).get("process", "")
            if proc:
                found = find_exe_by_process(proc)
                if found:
                    self._dm.batch_update_exe_paths({game_name: found})
                    pil_img = get_game_icon(game_name, found, 32)
        if not pil_img:
            return ""
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    # ── Paramètres ───────────────────────────────────────────────────────────

    def get_autostart(self) -> bool:
        from tray import is_autostart_enabled
        return is_autostart_enabled()

    def set_autostart(self, enabled: bool):
        from tray import set_autostart
        set_autostart(bool(enabled))

    # ── Sync / Compte ─────────────────────────────────────────────────────────

    def sync_get_info(self) -> dict:
        if not self._sync:
            return {"logged_in": False}
        return self._sync.get_sync_info()

    def sync_status(self) -> dict:
        if not self._sync:
            return {"available": False, "logged_in": False, "email": ""}
        s = self._sync.get_status()
        s["available"] = True
        return s

    def sync_sign_in(self, email: str, password: str) -> dict:
        if not self._sync:
            return {"ok": False, "error": "Sync non disponible"}
        return self._sync.sign_in(email, password)

    def sync_sign_up(self, email: str, password: str) -> dict:
        if not self._sync:
            return {"ok": False, "error": "Sync non disponible"}
        return self._sync.sign_up(email, password)

    def sync_start_reset_flow(self, email: str) -> dict:
        if not self._sync:
            return {"ok": False, "error": "Sync non disponible"}
        return self._sync.start_reset_flow(email)

    def sync_check_reset_token(self) -> str | None:
        if not self._sync:
            return None
        return self._sync.check_reset_token()

    def sync_update_password(self, token: str, new_password: str) -> dict:
        if not self._sync:
            return {"ok": False, "error": "Sync non disponible"}
        return self._sync.update_password(token, new_password)

    def sync_change_password(self, new_password: str) -> dict:
        if not self._sync:
            return {"ok": False, "error": "Sync non disponible"}
        return self._sync.change_password(new_password)

    def sync_sign_out(self) -> dict:
        if not self._sync:
            return {"ok": False, "error": "Sync non disponible"}
        return self._sync.sign_out()

    def sync_push_now(self) -> dict:
        """Push immédiat (ex: au démarrage pour initialiser le statut de sync)."""
        if not self._sync:
            return {"ok": False}
        r = self._sync._push()
        if r.get("ok"):
            from datetime import datetime, timezone
            self._sync._last_sync_ok    = True
            self._sync._last_sync_time  = datetime.now(timezone.utc)
            self._sync._last_sync_error = None
            self._sync._has_pending     = False
        return r

    def sync_pull_on_start(self) -> dict:
        """Appelé une fois par le JS après connexion. Fusionne les données distantes."""
        if not self._sync:
            return {"ok": True, "merged": 0}
        result = self._sync.pull_on_start()
        if result.get("ok"):
            self._version += 1  # toujours bumper : switch_user change les données même si merged=0
        return result

    # ── Notifications flottantes ──────────────────────────────────────────────

    def show_notification(self, title: str, message: str,
                          color: str = "blue", suggestion: dict | None = None) -> None:
        if suggestion:
            game_name = suggestion.get("game_name", "")
            exe_path  = suggestion.get("exe_path", "")
        else:
            game_name = title
            exe_path  = self._dm.get_games().get(game_name, {}).get("exe_path", "")

        icon = None
        if game_name and not any(d in (exe_path or "").lower() for d in _SKIP_DIRS):
            icon = get_game_icon(game_name, exe_path or "", 24)

        self._notif.show(title, message, color, suggestion, icon)

    # ── Steam ─────────────────────────────────────────────────────────────────

    def steam_get_config(self) -> dict:
        return self._dm.get_steam_config()

    def steam_save_config(self, api_key: str, steam_id: str) -> None:
        self._dm.save_steam_config(api_key.strip(), steam_id.strip())

    def steam_detect_ids(self) -> list:
        from steam import detect_steam_ids
        return detect_steam_ids()

    def steam_fetch(self, api_key: str, steam_id: str) -> dict:
        """Lance le chargement Steam en tâche de fond et retourne immédiatement.
        Le résultat est poussé via le mécanisme d'événements du poll()."""
        import threading
        api_key  = api_key.strip()
        steam_id = steam_id.strip()
        if not api_key or not steam_id:
            return {"ok": False, "error": "Clé API et Steam ID requis."}

        def _do():
            try:
                from steam import fetch_owned_games, get_all_games_status
                steam_games = fetch_owned_games(api_key, steam_id)
                if not steam_games:
                    ev = {"type": "steam_result", "ok": False,
                          "error": "Aucun jeu trouvé (profil privé ou Steam ID incorrect)."}
                else:
                    self._dm.save_steam_config(api_key, steam_id)
                    games = get_all_games_status(steam_games, self._dm.get_games())
                    ev = {"type": "steam_result", "ok": True, "games": games}
            except Exception as e:
                ev = {"type": "steam_result", "ok": False, "error": f"{type(e).__name__}: {e}"}
            with self._lock:
                self._events.append(ev)

        threading.Thread(target=_do, daemon=True).start()
        return {"ok": True}   # retour immédiat — résultat via poll()

    def steam_import_selection(self, selections: list) -> dict:
        """
        Importe les jeux sélectionnés.
        selections : [{"steam_name", "local_name"|null, "steam_hours"}, ...]
        """
        from steam import _norm
        local_games = self._dm.get_games()
        local_norm  = {_norm(n): n for n in local_games}
        updates     = {}
        created     = []

        steam_meta = {}   # {effective_name: (appid, icon_hash)}

        for sel in selections:
            steam_name  = sel.get("steam_name", "")
            local_name  = sel.get("local_name") or local_norm.get(_norm(steam_name))
            steam_secs  = int(sel.get("steam_hours", 0) * 3600)
            appid       = int(sel.get("appid") or 0)
            icon_hash   = sel.get("img_icon_url") or ""

            if local_name and local_name in local_games:
                current = local_games[local_name].get("total_seconds", 0)
                if steam_secs > current:
                    updates[local_name] = steam_secs - current
                if appid:
                    steam_meta[local_name] = (appid, icon_hash)
            else:
                self._dm.add_game(steam_name, "", "")
                updates[steam_name] = steam_secs
                created.append(steam_name)
                if appid:
                    steam_meta[steam_name] = (appid, icon_hash)

        if updates:
            self._dm.apply_steam_import(updates)

        for name, (appid, icon_hash) in steam_meta.items():
            self._dm.set_game_flag(name, "steam_appid",    appid)
            self._dm.set_game_flag(name, "steam_icon_hash", icon_hash)

        if updates or steam_meta:
            self._bump()

        # Pré-télécharge les icônes Steam en tâche de fond
        if steam_meta:
            import threading
            from icon_cache import fetch_steam_icon
            def _prefetch():
                for name, (appid, icon_hash) in steam_meta.items():
                    fetch_steam_icon(name, appid, icon_hash, 32)
            threading.Thread(target=_prefetch, daemon=True).start()

        return {
            "ok":           True,
            "imported":     len(updates),
            "added_seconds": sum(updates.values()),
            "created":      created,
        }

    # ── Mise à jour automatique ───────────────────────────────────────────────

    def set_quit_callback(self, cb) -> None:
        self._quit_cb = cb

    def check_update(self) -> None:
        """Lance la vérification de mise à jour en arrière-plan et pousse un événement."""
        def _do():
            import urllib.request
            import json as _json
            try:
                url = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": "TimeTracker"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = _json.loads(resp.read())
                tag = data.get("tag_name", "").lstrip("v")
                if not tag or tag == _VERSION:
                    return
                assets = data.get("assets", [])
                exe_url = next(
                    (a["browser_download_url"] for a in assets if a["name"].endswith(".exe")),
                    None,
                )
                if not exe_url:
                    return
                self._pending_update = {"version": tag, "url": exe_url}
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()

    def start_update(self, url: str) -> None:
        """Télécharge le setup en arrière-plan et émet des événements de progression."""
        import urllib.request
        import tempfile
        import os

        def _download():
            try:
                dest = os.path.join(tempfile.gettempdir(), "TimeTracker_Update.exe")
                with urllib.request.urlopen(url, timeout=120) as resp:
                    total = int(resp.headers.get("Content-Length") or 0)
                    downloaded = 0
                    with open(dest, "wb") as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                pct = int(downloaded * 100 / total)
                                with self._lock:
                                    self._events.append({"type": "update_progress", "pct": pct})
                with self._lock:
                    self._events.append({"type": "update_ready", "path": dest})
            except Exception as e:
                with self._lock:
                    self._events.append({"type": "update_error", "error": str(e)})

        threading.Thread(target=_download, daemon=True).start()

    def install_update(self, path: str) -> None:
        """Lance l'installeur en mode silencieux puis quitte l'application."""
        import subprocess
        import os
        if not os.path.isfile(path):
            return
        subprocess.Popen([path, "/VERYSILENT", "/NORESTART", "/CLOSEAPPLICATIONS"])
        def _do_quit():
            # Stopper le tray en premier pour que le processus puisse vraiment quitter
            # et libérer le mutex — sinon la nouvelle version ne peut pas démarrer.
            if self._tray and self._tray._icon:
                try:
                    self._tray._icon.stop()
                except Exception:
                    pass
            if self._quit_cb:
                self._quit_cb()
        threading.Thread(target=_do_quit, daemon=True).start()

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def fmt_duration(self, seconds: int) -> str:
        return format_duration(int(seconds))
