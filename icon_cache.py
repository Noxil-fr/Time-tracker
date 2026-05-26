"""
Gestion des icônes de jeux.
Flux : mémoire → disque (data/icons/<nom>.png) → extraction depuis l'exe.
L'icône est sauvegardée sur disque lors de la première extraction réussie,
ce qui la rend disponible même si l'exe est déplacé ou désinstallé.
"""
import re
import ctypes
import ctypes.wintypes as wintypes
from pathlib import Path

from PIL import Image

import os, sys
if getattr(sys, "frozen", False):
    ICON_DIR = Path(sys.executable).parent / "data" / "icons"
else:
    ICON_DIR = Path(os.environ.get("APPDATA", Path.home())) / "TimeTracker" / "icons"
_SAVE_SIZE = 32   # résolution de sauvegarde sur disque

_mem_cache: dict = {}   # (game_name, size) → Image


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip()


def get_game_icon(game_name: str, exe_path: str, size: int) -> Image.Image | None:
    """Charge l'icône : mémoire → disque → exe. Sauvegarde sur disque au premier succès."""
    key = (game_name, size)
    if key in _mem_cache:
        return _mem_cache[key]

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    disk_path = ICON_DIR / (_safe_filename(game_name) + ".png")

    if disk_path.exists():
        try:
            img = Image.open(disk_path).convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.Resampling.LANCZOS)
            _mem_cache[key] = img
            return img
        except Exception:
            pass

    if not exe_path:
        return None

    img = _extract_from_exe(exe_path, _SAVE_SIZE)
    if img is None:
        return None

    try:
        img.save(disk_path, "PNG")
    except Exception:
        pass

    if img.size != (size, size):
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    _mem_cache[key] = img
    return img


def rename_icon(old_name: str, new_name: str) -> None:
    """Rename disk file and update memory cache when a game is renamed."""
    old_path = ICON_DIR / (_safe_filename(old_name) + ".png")
    new_path = ICON_DIR / (_safe_filename(new_name) + ".png")
    if old_path.exists() and not new_path.exists():
        try:
            old_path.rename(new_path)
        except Exception:
            pass
    for key in list(_mem_cache.keys()):
        if key[0] == old_name:
            _mem_cache[(new_name, key[1])] = _mem_cache.pop(key)


def fetch_steam_icon(game_name: str, appid: int, icon_hash: str, size: int) -> Image.Image | None:
    """Télécharge l'icône Steam depuis le CDN, met en cache disque + mémoire.
    Essaie d'abord l'icône hash, puis le header image comme fallback."""
    import io, urllib.request

    if not appid:
        return None

    key = (game_name, size)
    if key in _mem_cache:
        return _mem_cache[key]

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    disk_path = ICON_DIR / (_safe_filename(game_name) + ".png")

    if disk_path.exists():
        try:
            img = Image.open(disk_path).convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.Resampling.LANCZOS)
            _mem_cache[key] = img
            return img
        except Exception:
            pass

    # Candidats URL : icône hash (32×32) puis header image (460×215, crop carré)
    candidates = []
    if icon_hash:
        candidates.append((
            f"https://media.steampowered.com/steamcommunity/public/images"
            f"/apps/{appid}/{icon_hash}.jpg",
            False,   # pas besoin de crop
        ))
    candidates.append((
        f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
        True,    # image large → crop carré centré
    ))

    for url, needs_crop in candidates:
        try:
            req  = urllib.request.Request(url, headers={"User-Agent": "TimeTracker/1.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read()
            img  = Image.open(io.BytesIO(data)).convert("RGBA")
            if needs_crop:
                w, h  = img.size
                side  = min(w, h)
                left  = (w - side) // 2
                top   = (h - side) // 2
                img   = img.crop((left, top, left + side, top + side))
            save = img.resize((_SAVE_SIZE, _SAVE_SIZE), Image.Resampling.LANCZOS)
            save.save(disk_path, "PNG")
            result = save if size == _SAVE_SIZE else save.resize((size, size), Image.Resampling.LANCZOS)
            _mem_cache[key] = result
            return result
        except Exception:
            continue

    return None


def fetch_steam_icon_by_name(game_name: str, size: int) -> Image.Image | None:
    """Recherche le jeu sur Steam par nom et télécharge son icône."""
    import io, urllib.request, urllib.parse

    key = (game_name, size)
    if key in _mem_cache:
        return _mem_cache[key]

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    disk_path = ICON_DIR / (_safe_filename(game_name) + ".png")
    if disk_path.exists():
        try:
            img = Image.open(disk_path).convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.Resampling.LANCZOS)
            _mem_cache[key] = img
            return img
        except Exception:
            pass

    try:
        q = urllib.parse.quote(game_name)
        req = urllib.request.Request(
            f"https://store.steampowered.com/api/storesearch/?term={q}&l=english&cc=US",
            headers={"User-Agent": "TimeTracker/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = __import__("json").loads(r.read())
        items = data.get("items", [])
        if not items:
            return None
        appid = items[0]["id"]
        url = f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
        req2 = urllib.request.Request(url, headers={"User-Agent": "TimeTracker/1.0"})
        with urllib.request.urlopen(req2, timeout=8) as r:
            raw = r.read()
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w - side) // 2, (h - side) // 2,
                        (w - side) // 2 + side, (h - side) // 2 + side))
        save = img.resize((_SAVE_SIZE, _SAVE_SIZE), Image.Resampling.LANCZOS)
        save.save(disk_path, "PNG")
        result = save if size == _SAVE_SIZE else save.resize((size, size), Image.Resampling.LANCZOS)
        _mem_cache[key] = result
        return result
    except Exception:
        return None


def find_exe_by_process(proc_name: str) -> str | None:
    """
    Cherche l'exe d'un jeu quand exe_path est inconnu.
    Vérifie le registre Battle.net / GOG / Epic, puis un scan 1 niveau
    dans Program Files et les dossiers "Games" des autres lecteurs.
    """
    import winreg, json, string

    name_lower = proc_name.lower()

    # ── Battle.net ────────────────────────────────────────────────────────
    BNET_EXES = {
        "wow.exe":          [r"_retail_\Wow.exe",        r"Wow.exe"],
        "wowclassic.exe":   [r"_classic_\WowClassic.exe", r"_classic_era_\WowClassic.exe", r"WowClassic.exe"],
        "wowt.exe":         [r"_ptr_\WowT.exe"],
        "diablo4.exe":      [r"Diablo IV.exe"],
        "overwatch.exe":    [r"Overwatch.exe"],
        "hearthstone.exe":  [r"Hearthstone.exe"],
        "starcraft2.exe":   [r"StarCraft II.exe"],
    }
    if name_lower in BNET_EXES:
        for reg_path in [
            r"SOFTWARE\WOW6432Node\Blizzard Entertainment",
            r"SOFTWARE\Blizzard Entertainment",
        ]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as parent:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(parent, i); i += 1
                            with winreg.OpenKey(parent, sub) as k:
                                install_dir = winreg.QueryValueEx(k, "InstallPath")[0]
                                for rel in BNET_EXES[name_lower]:
                                    c = Path(install_dir) / rel
                                    if c.exists():
                                        return str(c)
                        except OSError:
                            break
                        except FileNotFoundError:
                            continue
            except Exception:
                pass

    # ── GOG ───────────────────────────────────────────────────────────────
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\WOW6432Node\GOG.com\Games") as games:
            i = 0
            while True:
                try:
                    gid = winreg.EnumKey(games, i); i += 1
                    with winreg.OpenKey(games, gid) as g:
                        exe = winreg.QueryValueEx(g, "exe")[0]
                        if Path(exe).name.lower() == name_lower and Path(exe).exists():
                            return exe
                except OSError:
                    break
                except Exception:
                    continue
    except Exception:
        pass

    # ── Epic Games ────────────────────────────────────────────────────────
    manifests = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) \
                / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if manifests.exists():
        for mf in manifests.glob("*.item"):
            try:
                d = json.loads(mf.read_text(encoding="utf-8"))
                if Path(d.get("LaunchExecutable", "")).name.lower() == name_lower:
                    c = Path(d.get("InstallLocation", "")) / d["LaunchExecutable"]
                    if c.exists():
                        return str(c)
            except Exception:
                pass

    # ── Scan 1 niveau dans Program Files et dossiers Games ────────────────
    roots = [Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")]
    for drive in string.ascii_uppercase:
        for sub in ("Games", "GOG Games", "Jeux"):
            p = Path(f"{drive}:/{sub}")
            if p.exists():
                roots.append(p)
    for root in roots:
        try:
            for d in root.iterdir():
                if not d.is_dir():
                    continue
                c = d / proc_name
                if c.exists():
                    return str(c)
        except Exception:
            pass

    return None


def get_pil_icon(exe_path: str, size: int = 24) -> Image.Image | None:
    """Extraction directe depuis l'exe, sans cache disque (compat)."""
    return _extract_from_exe(exe_path, size)


def _extract_from_exe(exe_path: str, size: int) -> Image.Image | None:
    try:
        SHGFI_ICON      = 0x100
        SHGFI_LARGEICON = 0x0
        SHGFI_SMALLICON = 0x1

        class SHFILEINFOW(ctypes.Structure):
            _fields_ = [
                ("hIcon",         wintypes.HICON),
                ("iIcon",         ctypes.c_int),
                ("dwAttributes",  wintypes.DWORD),
                ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName",    ctypes.c_wchar * 80),
            ]

        shfi  = SHFILEINFOW()
        flags = SHGFI_ICON | (SHGFI_SMALLICON if size <= 16 else SHGFI_LARGEICON)
        ret   = ctypes.windll.shell32.SHGetFileInfoW(
            exe_path, 0, ctypes.byref(shfi), ctypes.sizeof(shfi), flags
        )
        if not ret or not shfi.hIcon:
            return None

        class ICONINFO(ctypes.Structure):
            _fields_ = [
                ("fIcon",    wintypes.BOOL),
                ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD),
                ("hbmMask",  wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP),
            ]

        ii = ICONINFO()
        ctypes.windll.user32.GetIconInfo(shfi.hIcon, ctypes.byref(ii))

        if not ii.hbmColor:
            ctypes.windll.user32.DestroyIcon(shfi.hIcon)
            return None

        class BITMAP(ctypes.Structure):
            _fields_ = [
                ("bmType",       ctypes.c_long),
                ("bmWidth",      ctypes.c_long),
                ("bmHeight",     ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long),
                ("bmPlanes",     wintypes.WORD),
                ("bmBitsPixel",  wintypes.WORD),
                ("bmBits",       ctypes.c_void_p),
            ]

        bmp = BITMAP()
        ctypes.windll.gdi32.GetObjectW(ii.hbmColor, ctypes.sizeof(bmp), ctypes.byref(bmp))
        w, h = bmp.bmWidth, abs(bmp.bmHeight)

        if w == 0 or h == 0:
            ctypes.windll.gdi32.DeleteObject(ii.hbmMask)
            ctypes.windll.gdi32.DeleteObject(ii.hbmColor)
            ctypes.windll.user32.DestroyIcon(shfi.hIcon)
            return None

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize",          wintypes.DWORD),
                ("biWidth",         ctypes.c_long),
                ("biHeight",        ctypes.c_long),
                ("biPlanes",        wintypes.WORD),
                ("biBitCount",      wintypes.WORD),
                ("biCompression",   wintypes.DWORD),
                ("biSizeImage",     wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed",       wintypes.DWORD),
                ("biClrImportant",  wintypes.DWORD),
            ]

        bi             = BITMAPINFOHEADER()
        bi.biSize      = ctypes.sizeof(bi)
        bi.biWidth     = w
        bi.biHeight    = h
        bi.biPlanes    = 1
        bi.biBitCount  = 32
        bi.biCompression = 0

        buf = ctypes.create_string_buffer(w * h * 4)
        hdc = ctypes.windll.user32.GetDC(None)
        ctypes.windll.gdi32.GetDIBits(hdc, ii.hbmColor, 0, h, buf, ctypes.byref(bi), 0)
        ctypes.windll.user32.ReleaseDC(None, hdc)

        ctypes.windll.gdi32.DeleteObject(ii.hbmMask)
        ctypes.windll.gdi32.DeleteObject(ii.hbmColor)
        ctypes.windll.user32.DestroyIcon(shfi.hIcon)

        data = bytearray(buf)
        for i in range(0, len(data), 4):           # BGRA → RGBA
            data[i], data[i + 2] = data[i + 2], data[i]

        if max(data[3::4]) == 0:                   # pas de canal alpha → opaque
            for i in range(3, len(data), 4):
                data[i] = 255

        img = Image.frombytes("RGBA", (w, h), bytes(data))
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)  # GetDIBits bottom-up

        if (w, h) != (size, size):
            img = img.resize((size, size), Image.Resampling.LANCZOS)

        return img
    except Exception:
        return None
