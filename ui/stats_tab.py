from datetime import datetime, timedelta

import customtkinter as ctk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from data_manager import DataManager
from utils import format_duration

COLORS = [
    "#89b4fa", "#a6e3a1", "#fab387", "#f38ba8",
    "#cba6f7", "#94e2d5", "#f9e2af", "#74c7ec",
]

PERIODS = ["7 jours", "30 jours", "3 mois", "Personnalisé"]
PERIOD_DAYS = {"7 jours": 7, "30 jours": 30, "3 mois": 90}


class StatsTab:
    def __init__(self, parent, dm: DataManager):
        self._dm = dm
        self._period = "7 jours"
        self._canvas = None
        self._fig = None

        # Contrôles
        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            controls, text="Statistiques",
            font=ctk.CTkFont("Segoe UI", 16, "bold"),
            text_color="#cdd6f4",
        ).pack(side="left")

        self._seg = ctk.CTkSegmentedButton(
            controls,
            values=PERIODS,
            command=self._on_period,
            font=ctk.CTkFont("Segoe UI", 12),
            selected_color="#89b4fa",
            selected_hover_color="#74c7ec",
            unselected_color="#313244",
            unselected_hover_color="#45475a",
            text_color="#cdd6f4",
        )
        self._seg.set("7 jours")
        self._seg.pack(side="right")

        # Champs date personnalisée (cachés par défaut)
        self._custom_frame = ctk.CTkFrame(parent, fg_color="transparent")

        ctk.CTkLabel(
            self._custom_frame, text="Du :",
            font=ctk.CTkFont("Segoe UI", 12), text_color="#a6adc8",
        ).pack(side="left", padx=(10, 4))

        self._start_entry = ctk.CTkEntry(
            self._custom_frame, placeholder_text="JJ/MM/AAAA",
            width=110, font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#313244", border_color="#45475a", text_color="#cdd6f4",
        )
        self._start_entry.pack(side="left")

        ctk.CTkLabel(
            self._custom_frame, text="  Au :",
            font=ctk.CTkFont("Segoe UI", 12), text_color="#a6adc8",
        ).pack(side="left", padx=(10, 4))

        self._end_entry = ctk.CTkEntry(
            self._custom_frame, placeholder_text="JJ/MM/AAAA",
            width=110, font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#313244", border_color="#45475a", text_color="#cdd6f4",
        )
        self._end_entry.pack(side="left")

        ctk.CTkButton(
            self._custom_frame, text="Appliquer",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#89b4fa", hover_color="#74c7ec",
            text_color="#11111b", corner_radius=8, width=90,
            command=self._apply_custom,
        ).pack(side="left", padx=10)

        self._custom_error = ctk.CTkLabel(
            self._custom_frame, text="",
            font=ctk.CTkFont("Segoe UI", 11), text_color="#f38ba8",
        )
        self._custom_error.pack(side="left")

        # Zone graphique
        self._chart_frame = ctk.CTkFrame(parent, fg_color="#1e1e2e", corner_radius=10)
        self._chart_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self._empty_label = ctk.CTkLabel(
            self._chart_frame,
            text="Aucune donnée pour cette période.",
            font=ctk.CTkFont("Segoe UI", 13),
            text_color="#585b70",
        )

        self._draw_chart()

    def _on_period(self, value: str):
        self._period = value
        if value == "Personnalisé":
            self._custom_frame.pack(fill="x", padx=10, pady=(0, 5))
        else:
            self._custom_frame.pack_forget()
            self._draw_chart()

    def _apply_custom(self):
        self._custom_error.configure(text="")
        try:
            start = datetime.strptime(self._start_entry.get().strip(), "%d/%m/%Y")
            end = datetime.strptime(self._end_entry.get().strip(), "%d/%m/%Y")
            end = end.replace(hour=23, minute=59, second=59)
        except ValueError:
            self._custom_error.configure(text="Format invalide (JJ/MM/AAAA)")
            return
        if start > end:
            self._custom_error.configure(text="La date de début doit être avant la fin.")
            return
        self._draw_chart(start, end)

    def refresh(self):
        if self._period != "Personnalisé":
            self._draw_chart()

    def _draw_chart(self, start: datetime | None = None, end: datetime | None = None):
        if self._canvas:
            self._canvas.get_tk_widget().destroy()
            plt.close(self._fig)
            self._canvas = None
            self._fig = None
        self._empty_label.pack_forget()

        if start is None:
            end = datetime.now()
            start = end - timedelta(days=PERIOD_DAYS.get(self._period, 7))

        data = self._dm.get_all_sessions_in_range(start, end)

        if not data:
            self._empty_label.pack(pady=80)
            return

        plt.style.use("dark_background")
        self._fig, axes = plt.subplots(1, 2, figsize=(9, 4.2))
        self._fig.patch.set_facecolor("#1e1e2e")

        names = list(data.keys())
        values = list(data.values())
        colors = (COLORS * ((len(names) // len(COLORS)) + 1))[: len(names)]

        # Camembert
        ax_pie = axes[0]
        ax_pie.set_facecolor("#1e1e2e")
        wedges, _, autotexts = ax_pie.pie(
            values,
            colors=colors,
            autopct="%1.1f%%",
            startangle=90,
            pctdistance=0.75,
            wedgeprops=dict(linewidth=2, edgecolor="#1e1e2e"),
        )
        for at in autotexts:
            at.set_color("#cdd6f4")
            at.set_fontsize(10)
        ax_pie.set_title(
            f"Répartition — {self._period}",
            color="#cdd6f4", fontsize=13, pad=15,
        )
        ax_pie.legend(
            wedges,
            [f"{n}  ({format_duration(v)})" for n, v in zip(names, values)],
            loc="lower center",
            bbox_to_anchor=(0.5, -0.18),
            ncol=2,
            frameon=False,
            labelcolor="#a6adc8",
            fontsize=9,
        )

        # Barres horizontales
        ax_bar = axes[1]
        ax_bar.set_facecolor("#1e1e2e")
        hours = [v / 3600 for v in values]
        bars = ax_bar.barh(names, hours, color=colors, height=0.55)
        ax_bar.set_xlabel("Heures", color="#a6adc8", fontsize=10)
        ax_bar.set_title("Temps de jeu", color="#cdd6f4", fontsize=13, pad=15)
        ax_bar.tick_params(colors="#a6adc8", labelsize=10)
        for spine in ("top", "right"):
            ax_bar.spines[spine].set_visible(False)
        for spine in ("bottom", "left"):
            ax_bar.spines[spine].set_color("#45475a")
        for bar, h in zip(bars, hours):
            ax_bar.text(
                bar.get_width() + 0.05,
                bar.get_y() + bar.get_height() / 2,
                f"{h:.1f}h",
                va="center", ha="left",
                color="#a6adc8", fontsize=9,
            )

        plt.tight_layout(pad=2.0)

        self._canvas = FigureCanvasTkAgg(self._fig, master=self._chart_frame)
        self._canvas.draw()
        self._canvas.get_tk_widget().configure(bg="#1e1e2e")
        self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
