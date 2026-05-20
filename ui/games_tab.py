import tkinter as tk
from datetime import datetime, timedelta

import customtkinter as ctk
from PIL import ImageTk

from data_manager import DataManager
from icon_cache import get_game_icon
from tracker import ProcessTracker
from utils import format_duration

_CARD_W = 162
_CARD_H = 224

_CARD_COLORS = [
    "#3b2f6e", "#1b4878", "#1a5c3a",
    "#6b3a1a", "#5c1a3a", "#1a3a5c",
    "#4a2a1a", "#2a4a1a", "#4a3a1a",
]

# Fixed column widths keep headers and rows aligned
_COL_TIME_W   = 130
_COL_STATUS_W = 108
_COL_MENU_W   = 28   # largeur du bouton ⋮
_COL_LAST_W   = 120  # largeur colonne "Dernier lancement"

_LIST_ICON = 28   # icon size in list rows
_CARD_ICON = 28   # icon size in card info panel

_ARCHIVE_DAYS = 30   # jours sans session → section Archivés

_SKIP_DIRS = (
    "\\windows\\system32\\",
    "\\windows\\syswow64\\",
    "\\windows\\winsxs\\",
)

_BG = "#181825"   # tab content background (matches main_window content frame)

# Tracks which _ScrollFrame currently owns the global mousewheel binding
_active_scroll: list = [None]



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


def _game_color(name: str) -> str:
    return _CARD_COLORS[abs(hash(name)) % len(_CARD_COLORS)]


class _ScrollFrame:
    """Lightweight scrollable frame using only native tk widgets.
    Replacing CTkScrollableFrame eliminates two CTk Canvases (CTkFrame wrapper +
    CTkScrollbar) that each fire _draw() on every resize event."""

    def __init__(self, parent, bg: str = _BG):
        self._bg = bg
        self._outer = tk.Frame(parent, bg=bg)
        self._canvas = tk.Canvas(self._outer, bg=bg, highlightthickness=0, bd=0)
        self._vsb = tk.Scrollbar(
            self._outer, orient="vertical", command=self._canvas.yview
        )
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
        self._view = "list"
        self._sort_key = "name"
        self._sort_asc = True
        self._rows: dict = {}
        self._rows_all: dict = {}
        self._cards: dict = {}
        self._cards_all: dict = {}
        self._last_names: set = set()
        self._last_archived: frozenset = frozenset()
        self._last_cols = -1
        self._icon_gen = 0

        self._build(parent)
        self.refresh()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self, parent):
        # Toolbar — tk.Frame: no Canvas, no _draw() on resize
        tb = tk.Frame(parent, bg=_BG)
        tb.pack(fill="x", padx=14, pady=(14, 8))

        ctk.CTkLabel(
            tb, text="Mes jeux récents",
            font=ctk.CTkFont("Segoe UI", 22, "bold"),
            text_color="#cdd6f4",
            fg_color=_BG,
        ).pack(side="left")

        right = tk.Frame(tb, bg=_BG)
        right.pack(side="right")

        # Sort controls (grid view only)
        self._sort_frame = tk.Frame(right, bg=_BG)
        self._sort_frame.pack(side="left", padx=(0, 8))

        self._sort_opt = ctk.CTkOptionMenu(
            self._sort_frame,
            values=["Nom", "Temps total", "Récemment joué"],
            font=ctk.CTkFont("Segoe UI", 14),
            fg_color="#313244", button_color="#45475a",
            dropdown_fg_color="#1e1e2e", text_color="#cdd6f4",
            width=165, height=40,
            command=self._on_sort_change,
        )
        self._sort_opt.set("Nom")
        self._sort_opt.pack(side="left", padx=(0, 5))

        self._dir_btn = ctk.CTkButton(
            self._sort_frame, text="↑",
            font=ctk.CTkFont("Segoe UI", 16),
            width=40, height=40,
            fg_color="#313244", hover_color="#45475a",
            text_color="#a6adc8",
            command=self._toggle_dir,
        )
        self._dir_btn.pack(side="left")

        # View toggle
        self._list_btn = ctk.CTkButton(
            right, text="☰",
            font=ctk.CTkFont("Segoe UI", 18),
            width=42, height=40,
            fg_color="#89b4fa", text_color="#11111b",
            hover_color="#74c7ec",
            command=self._set_list_view,
        )
        self._list_btn.pack(side="left", padx=(0, 4))

        self._grid_btn = ctk.CTkButton(
            right, text="⊞",
            font=ctk.CTkFont("Segoe UI", 18),
            width=42, height=40,
            fg_color="#313244", text_color="#cdd6f4",
            hover_color="#45475a",
            command=self._set_grid_view,
        )
        self._grid_btn.pack(side="left", padx=(0, 14))

        ctk.CTkButton(
            right, text="+ Ajouter",
            font=ctk.CTkFont("Segoe UI", 14),
            fg_color="#a6e3a1", hover_color="#94e2d5",
            text_color="#11111b", corner_radius=8,
            height=40, width=120,
            command=self._open_add,
        ).pack(side="left")

        self._hdr_name = None
        self._hdr_time = None
        self._hdr_last = None

        # Content area — tk.Frame: no Canvas overhead
        self._content = tk.Frame(parent, bg=_BG)
        self._content.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        # _ScrollFrame replaces CTkScrollableFrame — zero CTk canvas redraws on resize
        self._list_scroll = _ScrollFrame(self._content, bg=_BG)
        self._grid_scroll = _ScrollFrame(self._content, bg=_BG)

        self._empty_lbl = ctk.CTkLabel(
            self._content,
            text='Aucun jeu ajouté.\nCliquez sur "+ Ajouter" pour commencer.',
            font=ctk.CTkFont("Segoe UI", 16),
            text_color="#585b70", justify="center",
            fg_color=_BG,
        )

        # Default: list view
        self._sort_frame.pack_forget()
        self._list_scroll.pack(fill="both", expand=True)

    # ── View switching ─────────────────────────────────────────────────────────

    def _set_list_view(self):
        self._view = "list"
        self._list_btn.configure(fg_color="#89b4fa", text_color="#11111b")
        self._grid_btn.configure(fg_color="#313244", text_color="#cdd6f4")
        self._sort_frame.pack_forget()
        self._refresh_content()

    def _set_grid_view(self):
        self._view = "grid"
        self._grid_btn.configure(fg_color="#89b4fa", text_color="#11111b")
        self._list_btn.configure(fg_color="#313244", text_color="#cdd6f4")
        self._sort_frame.pack(side="left", padx=(0, 8))
        self._refresh_content()
        # Rebuild once layout has settled (winfo_width returns real value)
        self._parent.winfo_toplevel().after(60, self._check_grid_cols)

    def _check_grid_cols(self):
        if self._view != "grid":
            return
        if self._cols() != self._last_cols:
            games = self._dm.get_games()
            if games:
                self._rebuild_grid(games)
                self._update_grid(games, self._tracker.get_active())

    def _refresh_content(self):
        self._list_scroll.pack_forget()
        self._grid_scroll.pack_forget()
        self._empty_lbl.pack_forget()

        if not self._dm.get_games():
            self._empty_lbl.pack(expand=True)
            return

        if self._view == "list":
            self._list_scroll.pack(fill="both", expand=True)
        else:
            self._grid_scroll.pack(fill="both", expand=True)

    # ── Sorting ────────────────────────────────────────────────────────────────

    def _on_sort_change(self, value: str):
        mapping = {"Nom": ("name", True), "Temps total": ("time", False), "Récemment joué": ("recent", False)}
        self._sort_key, self._sort_asc = mapping.get(value, ("name", True))
        self._dir_btn.configure(text="↑" if self._sort_asc else "↓")
        self._force_rebuild()

    def _toggle_dir(self):
        self._sort_asc = not self._sort_asc
        self._dir_btn.configure(text="↑" if self._sort_asc else "↓")
        self._update_header_labels()
        self._force_rebuild()

    def _sort_by(self, key: str):
        if self._sort_key == key:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_key = key
            self._sort_asc = key == "name"
            labels = {"name": "Nom", "time": "Temps total", "recent": "Récemment joué"}
            self._sort_opt.set(labels.get(key, "Nom"))
        self._dir_btn.configure(text="↑" if self._sort_asc else "↓")
        self._update_header_labels()
        self._force_rebuild()

    def _build_list_headers(self, parent: tk.Frame):
        """En-têtes de colonnes triables, positionnés juste avant les lignes 'Mes jeux'."""
        hdr = tk.Frame(parent, bg=_BG)
        hdr.pack(fill="x", pady=(4, 0))

        tk.Frame(hdr, width=_COL_MENU_W, bg=_BG).pack(side="right", padx=(0, 14))
        ctk.CTkLabel(
            hdr, text="Statut",
            font=ctk.CTkFont("Segoe UI", 13),
            text_color="#585b70", fg_color=_BG,
            width=_COL_STATUS_W, anchor="center",
        ).pack(side="right", padx=(0, 4), pady=7)

        self._hdr_time = ctk.CTkButton(
            hdr, text="Temps total",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color="transparent", hover_color="#313244",
            text_color="#585b70", width=_COL_TIME_W, anchor="center",
            command=lambda: self._sort_by("time"),
        )
        self._hdr_time.pack(side="right", padx=(0, 4), pady=5)

        self._hdr_last = ctk.CTkButton(
            hdr, text="Dernier lancement",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color="transparent", hover_color="#313244",
            text_color="#585b70", width=_COL_LAST_W, anchor="center",
            command=lambda: self._sort_by("recent"),
        )
        self._hdr_last.pack(side="right", padx=(0, 4), pady=5)

        tk.Frame(hdr, width=_LIST_ICON + 22, bg=_BG).pack(side="left")
        self._hdr_name = ctk.CTkButton(
            hdr, text="Jeu",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color="transparent", hover_color="#313244",
            text_color="#585b70", anchor="w",
            command=lambda: self._sort_by("name"),
        )
        self._hdr_name.pack(side="left", fill="x", expand=True, padx=(4, 0), pady=5)
        self._update_header_labels()

    def _update_header_labels(self):
        if self._hdr_name is None:
            return
        arrow = "↑" if self._sort_asc else "↓"
        self._hdr_name.configure(
            text=f"Jeu  {arrow}" if self._sort_key == "name" else "Jeu",
            text_color="#cdd6f4" if self._sort_key == "name" else "#585b70",
        )
        self._hdr_time.configure(
            text=f"Temps total  {arrow}" if self._sort_key == "time" else "Temps total",
            text_color="#cdd6f4" if self._sort_key == "time" else "#585b70",
        )
        self._hdr_last.configure(
            text=f"Dernier lancement  {arrow}" if self._sort_key == "recent" else "Dernier lancement",
            text_color="#cdd6f4" if self._sort_key == "recent" else "#585b70",
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
        """Jeux joués dans les 30 derniers jours, toujours triés par dernière session (plus récent en premier)."""
        threshold = datetime.now() - timedelta(days=_ARCHIVE_DAYS)
        def _last_ts(item):
            s = item[1].get("sessions", [])
            return datetime.fromisoformat(s[-1]["end"]) if s else datetime.min
        recent = [(n, d) for n, d in self._dm.get_games().items() if _last_ts((n, d)) > threshold]
        return sorted(recent, key=_last_ts, reverse=True)

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
        tk.Frame(parent, bg="#313244", height=1).pack(fill="x", pady=(16, 0))
        tk.Label(
            parent, text=f"  {text}",
            font=("Segoe UI", 11, "bold"),
            bg=_BG, fg="#6c7086", anchor="w",
        ).pack(fill="x", pady=(6, 4))

    # ── Refresh ────────────────────────────────────────────────────────────────

    def _force_rebuild(self):
        self._last_names = set()
        self._last_cols = -1
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
            self._last_cols = -1
            if self._view == "grid":
                self._rebuild_grid(games)
            self._refresh_content()
        elif self._view == "grid" and self._cols() != self._last_cols:
            self._rebuild_grid(games)

        self._update_list(games, active)
        if self._view == "grid":
            self._update_grid(games, active)

    # ── List view ──────────────────────────────────────────────────────────────

    def _rebuild_list(self, games: dict):
        for w in self._list_scroll.winfo_children():
            w.destroy()
        self._rows = {}
        self._rows_all = {}
        icon_queue: list = []

        # ── Mes jeux récents (live, toujours triés par date) ─────────────
        for name, data in self._recent_games():
            icon_lbl = self._add_list_row(name, data, static=False)
            exe = data.get("exe_path", "")
            if exe:
                icon_queue.append((exe, icon_lbl, name))

        # ── Mes jeux (tous les jeux, triés par préférence, temps statique)
        self._add_section_header(self._list_scroll.inner, "Mes jeux")
        self._build_list_headers(self._list_scroll.inner)
        for name, data in self._sorted_games():
            icon_lbl = self._add_list_row(name, data, static=True)
            exe = data.get("exe_path", "")
            if exe:
                icon_queue.append((exe, icon_lbl, name))

        if icon_queue:
            self._load_icons(icon_queue, _LIST_ICON)

    def _add_list_row(self, name: str, data: dict, static: bool = False) -> tk.Label:
        row_bg   = "#181825"  if static else "#1e1e2e"
        border   = "#252535"  if static else "#313244"
        col_name = "#6c7086"  if static else "#cdd6f4"
        col_time = "#45475a"  if static else "#a6adc8"
        col_st   = "#45475a"  if static else "#585b70"

        row = tk.Frame(
            self._list_scroll.inner,
            bg=row_bg, highlightbackground=border, highlightthickness=1,
        )
        row.pack(fill="x", pady=2)

        # ── Droite (du plus à droite vers la gauche) ───────────────────────
        # Bouton ⋮ (rightmost)
        menu_wrap = tk.Frame(row, bg=row_bg, width=_COL_MENU_W)
        menu_wrap.pack(side="right", padx=(0, 14), fill="y")
        menu_wrap.pack_propagate(False)
        menu_btn = tk.Label(
            menu_wrap, text="⋮",
            font=("Segoe UI", 16), bg=row_bg, fg="#585b70", cursor="hand2",
        )
        menu_btn.pack(expand=True)
        menu_btn.bind("<Button-1>", lambda e, n=name: self._context_menu(e, n))

        # Statut
        status_wrap = tk.Frame(row, bg=row_bg, width=_COL_STATUS_W)
        status_wrap.pack(side="right", padx=(0, 4), fill="y")
        status_wrap.pack_propagate(False)
        status_lbl = tk.Label(
            status_wrap, text="—",
            font=("Segoe UI", 14, "bold"),
            bg=row_bg, fg=col_st, anchor="center",
        )
        status_lbl.pack(expand=True, fill="both")

        # Temps
        time_wrap = tk.Frame(row, bg=row_bg, width=_COL_TIME_W)
        time_wrap.pack(side="right", padx=(0, 4), fill="y")
        time_wrap.pack_propagate(False)
        time_lbl = tk.Label(
            time_wrap, text=format_duration(data["total_seconds"]),
            font=("Segoe UI", 15),
            bg=row_bg, fg=col_time, anchor="center",
        )
        time_lbl.pack(expand=True, fill="both")

        # Dernier lancement
        last_wrap = tk.Frame(row, bg=row_bg, width=_COL_LAST_W)
        last_wrap.pack(side="right", padx=(0, 4), fill="y")
        last_wrap.pack_propagate(False)
        last_lbl = tk.Label(
            last_wrap, text=_format_last_played(data.get("sessions", [])),
            font=("Segoe UI", 13),
            bg=row_bg, fg=col_time, anchor="center",
        )
        last_lbl.pack(expand=True, fill="both")

        # ── Gauche ────────────────────────────────────────────────────────
        icon_wrap = tk.Frame(row, bg=row_bg, width=_LIST_ICON + 4, height=_LIST_ICON)
        icon_wrap.pack(side="left", padx=(14, 4))
        icon_wrap.pack_propagate(False)
        icon_lbl = tk.Label(icon_wrap, bg=row_bg)
        icon_lbl.pack(expand=True, fill="both")

        name_lbl = tk.Label(
            row, text=name,
            font=("Segoe UI", 16, "bold"),
            bg=row_bg, fg=col_name, anchor="w",
        )
        name_lbl.pack(side="left", fill="x", expand=True, padx=(4, 8), pady=14)

        for w in (row, icon_wrap, icon_lbl, name_lbl,
                  last_wrap, last_lbl, time_wrap, time_lbl,
                  status_wrap, status_lbl, menu_wrap):
            w.bind("<Button-3>", lambda e, n=name: self._context_menu(e, n))

        row_dict = self._rows_all if static else self._rows
        row_dict[name] = {
            "row": row, "time": time_lbl, "status": status_lbl,
            "_active": None, "_time_str": "", "_border": border,
        }
        return icon_lbl

    def _update_list(self, games: dict, active: dict):
        for name, data in games.items():
            # Lignes live (Mes jeux récents) — temps + statut
            if name in self._rows:
                row = self._rows[name]
                total = data["total_seconds"]
                in_active = name in active
                if in_active:
                    elapsed = int((datetime.now() - active[name]).total_seconds())
                    total += elapsed

                time_str = format_duration(total)
                if time_str != row["_time_str"]:
                    row["time"].config(text=time_str)
                    row["_time_str"] = time_str

                if in_active != row["_active"]:
                    row["_active"] = in_active
                    if in_active:
                        row["status"].config(text="EN JEU", fg="#a6e3a1")
                        row["row"].config(highlightbackground="#a6e3a1")
                    else:
                        row["status"].config(text="—", fg="#585b70")
                        row["row"].config(highlightbackground=row["_border"])

            # Lignes statiques (Mes jeux) — statut uniquement
            if name in self._rows_all:
                row = self._rows_all[name]
                in_active = name in active
                if in_active != row["_active"]:
                    row["_active"] = in_active
                    if in_active:
                        row["status"].config(text="EN JEU", fg="#a6e3a1")
                        row["row"].config(highlightbackground="#a6e3a1")
                    else:
                        row["status"].config(text="—", fg="#45475a")
                        row["row"].config(highlightbackground=row["_border"])

    # ── Grid view ──────────────────────────────────────────────────────────────

    def _cols(self) -> int:
        w = self._grid_scroll.winfo_width()
        if w < 100:
            w = 900
        return max(2, (w - 20) // (_CARD_W + 16))

    def _rebuild_grid(self, games: dict):
        for w in self._grid_scroll.winfo_children():
            w.destroy()
        self._cards = {}
        self._cards_all = {}

        cols = self._cols()
        self._last_cols = cols
        icon_queue: list = []

        # ── Mes jeux récents (live, toujours triés par date) ─────────────
        row_frame = None
        for i, (name, data) in enumerate(self._recent_games()):
            if i % cols == 0:
                row_frame = tk.Frame(self._grid_scroll.inner, bg=_BG)
                row_frame.pack(anchor="w", pady=6, padx=4)
            icon_lbl = self._make_card(row_frame, name, data, static=False)
            exe = data.get("exe_path", "")
            if exe:
                icon_queue.append((exe, icon_lbl, name))

        # ── Mes jeux (tous, statique) ─────────────────────────────────────
        self._add_section_header(self._grid_scroll.inner, "Mes jeux")
        row_frame = None
        for i, (name, data) in enumerate(self._sorted_games()):
            if i % cols == 0:
                row_frame = tk.Frame(self._grid_scroll.inner, bg=_BG)
                row_frame.pack(anchor="w", pady=6, padx=4)
            icon_lbl = self._make_card(row_frame, name, data, static=True)
            exe = data.get("exe_path", "")
            if exe:
                icon_queue.append((exe, icon_lbl, name))

        if icon_queue:
            self._load_icons(icon_queue, _CARD_ICON)

    def _make_card(self, parent, name: str, data: dict, static: bool = False) -> ctk.CTkLabel:
        color = _game_color(name)
        border_color = "#252535" if static else "#45475a"
        name_color   = "#6c7086" if static else "#cdd6f4"

        card = ctk.CTkFrame(
            parent, width=_CARD_W, height=_CARD_H,
            fg_color=color, corner_radius=12,
            border_width=1, border_color=border_color,
        )
        card.pack(side="left", padx=6)
        card.pack_propagate(False)

        # Cover — letter initial
        cover = ctk.CTkFrame(card, fg_color=color, corner_radius=12)
        cover.place(x=0, y=0, relwidth=1, relheight=0.57)

        ctk.CTkLabel(
            cover,
            text=name[0].upper() if name else "?",
            font=ctk.CTkFont("Segoe UI", 58, "bold"),
            text_color="white", fg_color="transparent",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Info panel
        info = ctk.CTkFrame(
            card, fg_color="#1e1e2e", corner_radius=0,
            height=int(_CARD_H * 0.43),
        )
        info.place(x=0, rely=0.57, relwidth=1, relheight=0.43)
        info.pack_propagate(False)

        # Icon + name row
        name_row = ctk.CTkFrame(info, fg_color="transparent")
        name_row.pack(fill="x", padx=8, pady=(8, 2))

        icon_lbl = ctk.CTkLabel(
            name_row, text="", width=_CARD_ICON, height=_CARD_ICON,
        )
        icon_lbl.pack(side="left", padx=(0, 6))

        name_lbl = ctk.CTkLabel(
            name_row, text=name,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color=name_color, anchor="w",
            wraplength=_CARD_W - _CARD_ICON - 30,
        )
        name_lbl.pack(side="left", fill="x", expand=True)

        time_lbl = ctk.CTkLabel(
            info, text=format_duration(data["total_seconds"]),
            font=ctk.CTkFont("Segoe UI", 12),
            text_color="#a6adc8", anchor="w",
        )
        time_lbl.pack(anchor="w", padx=8)

        status_lbl = ctk.CTkLabel(
            info, text="",
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color="#a6e3a1", anchor="w",
        )
        status_lbl.pack(anchor="w", padx=8)

        for w in (card, cover, info, name_row, icon_lbl, name_lbl, time_lbl, status_lbl):
            w.bind("<Button-3>", lambda e, n=name: self._context_menu(e, n))

        card_dict = self._cards_all if static else self._cards
        card_dict[name] = {
            "frame": card, "time": time_lbl, "status": status_lbl,
            "_active": None, "_time_str": "",
        }
        return icon_lbl

    def _update_grid(self, games: dict, active: dict):
        for name, data in games.items():
            if name not in self._cards:
                continue
            c = self._cards[name]
            total = data["total_seconds"]
            in_active = name in active
            if in_active:
                elapsed = int((datetime.now() - active[name]).total_seconds())
                total += elapsed

            time_str = format_duration(total)
            if time_str != c["_time_str"]:
                c["time"].configure(text=time_str)
                c["_time_str"] = time_str

            if in_active != c["_active"]:
                c["_active"] = in_active
                if in_active:
                    c["status"].configure(text="● EN JEU")
                    c["frame"].configure(border_color="#a6e3a1", border_width=2)
                else:
                    c["status"].configure(text="")
                    c["frame"].configure(border_color="#45475a", border_width=1)

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
        root = self._parent.winfo_toplevel()
        dialog = AddGameDialog(root, self._dm, self._tracker)
        root.wait_window(dialog)
        self._force_rebuild()


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
