import math
import sys
import winreg

from PIL import Image, ImageDraw
import pystray

_AUTOSTART_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "Time Tracker"   # même nom que l'installeur (MyAppName dans TimeTracker.iss)
_LEGACY_AUTOSTART_NAME = "TimeTracker"  # ancien nom, créait un double lancement au démarrage

# ── Icône ────────────────────────────────────────────────────────────────────

def _make_icon(size: int = 64) -> Image.Image:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy, r = size // 2, size // 2, size // 2 - 1

    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 fill="#89b4fa", outline="#cdd6f4", width=2)

    ri = r - 6
    draw.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill="#1e1e2e")

    def _hand(angle_deg: float, length: float, width: int):
        rad = math.radians(angle_deg - 90)
        draw.line(
            [cx, cy, cx + length * math.cos(rad), cy + length * math.sin(rad)],
            fill="#cdd6f4", width=width,
        )

    _hand(0,   ri * 0.55, 3)
    _hand(150, ri * 0.75, 2)
    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill="#a6e3a1")
    return img


# ── Registre démarrage ────────────────────────────────────────────────────────

def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY) as k:
            val, _ = winreg.QueryValueEx(k, _AUTOSTART_NAME)
            return "--minimized" in val
    except OSError:
        return False


def cleanup_legacy_autostart() -> None:
    """Supprime l'ancienne entrée 'TimeTracker' qui doublonnait celle de l'installeur."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.DeleteValue(k, _LEGACY_AUTOSTART_NAME)
    except OSError:
        pass


def set_autostart(enabled: bool) -> None:
    if not _is_frozen():
        return
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
        ) as k:
            if enabled:
                value = f'"{sys.executable}" --minimized'
                winreg.SetValueEx(k, _AUTOSTART_NAME, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(k, _AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
    except OSError:
        pass


# ── Gestionnaire tray ─────────────────────────────────────────────────────────

class TrayManager:
    def __init__(self, window, quit_callback):
        self._window       = window
        self._quit_cb      = quit_callback
        self._icon: pystray.Icon | None = None

    # ── Callbacks pystray ────────────────────────────────────────────────────

    def _menu_show(self, icon=None, item=None):
        self._window.show()

    def _menu_toggle_autostart(self, icon, item):
        set_autostart(not is_autostart_enabled())

    def _menu_quit(self, icon=None, item=None):
        if self._icon:
            self._icon.stop()
        if self._quit_cb:
            self._quit_cb()

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self) -> pystray.Menu:
        items = [
            pystray.MenuItem("Afficher", self._menu_show, default=True),
            pystray.Menu.SEPARATOR,
        ]
        if _is_frozen():
            items.append(pystray.MenuItem(
                "Démarrer avec Windows",
                self._menu_toggle_autostart,
                checked=lambda _: is_autostart_enabled(),
            ))
            items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Quitter", self._menu_quit))
        return pystray.Menu(*items)

    # ── API publique ──────────────────────────────────────────────────────────

    def start(self) -> None:
        self._icon = pystray.Icon(
            "TimeTracker",
            _make_icon(),
            "Time Tracker",
            self._build_menu(),
        )
        self._icon.run_detached()
