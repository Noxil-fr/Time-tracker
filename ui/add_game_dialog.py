import re
from datetime import datetime

import customtkinter as ctk
import psutil

from data_manager import DataManager
from icon_cache import get_pil_icon
from tracker import ProcessTracker

_ICON_SIZE = 28
_BG       = "#11111b"
_CARD     = "#1e1e2e"
_MUTED    = "#313244"
_BORDER   = "#45475a"
_TEXT     = "#cdd6f4"
_SUB      = "#a6adc8"
_DIM      = "#585b70"


# ── Helpers psutil ─────────────────────────────────────────────────────────────

def _get_proc_paths(names_lower: set) -> dict[str, str]:
    result = {}
    for p in psutil.process_iter(["name", "exe"]):
        try:
            name = p.info["name"]
            if name and name.lower() in names_lower:
                result[name.lower()] = p.info["exe"] or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return result


def _get_all_processes() -> list[tuple[str, str]]:
    seen: set = set()
    result = []
    for p in psutil.process_iter(["name", "exe"]):
        try:
            name = p.info["name"]
            key = name.lower() if name else ""
            if key and key not in seen:
                seen.add(key)
                result.append((name, p.info["exe"] or ""))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(result, key=lambda x: x[0].lower())


# ── Dialog principal ───────────────────────────────────────────────────────────

class AddGameDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        dm: DataManager,
        tracker: ProcessTracker,
        preselect: tuple[str, str] | None = None,
        on_add=None,
    ):
        super().__init__(parent)
        self._dm = dm
        self._tracker = tracker
        self._on_add = on_add
        self._snapshot: set = set()
        self._selected_proc: str | None = None
        self._selected_exe: str = ""
        self._proc_exe_map: dict[str, str] = {}
        self._radio_var = ctk.StringVar(value="")
        self._alive = True
        self._all_procs: list[tuple[str, str]] = []
        self._icon_gen = 0

        self.title("Ajouter un jeu")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color=_BG)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._center(600, 680)
        self._build()

        self._snapshot = self._tracker.get_snapshot()

        if preselect:
            proc, exe = preselect
            self._proc_exe_map[proc] = exe
            self._on_select(proc)

    def _center(self, w: int, h: int):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _close(self):
        self._alive = False
        self.destroy()

    # ── Construction ───────────────────────────────────────────────────────────

    def _build(self):
        # En-tête
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(22, 14))

        ctk.CTkLabel(
            hdr, text="Ajouter un jeu",
            font=ctk.CTkFont("Segoe UI", 20, "bold"),
            text_color=_TEXT,
        ).pack(side="left")

        # Onglets
        self._tabs = ctk.CTkTabview(
            self,
            fg_color=_CARD,
            segmented_button_fg_color=_MUTED,
            segmented_button_selected_color="#89b4fa",
            segmented_button_selected_hover_color="#74c7ec",
            segmented_button_unselected_color=_MUTED,
            segmented_button_unselected_hover_color=_BORDER,
            text_color=_TEXT,
            corner_radius=10,
            command=self._on_tab_change,
        )
        self._tabs.pack(fill="both", expand=True, padx=24, pady=(0, 0))
        self._tabs.add("Détection auto")
        self._tabs.add("Parcourir les processus")

        self._build_detect_tab(self._tabs.tab("Détection auto"))
        self._build_browse_tab(self._tabs.tab("Parcourir les processus"))

        # Séparateur
        ctk.CTkFrame(self, fg_color=_MUTED, height=1).pack(
            fill="x", padx=24, pady=(12, 0)
        )

        # Carte "Nom du jeu"
        name_card = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=10)
        name_card.pack(fill="x", padx=24, pady=(12, 0))

        name_inner = ctk.CTkFrame(name_card, fg_color="transparent")
        name_inner.pack(fill="x", padx=16, pady=14)

        lbl_row = ctk.CTkFrame(name_inner, fg_color="transparent")
        lbl_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            lbl_row, text="Nom du jeu",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color="#89b4fa",
        ).pack(side="left")

        ctk.CTkLabel(
            lbl_row, text="modifiable avant d'ajouter",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=_DIM,
        ).pack(side="left", padx=(8, 0))

        self._name_entry = ctk.CTkEntry(
            name_inner,
            placeholder_text="Ex : Cyberpunk 2077",
            font=ctk.CTkFont("Segoe UI", 14),
            fg_color=_MUTED, border_color=_BORDER,
            text_color=_TEXT, height=42, corner_radius=8,
        )
        self._name_entry.pack(fill="x")

        # Message d'erreur
        self._error_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color="#f38ba8",
        )
        self._error_label.pack(pady=(6, 0))

        # Boutons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(6, 22))

        ctk.CTkButton(
            btn_row, text="Annuler",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color=_MUTED, hover_color=_BORDER,
            text_color=_TEXT, corner_radius=8,
            height=42, width=130,
            command=self._close,
        ).pack(side="left")

        self._add_btn = ctk.CTkButton(
            btn_row, text="Ajouter le jeu",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color="#a6e3a1", hover_color="#94e2d5",
            text_color="#11111b", corner_radius=8,
            height=42, width=160,
            command=self._confirm,
            state="disabled",
        )
        self._add_btn.pack(side="right")

    # ── Onglet 1 : Détection auto ──────────────────────────────────────────────

    def _build_detect_tab(self, parent):
        ctk.CTkLabel(
            parent,
            text="Lancez votre jeu, puis cliquez sur « Détecter ».\n"
                 "Les nouveaux processus apparus depuis l'ouverture de ce dialog seront listés.",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=_SUB,
            justify="left",
            wraplength=510,
        ).pack(anchor="w", pady=(12, 10))

        ctk.CTkButton(
            parent,
            text="⟳   Détecter les nouveaux processus",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color="#89b4fa", hover_color="#74c7ec",
            text_color="#11111b", corner_radius=8,
            height=40, width=280,
            command=self._detect,
        ).pack(anchor="w", pady=(0, 10))

        self._detect_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent", height=160
        )
        self._detect_scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            self._detect_scroll,
            text="En attente de la détection…",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=_DIM,
        ).pack(pady=20)

    def _detect(self):
        current = self._tracker.get_snapshot()
        new_procs = sorted(current - self._snapshot)

        for w in self._detect_scroll.winfo_children():
            w.destroy()

        if not new_procs:
            ctk.CTkLabel(
                self._detect_scroll,
                text="Aucun nouveau processus détecté.\n"
                     "Assurez-vous que le jeu est bien lancé.",
                font=ctk.CTkFont("Segoe UI", 12),
                text_color="#f38ba8",
                justify="center",
            ).pack(pady=16)
            return

        proc_paths = _get_proc_paths(set(new_procs))
        icon_labels: list[tuple[str, ctk.CTkLabel]] = []

        self._radio_var.set("")
        for proc in new_procs:
            exe = proc_paths.get(proc, "")
            self._proc_exe_map[proc] = exe
            lbl = self._add_proc_row(self._detect_scroll, proc, exe)
            icon_labels.append((exe, lbl))

        self._load_icons(icon_labels)

    # ── Onglet 2 : Parcourir les processus ────────────────────────────────────

    def _build_browse_tab(self, parent):
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", pady=(10, 8))

        ctk.CTkButton(
            toolbar, text="↻  Rafraîchir",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color=_MUTED, hover_color=_BORDER,
            text_color=_TEXT, corner_radius=8,
            height=38, width=130,
            command=self._load_all_procs,
        ).pack(side="left")

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())

        ctk.CTkEntry(
            toolbar,
            textvariable=self._search_var,
            placeholder_text="Rechercher un processus…",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color=_MUTED, border_color=_BORDER,
            text_color=_TEXT, height=38, corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(10, 0))

        self._browse_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent", height=160
        )
        self._browse_scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            self._browse_scroll,
            text='Cliquez sur "↻ Rafraîchir" pour charger tous les processus.',
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=_DIM,
        ).pack(pady=20)

    def _on_tab_change(self):
        if (
            self._tabs.get() == "Parcourir les processus"
            and not self._all_procs
        ):
            self._load_all_procs()

    def _load_all_procs(self):
        for w in self._browse_scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self._browse_scroll,
            text="Chargement des processus…",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=_DIM,
        ).pack(pady=20)
        self.after(50, self._fetch_procs)

    def _fetch_procs(self):
        if not self._alive:
            return
        self._populate_browse(_get_all_processes())

    def _populate_browse(self, procs: list[tuple[str, str]]):
        if not self._alive:
            return
        for w in self._browse_scroll.winfo_children():
            w.destroy()
        self._all_procs = procs
        self._radio_var.set("")
        search = self._search_var.get().lower()
        icon_labels: list[tuple[str, ctk.CTkLabel]] = []
        shown = 0

        for name, exe in procs:
            if search and search not in name.lower():
                continue
            if not search and shown >= 100:
                ctk.CTkLabel(
                    self._browse_scroll,
                    text=f"… {len(procs) - shown} autres — utilisez la recherche pour filtrer.",
                    font=ctk.CTkFont("Segoe UI", 11),
                    text_color=_DIM,
                ).pack(anchor="w", padx=10, pady=4)
                break
            self._proc_exe_map[name] = exe
            lbl = self._add_proc_row(self._browse_scroll, name, exe)
            icon_labels.append((exe, lbl))
            shown += 1

        self._load_icons(icon_labels)

    def _filter(self):
        if not self._all_procs:
            return
        for w in self._browse_scroll.winfo_children():
            w.destroy()
        search = self._search_var.get().lower()
        icon_labels: list[tuple[str, ctk.CTkLabel]] = []
        shown = 0

        for name, exe in self._all_procs:
            if search and search not in name.lower():
                continue
            if not search and shown >= 100:
                break
            self._proc_exe_map[name] = exe
            lbl = self._add_proc_row(self._browse_scroll, name, exe)
            icon_labels.append((exe, lbl))
            shown += 1

        self._load_icons(icon_labels)

    # ── Ligne processus ────────────────────────────────────────────────────────

    def _add_proc_row(self, parent, proc_name: str, exe_path: str) -> ctk.CTkLabel:
        row = ctk.CTkFrame(
            parent, fg_color=_MUTED, corner_radius=8,
        )
        row.pack(fill="x", pady=3, padx=2)

        icon_lbl = ctk.CTkLabel(
            row, text="", width=_ICON_SIZE + 8, height=_ICON_SIZE + 8,
            fg_color="transparent",
        )
        icon_lbl.pack(side="left", padx=(10, 0))

        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True, padx=(6, 0), pady=8)

        ctk.CTkRadioButton(
            text_col,
            text=proc_name,
            variable=self._radio_var,
            value=proc_name,
            font=ctk.CTkFont("Segoe UI", 13),
            text_color=_TEXT,
            radiobutton_width=18,
            radiobutton_height=18,
            fg_color="#89b4fa",
            hover_color="#74c7ec",
            command=lambda p=proc_name: self._on_select(p),
        ).pack(anchor="w")

        if exe_path:
            parts = exe_path.replace("\\", "/").split("/")
            short = (
                f"…/{parts[-2]}/{parts[-1]}"
                if len(parts) >= 3
                else exe_path
            )
            ctk.CTkLabel(
                text_col, text=short,
                font=ctk.CTkFont("Segoe UI", 10),
                text_color=_DIM,
                anchor="w",
            ).pack(anchor="w")

        return icon_lbl

    # ── Icônes ─────────────────────────────────────────────────────────────────

    _SKIP_DIRS = (
        "\\windows\\system32\\",
        "\\windows\\syswow64\\",
        "\\windows\\winsxs\\",
    )

    def _load_icons(self, items: list[tuple[str, ctk.CTkLabel]]):
        self._icon_gen += 1
        queue = [
            (exe, lbl) for exe, lbl in items
            if exe and not any(d in exe.lower() for d in self._SKIP_DIRS)
        ]
        gen = self._icon_gen
        self.after(1, lambda: self._process_icon_queue(queue, gen))

    def _process_icon_queue(self, queue: list, gen: int):
        if not self._alive or gen != self._icon_gen or not queue:
            return
        exe_path, icon_lbl = queue.pop(0)
        pil_img = get_pil_icon(exe_path, _ICON_SIZE)
        if pil_img:
            try:
                if icon_lbl.winfo_exists():
                    ctk_img = ctk.CTkImage(
                        light_image=pil_img,
                        dark_image=pil_img,
                        size=(_ICON_SIZE, _ICON_SIZE),
                    )
                    icon_lbl.configure(image=ctk_img)
            except Exception:
                pass
        if queue and self._alive and gen == self._icon_gen:
            self.after(1, lambda: self._process_icon_queue(queue, gen))

    # ── Sélection et confirmation ──────────────────────────────────────────────

    def _on_select(self, proc: str):
        self._selected_proc = proc
        self._selected_exe = self._proc_exe_map.get(proc, "")
        name = re.sub(r"\.exe$", "", proc, flags=re.IGNORECASE)
        name = re.sub(r"[\s_\-]*(64|32|x64|x86|win64|win32)$", "", name, flags=re.IGNORECASE)
        name = " ".join(
            w.capitalize()
            for w in name.replace("_", " ").replace("-", " ").split()
        )
        self._name_entry.delete(0, "end")
        self._name_entry.insert(0, name)
        self._name_entry.select_range(0, "end")
        self._name_entry.focus()
        self._add_btn.configure(state="normal")
        self._error_label.configure(text="")

    def _get_process_start(self, proc_name: str) -> datetime | None:
        proc_lower = proc_name.lower()
        for p in psutil.process_iter(["name", "create_time"]):
            try:
                if p.info["name"] and p.info["name"].lower() == proc_lower:
                    return datetime.fromtimestamp(p.info["create_time"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return None

    def _confirm(self):
        name = self._name_entry.get().strip()
        proc = self._selected_proc
        if not name or not proc:
            return
        if self._dm.game_exists(name):
            self._error_label.configure(text=f'Un jeu nommé "{name}" existe déjà.')
            return

        retroactive_start = self._get_process_start(proc)
        self._dm.add_game(name, proc, self._selected_exe)

        if self._on_add:
            self._on_add()

        parent = self.master
        self._alive = False
        self.destroy()

        if retroactive_start is not None:
            elapsed = int((datetime.now() - retroactive_start).total_seconds())
            if elapsed >= 60:
                _RetroactiveDialog(parent, self._dm, name, retroactive_start)


# ── Dialog session rétroactive ─────────────────────────────────────────────────

class _RetroactiveDialog(ctk.CTkToplevel):
    def __init__(self, parent, dm: DataManager, game_name: str, start: datetime):
        super().__init__(parent)
        self._dm = dm
        self._game_name = game_name
        self._start = start

        self.title("Session en cours détectée")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color=_BG)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        elapsed = int((datetime.now() - start).total_seconds())
        h, m = divmod(elapsed // 60, 60)
        elapsed_str = f"{h}h {m:02d}min" if h else f"{m} min"

        card = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=12)
        card.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            card,
            text="Session en cours détectée",
            font=ctk.CTkFont("Segoe UI", 16, "bold"),
            text_color=_TEXT,
        ).pack(pady=(20, 6), padx=20)

        ctk.CTkLabel(
            card,
            text=f"{game_name} est en cours depuis {elapsed_str}.",
            font=ctk.CTkFont("Segoe UI", 14),
            text_color="#89b4fa",
            wraplength=360,
        ).pack(padx=20, pady=(0, 6))

        ctk.CTkLabel(
            card,
            text="Voulez-vous récupérer ce temps dans votre historique ?",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=_SUB,
            wraplength=360,
        ).pack(padx=20, pady=(0, 20))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(
            btn_row, text="Non, ignorer",
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color=_MUTED, hover_color=_BORDER,
            text_color=_TEXT, corner_radius=8,
            height=40, width=130,
            command=self.destroy,
        ).pack(side="left")

        ctk.CTkButton(
            btn_row, text="Oui, récupérer",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color="#a6e3a1", hover_color="#94e2d5",
            text_color="#11111b", corner_radius=8,
            height=40, width=140,
            command=self._confirm,
        ).pack(side="right")

        self._center(420, 240)

    def _center(self, w: int, h: int):
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _confirm(self):
        self._dm.record_session(self._game_name, self._start, datetime.now())
        self.destroy()
