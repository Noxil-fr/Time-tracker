from datetime import datetime

import customtkinter as ctk

from data_manager import DataManager
from utils import format_duration, format_date_fr


class HistoryTab:
    def __init__(self, parent, dm: DataManager):
        self._dm = dm
        self._current_game: str | None = None

        # Barre du haut
        topbar = ctk.CTkFrame(parent, fg_color="transparent")
        topbar.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            topbar, text="Historique",
            font=ctk.CTkFont("Segoe UI", 16, "bold"),
            text_color="#cdd6f4",
        ).pack(side="left")

        self._selector = ctk.CTkOptionMenu(
            topbar,
            values=["Sélectionner un jeu"],
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#313244", button_color="#45475a",
            dropdown_fg_color="#1e1e2e", text_color="#cdd6f4",
            corner_radius=8,
            command=self._on_select,
        )
        self._selector.pack(side="right")

        self._scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self._placeholder = ctk.CTkLabel(
            self._scroll,
            text="Sélectionnez un jeu pour voir son historique.",
            font=ctk.CTkFont("Segoe UI", 13),
            text_color="#585b70",
        )
        self._placeholder.pack(pady=50)

        self.refresh()

    def refresh(self):
        games = self._dm.get_games()
        names = list(games.keys())

        if names:
            self._selector.configure(values=names)
            if self._current_game and self._current_game in names:
                self._show_history(self._current_game)
        else:
            self._selector.configure(values=["Aucun jeu"])

    def _on_select(self, value: str):
        self._current_game = value
        self._show_history(value)

    def _show_history(self, game_name: str):
        for w in self._scroll.winfo_children():
            w.destroy()

        games = self._dm.get_games()
        if game_name not in games:
            return

        sessions = games[game_name]["sessions"]
        if not sessions:
            ctk.CTkLabel(
                self._scroll,
                text="Aucune session enregistrée.",
                font=ctk.CTkFont("Segoe UI", 13),
                text_color="#585b70",
            ).pack(pady=50)
            return

        # Regrouper par jour
        days: dict[str, list] = {}
        for s in sessions:
            day = s["start"][:10]
            days.setdefault(day, []).append(s)

        for day_key in sorted(days, reverse=True):
            day_sessions = days[day_key]
            day_total = sum(s["duration"] for s in day_sessions)
            dt = datetime.fromisoformat(day_key)

            # Bloc du jour
            day_frame = ctk.CTkFrame(self._scroll, fg_color="#1e1e2e", corner_radius=8)
            day_frame.pack(fill="x", pady=(5, 2))

            header = ctk.CTkFrame(day_frame, fg_color="#313244", corner_radius=8)
            header.pack(fill="x", padx=1, pady=1)

            ctk.CTkLabel(
                header, text=format_date_fr(dt),
                font=ctk.CTkFont("Segoe UI", 12, "bold"),
                text_color="#cdd6f4",
            ).pack(side="left", padx=15, pady=8)

            ctk.CTkLabel(
                header, text=format_duration(day_total),
                font=ctk.CTkFont("Segoe UI", 12),
                text_color="#89b4fa",
            ).pack(side="right", padx=15, pady=8)

            # Sessions du jour
            for s in sorted(day_sessions, key=lambda x: x["start"]):
                start_dt = datetime.fromisoformat(s["start"])
                end_dt = datetime.fromisoformat(s["end"])

                row = ctk.CTkFrame(day_frame, fg_color="transparent")
                row.pack(fill="x", padx=10, pady=2)

                ctk.CTkLabel(
                    row,
                    text=f"{start_dt.strftime('%H:%M')} → {end_dt.strftime('%H:%M')}",
                    font=ctk.CTkFont("Segoe UI", 11),
                    text_color="#a6adc8",
                ).pack(side="left", padx=5)

                ctk.CTkLabel(
                    row,
                    text=format_duration(s["duration"]),
                    font=ctk.CTkFont("Segoe UI", 11),
                    text_color="#585b70",
                ).pack(side="right", padx=5, pady=4)
