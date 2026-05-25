"""
Intégration Steam : détection locale + API Web.
"""
import json
import re
import winreg
from pathlib import Path
from urllib import parse as urlparse


# ── Détection locale ──────────────────────────────────────────────────────────

def get_steam_path() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return winreg.QueryValueEx(k, "SteamPath")[0]
    except OSError:
        return None


def detect_steam_ids() -> list[str]:
    """Retourne les Steam ID 64-bit trouvés dans le dossier userdata de Steam."""
    steam_path = get_steam_path()
    if not steam_path:
        return []
    userdata = Path(steam_path) / "userdata"
    if not userdata.exists():
        return []
    ids = []
    for folder in sorted(userdata.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            account_id = int(folder.name)
            if account_id > 0:
                ids.append(str(account_id + 76561197960265728))
        except (ValueError, OSError):
            pass
    return ids


# ── API Steam ─────────────────────────────────────────────────────────────────

def fetch_owned_games(api_key: str, steam_id: str) -> list[dict]:
    """Appelle IPlayerService/GetOwnedGames (appel direct, à lancer depuis un thread de fond)."""
    import urllib.request

    params = urlparse.urlencode({
        "key":                       api_key,
        "steamid":                   steam_id,
        "include_appinfo":           1,
        "include_played_free_games": 1,
        "format":                    "json",
    })
    url  = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?{params}"
    req  = urllib.request.Request(url, headers={"User-Agent": "TimeTracker/1.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read().decode())
    return data.get("response", {}).get("games", [])


# ── Correspondance de noms ────────────────────────────────────────────────────

def _norm(name: str) -> str:
    """Normalise un nom pour la comparaison : minuscules + alphanumérique uniquement."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def get_all_games_status(steam_games: list[dict], local_games: dict) -> list[dict]:
    """
    Retourne TOUS les jeux Steam avec leur statut par rapport aux jeux locaux.
    status: 'match' (à importer), 'new' (pas dans TT), 'synced' (déjà à jour)
    """
    local_norm = {_norm(name): name for name in local_games}
    result = []

    for sg in steam_games:
        steam_name = sg.get("name", "")
        steam_mins = sg.get("playtime_forever", 0)
        if not steam_name:
            continue

        steam_secs  = steam_mins * 60
        steam_hours = round(steam_mins / 60, 1)
        local_name  = local_norm.get(_norm(steam_name))

        if local_name:
            local_secs  = local_games[local_name].get("total_seconds", 0)
            local_hours = round(local_secs / 3600, 1)
            added_secs  = max(0, steam_secs - local_secs)
            status      = "match" if added_secs > 720 else "synced"
        else:
            local_hours = 0
            added_secs  = steam_secs
            status      = "new" if steam_mins > 0 else "never"

        result.append({
            "steam_name":    steam_name,
            "steam_hours":   steam_hours,
            "local_name":    local_name,
            "local_hours":   local_hours,
            "added_secs":    added_secs,
            "status":        status,
            "appid":         sg.get("appid", 0),
            "img_icon_url":  sg.get("img_icon_url", ""),
        })

    _order = {"match": 0, "new": 1, "synced": 2, "never": 3}
    result.sort(key=lambda x: (_order.get(x["status"], 4), -x["steam_hours"]))
    return result
