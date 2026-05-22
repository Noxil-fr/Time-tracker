import tkinter as tk
from datetime import datetime, timedelta

import customtkinter as ctk

from data_manager import DataManager
from utils import format_duration

_BG = "#181825"

_MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin",
              "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
_DAYS_FR   = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _fmt_day(dt: datetime) -> str:
    return f"{_DAYS_FR[dt.weekday()]} {dt.day} {_MONTHS_FR[dt.month - 1]} {dt.year}"


def _fmt_week(start: datetime, end: datetime) -> str:
    if start.month == end.month:
        return f"{start.day} – {end.day} {_MONTHS_FR[end.month - 1]} {end.year}"
    return (f"{start.day} {_MONTHS_FR[start.month - 1]}"
            f" – {end.day} {_MONTHS_FR[end.month - 1]} {end.year}")


class HistoryTab:
    def __init__(self, parent, dm: DataManager):
        self._dm = dm
        self._mode = "day"
        self._ref  = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self._custom_start: datetime | None = None
        self._custom_end:   datetime | None = None
        self._game_filter:  str | None = None
        self._last_hash: int | None = None

        self._build(parent)
        self.refresh()

    # ── Construction ───────────────────────────────────────────────────────────

    def _build(self, parent):
        # Titre + filtre jeu
        topbar = tk.Frame(parent, bg=_BG)
        topbar.pack(fill="x", padx=14, pady=(14, 8))

        ctk.CTkLabel(
            topbar, text="Historique",
            font=ctk.CTkFont("Segoe UI", 22, "bold"),
            text_color="#cdd6f4", fg_color=_BG,
        ).pack(side="left")

        self._game_sel = ctk.CTkOptionMenu(
            topbar,
            values=["Tous les jeux"],
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#313244", button_color="#45475a",
            dropdown_fg_color="#1e1e2e", text_color="#cdd6f4",
            width=200, corner_radius=8,
            command=self._on_game_filter,
        )
        self._game_sel.pack(side="right")

        # Boutons de mode
        mode_bar = tk.Frame(parent, bg=_BG)
        mode_bar.pack(fill="x", padx=14, pady=(0, 6))

        self._mode_btns: dict[str, ctk.CTkButton] = {}
        for key, label in [("day", "Jour"), ("week", "Semaine"), ("custom", "Personnalisé")]:
            btn = ctk.CTkButton(
                mode_bar, text=label,
                font=ctk.CTkFont("Segoe UI", 13),
                fg_color="#89b4fa" if key == "day" else "#313244",
                hover_color="#74c7ec" if key == "day" else "#45475a",
                text_color="#11111b" if key == "day" else "#cdd6f4",
                corner_radius=8, height=34, width=120,
                command=lambda k=key: self._set_mode(k),
            )
            btn.pack(side="left", padx=(0, 6))
            self._mode_btns[key] = btn

        # Barre de navigation (contenu reconstruit selon le mode)
        self._nav_frame = tk.Frame(parent, bg=_BG)
        self._nav_frame.pack(fill="x", padx=14, pady=(0, 8))
        self._build_nav()

        # Contenu scrollable
        self._scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _build_nav(self):
        for w in self._nav_frame.winfo_children():
            w.destroy()

        if self._mode in ("day", "week"):
            ctk.CTkButton(
                self._nav_frame, text="<",
                font=ctk.CTkFont("Segoe UI", 14, "bold"),
                fg_color="#313244", hover_color="#45475a",
                text_color="#cdd6f4", corner_radius=8,
                height=32, width=36,
                command=self._nav_prev,
            ).pack(side="left")

            self._nav_lbl = ctk.CTkLabel(
                self._nav_frame, text="",
                font=ctk.CTkFont("Segoe UI", 13),
                text_color="#cdd6f4", fg_color="transparent",
                width=260, anchor="center",
            )
            self._nav_lbl.pack(side="left", padx=6)
            self._refresh_nav_label()

            ctk.CTkButton(
                self._nav_frame, text=">",
                font=ctk.CTkFont("Segoe UI", 14, "bold"),
                fg_color="#313244", hover_color="#45475a",
                text_color="#cdd6f4", corner_radius=8,
                height=32, width=36,
                command=self._nav_next,
            ).pack(side="left")

            today_lbl = "Aujourd'hui" if self._mode == "day" else "Cette semaine"
            ctk.CTkButton(
                self._nav_frame, text=today_lbl,
                font=ctk.CTkFont("Segoe UI", 12),
                fg_color="transparent", hover_color="#313244",
                text_color="#585b70", corner_radius=8, height=32,
                command=self._nav_today,
            ).pack(side="left", padx=(8, 0))

        else:  # custom
            ctk.CTkLabel(
                self._nav_frame, text="Du",
                font=ctk.CTkFont("Segoe UI", 12),
                text_color="#a6adc8", fg_color="transparent",
            ).pack(side="left", padx=(0, 6))

            self._start_var = tk.StringVar(value=self._ref.strftime("%d/%m/%Y"))
            ctk.CTkEntry(
                self._nav_frame, textvariable=self._start_var,
                font=ctk.CTkFont("Segoe UI", 12),
                fg_color="#313244", border_color="#45475a",
                text_color="#cdd6f4", height=32, width=105, corner_radius=8,
            ).pack(side="left")

            ctk.CTkLabel(
                self._nav_frame, text="au",
                font=ctk.CTkFont("Segoe UI", 12),
                text_color="#a6adc8", fg_color="transparent",
            ).pack(side="left", padx=6)

            self._end_var = tk.StringVar(value=self._ref.strftime("%d/%m/%Y"))
            ctk.CTkEntry(
                self._nav_frame, textvariable=self._end_var,
                font=ctk.CTkFont("Segoe UI", 12),
                fg_color="#313244", border_color="#45475a",
                text_color="#cdd6f4", height=32, width=105, corner_radius=8,
            ).pack(side="left")

            ctk.CTkButton(
                self._nav_frame, text="Appliquer",
                font=ctk.CTkFont("Segoe UI", 12),
                fg_color="#89b4fa", hover_color="#74c7ec",
                text_color="#11111b", corner_radius=8, height=32,
                command=self._apply_custom,
            ).pack(side="left", padx=(10, 0))

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _refresh_nav_label(self):
        if not hasattr(self, "_nav_lbl"):
            return
        if self._mode == "day":
            self._nav_lbl.configure(text=_fmt_day(self._ref))
        else:
            s, e = self._week_range()
            self._nav_lbl.configure(text=_fmt_week(s, e))

    def _week_range(self) -> tuple[datetime, datetime]:
        monday = self._ref - timedelta(days=self._ref.weekday())
        return monday, monday + timedelta(days=6)

    def _nav_prev(self):
        self._ref -= timedelta(days=1) if self._mode == "day" else timedelta(weeks=1)
        self._refresh_nav_label()
        self._render()

    def _nav_next(self):
        self._ref += timedelta(days=1) if self._mode == "day" else timedelta(weeks=1)
        self._refresh_nav_label()
        self._render()

    def _nav_today(self):
        self._ref = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self._refresh_nav_label()
        self._render()

    def _set_mode(self, mode: str):
        if self._mode == mode:
            return
        self._mode = mode
        for k, btn in self._mode_btns.items():
            active = k == mode
            btn.configure(
                fg_color="#89b4fa"  if active else "#313244",
                hover_color="#74c7ec" if active else "#45475a",
                text_color="#11111b" if active else "#cdd6f4",
            )
        self._build_nav()
        self._render()

    def _on_game_filter(self, value: str):
        self._game_filter = None if value == "Tous les jeux" else value
        self._render()

    def _apply_custom(self):
        try:
            start = datetime.strptime(self._start_var.get().strip(), "%d/%m/%Y")
            end   = datetime.strptime(self._end_var.get().strip(), "%d/%m/%Y")
            end   = end.replace(hour=23, minute=59, second=59)
            if start <= end:
                self._custom_start = start
                self._custom_end   = end
                self._render()
        except ValueError:
            pass

    # ── Plage de dates active ──────────────────────────────────────────────────

    def _get_range(self) -> tuple[datetime, datetime]:
        if self._mode == "day":
            return (self._ref.replace(hour=0, minute=0, second=0),
                    self._ref.replace(hour=23, minute=59, second=59))
        if self._mode == "week":
            s, e = self._week_range()
            return (s.replace(hour=0, minute=0, second=0),
                    e.replace(hour=23, minute=59, second=59))
        # custom
        if self._custom_start and self._custom_end:
            return self._custom_start, self._custom_end
        return (self._ref.replace(hour=0, minute=0, second=0),
                self._ref.replace(hour=23, minute=59, second=59))

    # ── Données ────────────────────────────────────────────────────────────────

    def _get_sessions(self, start: datetime, end: datetime) -> list[dict]:
        result = []
        for name, data in self._dm.get_games().items():
            if self._game_filter and name != self._game_filter:
                continue
            for s in data["sessions"]:
                s_start = datetime.fromisoformat(s["start"])
                if start <= s_start <= end:
                    result.append({
                        "game":     name,
                        "start":    s_start,
                        "end":      datetime.fromisoformat(s["end"]),
                        "duration": s["duration"],
                    })
        return sorted(result, key=lambda x: x["start"])

    # ── Rendu ──────────────────────────────────────────────────────────────────

    def refresh(self):
        games = self._dm.get_games()
        names = sorted(games.keys())
        self._game_sel.configure(values=["Tous les jeux"] + names)
        if self._game_filter and self._game_filter not in games:
            self._game_filter = None
            self._game_sel.set("Tous les jeux")
        # Ne reconstruit que si les données ont changé
        h = sum(len(d.get("sessions", [])) for d in games.values())
        if h == self._last_hash:
            return
        self._last_hash = h
        self._render()

    def _render(self):
        for w in self._scroll.winfo_children():
            w.destroy()

        start, end = self._get_range()
        sessions = self._get_sessions(start, end)

        if not sessions:
            ctk.CTkLabel(
                self._scroll,
                text="Aucune session sur cette période.",
                font=ctk.CTkFont("Segoe UI", 13),
                text_color="#585b70",
            ).pack(pady=50)
            return

        # Regrouper par jour (clé YYYY-MM-DD)
        days: dict[str, list] = {}
        for s in sessions:
            days.setdefault(s["start"].strftime("%Y-%m-%d"), []).append(s)

        for day_key in sorted(days, reverse=True):
            day_sessions = days[day_key]
            day_total    = sum(s["duration"] for s in day_sessions)
            dt           = datetime.fromisoformat(day_key)

            block = ctk.CTkFrame(self._scroll, fg_color="#1e1e2e", corner_radius=8)
            block.pack(fill="x", pady=(5, 2))

            hdr = ctk.CTkFrame(block, fg_color="#313244", corner_radius=8)
            hdr.pack(fill="x", padx=1, pady=1)

            ctk.CTkLabel(
                hdr, text=_fmt_day(dt),
                font=ctk.CTkFont("Segoe UI", 12, "bold"),
                text_color="#cdd6f4",
            ).pack(side="left", padx=15, pady=8)

            ctk.CTkLabel(
                hdr, text=format_duration(day_total),
                font=ctk.CTkFont("Segoe UI", 12),
                text_color="#89b4fa",
            ).pack(side="right", padx=15, pady=8)

            for s in sorted(day_sessions, key=lambda x: x["start"]):
                row = ctk.CTkFrame(block, fg_color="transparent")
                row.pack(fill="x", padx=10, pady=2)

                ctk.CTkLabel(
                    row,
                    text=f"{s['start'].strftime('%H:%M')} → {s['end'].strftime('%H:%M')}",
                    font=ctk.CTkFont("Segoe UI", 11),
                    text_color="#a6adc8",
                ).pack(side="left", padx=5)

                if self._game_filter is None:
                    ctk.CTkLabel(
                        row, text=s["game"],
                        font=ctk.CTkFont("Segoe UI", 11, "bold"),
                        text_color="#cdd6f4",
                    ).pack(side="left", padx=(10, 0))

                ctk.CTkLabel(
                    row, text=format_duration(s["duration"]),
                    font=ctk.CTkFont("Segoe UI", 11),
                    text_color="#585b70",
                ).pack(side="right", padx=15, pady=4)
