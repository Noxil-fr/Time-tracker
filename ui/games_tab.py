import tkinter as tk
from datetime import datetime, timedelta

import customtkinter as ctk
from PIL import ImageTk

from data_manager import DataManager
from icon_cache import get_game_icon
from tracker import ProcessTracker
from utils import format_duration

# Fixed column widths keep headers and rows aligned
_COL_TIME_W   = 110
_COL_LAST_W   = 134
_COL_STATUS_W = 90
_COL_MENU_W   = 30
_ACCENT_W     = 3    # barre verticale gauche quand In Game

_LIST_ICON   = 40   # icon size in list rows

_ARCHIVE_DAYS = 30   # jours sans session → section Archivés

_SKIP_DIRS = (
    "\\windows\\system32\\",
    "\\windows\\syswow64\\",
    "\\windows\\winsxs\\",
)

_BG = "#181825"   # tab content background (matches main_window content frame)

# Tracks which _ScrollFrame currently owns the global mousewheel binding
_active_scroll: list = [None]

_SB_TRACK = "#1e1e2e"
_SB_THUMB = "#45475a"
_SB_HOVER = "#585b70"
_SB_W     = 6
_SB_PAD   = 2   # espace entre bord et poignée


class _DarkScrollbar:
    """Ascenseur Canvas entièrement personnalisé, indépendant du thème Windows."""

    def __init__(self, parent, command):
        self._cmd      = command
        self._lo       = 0.0
        self._hi       = 1.0
        self._drag_off = None   # offset y au début du drag

        self._cv = tk.Canvas(
            parent, width=_SB_W + _SB_PAD * 2,
            bg=_SB_TRACK, highlightthickness=0, bd=0,
        )
        self._cv.bind("<Configure>",       self._draw)
        self._cv.bind("<ButtonPress-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",       self._on_motion)
        self._cv.bind("<ButtonRelease-1>", self._on_release)
        self._cv.bind("<Enter>",  lambda _: self._tint(True))
        self._cv.bind("<Leave>",  lambda _: self._tint(False))
        self._hovering = False

    # ── Interface compatible tk.Scrollbar ─────────────────────────────────────

    def set(self, lo: str, hi: str):
        self._lo, self._hi = float(lo), float(hi)
        self._draw()

    def pack(self, **kw):
        self._cv.pack(**kw)

    # ── Rendu ─────────────────────────────────────────────────────────────────

    def _thumb_rect(self):
        h = self._cv.winfo_height() or 1
        size   = max(0.04, self._hi - self._lo)
        th     = max(28, int(size * h))
        ty     = int(self._lo * h)
        ty     = min(ty, h - th)
        x0, x1 = _SB_PAD, _SB_PAD + _SB_W
        return x0, ty, x1, ty + th

    def _draw(self, _=None):
        self._cv.delete("thumb")
        x0, y0, x1, y1 = self._thumb_rect()
        if self._hi - self._lo >= 1.0:
            return
        color = _SB_HOVER if self._hovering else _SB_THUMB
        r = _SB_W // 2
        # Poignée avec coins arrondis
        self._cv.create_arc( x0, y0, x0+2*r, y0+2*r, start=90,  extent=90,  fill=color, outline="", tags="thumb")
        self._cv.create_arc( x1-2*r, y0, x1, y0+2*r, start=0,   extent=90,  fill=color, outline="", tags="thumb")
        self._cv.create_arc( x0, y1-2*r, x0+2*r, y1, start=180, extent=90,  fill=color, outline="", tags="thumb")
        self._cv.create_arc( x1-2*r, y1-2*r, x1, y1, start=270, extent=90,  fill=color, outline="", tags="thumb")
        self._cv.create_rectangle(x0+r, y0, x1-r, y1, fill=color, outline="", tags="thumb")
        self._cv.create_rectangle(x0,   y0+r, x1, y1-r, fill=color, outline="", tags="thumb")

    def _tint(self, state: bool):
        self._hovering = state
        self._draw()

    # ── Interactions ──────────────────────────────────────────────────────────

    def _on_press(self, e):
        x0, y0, x1, y1 = self._thumb_rect()
        if y0 <= e.y <= y1:
            self._drag_off = e.y - y0
        else:
            h = self._cv.winfo_height() or 1
            self._cmd("moveto", str(e.y / h))

    def _on_motion(self, e):
        if self._drag_off is None:
            return
        h  = self._cv.winfo_height() or 1
        th = self._thumb_rect()[3] - self._thumb_rect()[1]
        frac = (e.y - self._drag_off) / max(h - th, 1)
        self._cmd("moveto", str(max(0.0, min(1.0, frac))))

    def _on_release(self, _):
        self._drag_off = None



_MONTHS_FR = ["jan.", "fév.", "mar.", "avr.", "mai", "juin",
              "juil.", "août", "sep.", "oct.", "nov.", "déc."]


def _format_last_played(sessions: list) -> str:
    if not sessions:
        return "Jamais"
    try:
        last = datetime.fromisoformat(sessions[-1]["end"])
    except (ValueError, KeyError):
        return "—"
    delta = datetime.now() - last
    days = delta.days
    if days == 0:
        return "Aujourd'hui"
    if days == 1:
        return "Hier"
    if days < 7:
        return f"il y a {days}j"
    if days < 30:
        return f"il y a {days // 7} sem."
    if days < 365:
        return f"il y a {days // 30} mois"
    return f"{last.day} {_MONTHS_FR[last.month - 1]} {last.year}"



class _ScrollFrame:
    """Lightweight scrollable frame using only native tk widgets.
    Replacing CTkScrollableFrame eliminates two CTk Canvases (CTkFrame wrapper +
    CTkScrollbar) that each fire _draw() on every resize event."""

    def __init__(self, parent, bg: str = _BG):
        self._bg = bg
        self._outer = tk.Frame(parent, bg=bg)
        self._canvas = tk.Canvas(self._outer, bg=bg, highlightthickness=0, bd=0)
        self._vsb = _DarkScrollbar(self._outer, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vsb.set)
        self._vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._inner = tk.Frame(self._canvas, bg=bg)
        self._win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", self._sync_scrollregion)
        self._canvas.bind("<Configure>", self._sync_width)

    def _sync_scrollregion(self, _e=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _sync_width(self, e):
        self._canvas.itemconfig(self._win, width=e.width)

    def _on_scroll(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    # ── CTkScrollableFrame-compatible interface ────────────────────────────────

    @property
    def inner(self) -> tk.Frame:
        """The frame widgets should be parented to."""
        return self._inner

    def winfo_children(self):
        return self._inner.winfo_children()

    def winfo_width(self):
        return self._canvas.winfo_width()

    def pack(self, **kwargs):
        self._outer.pack(**kwargs)
        _active_scroll[0] = self
        # Bind after layout settles so winfo_toplevel() is valid
        self._outer.after(0, self._grab_scroll)

    def pack_forget(self):
        self._outer.pack_forget()
        if _active_scroll[0] is self:
            _active_scroll[0] = None
            try:
                self._outer.winfo_toplevel().unbind_all("<MouseWheel>")
            except Exception:
                pass

    def _grab_scroll(self):
        if _active_scroll[0] is self:
            try:
                self._outer.winfo_toplevel().bind_all(
                    "<MouseWheel>", self._on_scroll
                )
            except Exception:
                pass


class GamesTab:
    def __init__(self, parent, dm: DataManager, tracker: ProcessTracker):
        self._dm = dm
        self._tracker = tracker
        self._parent = parent
        self._sort_key = "name"
        self._sort_asc = True
        self._rows: dict = {}
        self._rows_all: dict = {}
        self._last_names: set = set()
        self._last_archived: frozenset = frozenset()
        self._icon_gen = 0

        self._build(parent)
        self.refresh()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self, parent):
        self._hdr_name = None
        self._hdr_time = None
        self._hdr_last = None

        self._content = tk.Frame(parent, bg=_BG)
        self._content.pack(fill="both", expand=True, padx=14, pady=(6, 10))

        self._list_scroll = _ScrollFrame(self._content, bg=_BG)

        self._empty_lbl = ctk.CTkLabel(
            self._content,
            text='Aucun jeu ajouté.\nCliquez sur "+ Ajouter" pour commencer.',
            font=ctk.CTkFont("Segoe UI", 16),
            text_color="#585b70", justify="center",
            fg_color=_BG,
        )

        self._list_scroll.pack(fill="both", expand=True)

    def _refresh_content(self):
        self._list_scroll.pack_forget()
        self._empty_lbl.pack_forget()

        if not self._dm.get_games():
            self._empty_lbl.pack(expand=True)
            return

        self._list_scroll.pack(fill="both", expand=True)

    # ── Sorting ────────────────────────────────────────────────────────────────

    def _sort_by(self, key: str):
        if self._sort_key == key:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_key = key
            self._sort_asc = key == "name"
        self._update_header_labels()
        self._force_rebuild()

    def _build_list_headers(self, parent: tk.Frame):
        hdr = tk.Frame(parent, bg=_BG)
        hdr.pack(fill="x", pady=(2, 0))

        # Spacer : accent bar + icon + padding gauche
        tk.Frame(hdr, width=_ACCENT_W + _LIST_ICON + 22, bg=_BG).pack(side="left")

        self._hdr_name = ctk.CTkButton(
            hdr, text="Jeu",
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color="transparent", hover_color="#252535",
            text_color="#45475a", anchor="w", height=28,
            command=lambda: self._sort_by("name"),
        )
        self._hdr_name.pack(side="left", fill="x", expand=True, pady=2)

        tk.Frame(hdr, width=_COL_MENU_W + 8, bg=_BG).pack(side="right")
        tk.Frame(hdr, width=_COL_STATUS_W, bg=_BG).pack(side="right")

        self._hdr_time = ctk.CTkButton(
            hdr, text="Temps total",
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color="transparent", hover_color="#252535",
            text_color="#45475a", width=_COL_TIME_W, anchor="center", height=28,
            command=lambda: self._sort_by("time"),
        )
        self._hdr_time.pack(side="right", pady=2)

        self._hdr_last = ctk.CTkButton(
            hdr, text="Dernier lancement",
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color="transparent", hover_color="#252535",
            text_color="#45475a", width=_COL_LAST_W, anchor="center", height=28,
            command=lambda: self._sort_by("recent"),
        )
        self._hdr_last.pack(side="right", pady=2)

        self._update_header_labels()

    def _update_header_labels(self):
        if self._hdr_name is None:
            return
        arrow = " ↑" if self._sort_asc else " ↓"
        self._hdr_name.configure(
            text=f"Jeu{arrow}" if self._sort_key == "name" else "Jeu",
            text_color="#a6adc8" if self._sort_key == "name" else "#45475a",
        )
        self._hdr_time.configure(
            text=f"Temps total{arrow}" if self._sort_key == "time" else "Temps total",
            text_color="#a6adc8" if self._sort_key == "time" else "#45475a",
        )
        self._hdr_last.configure(
            text=f"Dernier lancement{arrow}" if self._sort_key == "recent" else "Dernier lancement",
            text_color="#a6adc8" if self._sort_key == "recent" else "#45475a",
        )

    def _sorted_games(self) -> list:
        games = self._dm.get_games()
        if self._sort_key == "name":
            return sorted(games.items(), key=lambda x: x[0].lower(), reverse=not self._sort_asc)
        if self._sort_key == "time":
            return sorted(games.items(), key=lambda x: x[1]["total_seconds"], reverse=not self._sort_asc)
        # recent
        def _last_ts(item):
            s = item[1].get("sessions", [])
            return datetime.fromisoformat(s[-1]["end"]) if s else datetime.min
        return sorted(games.items(), key=_last_ts, reverse=not self._sort_asc)

    def _recent_games(self) -> list:
        """Jeux joués dans les 30 derniers jours ou actuellement actifs, triés par date (récent en premier)."""
        threshold = datetime.now() - timedelta(days=_ARCHIVE_DAYS)
        currently_active = set(self._tracker.get_active().keys())

        def _last_ts(item):
            s = item[1].get("sessions", [])
            return datetime.fromisoformat(s[-1]["end"]) if s else datetime.min

        recent = [
            (n, d) for n, d in self._dm.get_games().items()
            if n in currently_active or _last_ts((n, d)) > threshold
        ]
        # Jeux actifs en tête, puis par date de dernière session
        return sorted(recent, key=lambda x: (x[0] not in currently_active, -_last_ts(x).timestamp()))

    def _split_games(self) -> tuple[list, list]:
        """Retourne (actifs, archivés) selon la date de dernière session."""
        threshold = datetime.now() - timedelta(days=_ARCHIVE_DAYS)
        active, archived = [], []
        for name, data in self._sorted_games():
            sessions = data.get("sessions", [])
            if sessions and datetime.fromisoformat(sessions[-1]["end"]) < threshold:
                archived.append((name, data))
            else:
                active.append((name, data))
        return active, archived

    def _add_section_header(self, parent: tk.Frame, text: str):
        wrap = tk.Frame(parent, bg=_BG)
        wrap.pack(fill="x", padx=6, pady=(8, 4))
        tk.Label(
            wrap, text=text.upper(),
            font=("Segoe UI", 10, "bold"),
            bg=_BG, fg="#45475a", anchor="w",
        ).pack(side="left")
        tk.Frame(wrap, bg="#313244", height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=1
        )

    # ── Refresh ────────────────────────────────────────────────────────────────

    def _force_rebuild(self):
        self._last_names = set()
        self.refresh()

    def refresh(self):
        games = self._dm.get_games()
        active = self._tracker.get_active()
        current_names = set(games.keys())
        recent_names = frozenset(n for n, _ in self._recent_games())

        if current_names != self._last_names or recent_names != self._last_archived:
            self._last_names = current_names
            self._last_archived = recent_names
            self._rebuild_list(games)
            self._refresh_content()

        self._update_list(games, active)

    # ── List view ──────────────────────────────────────────────────────────────

    def _rebuild_list(self, games: dict):
        for w in self._list_scroll.winfo_children():
            w.destroy()
        self._rows = {}
        self._rows_all = {}
        icon_queue: list = []

        # ── Mes jeux récents (live, toujours triés par date) ─────────────
        self._add_section_header(self._list_scroll.inner, "Mes jeux récents")
        for name, data in self._recent_games():
            icon_lbl = self._add_list_row(name, data, static=False)
            exe = data.get("exe_path", "")
            if exe:
                icon_queue.append((exe, icon_lbl, name))

        # ── Mes jeux (tous les jeux, triés par préférence, temps statique)
        self._add_section_header(self._list_scroll.inner, "Ma bibliothèque")
        self._build_list_headers(self._list_scroll.inner)
        for idx, (name, data) in enumerate(self._sorted_games()):
            icon_lbl = self._add_list_row(name, data, static=True, index=idx)
            exe = data.get("exe_path", "")
            if exe:
                icon_queue.append((exe, icon_lbl, name))

        if icon_queue:
            self._load_icons(icon_queue, _LIST_ICON)

    def _add_list_row(self, name: str, data: dict, static: bool = False, index: int = 0) -> tk.Label:
        if static:
            row_bg   = "#222236" if index % 2 else "#1e1e2e"
            col_name = "#a6adc8"
            col_time = "#6c7086"
            col_meta = "#45475a"
        else:
            row_bg   = "#1e1e2e"
            col_name = "#cdd6f4"
            col_time = "#89b4fa"
            col_meta = "#585b70"

        # Conteneur externe : accent bar + ligne
        outer = tk.Frame(self._list_scroll.inner, bg=_BG)
        outer.pack(fill="x", pady=1)

        # Barre d'accent gauche (3 px — verte quand In Game)
        accent = tk.Frame(outer, width=_ACCENT_W, bg=_BG)
        accent.pack(side="left", fill="y")
        accent.pack_propagate(False)

        row = tk.Frame(outer, bg=row_bg)
        row.pack(side="left", fill="x", expand=True)

        # ── Droite ────────────────────────────────────────────────────────
        menu_btn = tk.Label(
            row, text="⋮",
            font=("Segoe UI", 15), bg=row_bg, fg="#45475a", cursor="hand2",
            width=2,
        )
        menu_btn.pack(side="right", padx=(0, 12), pady=0)
        menu_btn.bind("<Button-1>", lambda e, n=name: self._context_menu(e, n))

        # Badge "In Game" — largeur fixe pour garder les colonnes alignées
        status_wrap = tk.Frame(row, bg=row_bg, width=_COL_STATUS_W)
        status_wrap.pack(side="right", fill="y")
        status_wrap.pack_propagate(False)
        status_lbl = tk.Label(
            status_wrap, text="",
            font=("Segoe UI", 10, "bold"),
            bg=row_bg, fg="#a6e3a1", anchor="center",
        )
        status_lbl.pack(expand=True, fill="both")

        # Temps
        time_wrap = tk.Frame(row, bg=row_bg, width=_COL_TIME_W)
        time_wrap.pack(side="right", fill="y")
        time_wrap.pack_propagate(False)
        time_lbl = tk.Label(
            time_wrap, text=format_duration(data["total_seconds"]),
            font=("Segoe UI", 13),
            bg=row_bg, fg=col_time, anchor="e",
        )
        time_lbl.pack(expand=True, fill="both", padx=(0, 4))

        # Dernier lancement
        last_wrap = tk.Frame(row, bg=row_bg, width=_COL_LAST_W)
        last_wrap.pack(side="right", fill="y")
        last_wrap.pack_propagate(False)
        last_lbl = tk.Label(
            last_wrap, text=_format_last_played(data.get("sessions", [])),
            font=("Segoe UI", 12),
            bg=row_bg, fg=col_meta, anchor="e",
        )
        last_lbl.pack(expand=True, fill="both", padx=(0, 4))

        # ── Gauche ────────────────────────────────────────────────────────
        icon_wrap = tk.Frame(row, bg=row_bg, width=_LIST_ICON + 4, height=_LIST_ICON + 4)
        icon_wrap.pack(side="left", padx=(12, 8), pady=5)
        icon_wrap.pack_propagate(False)
        icon_lbl = tk.Label(icon_wrap, bg=row_bg)
        icon_lbl.pack(expand=True, fill="both")

        name_lbl = tk.Label(
            row, text=name,
            font=("Segoe UI", 13, "bold"),
            bg=row_bg, fg=col_name, anchor="w",
        )
        name_lbl.pack(side="left", fill="x", expand=True, pady=8)

        # Séparateur bas
        sep_color = "#2d2d45" if static else "#252535"
        tk.Frame(outer, bg=sep_color, height=1).pack(fill="x", side="bottom")

        for w in (outer, row, accent, icon_wrap, icon_lbl, name_lbl,
                  last_wrap, last_lbl, time_wrap, time_lbl, status_lbl):
            w.bind("<Button-3>", lambda e, n=name: self._context_menu(e, n))

        row_dict = self._rows_all if static else self._rows
        row_dict[name] = {
            "outer": outer, "row": row, "accent": accent,
            "time": time_lbl, "status": status_lbl,
            "_active": None, "_time_str": "",
            "row_bg": row_bg,
        }
        return icon_lbl

    def _update_list(self, games: dict, active: dict):
        for name, data in games.items():
            # Lignes live (Mes jeux récents) — temps + statut
            if name in self._rows:
                r = self._rows[name]
                total = data["total_seconds"]
                in_active = name in active
                if in_active:
                    elapsed = int((datetime.now() - active[name]).total_seconds())
                    total += elapsed

                time_str = format_duration(total)
                if time_str != r["_time_str"]:
                    r["time"].config(text=time_str)
                    r["_time_str"] = time_str

                if in_active != r["_active"]:
                    r["_active"] = in_active
                    if in_active:
                        r["accent"].config(bg="#a6e3a1")
                        r["status"].config(text="● In Game")
                    else:
                        r["accent"].config(bg=_BG)
                        r["status"].config(text="")

            # Lignes statiques (Ma bibliothèque) — statut uniquement
            if name in self._rows_all:
                r = self._rows_all[name]
                in_active = name in active
                if in_active != r["_active"]:
                    r["_active"] = in_active
                    if in_active:
                        r["accent"].config(bg="#a6e3a1")
                        r["status"].config(text="● In Game")
                    else:
                        r["accent"].config(bg=_BG)
                        r["status"].config(text="")

    # ── Icon loading ───────────────────────────────────────────────────────────

    def _load_icons(self, items: list, size: int):
        self._icon_gen += 1
        queue = [
            (exe, lbl, name) for exe, lbl, name in items
            if exe and not any(d in exe.lower() for d in _SKIP_DIRS)
        ]
        gen = self._icon_gen
        if queue:
            self._parent.winfo_toplevel().after(
                1, lambda: self._process_icon_queue(queue, gen, size)
            )

    def _process_icon_queue(self, queue: list, gen: int, size: int):
        if gen != self._icon_gen or not queue:
            return
        exe_path, icon_lbl, game_name = queue.pop(0)
        pil_img = get_game_icon(game_name, exe_path, size)
        if pil_img:
            try:
                if icon_lbl.winfo_exists():
                    if isinstance(icon_lbl, ctk.CTkLabel):
                        img = ctk.CTkImage(
                            light_image=pil_img, dark_image=pil_img,
                            size=(size, size),
                        )
                        icon_lbl.configure(image=img)
                    else:
                        photo = ImageTk.PhotoImage(pil_img)
                        icon_lbl.config(image=photo)
                        icon_lbl._photo = photo
            except Exception:
                pass
        if queue and gen == self._icon_gen:
            self._parent.winfo_toplevel().after(
                1, lambda: self._process_icon_queue(queue, gen, size)
            )

    # ── Context menu ───────────────────────────────────────────────────────────

    def _context_menu(self, event, name: str):
        root = self._parent.winfo_toplevel()
        menu = tk.Menu(
            root, tearoff=0,
            bg="#1e1e2e", fg="#cdd6f4",
            activebackground="#313244", activeforeground="#cdd6f4",
            font=("Segoe UI", 13),
        )
        menu.add_command(label="  Renommer", command=lambda: self._rename(name))
        menu.add_separator()
        menu.add_command(
            label="  Supprimer",
            foreground="#f38ba8", activeforeground="#f38ba8",
            command=lambda: self._delete(name),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _rename(self, old_name: str):
        root = self._parent.winfo_toplevel()
        dialog = RenameDialog(root, old_name, self._dm)
        root.wait_window(dialog)
        self._force_rebuild()

    def _delete(self, name: str):
        root = self._parent.winfo_toplevel()
        dialog = ConfirmDeleteDialog(root, name)
        root.wait_window(dialog)
        if dialog.confirmed:
            self._dm.delete_game(name)
            self._force_rebuild()

    def _open_add(self):
        from ui.add_game_dialog import AddGameDialog
        AddGameDialog(
            self._parent.winfo_toplevel(),
            self._dm, self._tracker,
            on_add=self._force_rebuild,
        )


# ── Dialogs ───────────────────────────────────────────────────────────────────

class RenameDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_name: str, dm):
        super().__init__(parent)
        self._dm = dm
        self._current = current_name

        self.title("Renommer le jeu")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color="#11111b")
        self._center(380, 195)
        self._build()

    def _center(self, w: int, h: int):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        ctk.CTkLabel(
            self, text="Renommer le jeu",
            font=ctk.CTkFont("Segoe UI", 16, "bold"),
            text_color="#cdd6f4",
        ).pack(pady=(20, 12), padx=20, anchor="w")

        self._entry = ctk.CTkEntry(
            self,
            font=ctk.CTkFont("Segoe UI", 14),
            fg_color="#313244", border_color="#45475a",
            text_color="#cdd6f4", height=40, corner_radius=8,
        )
        self._entry.insert(0, self._current)
        self._entry.select_range(0, "end")
        self._entry.pack(fill="x", padx=20)
        self._entry.bind("<Return>", lambda _: self._confirm())
        self._entry.focus()

        self._err = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color="#f38ba8",
        )
        self._err.pack(pady=(5, 0))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(8, 20))

        ctk.CTkButton(
            btn_row, text="Annuler",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color="#313244", hover_color="#45475a",
            text_color="#cdd6f4", corner_radius=8,
            command=self.destroy,
        ).pack(side="left")

        ctk.CTkButton(
            btn_row, text="Renommer",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color="#89b4fa", hover_color="#74c7ec",
            text_color="#11111b", corner_radius=8,
            command=self._confirm,
        ).pack(side="right")

    def _confirm(self):
        new_name = self._entry.get().strip()
        if not new_name:
            return
        if new_name == self._current:
            self.destroy()
            return
        if not self._dm.rename_game(self._current, new_name):
            self._err.configure(text=f'"{new_name}" existe déjà.')
            return
        self.destroy()


class ConfirmDeleteDialog(ctk.CTkToplevel):
    def __init__(self, parent, name: str):
        super().__init__(parent)
        self.confirmed = False

        self.title("Supprimer")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color="#11111b")
        self._center(380, 165)
        self._build(name)

    def _center(self, w: int, h: int):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self, name: str):
        ctk.CTkLabel(
            self,
            text=f'Supprimer "{name}" ?',
            font=ctk.CTkFont("Segoe UI", 15, "bold"),
            text_color="#cdd6f4",
        ).pack(pady=(22, 6), padx=20)

        ctk.CTkLabel(
            self,
            text="Toutes les sessions enregistrées seront perdues.",
            font=ctk.CTkFont("Segoe UI", 13),
            text_color="#a6adc8",
        ).pack(padx=20)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(16, 20))

        ctk.CTkButton(
            btn_row, text="Annuler",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color="#313244", hover_color="#45475a",
            text_color="#cdd6f4", corner_radius=8,
            command=self.destroy,
        ).pack(side="left")

        ctk.CTkButton(
            btn_row, text="Supprimer",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color="#f38ba8", hover_color="#eba0ac",
            text_color="#11111b", corner_radius=8,
            command=self._confirm,
        ).pack(side="right")

    def _confirm(self):
        self.confirmed = True
        self.destroy()
