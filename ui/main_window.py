import tkinter as tk

import customtkinter as ctk

from data_manager import DataManager
from notifier import NotificationManager
from tracker import ProcessTracker
from utils import format_duration
from ui.games_tab import GamesTab
from ui.history_tab import HistoryTab
from ui.stats_tab import StatsTab

_BG      = "#181825"
_BG_ROOT = "#11111b"

_TABS = [
    ("Jeux",         "🎮"),
    ("Historique",   "📅"),
    ("Statistiques", "📊"),
]


class MainWindow:
    def __init__(self, root: ctk.CTk):
        self._root = root
        self._root.title("Time Tracker")
        self._root.geometry("960x640")
        self._root.minsize(700, 520)
        self._root.configure(fg_color=_BG_ROOT)

        self._dm = DataManager()
        self._notifier = NotificationManager(root)
        self._tracker = ProcessTracker(
            self._dm,
            on_game_start=self._on_game_start,
            on_game_stop=self._on_game_stop,
        )

        self._current_tab = "Jeux"
        self._tab_btns: dict = {}
        self._tab_indicators: dict = {}
        self._tab_frames: dict = {}

        self._build_ui()
        self._tracker.start()
        self._refresh_loop()
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # ── Header — tk.Frame avoids per-pixel Canvas redraw ──────────────────
        header = tk.Frame(self._root, height=54, bg=_BG)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="⏱  Time Tracker",
            font=ctk.CTkFont("Segoe UI", 18, "bold"),
            text_color="#cdd6f4",
            fg_color=_BG,          # explicit so CTkLabel doesn't guess parent bg
        ).pack(side="left", padx=20)

        self._status_label = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont("Segoe UI", 13),
            text_color="#a6e3a1",
            fg_color=_BG,
        )
        self._status_label.pack(side="right", padx=20)

        # ── Tab bar ───────────────────────────────────────────────────────────
        tab_bar = tk.Frame(self._root, bg=_BG)
        tab_bar.pack(fill="x")

        btn_row = tk.Frame(tab_bar, bg=_BG)
        btn_row.pack(side="left", padx=14, pady=(10, 0))

        for name, icon in _TABS:
            col = tk.Frame(btn_row, bg=_BG)
            col.pack(side="left", padx=3)

            btn = ctk.CTkButton(
                col,
                text=f"{icon}  {name}",
                font=ctk.CTkFont("Segoe UI", 15, "bold"),
                fg_color="transparent",
                hover_color="#313244",
                text_color="#6c7086",
                corner_radius=8,
                height=46,
                width=155,
                command=lambda n=name: self._switch_tab(n),
            )
            btn.pack()

            # CTkFrame kept here: it shows a colored indicator bar
            indicator = ctk.CTkFrame(
                col, height=3, fg_color="transparent", corner_radius=2
            )
            indicator.pack(fill="x", padx=10, pady=(3, 8))

            self._tab_btns[name] = btn
            self._tab_indicators[name] = indicator

        # ── Content area ——————————————————————————————————————————————————————
        content = tk.Frame(self._root, bg=_BG)
        content.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        for name, _ in _TABS:
            frame = tk.Frame(content, bg=_BG)
            self._tab_frames[name] = frame

        # Activate first tab
        self._tab_frames["Jeux"].pack(fill="both", expand=True)
        self._tab_btns["Jeux"].configure(fg_color="#1e1e2e", text_color="#cdd6f4")
        self._tab_indicators["Jeux"].configure(fg_color="#89b4fa")

        # Build tab content
        self._games_tab   = GamesTab(self._tab_frames["Jeux"], self._dm, self._tracker)
        self._history_tab = HistoryTab(self._tab_frames["Historique"], self._dm)
        self._stats_tab   = StatsTab(self._tab_frames["Statistiques"], self._dm)

    # ── Tab switching ──────────────────────────────────────────────────────────

    def _switch_tab(self, name: str):
        if name == self._current_tab:
            return
        self._tab_btns[self._current_tab].configure(
            fg_color="transparent", text_color="#6c7086"
        )
        self._tab_indicators[self._current_tab].configure(fg_color="transparent")
        self._tab_frames[self._current_tab].pack_forget()

        self._current_tab = name
        self._tab_btns[name].configure(fg_color="#1e1e2e", text_color="#cdd6f4")
        self._tab_indicators[name].configure(fg_color="#89b4fa")
        self._tab_frames[name].pack(fill="both", expand=True)

        if name == "Historique":
            self._history_tab.refresh()
        elif name == "Statistiques":
            self._stats_tab.refresh()

    # ── Tracker callbacks ──────────────────────────────────────────────────────

    def _on_game_start(self, name: str):
        self._notifier.show(name, "Suivi démarré")

    def _on_game_stop(self, name: str, start, end):
        duration = int((end - start).total_seconds())
        total = self._dm.get_games()[name]["total_seconds"]
        self._notifier.show(
            name,
            f"Session : {format_duration(duration)}  •  Total : {format_duration(total)}",
        )
        self._root.after(100, self._post_session_refresh)

    def _post_session_refresh(self):
        self._games_tab.refresh()
        if self._current_tab == "Historique":
            self._history_tab.refresh()
        elif self._current_tab == "Statistiques":
            self._stats_tab.refresh()

    # ── Refresh loop ───────────────────────────────────────────────────────────

    def _refresh_loop(self):
        self._games_tab.refresh()
        self._update_status()
        self._root.after(1000, self._refresh_loop)

    def _update_status(self):
        active = self._tracker.get_active()
        if active:
            names = ", ".join(active.keys())
            self._status_label.configure(text=f"En jeu : {names}")
        else:
            self._status_label.configure(text="")

    def _on_close(self):
        self._tracker.stop()
        self._root.destroy()
