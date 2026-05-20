import customtkinter as ctk
import psutil

from data_manager import DataManager
from icon_cache import get_pil_icon
from tracker import ProcessTracker

_ICON_SIZE = 24


# ── Helpers psutil ─────────────────────────────────────────────────────────────

def _get_proc_paths(names_lower: set) -> dict[str, str]:
    """Retourne {name_lower: exe_path} pour les processus dont le nom est dans names_lower."""
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
    """Retourne une liste dédupliquée et triée de (name, exe_path) de tous les processus."""
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


# ── Dialog ─────────────────────────────────────────────────────────────────────

class AddGameDialog(ctk.CTkToplevel):
    def __init__(self, parent, dm: DataManager, tracker: ProcessTracker):
        super().__init__(parent)
        self._dm = dm
        self._tracker = tracker
        self._snapshot: set = set()
        self._selected_proc: str | None = None
        self._selected_exe: str = ""
        self._proc_exe_map: dict[str, str] = {}
        self._radio_var = ctk.StringVar(value="")
        self._alive = True
        self._all_procs: list[tuple[str, str]] = []
        self._icon_gen = 0

        self.title("Ajouter un jeu")
        self.geometry("560x610")
        self.minsize(500, 540)
        self.grab_set()
        self.configure(fg_color="#11111b")
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._center(560, 610)
        self._build()

        self._snapshot = self._tracker.get_snapshot()

    def _center(self, w: int, h: int):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _close(self):
        self._alive = False
        self.destroy()

    # ── Construction de l'UI ───────────────────────────────────────────────────

    def _build(self):
        ctk.CTkLabel(
            self,
            text="Ajouter un jeu",
            font=ctk.CTkFont("Segoe UI", 18, "bold"),
            text_color="#cdd6f4",
        ).pack(pady=(20, 10), padx=20, anchor="w")

        # Les deux méthodes dans un CTkTabview
        self._tabs = ctk.CTkTabview(
            self,
            fg_color="#1e1e2e",
            segmented_button_fg_color="#313244",
            segmented_button_selected_color="#89b4fa",
            segmented_button_selected_hover_color="#74c7ec",
            segmented_button_unselected_color="#313244",
            segmented_button_unselected_hover_color="#45475a",
            text_color="#cdd6f4",
            command=self._on_tab_change,
        )
        self._tabs.pack(fill="both", expand=True, padx=20, pady=(0, 5))
        self._tabs.add("Détection auto")
        self._tabs.add("Parcourir les processus")

        self._build_detect_tab(self._tabs.tab("Détection auto"))
        self._build_browse_tab(self._tabs.tab("Parcourir les processus"))

        # Nom du jeu (partagé entre les deux méthodes)
        name_frame = ctk.CTkFrame(self, fg_color="#1e1e2e", corner_radius=10)
        name_frame.pack(fill="x", padx=20, pady=5)

        name_header = ctk.CTkFrame(name_frame, fg_color="transparent")
        name_header.pack(fill="x", padx=15, pady=(12, 5))

        ctk.CTkLabel(
            name_header,
            text="Nom du jeu",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color="#89b4fa",
        ).pack(side="left")

        ctk.CTkLabel(
            name_header,
            text="  — modifiable",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#585b70",
        ).pack(side="left", pady=(1, 0))

        self._name_entry = ctk.CTkEntry(
            name_frame,
            placeholder_text="Ex : Cyberpunk 2077",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#313244",
            border_color="#45475a",
            text_color="#cdd6f4",
            height=36,
            corner_radius=8,
        )
        self._name_entry.pack(fill="x", padx=15, pady=(0, 12))

        self._error_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#f38ba8",
        )
        self._error_label.pack()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(5, 20))

        ctk.CTkButton(
            btn_row, text="Annuler",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#313244", hover_color="#45475a",
            text_color="#cdd6f4", corner_radius=8,
            command=self._close,
        ).pack(side="left")

        self._add_btn = ctk.CTkButton(
            btn_row, text="Ajouter",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color="#a6e3a1", hover_color="#94e2d5",
            text_color="#11111b", corner_radius=8,
            command=self._confirm,
            state="disabled",
        )
        self._add_btn.pack(side="right")

    # ── Onglet 1 : Détection auto ──────────────────────────────────────────────

    def _build_detect_tab(self, parent):
        ctk.CTkLabel(
            parent,
            text="Lancez votre jeu, puis cliquez sur « Détecter ».\n"
                 "Les nouveaux processus apparus seront listés ci-dessous.",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color="#a6adc8",
            justify="left",
            wraplength=480,
        ).pack(anchor="w", pady=(10, 8))

        ctk.CTkButton(
            parent,
            text="Détecter les nouveaux processus",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#89b4fa", hover_color="#74c7ec",
            text_color="#11111b", corner_radius=8,
            command=self._detect,
        ).pack(anchor="w", pady=(0, 8))

        self._detect_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent"
        )
        self._detect_scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            self._detect_scroll,
            text="En attente de la détection…",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#585b70",
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
                font=ctk.CTkFont("Segoe UI", 11),
                text_color="#f38ba8",
                justify="center",
            ).pack(pady=10)
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
        toolbar.pack(fill="x", pady=(8, 5))

        ctk.CTkButton(
            toolbar, text="↻  Rafraîchir",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#313244", hover_color="#45475a",
            text_color="#cdd6f4", corner_radius=8, width=120,
            command=self._load_all_procs,
        ).pack(side="left")

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())

        ctk.CTkEntry(
            toolbar,
            textvariable=self._search_var,
            placeholder_text="Rechercher un processus…",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color="#313244", border_color="#45475a",
            text_color="#cdd6f4", height=32, corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        self._browse_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent"
        )
        self._browse_scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            self._browse_scroll,
            text='Cliquez sur "↻ Rafraîchir" pour charger tous les processus.',
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#585b70",
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
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#585b70",
        ).pack(pady=20)
        # Récupération des processus en différé pour ne pas bloquer l'UI
        self.after(50, self._fetch_procs)

    def _fetch_procs(self):
        if not self._alive:
            return
        procs = _get_all_processes()
        self._populate_browse(procs)

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
                    text=f"… {len(procs) - shown} autres processus — utilisez la recherche pour filtrer.",
                    font=ctk.CTkFont("Segoe UI", 10),
                    text_color="#585b70",
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

    # ── Shared : construction d'une ligne processus ───────────────────────────

    def _add_proc_row(
        self, parent, proc_name: str, exe_path: str
    ) -> ctk.CTkLabel:
        """Ajoute une ligne [icône] [radio] nom  …/chemin. Retourne le label icône."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)

        # Placeholder icône (largeur fixe pour éviter le décalage au chargement)
        icon_lbl = ctk.CTkLabel(
            row, text="", width=_ICON_SIZE + 6, height=_ICON_SIZE
        )
        icon_lbl.pack(side="left", padx=(4, 4))

        ctk.CTkRadioButton(
            row,
            text=proc_name,
            variable=self._radio_var,
            value=proc_name,
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#cdd6f4",
            radiobutton_width=16,
            radiobutton_height=16,
            fg_color="#89b4fa",
            command=lambda p=proc_name: self._on_select(p),
        ).pack(side="left")

        if exe_path:
            parts = exe_path.replace("\\", "/").split("/")
            short = (
                f"  …/{parts[-2]}/{parts[-1]}"
                if len(parts) >= 3
                else f"  {exe_path}"
            )
            ctk.CTkLabel(
                row, text=short,
                font=ctk.CTkFont("Segoe UI", 9),
                text_color="#585b70",
            ).pack(side="left")

        return icon_lbl

    # ── Chargement des icônes via after() — 100% thread principal ─────────────

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
        """Traite une icône à la fois. Abandonné si la génération change (nouveau filtre)."""
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
        name = proc.replace(".exe", "").replace(".EXE", "")
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

    def _confirm(self):
        name = self._name_entry.get().strip()
        proc = self._selected_proc
        if not name or not proc:
            return
        if self._dm.game_exists(name):
            self._error_label.configure(
                text=f'Un jeu nommé "{name}" existe déjà.'
            )
            return
        self._dm.add_game(name, proc, self._selected_exe)
        self._alive = False
        self.destroy()
