from typing import Callable

import customtkinter as ctk


_W        = 380
_GAP      = 8
_MARGIN_X = 24
_MARGIN_Y = 64


class NotificationManager:
    def __init__(self, root: ctk.CTk):
        self._root  = root
        self._stack: list[tuple] = []   # [(popup, height), ...]

    # ── Empilage ──────────────────────────────────────────────────────────────

    def _next_y(self) -> int:
        screen_h = self._root.winfo_screenheight()
        y = screen_h - _MARGIN_Y
        for popup, h in list(self._stack):
            try:
                if popup.winfo_exists():
                    y -= h + _GAP
            except Exception:
                pass
        return y

    def _remove(self, popup):
        self._stack = [(p, h) for p, h in self._stack if p is not popup]

    def _place(self, popup) -> int:
        popup.update_idletasks()
        h = popup.winfo_reqheight()
        x = self._root.winfo_screenwidth() - _W - _MARGIN_X
        y = self._next_y() - h
        popup.geometry(f"{_W}x{h}+{x}+{y}")
        popup.deiconify()
        self._stack.append((popup, h))
        return h

    # ── Notification standard (auto-dismiss) ──────────────────────────────────

    def show(self, title: str, message: str, duration_ms: int = 4500):
        self._root.after(0, lambda: self._create(title, message, duration_ms))

    def _create(self, title: str, message: str, duration_ms: int):
        popup, _ = self._build_popup(title=title, body=message)
        self._place(popup)
        self._fade_in(popup, 0.0, stay_ms=duration_ms, persistent=False)

    # ── Notification suggestion (persistante) ─────────────────────────────────

    def show_suggestion(
        self,
        proc_name: str,
        exe_path: str,
        on_add: Callable[[], None],
        duration_ms: int = 0,   # ignoré — reste jusqu'au clic
    ):
        self._root.after(0, lambda: self._create_suggestion(proc_name, exe_path, on_add))

    def _create_suggestion(self, proc_name: str, exe_path: str, on_add: Callable):
        parts   = exe_path.replace("\\", "/").split("/") if exe_path else []
        display = parts[-2] if len(parts) >= 2 else proc_name

        popup, frame = self._build_popup(
            title="Jeu non suivi détecté",
            title_color="#f9e2af",
            body=display,
        )

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(0, 16))

        def _dismiss():
            self._remove(popup)
            try:
                popup.destroy()
            except Exception:
                pass

        def _on_add():
            _dismiss()
            on_add()

        ctk.CTkButton(
            btn_row, text="Annuler",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color="#313244", hover_color="#45475a",
            text_color="#cdd6f4", corner_radius=8,
            height=34, width=100,
            command=_dismiss,
        ).pack(side="left")

        ctk.CTkButton(
            btn_row, text="Ajouter",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color="#f9e2af", hover_color="#f2cdcd",
            text_color="#11111b", corner_radius=8,
            height=34, width=100,
            command=_on_add,
        ).pack(side="right")

        self._place(popup)
        self._fade_in(popup, 0.0, stay_ms=0, persistent=True)

    # ── Construction du popup ─────────────────────────────────────────────────

    def _build_popup(
        self,
        title: str,
        body: str,
        title_color: str = "#cdd6f4",
    ) -> tuple:
        popup = ctk.CTkToplevel(self._root)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.0)

        frame = ctk.CTkFrame(
            popup,
            corner_radius=14,
            fg_color="#1e1e2e",
            border_width=1,
            border_color="#45475a",
        )
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont("Segoe UI", 15, "bold"),
            text_color=title_color,
            anchor="w",
        ).pack(pady=(16, 4), padx=18, fill="x")

        ctk.CTkLabel(
            frame,
            text=body,
            font=ctk.CTkFont("Segoe UI", 13),
            text_color="#a6adc8",
            anchor="w",
            wraplength=_W - 36,
        ).pack(padx=18, pady=(0, 14), fill="x")

        return popup, frame

    # ── Animation ─────────────────────────────────────────────────────────────

    def _fade_in(self, popup, alpha: float, stay_ms: int, persistent: bool):
        alpha = min(alpha + 0.12, 0.95)
        try:
            popup.attributes("-alpha", alpha)
        except Exception:
            return
        if alpha < 0.95:
            popup.after(20, lambda: self._fade_in(popup, alpha, stay_ms, persistent))
        elif not persistent:
            popup.after(stay_ms, lambda: self._fade_out(popup))

    def _fade_out(self, popup, alpha: float = 0.95):
        alpha = max(alpha - 0.08, 0.0)
        try:
            popup.attributes("-alpha", alpha)
        except Exception:
            return
        if alpha > 0:
            popup.after(25, lambda: self._fade_out(popup, alpha))
        else:
            self._remove(popup)
            try:
                popup.destroy()
            except Exception:
                pass
