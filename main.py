import ctypes
import sys

import customtkinter as ctk

from tray import TrayManager, acquire_single_instance_lock, set_autostart, is_autostart_enabled, _is_frozen
from ui.main_window import MainWindow


def _patch_ctk_draw():
    """
    Debounce _draw() on every CTk widget subclass to cap redraws at ~60 fps.

    Each CTk widget overrides _draw() and calls it on every <Configure> event
    (one per resize pixel, 300+ /sec on Windows). This patch replaces each
    class's own _draw with a version that coalesces rapid calls via after(16).
    CTkBaseClass._draw alone is never reached because subclasses override it.
    """
    def _make_debounced(orig_fn):
        def _debounced(self, no_color_updates: bool = False):
            if getattr(self, "_draw_pending", False):
                if not no_color_updates:
                    self._draw_nc = False
                return
            self._draw_pending = True
            self._draw_nc = no_color_updates

            def _execute():
                self._draw_pending = False
                if self.winfo_exists():
                    orig_fn(self, self._draw_nc)

            try:
                self.after(16, _execute)
            except Exception:
                orig_fn(self, no_color_updates)

        _debounced._ctk_patched = True
        return _debounced

    def _patch_class(cls):
        if "_draw" in cls.__dict__ and not getattr(cls.__dict__["_draw"], "_ctk_patched", False):
            cls._draw = _make_debounced(cls.__dict__["_draw"])
        for sub in cls.__subclasses__():
            _patch_class(sub)

    _patch_class(ctk.CTkBaseClass)


def main():
    # ── Instance unique ───────────────────────────────────────────────────────
    if not acquire_single_instance_lock():
        ctypes.windll.user32.MessageBoxW(
            0,
            "Time Tracker est déjà en cours d'exécution.\n"
            "Consultez l'icône dans la barre des tâches.",
            "Time Tracker",
            0x40,  # MB_ICONINFORMATION
        )
        return

    start_hidden = "--minimized" in sys.argv

    _patch_ctk_draw()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    win  = MainWindow(root)

    tray = TrayManager(root, quit_callback=win.quit)
    tray.start()

    # Masquer la fenêtre via le tray plutôt que la fermer
    win.set_hide_on_close(tray.hide_window)

    # Démarrage au lancement Windows : fenêtre cachée dès le départ
    if start_hidden:
        root.withdraw()

    # Activer le démarrage automatique si on tourne en .exe et que ce n'est pas déjà fait
    if _is_frozen() and not is_autostart_enabled():
        set_autostart(True)

    root.mainloop()


if __name__ == "__main__":
    main()
