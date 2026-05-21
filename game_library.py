import json
import os
import re
import winreg
from pathlib import Path


class KnownGames:
    """Maps exe paths/directories to game names from installed launchers."""

    def __init__(self):
        self._exact: dict[str, str] = {}          # {exe_path_lower: game_name}
        self._dirs:  list[tuple[str, str]] = []   # [(dir_prefix_lower, game_name)]

    def _add_dir(self, directory: str, name: str):
        prefix = directory.lower().rstrip("\\/") + "\\"
        self._dirs.append((prefix, name))

    def _add_exe(self, exe_path: str, name: str):
        if exe_path:
            self._exact[exe_path.lower()] = name

    def lookup(self, exe_path: str) -> str | None:
        """Returns the game name for this exe path, or None if unknown."""
        low = exe_path.lower()
        name = self._exact.get(low)
        if name:
            return name
        for prefix, name in self._dirs:
            if low.startswith(prefix):
                return name
        return None

    def __len__(self):
        return len(self._exact) + len(self._dirs)


# ── Parsers ────────────────────────────────────────────────────────────────────

def _parse_vdf(text: str) -> dict[str, str]:
    """Extrait les paires clé-valeur de premier niveau d'un fichier VDF/ACF."""
    return dict(re.findall(r'"(\w+)"\s+"([^"]*)"', text))


# ── Sources ────────────────────────────────────────────────────────────────────

def _load_steam(known: KnownGames) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam_root = Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        return

    libraries = [steam_root / "steamapps"]
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf_path.exists():
        text = vdf_path.read_text(encoding="utf-8", errors="ignore")
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            lib = Path(raw.replace("\\\\", "\\")) / "steamapps"
            if lib not in libraries:
                libraries.append(lib)

    for lib in libraries:
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                data = _parse_vdf(acf.read_text(encoding="utf-8", errors="ignore"))
                name       = data.get("name", "")
                installdir = data.get("installdir", "")
                if name and installdir:
                    known._add_dir(str(lib / "common" / installdir), name)
            except Exception:
                pass


def _load_gog(known: KnownGames) -> None:
    key = None
    for path in (r"SOFTWARE\WOW6432Node\GOG.com\Games", r"SOFTWARE\GOG.com\Games"):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
            break
        except OSError:
            continue
    if key is None:
        return

    with key:
        i = 0
        while True:
            try:
                sub_name = winreg.EnumKey(key, i)
                with winreg.OpenKey(key, sub_name) as sub:
                    try:
                        exe  = winreg.QueryValueEx(sub, "exe")[0]
                        name = winreg.QueryValueEx(sub, "gameName")[0]
                        if exe and name:
                            known._add_exe(exe, name)
                    except OSError:
                        pass
                i += 1
            except OSError:
                break


def _load_epic(known: KnownGames) -> None:
    manifests = (
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    )
    if not manifests.exists():
        return
    for item in manifests.glob("*.item"):
        try:
            data        = json.loads(item.read_text(encoding="utf-8"))
            name        = data.get("DisplayName", "")
            install_loc = data.get("InstallLocation", "")
            launch_exe  = data.get("LaunchExecutable", "")
            if name and install_loc and launch_exe:
                known._add_exe(str(Path(install_loc) / launch_exe), name)
        except Exception:
            pass


def _load_xbox(known: KnownGames) -> None:
    try:
        base = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"System\GameConfigStore\Children",
        )
    except OSError:
        return

    with base:
        i = 0
        while True:
            try:
                sub_name = winreg.EnumKey(base, i)
                with winreg.OpenKey(base, sub_name) as sub:
                    try:
                        exe = winreg.QueryValueEx(sub, "MatchedExeFullPath")[0]
                        if exe:
                            stem = Path(exe).stem
                            name = " ".join(
                                w.capitalize()
                                for w in stem.replace("_", " ").replace("-", " ").split()
                            )
                            known._add_exe(exe, name)
                    except OSError:
                        pass
                i += 1
            except OSError:
                break


# ── API publique ───────────────────────────────────────────────────────────────

def build_known_games() -> KnownGames:
    """Construit la base de jeux connus depuis Steam, GOG, Epic et Xbox Game Bar."""
    known = KnownGames()
    for loader in (_load_steam, _load_gog, _load_epic, _load_xbox):
        try:
            loader(known)
        except Exception:
            pass
    return known
