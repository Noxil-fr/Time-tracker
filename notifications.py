import base64
import io
import json
import os
import subprocess
import sys
import threading


_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notif_helper.py")
_FROZEN = getattr(sys, "frozen", False)


class NotificationManager:
    """Lance un sous-processus notif_helper.py par notification."""

    def __init__(self):
        self._on_add:    callable | None = None
        self._on_ignore: callable | None = None

    def set_on_add_game(self, cb: callable) -> None:
        self._on_add = cb

    def set_on_ignore_game(self, cb: callable) -> None:
        self._on_ignore = cb

    def show(self, title: str, message: str,
             color: str = "blue", suggestion: dict | None = None,
             icon=None, _duration: int | None = None) -> None:
        icon_b64 = ""
        if icon is not None:
            try:
                buf = io.BytesIO()
                icon.save(buf, format="PNG")
                icon_b64 = base64.b64encode(buf.getvalue()).decode()
            except Exception:
                pass

        data = {
            "title":      title,
            "message":    message,
            "color":      color,
            "suggestion": suggestion,
            "icon_b64":   icon_b64,
        }
        if _duration is not None:
            data["_duration"] = _duration

        threading.Thread(target=self._spawn, args=(data, suggestion),
                         daemon=True).start()

    def hide(self) -> None:
        pass  # le sous-processus gère lui-même sa fermeture

    def _spawn(self, data: dict, suggestion: dict | None) -> None:
        try:
            json_str = json.dumps(data, ensure_ascii=False)
            cmd = ([sys.executable, '--notif-helper', json_str] if _FROZEN
                   else [sys.executable, _HELPER, json_str])
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE if suggestion else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,   # CREATE_NO_WINDOW
            )
            if suggestion and (self._on_add or self._on_ignore):
                try:
                    out, _ = proc.communicate(timeout=300)
                    response = out.strip() if out else b""
                    if response == b"add" and self._on_add:
                        self._on_add(
                            suggestion["game_name"],
                            suggestion["proc_name"],
                            suggestion["exe_path"],
                        )
                    elif response == b"ignore" and self._on_ignore:
                        self._on_ignore(suggestion["proc_name"])
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass
