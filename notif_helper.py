"""
Fenêtre de notification autonome — appelé en sous-processus.
Usage : python notif_helper.py '<json>'
"""
import base64
import io
import json
import sys
import tkinter as tk

_BLUE  = "#4a9eff"
_GREEN = "#22c55e"
_BASE  = "#161616"
_SURF1 = "#2a2a2a"
_SURF2 = "#383838"
_TEXT  = "#f0f0f0"
_SUB   = "#aaaaaa"
_CRUST = "#080808"


def _make_window(data: dict) -> tk.Tk:
    title      = data.get("title", "")
    message    = data.get("message", "")
    color      = data.get("color", "blue")
    suggestion = data.get("suggestion")
    icon_b64   = data.get("icon_b64", "")

    accent = _GREEN if color == "green" else _BLUE
    W, H   = 340, 98 + (50 if suggestion else 0)

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=_BASE)

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{sw - W - 16}+{sh - H - 56}")

    # Bordure colorée
    tk.Frame(root, bg=accent, height=3).pack(fill="x")

    body = tk.Frame(root, bg=_BASE, padx=12, pady=10)
    body.pack(fill="both", expand=True)

    hdr = tk.Frame(body, bg=_BASE)
    hdr.pack(fill="x")

    # Icône ou dot
    shown_icon = False
    if icon_b64:
        try:
            from PIL import Image, ImageTk
            img  = Image.open(io.BytesIO(base64.b64decode(icon_b64)))
            photo = ImageTk.PhotoImage(img)
            lbl   = tk.Label(hdr, image=photo, bg=_BASE)
            lbl._photo = photo
            lbl.pack(side="left", padx=(0, 8))
            shown_icon = True
        except Exception:
            pass
    if not shown_icon:
        dot = tk.Canvas(hdr, width=8, height=8, bg=_BASE, highlightthickness=0)
        dot.create_oval(1, 1, 7, 7, fill=accent, outline="")
        dot.pack(side="left", padx=(0, 8), pady=2)

    tk.Label(hdr, text=title, bg=_BASE, fg=_TEXT,
             font=("Segoe UI", 10, "bold"), anchor="w").pack(
        side="left", fill="x", expand=True)

    btn_x = tk.Label(hdr, text="✕", bg=_BASE, fg=_SUB,
                     font=("Segoe UI", 10), cursor="hand2")
    btn_x.pack(side="right")
    btn_x.bind("<Button-1>", lambda _: root.destroy())
    btn_x.bind("<Enter>",    lambda _: btn_x.config(fg=_TEXT))
    btn_x.bind("<Leave>",    lambda _: btn_x.config(fg=_SUB))

    if message:
        tk.Label(body, text=message, bg=_BASE, fg=_SUB,
                 font=("Segoe UI", 9), anchor="w",
                 wraplength=W - 40, justify="left").pack(fill="x", pady=(4, 0))

    if suggestion:
        tk.Frame(root, bg=_SURF1, height=1).pack(fill="x")
        act = tk.Frame(root, bg=_BASE, padx=12, pady=8)
        act.pack(fill="x")

        ign = tk.Label(act, text="Ignorer", bg=_SURF1, fg=_TEXT,
                       font=("Segoe UI", 9, "bold"), padx=12, pady=5, cursor="hand2")
        ign.pack(side="right", padx=(6, 0))
        ign.bind("<Button-1>", lambda _: root.destroy())
        ign.bind("<Enter>",    lambda _: ign.config(bg=_SURF2))
        ign.bind("<Leave>",    lambda _: ign.config(bg=_SURF1))

        def _add():
            sys.stdout.write("add\n")
            sys.stdout.flush()
            root.destroy()

        add = tk.Label(act, text="Ajouter →", bg=_GREEN, fg=_CRUST,
                       font=("Segoe UI", 9, "bold"), padx=12, pady=5, cursor="hand2")
        add.pack(side="right")
        add.bind("<Button-1>", lambda _: _add())
        add.bind("<Enter>",    lambda _: add.config(bg="#16a34a"))
        add.bind("<Leave>",    lambda _: add.config(bg=_GREEN))
    else:
        root.after(5000, root.destroy)

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
