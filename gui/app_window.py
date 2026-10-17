import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import keyboard

from core.camera_patcher import CameraPatcherError


class DiabloToolkitApp:
    COLORS = {
        "background": "#111214",
        "surface": "#1a1b1f",
        "surface_alt": "#222329",
        "border": "#39383a",
        "text": "#eee9df",
        "muted": "#a7a198",
        "red": "#a8232b",
        "red_hover": "#c4323b",
        "gold": "#c8a55a",
        "green": "#76b77b",
        "orange": "#d9a34a",
    }

    def __init__(self, root, autokey_service, camera_service):
        self.root = root
        self.autokey = autokey_service
        self.camera = camera_service
        self.current_toggle_key = "f1"
        self.presets = {}
        self.camera_controls = []
        self.slider_value_labels = {}

        self._configure_window()
        self._configure_styles()
        self._build_layout()
        self._load_presets()
        self._register_hotkey()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _configure_window(self):
        self.root.title("Diablo IV")
        self.root.geometry("760x650")
        self.root.minsize(680, 590)
        self.root.configure(bg=self.COLORS["background"])

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=self.COLORS["background"])
        style.configure("Surface.TFrame", background=self.COLORS["surface"])
        style.configure("Inset.TFrame", background=self.COLORS["surface_alt"])
        style.configure(
            "TLabel",
            background=self.COLORS["background"],
            foreground=self.COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Surface.TLabel",
            background=self.COLORS["surface"],
            foreground=self.COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Inset.TLabel",
            background=self.COLORS["surface_alt"],
            foreground=self.COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Title.TLabel",
            background=self.COLORS["background"],
            foreground=self.COLORS["text"],
            font=("Segoe UI Semibold", 20),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self.COLORS["background"],
            foreground=self.COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Section.TLabel",
            background=self.COLORS["surface"],
            foreground=self.COLORS["gold"],
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "Muted.Surface.TLabel",
            background=self.COLORS["surface"],
            foreground=self.COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Value.Surface.TLabel",
            background=self.COLORS["surface"],
            foreground=self.COLORS["gold"],
            font=("Consolas", 10, "bold"),
        )
        style.configure(
            "TNotebook",
            background=self.COLORS["background"],
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=self.COLORS["surface_alt"],
            foreground=self.COLORS["muted"],
            padding=(18, 11),
            font=("Segoe UI Semibold", 10),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.COLORS["red"])],
            foreground=[("selected", self.COLORS["text"])],
        )
        style.configure(
            "TButton",
            background=self.COLORS["surface_alt"],
            foreground=self.COLORS["text"],
            padding=(13, 9),
            borderwidth=1,
            relief="flat",
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "TButton",
            background=[
                ("disabled", self.COLORS["surface_alt"]),
                ("active", self.COLORS["border"]),
            ],
            foreground=[("disabled", "#706d68")],
        )
        style.configure(
            "Accent.TButton",
            background=self.COLORS["red"],
            foreground=self.COLORS["text"],
            padding=(15, 10),
            borderwidth=0,
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Accent.TButton",
            background=[
                ("disabled", "#513035"),
                ("active", self.COLORS["red_hover"]),
            ],
            foreground=[("disabled", "#aaa198")],
        )
        style.configure(
            "TEntry",
            fieldbackground=self.COLORS["surface_alt"],
            foreground=self.COLORS["text"],
            insertcolor=self.COLORS["text"],
            padding=7,
            borderwidth=1,
            relief="flat",
        )
        style.configure(
            "TCombobox",
            fieldbackground=self.COLORS["surface_alt"],
            background=self.COLORS["surface_alt"],
            foreground=self.COLORS["text"],
            arrowcolor=self.COLORS["gold"],
            padding=7,
            borderwidth=1,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.COLORS["surface_alt"])],
            foreground=[("readonly", self.COLORS["text"])],
        )
        style.configure(
            "Horizontal.TScale",
            background=self.COLORS["surface"],
            troughcolor=self.COLORS["surface_alt"],
            sliderthickness=15,
        )

    def _build_layout(self):
        container = ttk.Frame(self.root, padding=(26, 20, 26, 20))
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container)
        header.pack(fill=tk.X, pady=(0, 18))

        brand = ttk.Frame(header)
        brand.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(brand, text="DIABLO IV", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            brand,
            text="TOOLKIT  /  UTILITÁRIOS DE JOGO",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))
        tk.Frame(header, bg=self.COLORS["red"], width=4, height=48).pack(
            side=tk.RIGHT, padx=(16, 2), pady=3
        )

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.tab_autokey = ttk.Frame(self.notebook, padding=18)
        self.tab_camera = ttk.Frame(self.notebook, padding=18)
        self.notebook.add(self.tab_autokey, text="AUTOKEY")
        self.notebook.add(self.tab_camera, text="CÂMERA")

        self._build_autokey_tab()
        self._build_camera_tab()

        footer = ttk.Frame(container)
        footer.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(
            footer,
            text="DIABLO IV TOOLKIT",
            style="Subtitle.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Label(
            footer,
            text="Use com responsabilidade",
            style="Subtitle.TLabel",
        ).pack(side=tk.RIGHT)

    def _build_autokey_tab(self):
        frame = self.tab_autokey
        ttk.Label(frame, text="AUTOKEYER", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            frame,
            text="Mantenha suas teclas selecionadas ativas enquanto joga.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(3, 18))

        keys_card = ttk.Frame(frame, style="Surface.TFrame", padding=18)
        keys_card.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(keys_card, text="TECLAS ATIVAS", style="Section.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            keys_card,
            text="Deixe em branco os espaços que não quiser usar.",
            style="Muted.Surface.TLabel",
        ).pack(anchor=tk.W, pady=(3, 13))

        self.keys_frame = ttk.Frame(keys_card, style="Surface.TFrame")
        self.keys_frame.pack(anchor=tk.W)
        self.key_entries = []
        for index in range(4):
            slot = ttk.Frame(self.keys_frame, style="Surface.TFrame")
            slot.grid(row=0, column=index, padx=(0 if index == 0 else 12, 0))
            ttk.Label(
                slot,
                text=f"SLOT {index + 1}",
                style="Muted.Surface.TLabel",
            ).pack(anchor=tk.CENTER, pady=(0, 5))
            entry = ttk.Entry(slot, width=7, justify="center", font=("Segoe UI", 13))
            entry.pack()
            self.key_entries.append(entry)

        toggle_card = ttk.Frame(frame, style="Surface.TFrame", padding=18)
        toggle_card.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(toggle_card, text="TECLA DE ATIVAÇÃO", style="Section.TLabel").pack(
            anchor=tk.W
        )
        toggle_row = ttk.Frame(toggle_card, style="Surface.TFrame")
        toggle_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(
            toggle_row,
            text="Ativar ou pausar o AutoKeyer",
            style="Muted.Surface.TLabel",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.toggle_entry = ttk.Entry(toggle_row, width=12, justify="center")
        self.toggle_entry.insert(0, self.current_toggle_key.upper())
        self.toggle_entry.pack(side=tk.RIGHT)

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X, pady=(4, 0))
        self.lbl_ak_status = tk.Label(
            action_row,
            text="●  INATIVO",
            bg=self.COLORS["background"],
            fg=self.COLORS["muted"],
            font=("Segoe UI Semibold", 10),
        )
        self.lbl_ak_status.pack(side=tk.LEFT, pady=8)
        ttk.Button(
            action_row,
            text="SALVAR CONFIGURAÇÕES",
            style="Accent.TButton",
            command=self.apply_autokey,
        ).pack(side=tk.RIGHT)

    def _build_camera_tab(self):
        frame = self.tab_camera
        ttk.Label(frame, text="CÂMERA", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            frame,
            text="Ajuste o enquadramento e a distância da câmera.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(3, 15))

        connection_card = ttk.Frame(frame, style="Surface.TFrame", padding=15)
        connection_card.pack(fill=tk.X, pady=(0, 12))
        connection_row = ttk.Frame(connection_card, style="Surface.TFrame")
        connection_row.pack(fill=tk.X)
        connection_text = ttk.Frame(connection_row, style="Surface.TFrame")
        connection_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            connection_text,
            text="CONEXÃO COM O JOGO",
            style="Section.TLabel",
        ).pack(anchor=tk.W)
        self.lbl_cam_status = tk.Label(
            connection_text,
            text="Aguardando conexão com Diablo IV",
            bg=self.COLORS["surface"],
            fg=self.COLORS["muted"],
            font=("Segoe UI", 9),
            anchor=tk.W,
        )
        self.lbl_cam_status.pack(anchor=tk.W, pady=(4, 0))
        self.attach_button = ttk.Button(
            connection_row,
            text="CONECTAR",
            style="Accent.TButton",
            command=self.attach_and_scan,
        )
        self.attach_button.pack(side=tk.RIGHT, padx=(12, 0))

        preset_card = ttk.Frame(frame, style="Surface.TFrame", padding=15)
        preset_card.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(preset_card, text="PREDEFINIÇÃO", style="Section.TLabel").pack(
            anchor=tk.W
        )
        preset_row = ttk.Frame(preset_card, style="Surface.TFrame")
        preset_row.pack(fill=tk.X, pady=(9, 0))
        self.combo_presets = ttk.Combobox(preset_row, state="readonly")
        self.combo_presets.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.apply_preset_button = ttk.Button(
            preset_row,
            text="APLICAR",
            command=self.apply_preset,
            state=tk.DISABLED,
        )
        self.apply_preset_button.pack(side=tk.RIGHT, padx=(9, 0))

        controls_card = ttk.Frame(frame, style="Surface.TFrame", padding=15)
        controls_card.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            controls_card,
            text="AJUSTE MANUAL",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 9))

        self.sliders = {}
        controls = [
            ("FOV", "Campo de visão", 0.0, 2.0),
            ("Zoom", "Zoom", 0.0, 2.0),
            ("Height", "Altura", -10.0, 10.0),
            ("Angle", "Ângulo", 0.0, 25.0),
        ]
        for name, label, minimum, maximum in controls:
            row = ttk.Frame(controls_card, style="Surface.TFrame")
            row.pack(fill=tk.X, pady=5)
            title = ttk.Frame(row, style="Surface.TFrame")
            title.pack(fill=tk.X, pady=(0, 2))
            ttk.Label(title, text=label, style="Surface.TLabel").pack(side=tk.LEFT)
            value_label = ttk.Label(
                title,
                text="0.00",
                style="Value.Surface.TLabel",
            )
            value_label.pack(side=tk.RIGHT)

            variable = tk.DoubleVar(value=0.0)
            slider = ttk.Scale(
                row,
                from_=minimum,
                to=maximum,
                variable=variable,
                orient=tk.HORIZONTAL,
                command=lambda value, target=value_label: target.configure(
                    text=f"{float(value):.2f}"
                ),
            )
            slider.pack(fill=tk.X)
            slider.bind(
                "<ButtonRelease-1>",
                lambda event, key=name, var=variable: self.update_camera(
                    key, var.get()
                ),
            )
            slider.bind(
                "<KeyRelease>",
                lambda event, key=name, var=variable: self.update_camera(
                    key, var.get()
                ),
            )
            self.sliders[name] = variable
            self.slider_value_labels[name] = value_label
            slider.state(["disabled"])
            self.camera_controls.append(slider)

    def _load_presets(self):
        preset_path = Path(__file__).resolve().parents[1] / "core" / "DiabloCameraPresets.json"
        try:
            with preset_path.open("r", encoding="utf-8-sig") as preset_file:
                data = json.load(preset_file)
        except (OSError, json.JSONDecodeError) as error:
            self.lbl_cam_status.config(
                text=f"Não foi possível carregar as predefinições: {error}",
                fg=self.COLORS["orange"],
            )
            return

        for preset in data.get("presets", []):
            self.presets[preset["name"]] = preset["values"]
        self.combo_presets["values"] = list(self.presets.keys())
        if self.presets:
            self.combo_presets.current(0)

    def apply_autokey(self):
        keys = [entry.get() for entry in self.key_entries]
        self.autokey.set_keys(keys)
        new_toggle = self.toggle_entry.get().lower().strip()
        if new_toggle and new_toggle != self.current_toggle_key:
            self.current_toggle_key = new_toggle
            self._register_hotkey()
        messagebox.showinfo(
            "Configurações salvas",
            "As configurações do AutoKeyer foram aplicadas.",
            parent=self.root,
        )

    def _register_hotkey(self):
        keyboard.unhook_all()
        keyboard.on_press_key(self.current_toggle_key, self.on_toggle)

    def on_toggle(self, event=None):
        is_active = self.autokey.toggle()
        self.root.after(0, self._update_autokey_status, is_active)

    def _update_autokey_status(self, is_active):
        self.lbl_ak_status.config(
            text="●  ATIVO" if is_active else "●  INATIVO",
            fg=self.COLORS["green"] if is_active else self.COLORS["muted"],
        )

    def attach_and_scan(self):
        self.attach_button.config(state=tk.DISABLED, text="CONECTANDO...")
        self._set_camera_status("Procurando Diablo IV...", self.COLORS["orange"])
        if self.camera.attach():
            self._set_camera_status(
                "Conectado. Procurando os dados da câmera...",
                self.COLORS["orange"],
            )
            threading.Thread(target=self._scan_thread_worker, daemon=True).start()
        else:
            self._set_camera_status(
                "Processo Diablo IV.exe não encontrado.",
                self.COLORS["red_hover"],
            )
            self.attach_button.config(state=tk.NORMAL, text="TENTAR NOVAMENTE")

    def _scan_thread_worker(self):
        try:
            self.camera.scan_and_patch()
            self.camera.start_loop_writer()
            self.root.after(0, self._scan_success)
        except Exception as error:
            self.root.after(0, lambda err=error: self._scan_error(err))

    def _scan_success(self):
        self._set_camera_status(
            "Câmera conectada e pronta para ajuste.",
            self.COLORS["green"],
        )
        self.attach_button.config(state=tk.DISABLED, text="CONECTADO")
        for control in self.camera_controls:
            control.state(["!disabled"])
        if self.presets:
            self.apply_preset_button.config(state=tk.NORMAL)
        self.root.after(500, self._monitor_camera_writer)

    def _monitor_camera_writer(self):
        if not self.camera.is_attached:
            return
        error = self.camera.writer_error
        if error is not None:
            self.camera.stop_writer_only()
            self._set_camera_status(str(error), self.COLORS["red_hover"])
            return
        self.root.after(500, self._monitor_camera_writer)

    def _scan_error(self, error):
        self._set_camera_status(str(error), self.COLORS["red_hover"])
        self.attach_button.config(state=tk.NORMAL, text="TENTAR NOVAMENTE")

    def _set_camera_status(self, text, color):
        self.lbl_cam_status.config(text=text, fg=color)

    def update_camera(self, name, value):
        try:
            self.camera.write_camera_value(name, value)
        except CameraPatcherError as error:
            self._set_camera_status(str(error), self.COLORS["red_hover"])

    def apply_preset(self):
        selected = self.combo_presets.get()
        if selected in self.presets:
            values = self.presets[selected]
            for key, value in values.items():
                if key in self.sliders:
                    self.sliders[key].set(value)
                    self.slider_value_labels[key].config(text=f"{float(value):.2f}")
                    self.update_camera(key, value)

    def on_close(self):
        self.autokey.stop()
        self.camera.stop_loop_writer()
        keyboard.unhook_all()
        self.root.destroy()
