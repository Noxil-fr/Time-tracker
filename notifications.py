import queue
import sys
import threading
import tkinter as tk


class NotificationManager:
    """Notifications flottantes bottom-right via tkinter dans un thread dédié."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self._root: tk.Tk | None = None
        self._win:  tk.Toplevel | None = None
        self._after_id = None
        self._on_add: callable | None = None

        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def set_on_add_game(self, cb: callable) -> None:
        self._on_add = cb

    # ── API publique (thread-safe) ─────────────────────────────────────────────

    def show(self, title: str, message: str,
             color: str = "blue", suggestion: dict | None = None,
             icon=None) -> None:
        self._q.put(("show", title, message, color, suggestion, icon))

    def hide(self) -> None:
        self._q.put(("hide",))

    # ── Loop tkinter (thread dédié) ───────────────────────────────────────────

    def _loop(self) -> None:
        try:
            self._root = tk.Tk()
            self._root.withdraw()
            self._root.after(50, self._drain)
            self._root.mainloop()
        except Exception:
            print("[NotifManager] crash _loop:", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _drain(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                cmd = msg[0]
                try:
                    if cmd == "show":
                        self._show(msg[1], msg[2], msg[3], msg[4],
                                   msg[5] if len(msg) > 5 else None)
                    elif cmd == "hide":
                        self._close()
                except Exception:
                    print("[NotifManager] crash _show:", file=sys.stderr)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
        except queue.Empty:
            pass
        finally:
            # toujours replanifier, même après une exception
            if self._root:
                self._root.after(50, self._drain)

    # ── Création de la fenêtre ────────────────────────────────────────────────

    _BLUE  = "#4a9eff"
    _GREEN = "#22c55e"
    _BASE  = "#161616"
    _SURF1 = "#2a2a2a"
    _SURF2 = "#383838"
    _TEXT  = "#f0f0f0"
    _SUB   = "#aaaaaa"
    _CRUST = "#080808"

    def _show(self, title: str, message: str,
              color: str, suggestion: dict | None,
              icon=None) -> None:
        accent = self._GREEN if color == "green" else self._BLUE

        self._close(cancel_only=True)

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        W = 340
        H = 98 + (50 if suggestion else 0)
        x = sw - W - 16
        y = sh - H - 56

        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{W}x{H}+{x}+{y}")
        win.configure(bg=self._BASE)
        self._win = win

        # Bordure colorée
        tk.Frame(win, bg=accent, height=3).pack(fill="x")

        # Corps
        body = tk.Frame(win, bg=self._BASE, padx=12, pady=10)
        body.pack(fill="both", expand=True)

        hdr = tk.Frame(body, bg=self._BASE)
        hdr.pack(fill="x")

        # Icône ou dot
        if icon is not None:
            try:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(icon)
                lbl_icon = tk.Label(hdr, image=photo, bg=self._BASE)
                lbl_icon._photo = photo  # empêche le GC
                lbl_icon.pack(side="left", padx=(0, 8))
            except Exception:
                icon = None
        if icon is None:
            dot = tk.Canvas(hdr, width=8, height=8, bg=self._BASE,
                            highlightthickness=0)
            dot.create_oval(1, 1, 7, 7, fill=accent, outline="")
            dot.pack(side="left", padx=(0, 8), pady=2)

        lbl_title = tk.Label(hdr, text=title, bg=self._BASE, fg=self._TEXT,
                             font=("Segoe UI", 10, "bold"), anchor="w")
        lbl_title.pack(side="left", fill="x", expand=True)

        btn_x = tk.Label(hdr, text="✕", bg=self._BASE, fg=self._SUB,
                         font=("Segoe UI", 10), cursor="hand2")
        btn_x.pack(side="right")
        btn_x.bind("<Button-1>", lambda _: self._dismiss())
        btn_x.bind("<Enter>",    lambda _: btn_x.config(fg=self._TEXT))
        btn_x.bind("<Leave>",    lambda _: btn_x.config(fg=self._SUB))

        if message:
            tk.Label(body, text=message, bg=self._BASE, fg=self._SUB,
                     font=("Segoe UI", 9), anchor="w",
                     wraplength=W - 40, justify="left").pack(fill="x", pady=(4, 0))

        if suggestion:
            tk.Frame(win, bg=self._SURF1, height=1).pack(fill="x")
            act = tk.Frame(win, bg=self._BASE, padx=12, pady=8)
            act.pack(fill="x")

            ign = tk.Label(act, text="Ignorer", bg=self._SURF1, fg=self._TEXT,
                           font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                           cursor="hand2")
            ign.pack(side="right", padx=(6, 0))
            ign.bind("<Button-1>", lambda _: self._dismiss())
            ign.bind("<Enter>",    lambda _: ign.config(bg=self._SURF2))
            ign.bind("<Leave>",    lambda _: ign.config(bg=self._SURF1))

            add = tk.Label(act, text="Ajouter →", bg=self._GREEN, fg=self._CRUST,
                           font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                           cursor="hand2")
            add.pack(side="right")
            add.bind("<Button-1>", lambda _, s=suggestion: self._add_game(s))
            add.bind("<Enter>",    lambda _: add.config(bg="#16a34a"))
            add.bind("<Leave>",    lambda _: add.config(bg=self._GREEN))

        win.update()
        win.lift()

        if not suggestion:
            self._after_id = self._root.after(5000, self._dismiss)

    def _dismiss(self) -> None:
        self._close()

    def _add_game(self, suggestion: dict) -> None:
        self._close()
        if self._on_add:
            try:
                self._on_add(
                    suggestion["game_name"],
                    suggestion["proc_name"],
                    suggestion["exe_path"],
                )
            except Exception:
                import traceback
                traceback.print_exc(file=sys.stderr)

    def _close(self, cancel_only: bool = False) -> None:
        if self._after_id:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if not cancel_only and self._win:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None
