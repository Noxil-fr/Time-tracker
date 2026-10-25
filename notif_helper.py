"""
Fenêtre de notification autonome — appelé en sous-processus.
Usage : python notif_helper.py '<json>'
"""
import base64
import ctypes
import ctypes.wintypes as wintypes
import io
import json
import os
import sys
import tkinter as tk

_MANTLE  = "#0f0f0f"
_BASE    = "#161616"
_SURF0   = "#222222"
_SURF1   = "#2a2a2a"
_SURF2   = "#383838"
_OVERLAY = "#555555"
_TEXT    = "#f0f0f0"
_SUB     = "#aaaaaa"
_BLUE    = "#4a9eff"
_BLUE_D  = "#3a8ef0"
_GREEN   = "#22c55e"
_GREEN_D = "#16a34a"
_GOLD    = "#f5c542"
_GOLD_D  = "#d4a017"


def _apply_dwm(hwnd: int, accent_hex: str) -> None:
    """Windows 11 : coins arrondis + bordure colorée via DWM."""
    try:
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref)
        )
        r = int(accent_hex[1:3], 16)
        g = int(accent_hex[3:5], 16)
        b = int(accent_hex[5:7], 16)
        color = ctypes.c_int((b << 16) | (g << 8) | r)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 34, ctypes.byref(color), ctypes.sizeof(color)
        )
    except Exception:
        pass


def _show_on_top(root: tk.Tk, x: int, y: int, w: int, h: int) -> bool:
    """Affiche la fenêtre au-dessus des jeux en plein écran fenêtré, sans jamais prendre le focus
    (prendre le focus réduirait un jeu en plein écran exclusif). False si l'API Windows échoue."""
    try:
        user32 = ctypes.windll.user32
        user32.GetAncestor.restype     = wintypes.HWND
        user32.GetAncestor.argtypes    = [wintypes.HWND, ctypes.c_uint]
        user32.GetWindowLongW.restype  = ctypes.c_long
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowPos.argtypes   = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                          ctypes.c_uint]

        GA_ROOT          = 2
        GWL_EXSTYLE      = -20
        WS_EX_TOPMOST    = 0x00000008
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        HWND_TOPMOST     = wintypes.HWND(-1)
        SWP_NOACTIVATE   = 0x0010
        SWP_SHOWWINDOW   = 0x0040
        SWP_FLAGS        = 0x0001 | 0x0002 | SWP_NOACTIVATE  # NOSIZE|NOMOVE|NOACTIVATE

        hwnd  = user32.GetAncestor(root.winfo_id(), GA_ROOT) or root.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              style | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)

        def _raise():
            try:
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)
                root.after(500, _raise)   # le jeu peut repasser devant : on réaffirme
            except Exception:
                pass

        # root.deiconify() activerait la fenêtre : on l'affiche (et la place) sans activation
        user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        root.after(500, _raise)
        return True
    except Exception:
        return False


def _make_window(data: dict) -> tk.Tk:
    title      = data.get("title", "")
    message    = data.get("message", "")
    color      = data.get("color", "blue")
    suggestion = data.get("suggestion")
    icon_b64   = data.get("icon_b64", "")

    accent   = _GREEN if color == "green" else (_GOLD if color == "gold" else _BLUE)
    accent_d = _GREEN_D if color == "green" else (_GOLD_D if color == "gold" else _BLUE_D)
    W = 380 if color == "gold" else 360

    # Tk demande le premier plan à son démarrage. Si Windows nous l'autorise (ex. joueur
    # inactif depuis plus de 200 s), on verrouille d'abord : la popup ne volera pas le focus
    # au jeu. Le verrou se lève tout seul à la prochaine action de l'utilisateur.
    try:
        ctypes.windll.user32.LockSetForegroundWindow(1)   # LSFW_LOCK
    except Exception:
        pass

    root = tk.Tk()
    root.overrideredirect(True)
    # Pas de root.attributes("-topmost") : Tk le pose sans SWP_NOACTIVATE et vole le focus.
    # _show_on_top() gère le premier plan sans activation.
    root.configure(bg=_BASE)
    root.withdraw()

    # ── Layout racine : [barre accent | contenu] ──────────────────────────
    outer = tk.Frame(root, bg=_BASE)
    outer.pack(fill="both", expand=True)

    # Barre accent gauche (plus épaisse pour les notifs festives)
    bar_w = 5 if color == "gold" else 3
    tk.Frame(outer, bg=accent, width=bar_w).pack(side="left", fill="y")

    # Zone contenu
    content = tk.Frame(outer, bg=_BASE)
    content.pack(side="left", fill="both", expand=True)

    # ── Corps principal ───────────────────────────────────────────────────
    body = tk.Frame(content, bg=_BASE, padx=14, pady=14)
    body.pack(fill="both", expand=True)

    hdr = tk.Frame(body, bg=_BASE)
    hdr.pack(fill="x")

    # Icône (optionnelle)
    if icon_b64:
        try:
            from PIL import Image, ImageTk
            img   = Image.open(io.BytesIO(base64.b64decode(icon_b64)))
            img   = img.resize((36, 36), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            wrap  = tk.Frame(hdr, bg=_SURF0, width=36, height=36)
            wrap.pack(side="left", padx=(0, 11))
            wrap.pack_propagate(False)
            lbl = tk.Label(wrap, image=photo, bg=_SURF0)
            lbl._photo = photo
            lbl.pack(expand=True)
        except Exception:
            pass

    # Colonne texte
    text_col = tk.Frame(hdr, bg=_BASE)
    text_col.pack(side="left", fill="both", expand=True)

    title_row = tk.Frame(text_col, bg=_BASE)
    title_row.pack(fill="x")

    tk.Label(title_row, text=title, bg=_BASE, fg=_TEXT,
             font=("Segoe UI", 12, "bold"), anchor="w").pack(
        side="left", fill="x", expand=True)

    btn_x = tk.Label(title_row, text="✕", bg=_BASE, fg=_OVERLAY,
                     font=("Segoe UI", 10), cursor="hand2", padx=2)
    btn_x.pack(side="right")
    btn_x.bind("<Button-1>", lambda _: root.destroy())
    btn_x.bind("<Enter>",    lambda _: btn_x.config(fg=_TEXT))
    btn_x.bind("<Leave>",    lambda _: btn_x.config(fg=_OVERLAY))

    if message:
        tk.Label(text_col, text=message, bg=_BASE, fg=_SUB,
                 font=("Segoe UI", 10), anchor="w",
                 wraplength=W - 70, justify="left").pack(fill="x", pady=(5, 0))

    # ── Boutons d'action (suggestion) ────────────────────────────────────
    if suggestion:
        tk.Frame(content, bg=_SURF0, height=1).pack(fill="x")
        act = tk.Frame(content, bg=_SURF0, padx=14, pady=9)
        act.pack(fill="x")

        def _add():
            try:
                os.write(1, b"add\n")
            except Exception:
                pass
            root.destroy()

        def _ignore_forever():
            try:
                os.write(1, b"ignore\n")
            except Exception:
                pass
            root.destroy()

        add = tk.Label(act, text="Ajouter →", bg=accent, fg=_MANTLE,
                       font=("Segoe UI", 9, "bold"), padx=14, pady=5, cursor="hand2")
        add.pack(side="right")
        add.bind("<Button-1>", lambda _: _add())
        add.bind("<Enter>",    lambda _: add.config(bg=accent_d))
        add.bind("<Leave>",    lambda _: add.config(bg=accent))

        ign = tk.Label(act, text="Ignorer", bg=_SURF1, fg=_SUB,
                       font=("Segoe UI", 9), padx=14, pady=5, cursor="hand2")
        ign.pack(side="right", padx=(0, 6))
        ign.bind("<Button-1>", lambda _: root.destroy())
        ign.bind("<Enter>",    lambda _: ign.config(bg=_SURF2, fg=_TEXT))
        ign.bind("<Leave>",    lambda _: ign.config(bg=_SURF1, fg=_SUB))

        never = tk.Label(act, text="Ne plus proposer", bg=_SURF1, fg=_SUB,
                         font=("Segoe UI", 9), padx=14, pady=5, cursor="hand2")
        never.pack(side="left")
        never.bind("<Button-1>", lambda _: _ignore_forever())
        never.bind("<Enter>",    lambda _: never.config(bg=_SURF2, fg=_TEXT))
        never.bind("<Leave>",    lambda _: never.config(bg=_SURF1, fg=_SUB))

    else:
        duration = data.get("_duration", 5000)
        root.after(duration, root.destroy)

    # ── DWM : coins arrondis + bordure ───────────────────────────────────
    root.update_idletasks()
    _apply_dwm(root.winfo_id(), accent)

    # ── Position : bas à droite ───────────────────────────────────────────
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w  = root.winfo_reqwidth()
    h  = root.winfo_reqheight()
    y_from_bottom = data.get("_y_bottom", 56)
    x, y = sw - w - 16, sh - h - y_from_bottom
    root.geometry(f"{w}x{h}+{x}+{y}")
    if not _show_on_top(root, x, y, w, h):
        root.deiconify()

    # Son discret pour les notifs qui attendent une réponse (audible même en plein écran)
    if suggestion:
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    return root


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    try:
        data = json.loads(sys.argv[1])
        root = _make_window(data)
        root.mainloop()
    except Exception:
        sys.exit(1)
