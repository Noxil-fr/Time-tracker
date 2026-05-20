import customtkinter as ctk


class NotificationManager:
    def __init__(self, root: ctk.CTk):
        self._root = root

    def show(self, title: str, message: str, duration_ms: int = 4500):
        self._root.after(0, lambda: self._create(title, message, duration_ms))

    def _create(self, title: str, message: str, duration_ms: int):
        popup = ctk.CTkToplevel(self._root)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.0)

        frame = ctk.CTkFrame(
            popup,
            corner_radius=12,
            fg_color="#1e1e2e",
            border_width=1,
            border_color="#45475a",
        )
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color="#cdd6f4",
            anchor="w",
        ).pack(pady=(12, 2), padx=15, fill="x")

        ctk.CTkLabel(
            frame,
            text=message,
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#a6adc8",
            anchor="w",
        ).pack(padx=15, pady=(0, 12), fill="x")

        popup.update_idletasks()
        w = max(300, popup.winfo_reqwidth() + 20)
        h = popup.winfo_reqheight()
        x = popup.winfo_screenwidth() - w - 20
        y = popup.winfo_screenheight() - h - 60
        popup.geometry(f"{w}x{h}+{x}+{y}")
        popup.deiconify()

        self._fade_in(popup, 0.0, duration_ms)

    def _fade_in(self, popup, alpha: float, stay_ms: int):
        alpha = min(alpha + 0.12, 0.95)
        try:
            popup.attributes("-alpha", alpha)
        except Exception:
            return
        if alpha < 0.95:
            popup.after(20, lambda: self._fade_in(popup, alpha, stay_ms))
        else:
            popup.after(stay_ms, lambda: self._fade_out(popup, alpha))

    def _fade_out(self, popup, alpha: float):
        alpha = max(alpha - 0.08, 0.0)
        try:
            popup.attributes("-alpha", alpha)
        except Exception:
            return
        if alpha > 0:
            popup.after(25, lambda: self._fade_out(popup, alpha))
        else:
            try:
                popup.destroy()
            except Exception:
                pass
