import http.server
import json
import os
import queue
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_SUPABASE_URL = "https://lvhfutmsjdgwchpxrojz.supabase.co"
_SUPABASE_KEY = "sb_publishable__FDSLgnFmVJsq-6g-J86Uw_xecbLg11"
if getattr(__import__("sys"), "frozen", False):
    _AUTH_FILE = Path(__import__("sys").executable).parent / "data" / "auth.json"
else:
    _AUTH_FILE = Path(os.environ.get("APPDATA", Path.home())) / "TimeTracker" / "auth.json"
_TABLE        = "TT_data"
_TIMEOUT      = 12
_RESET_PORT   = 37123

_RESET_HTML = (
    "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
    "<style>body{font-family:system-ui,sans-serif;background:#161616;color:#f0f0f0;"
    "display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}"
    "p{font-size:17px;text-align:center;line-height:1.6;max-width:400px;}</style></head>"
    "<body><p id=\"m\">Chargement...</p><script>"
    "var h=location.hash.slice(1),p={};"
    "h.split('&').forEach(function(x){var kv=x.split('=');p[kv[0]]=decodeURIComponent(kv[1]||'');});"
    "if(p.access_token&&p.type==='recovery'){"
    "fetch('/token?t='+encodeURIComponent(p.access_token))"
    ".then(function(){document.getElementById('m').innerHTML="
    "'Retourne dans <strong>Time Tracker</strong> pour choisir ton nouveau mot de passe.';})"
    ".catch(function(){document.getElementById('m').textContent='Erreur. Reessaie.';});"
    "}else if(p.error){document.getElementById('m').textContent=p.error_description||p.error;"
    "}else{document.getElementById('m').textContent='Parametres manquants.';}"
    "</script></body></html>"
)


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _http(method: str, url: str, payload: dict | None, headers: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req  = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8").strip()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8").strip()
            return e.code, (json.loads(raw) if raw else {})
        except Exception:
            return e.code, {}


def _run_threaded(fn) -> dict:
    q = queue.Queue()

    def _worker():
        try:
            q.put(fn())
        except Exception as e:
            q.put({"ok": False, "error": str(e)})

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    try:
        return q.get(timeout=_TIMEOUT + 2)
    except queue.Empty:
        return {"ok": False, "error": "Timeout reseau."}


# ── SyncManager ───────────────────────────────────────────────────────────────

class SyncManager:
    def __init__(self, dm):
        self._dm      = dm
        self._session = {}
        self._lock    = threading.Lock()
        self._load_session()

    # ── Session locale ────────────────────────────────────────────────────────

    def _load_session(self):
        if _AUTH_FILE.exists():
            try:
                with open(_AUTH_FILE, "r", encoding="utf-8") as f:
                    self._session = json.load(f)
            except Exception:
                self._session = {}

    def _save_session(self):
        try:
            _AUTH_FILE.parent.mkdir(exist_ok=True)
            with open(_AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(self._session, f, indent=2)
        except Exception:
            pass

    def _clear_session(self):
        self._session = {}
        try:
            if _AUTH_FILE.exists():
                _AUTH_FILE.unlink()
        except Exception:
            pass

    def clear_local_session(self) -> None:
        """Supprime la session locale (auth.json) sans appeler l'API Supabase."""
        self._clear_session()

    def _store_session(self, data: dict):
        self._session = {
            "access_token":  data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "user_id":       data["user"]["id"],
            "email":         data["user"]["email"],
        }
        self._save_session()

    # ── Helpers HTTP ──────────────────────────────────────────────────────────

    def _headers(self, with_auth: bool = True) -> dict:
        h = {"apikey": _SUPABASE_KEY, "Content-Type": "application/json"}
        if with_auth and self._session.get("access_token"):
            h["Authorization"] = f"Bearer {self._session['access_token']}"
        return h

    def _auth_url(self, path: str) -> str:
        return f"{_SUPABASE_URL}/auth/v1{path}"

    def _rest_url(self, path: str) -> str:
        return f"{_SUPABASE_URL}/rest/v1{path}"

    # ── Auth ──────────────────────────────────────────────────────────────────

    def sign_up(self, email: str, password: str) -> dict:
        def _do():
            status, data = _http(
                "POST", self._auth_url("/signup"),
                {"email": email, "password": password},
                self._headers(with_auth=False),
            )
            if status in (200, 201):
                if data.get("access_token"):
                    self._store_session(data)
                    return {"ok": True, "email": self._session["email"]}
                if data.get("id") or data.get("email"):
                    return {"ok": False, "needs_confirm": True, "error": "Compte créé — vérifie ton email pour confirmer."}
            msg = (data.get("msg") or data.get("message")
                   or data.get("error_description") or f"Erreur HTTP {status}")
            return {"ok": False, "error": msg}
        return _run_threaded(_do)

    def sign_in(self, email: str, password: str) -> dict:
        def _do():
            status, data = _http(
                "POST", self._auth_url("/token?grant_type=password"),
                {"email": email, "password": password},
                self._headers(with_auth=False),
            )
            if status == 200 and data.get("access_token"):
                self._store_session(data)
                return {"ok": True, "email": self._session["email"]}
            msg = (data.get("error_description") or data.get("message")
                   or data.get("msg") or f"Identifiants incorrects (HTTP {status})")
            return {"ok": False, "error": msg}
        return _run_threaded(_do)

    def sign_out(self) -> dict:
        def _do():
            try:
                _http("POST", self._auth_url("/logout"), None, self._headers())
            except Exception:
                pass
            self._clear_session()
            return {"ok": True}
        return _run_threaded(_do)

    def get_status(self) -> dict:
        if self._session.get("access_token"):
            return {"logged_in": True, "email": self._session.get("email", "")}
        return {"logged_in": False, "email": ""}

    # ── Reset mot de passe (serveur local) ────────────────────────────────────

    def start_reset_flow(self, email: str) -> dict:
        def _do():
            self._stop_reset_server()
            self._pending_reset_token = None
            mgr = self

            class _Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    parsed = urllib.parse.urlparse(self.path)
                    if parsed.path == "/":
                        body = _RESET_HTML.encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body)
                    elif parsed.path == "/token":
                        qs  = urllib.parse.parse_qs(parsed.query)
                        tok = qs.get("t", [""])[0]
                        if tok:
                            mgr._pending_reset_token = tok
                            threading.Timer(1.0, mgr._stop_reset_server).start()
                        self.send_response(200)
                        self.end_headers()
                    else:
                        self.send_response(404)
                        self.end_headers()

                def log_message(self, *_):
                    pass

            redirect = f"http://localhost:{_RESET_PORT}"
            url = (self._auth_url("/recover") + "?"
                   + urllib.parse.urlencode({"redirect_to": redirect}))
            status, data = _http("POST", url, {"email": email},
                                 self._headers(with_auth=False))
            if status not in (200, 204):
                msg = (data.get("msg") or data.get("message")
                       or data.get("error_description") or f"Erreur HTTP {status}")
                return {"ok": False, "error": msg}

            try:
                srv = http.server.HTTPServer(("localhost", _RESET_PORT), _Handler)
                self._reset_server = srv
                t = threading.Thread(target=srv.serve_forever, daemon=True)
                t.start()
            except OSError:
                pass
            return {"ok": True}
        return _run_threaded(_do)

    def check_reset_token(self) -> str | None:
        tok = getattr(self, "_pending_reset_token", None)
        if tok:
            self._pending_reset_token = None
        return tok

    def _stop_reset_server(self):
        srv = getattr(self, "_reset_server", None)
        if srv:
            try:
                srv.shutdown()
            except Exception:
                pass
            self._reset_server = None

    def update_password(self, token: str, new_password: str) -> dict:
        def _do():
            status, data = _http(
                "PUT", f"{_SUPABASE_URL}/auth/v1/user",
                {"password": new_password},
                {"apikey": _SUPABASE_KEY, "Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
            )
            if status == 200:
                return {"ok": True}
            return {"ok": False, "error": data.get("message") or f"Erreur HTTP {status}"}
        return _run_threaded(_do)

    def change_password(self, new_password: str) -> dict:
        def _do():
            if not self._session.get("access_token"):
                return {"ok": False, "error": "Non connecte"}
            status, data = _http(
                "PUT", f"{_SUPABASE_URL}/auth/v1/user",
                {"password": new_password},
                self._headers(with_auth=True),
            )
            if status == 200:
                return {"ok": True}
            return {"ok": False, "error": data.get("message") or f"Erreur HTTP {status}"}
        return _run_threaded(_do)

    # ── Refresh silencieux ────────────────────────────────────────────────────

    def _try_refresh(self) -> bool:
        rt = self._session.get("refresh_token")
        if not rt:
            return False
        try:
            status, data = _http(
                "POST", self._auth_url("/token?grant_type=refresh_token"),
                {"refresh_token": rt},
                self._headers(with_auth=False),
            )
            if status == 200 and data.get("access_token"):
                self._session["access_token"]  = data["access_token"]
                self._session["refresh_token"] = data.get("refresh_token", rt)
                self._save_session()
                return True
        except Exception:
            pass
        return False

    # ── Statut de sync ────────────────────────────────────────────────────────

    def get_sync_info(self) -> dict:
        if not self._session.get("access_token"):
            return {"logged_in": False}
        last_ok    = getattr(self, "_last_sync_ok",    None)
        last_time  = getattr(self, "_last_sync_time",  None)
        last_error = getattr(self, "_last_sync_error", None)
        pending    = getattr(self, "_has_pending",     False)

        ago = None
        if last_time:
            secs = int((datetime.now(timezone.utc) - last_time).total_seconds())
            if secs < 60:
                ago = "il y a quelques secondes"
            elif secs < 3600:
                ago = f"il y a {secs // 60} min"
            elif secs < 86400:
                ago = f"il y a {secs // 3600} h"
            else:
                ago = f"il y a {secs // 86400} j"

        return {
            "logged_in": True,
            "email":     self._session.get("email", ""),
            "synced":    last_ok is True and not pending,
            "pending":   pending,
            "last_sync": ago,
            "error":     last_error if last_ok is False else None,
        }

    # ── Push automatique ──────────────────────────────────────────────────────

    def schedule_push(self) -> None:
        self._has_pending = True
        with self._lock:
            if getattr(self, "_push_timer", None):
                self._push_timer.cancel()
            t = threading.Timer(2.0, self._bg_push)
            t.daemon = True
            t.start()
            self._push_timer = t

    def _bg_push(self) -> None:
        with self._lock:
            self._push_timer = None
            rt = getattr(self, "_retry_timer", None)
            if rt:
                rt.cancel()
            self._retry_timer = None
        r = self._push_inner()
        if r.get("ok"):
            self._last_sync_ok    = True
            self._last_sync_time  = datetime.now(timezone.utc)
            self._last_sync_error = None
            self._has_pending     = False
        else:
            self._last_sync_ok    = False
            self._last_sync_error = r.get("error", "Erreur inconnue")
            # Retry automatique dans 30s
            with self._lock:
                t = threading.Timer(30.0, self._bg_push)
                t.daemon = True
                t.start()
                self._retry_timer = t

    def _push_inner(self) -> dict:
        """Synchrone — toujours appelé depuis un thread background."""
        if not self._session.get("access_token"):
            return {"ok": False, "error": "Non connecte"}

        user_id = self._session["user_id"]

        # 1. Merge-before-push : récupère le distant et fusionne avant d'écraser
        try:
            url = self._rest_url(f"/{_TABLE}?user_id=eq.{user_id}&select=games")
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw  = resp.read().decode("utf-8").strip()
                rows = json.loads(raw) if raw else []
                if isinstance(rows, list) and rows:
                    remote_games = rows[0].get("games") or {}
                    if remote_games:
                        self._dm.merge_games(remote_games)
        except Exception:
            pass  # réseau indisponible — on pousse l'état local tel quel

        # 2. Pousse l'état fusionné
        payload = {
            "user_id":    user_id,
            "games":      self._dm.get_games(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        hdrs = {**self._headers(), "Prefer": "resolution=merge-duplicates"}
        status, data = _http("POST", self._rest_url(f"/{_TABLE}"), payload, hdrs)
        if status == 401 and self._try_refresh():
            return self._push_inner()
        if status in (200, 201):
            return {"ok": True}
        return {"ok": False, "error": f"HTTP {status}: {data}"}

    def _push(self) -> dict:
        """Wrapper threadé — pour les appels depuis le thread webview (sync_push_now)."""
        return _run_threaded(self._push_inner)

    def flush(self) -> None:
        """Push synchrone bloquant — à appeler à la fermeture de l'app."""
        if not self._session.get("access_token"):
            return
        # Annule les timers en attente pour éviter un double push
        with self._lock:
            for attr in ("_push_timer", "_retry_timer"):
                t = getattr(self, attr, None)
                if t:
                    t.cancel()
                setattr(self, attr, None)
        self._push_inner()

    def reset_cloud_data(self) -> dict:
        if not self._session.get("access_token"):
            return {"ok": False, "error": "Non connecté"}

        def _do():
            payload = {
                "user_id":    self._session["user_id"],
                "games":      {},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            hdrs = {**self._headers(), "Prefer": "resolution=merge-duplicates"}
            status, data = _http("POST", self._rest_url(f"/{_TABLE}"), payload, hdrs)
            if status in (200, 201):
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {status}: {data}"}
        return _run_threaded(_do)

    def pull_on_start(self) -> dict:
        if not self._session.get("access_token"):
            return {"ok": False, "error": "Non connecte"}

        def _do():
            user_id = self._session["user_id"]
            self._dm.switch_user(user_id)
            url = self._rest_url(
                f"/{_TABLE}?user_id=eq.{user_id}&select=games,updated_at"
            )
            status, data = _http("GET", url, None, self._headers())
            if status == 401 and self._try_refresh():
                return self.pull_on_start()
            if status != 200:
                return {"ok": False, "error": f"HTTP {status}"}
            rows = data if isinstance(data, list) else []
            if not rows:
                return {"ok": True, "merged": 0}
            remote_games = rows[0].get("games") or {}
            merged = self._dm.merge_games(remote_games)
            return {"ok": True, "merged": merged}
        return _run_threaded(_do)
