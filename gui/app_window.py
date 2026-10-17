import ctypes
import json
import struct
import tempfile
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from ctypes import wintypes
from tkinter import messagebox, ttk
import winreg

import keyboard

from core.camera_patcher import CameraPatcherError


class DiabloToolkitApp:
    FONT_FAMILY = "Roboto"
    PRIVATE_FONT_FLAG = 0x10

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
        self._wheel_remainder = 0
        self.pages = {}
        self.emoji_font = ("Segoe UI Emoji", 11, "bold")
        self._applying_preset = False
        self._key_capture_entry = None
        self._key_capture_allowed_keys = None
        self._key_capture_placeholder = ""
        self._tooltip_window = None
        self._placeholder_label_map = {}

        self._load_application_font()
        self._configure_window()
        self._configure_styles()
        self._build_layout()
        self._load_presets()
        self._load_saved_settings()
        self._register_hotkey()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _load_application_font(self):
        font_path = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "fonts"
            / "Roboto-Variable.ttf"
        )
        if not font_path.is_file():
            raise FileNotFoundError(f"Bundled Roboto font not found: {font_path}")

        self._font_api = ctypes.WinDLL("gdi32", use_last_error=True)
        self._font_api.AddFontResourceExW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        self._font_api.AddFontResourceExW.restype = wintypes.INT
        self._font_api.RemoveFontResourceExW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        self._font_api.RemoveFontResourceExW.restype = wintypes.BOOL

        self._font_path = str(font_path)
        if not self._font_api.AddFontResourceExW(
            self._font_path, self.PRIVATE_FONT_FLAG, None
        ):
            error = ctypes.get_last_error()
            raise OSError(error, f"Could not load bundled Roboto font: {font_path}")

        available_fonts = self.root.tk.call("font", "families")
        if self.FONT_FAMILY not in available_fonts:
            self._font_api.RemoveFontResourceExW(
                self._font_path, self.PRIVATE_FONT_FLAG, None
            )
            raise RuntimeError("Roboto was loaded but is unavailable to Tk.")

    def _configure_window(self):
        self.root.title("Diablo IV Toolkit")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1120, max(760, screen_width - 80))
        height = min(860, max(620, screen_height - 100))
        width = min(width, screen_width)
        height = min(height, screen_height)
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min(720, screen_width), min(580, screen_height))
        self.root.configure(bg=self.COLORS["background"])
        self._configure_window_icon()

    def _apply_pointer_cursor(self, widget):
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            return
        widget.bind("<Enter>", lambda _event, target=widget: target.configure(cursor="hand2"))
        widget.bind("<Leave>", lambda _event, target=widget: target.configure(cursor="arrow"))

    def _configure_window_icon(self):
        logo_path = Path(__file__).resolve().parents[1] / "assets" / "images" / "logo.png"
        if not logo_path.is_file():
            return

        try:
            self.window_icon = tk.PhotoImage(file=str(logo_path))
            self.root.iconphoto(True, self.window_icon)
            self.root.wm_iconphoto(True, self.window_icon)
        except tk.TclError:
            pass

        ico_path = self._create_windows_ico_from_png(logo_path)
        if not ico_path:
            return

        try:
            self.root.iconbitmap(default=str(ico_path))
            self.root.wm_iconbitmap(str(ico_path))
        except tk.TclError:
            pass

    @staticmethod
    def _create_windows_ico_from_png(png_path):
        try:
            png_bytes = png_path.read_bytes()
        except OSError:
            return None

        if len(png_bytes) < 8 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
            return None

        index = 8
        width = height = 0
        while index + 8 <= len(png_bytes):
            chunk_length = int.from_bytes(png_bytes[index : index + 4], "big")
            chunk_type = png_bytes[index + 4 : index + 8]
            if chunk_type == b"IHDR":
                if index + 8 + 8 <= len(png_bytes):
                    width = int.from_bytes(png_bytes[index + 8 : index + 12], "big")
                    height = int.from_bytes(png_bytes[index + 12 : index + 16], "big")
                break
            index += 12 + chunk_length

        if width <= 0 or height <= 0:
            return None

        width_value = 0 if width >= 256 else width
        height_value = 0 if height >= 256 else height
        ico_path = Path(tempfile.gettempdir()) / "diablo4_toolkit_logo.ico"

        header = b"\x00\x00\x01\x00\x01\x00"
        entry = struct.pack(
            "<BBBBHHII",
            width_value,
            height_value,
            0,
            0,
            1,
            32,
            len(png_bytes),
            22,
        )
        ico_bytes = header + entry + png_bytes

        try:
            ico_path.write_bytes(ico_bytes)
            return str(ico_path)
        except OSError:
            return None

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
            font=(self.FONT_FAMILY, 10),
        )
        style.configure(
            "Surface.TLabel",
            background=self.COLORS["surface"],
            foreground=self.COLORS["text"],
            font=(self.FONT_FAMILY, 10),
        )
        style.configure(
            "Inset.TLabel",
            background=self.COLORS["surface_alt"],
            foreground=self.COLORS["text"],
            font=(self.FONT_FAMILY, 10),
        )
        style.configure(
            "Title.TLabel",
            background=self.COLORS["background"],
            foreground=self.COLORS["text"],
            font=(self.FONT_FAMILY, 20, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self.COLORS["background"],
            foreground=self.COLORS["muted"],
            font=(self.FONT_FAMILY, 9),
        )
        style.configure(
            "Section.TLabel",
            background=self.COLORS["surface"],
            foreground=self.COLORS["gold"],
            font=(self.FONT_FAMILY, 11, "bold"),
        )
        style.configure(
            "Muted.Surface.TLabel",
            background=self.COLORS["surface"],
            foreground=self.COLORS["muted"],
            font=(self.FONT_FAMILY, 9),
        )
        style.configure(
            "Value.Surface.TLabel",
            background=self.COLORS["surface"],
            foreground=self.COLORS["gold"],
            font=(self.FONT_FAMILY, 10, "bold"),
        )
        style.configure(
            "TButton",
            background=self.COLORS["surface_alt"],
            foreground=self.COLORS["text"],
            padding=(13, 9),
            borderwidth=1,
            relief="flat",
            font=(self.FONT_FAMILY, 9, "bold"),
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
            font=(self.FONT_FAMILY, 9, "bold"),
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
            font=(self.FONT_FAMILY, 10),
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
            font=(self.FONT_FAMILY, 10),
            padding=7,
            borderwidth=1,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.COLORS["surface_alt"])],
            foreground=[("readonly", self.COLORS["text"])],
        )
        style.configure(
            "TSpinbox",
            fieldbackground=self.COLORS["surface_alt"],
            foreground=self.COLORS["text"],
            arrowcolor=self.COLORS["gold"],
            font=(self.FONT_FAMILY, 10),
            padding=7,
        )
        style.configure(
            "Horizontal.TScale",
            background=self.COLORS["surface"],
            troughcolor=self.COLORS["surface_alt"],
            sliderthickness=15,
        )
        style.configure(
            "Nav.TButton",
            background=self.COLORS["background"],
            foreground=self.COLORS["muted"],
            padding=(16, 13),
            anchor=tk.W,
            borderwidth=0,
            font=(self.FONT_FAMILY, 10, "bold"),
        )
        style.map(
            "Nav.TButton",
            background=[("active", self.COLORS["surface_alt"])],
            foreground=[("active", self.COLORS["text"])],
        )
        style.configure(
            "ActiveNav.TButton",
            background=self.COLORS["surface"],
            foreground=self.COLORS["gold"],
            padding=(16, 13),
            anchor=tk.W,
            borderwidth=0,
            font=(self.FONT_FAMILY, 10, "bold"),
        )
        style.map(
            "ActiveNav.TButton",
            foreground=[("active", self.COLORS["gold"])],
            background=[("active", self.COLORS["surface"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=self.COLORS["surface_alt"],
            troughcolor=self.COLORS["background"],
            bordercolor=self.COLORS["background"],
            arrowcolor=self.COLORS["muted"],
        )

    def _build_layout(self):
        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        sidebar_wrapper = ttk.Frame(container, style="TFrame")
        sidebar_wrapper.grid(row=0, column=0, sticky="ns")

        sidebar = ttk.Frame(sidebar_wrapper, style="TFrame", padding=(16, 22, 12, 18))
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        tk.Frame(sidebar_wrapper, bg=self.COLORS["border"], width=1).pack(
            side=tk.LEFT, fill=tk.Y
        )

        logo_path = Path(__file__).resolve().parents[1] / "assets" / "images" / "logo.png"
        self.logo_image = tk.PhotoImage(file=str(logo_path)).subsample(4, 4)
        ttk.Label(
            sidebar,
            image=self.logo_image,
            background=self.COLORS["background"],
        ).pack(anchor=tk.CENTER, pady=(0, 24))

        ttk.Label(sidebar, text="TOOLS", style="Subtitle.TLabel").pack(
            anchor=tk.W, padx=(12, 0), pady=(0, 8)
        )
        self.nav_autokey = tk.Button(
            sidebar,
            text="⚒️  KeyForge",
            bg=self.COLORS["surface"],
            fg=self.COLORS["gold"],
            activebackground=self.COLORS["surface_alt"],
            activeforeground=self.COLORS["gold"],
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            justify=tk.LEFT,
            anchor=tk.W,
            compound=tk.LEFT,
            padx=16,
            pady=13,
            font=self.emoji_font,
            command=lambda: self._show_page("autokey"),
        )
        self._apply_pointer_cursor(self.nav_autokey)
        self.nav_autokey.pack(fill=tk.X, pady=2)
        self.nav_camera = tk.Button(
            sidebar,
            text="📷  ZoomSettings",
            bg=self.COLORS["background"],
            fg=self.COLORS["muted"],
            activebackground=self.COLORS["surface_alt"],
            activeforeground=self.COLORS["text"],
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            justify=tk.LEFT,
            anchor=tk.W,
            compound=tk.LEFT,
            padx=16,
            pady=13,
            font=self.emoji_font,
            command=lambda: self._show_page("camera"),
        )
        self._apply_pointer_cursor(self.nav_camera)
        self.nav_camera.pack(fill=tk.X, pady=2)

        ttk.Frame(sidebar).pack(fill=tk.BOTH, expand=True)
        donation_button = ttk.Button(
            sidebar,
            text="☕  Buy me a coffee",
            style="Accent.TButton",
            command=self.open_donation_page,
        )
        self._apply_pointer_cursor(donation_button)
        donation_button.pack(fill=tk.X, padx=4, pady=(0, 12))
        tk.Frame(sidebar, bg=self.COLORS["red"], height=2).pack(fill=tk.X, pady=(8, 12))

        main_area = ttk.Frame(container, padding=(24, 20, 20, 12))
        main_area.grid(row=0, column=1, sticky="nsew")
        main_area.columnconfigure(0, weight=1)
        main_area.rowconfigure(0, weight=1)
        self.content_area = ttk.Frame(main_area)
        self.content_area.grid(row=0, column=0, sticky="nsew")
        self.content_area.columnconfigure(0, weight=1)
        self.content_area.rowconfigure(0, weight=1)

        self.tab_autokey = self._create_scrollable_page("autokey")
        self.tab_camera = self._create_scrollable_page("camera")

        self._build_autokey_tab()
        self._build_camera_tab()
        ttk.Label(
            main_area,
            text="v0.1 S15   •   DIABLO IV TOOLKIT   •   Use responsibly   •   By Kren",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="e", pady=(8, 0))
        self._show_page("autokey")

    def _create_scrollable_page(self, name):
        page = ttk.Frame(self.content_area)
        page.grid(row=0, column=0, sticky="nsew")
        self.pages[name] = page
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        canvas = tk.Canvas(
            page,
            bg=self.COLORS["background"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            page,
            orient=tk.VERTICAL,
            command=canvas.yview,
            style="Vertical.TScrollbar",
        )
        canvas.configure(
            yscrollcommand=lambda first, last: self._sync_scrollbar(
                scrollbar, first, last
            )
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas, padding=(2, 2, 16, 12))
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind(
            "<Configure>",
            lambda _event, target=canvas: target.configure(
                scrollregion=target.bbox("all")
            ),
        )
        canvas.bind(
            "<Configure>",
            lambda event, target=canvas, item=window_id: target.itemconfigure(
                item, width=event.width
            ),
        )
        canvas.bind(
            "<Enter>",
            lambda _event, target=canvas: self._enable_mousewheel(target),
        )
        canvas.bind("<Leave>", lambda _event: self._disable_mousewheel())
        setattr(self, f"{name}_canvas", canvas)
        return inner

    def _start_key_capture(self, entry, placeholder, allowed_keys=None):
        self._clear_key_capture()
        self._key_capture_entry = entry
        self._key_capture_allowed_keys = allowed_keys
        self._key_capture_placeholder = placeholder
        entry.unbind("<KeyPress>")
        entry.bind("<KeyPress>", self._handle_key_capture)
        if entry.get().strip() == "":
            self._show_placeholder(entry, placeholder)
        else:
            self._hide_placeholder(entry)

    def _show_placeholder(self, entry, placeholder):
        entry.config(foreground=self.COLORS["muted"])
        label = self._placeholder_label_map.get(id(entry))
        if label is None:
            label = tk.Label(
                entry.winfo_toplevel(),
                text=placeholder,
                bg=self.COLORS["surface_alt"],
                fg=self.COLORS["muted"],
                font=(self.FONT_FAMILY, 8),
                anchor="w",
            )
            self._placeholder_label_map[id(entry)] = label
        label.config(text=placeholder)
        label.place(in_=entry, x=6, y=1, relwidth=1, height=entry.winfo_reqheight())
        label.lift()

    def _hide_placeholder(self, entry):
        label = self._placeholder_label_map.get(id(entry))
        if label is not None:
            label.place_forget()

    def _clear_key_capture(self, _event=None):
        if self._key_capture_entry is not None:
            self._hide_placeholder(self._key_capture_entry)
        self._key_capture_entry = None
        self._key_capture_allowed_keys = None
        self._key_capture_placeholder = ""

    def _handle_key_capture(self, event):
        if not hasattr(self, "_key_capture_entry") or self._key_capture_entry is None:
            return "break"

        keysym = event.keysym.upper()
        entry = self._key_capture_entry

        if keysym == "BACKSPACE":
            entry.delete(0, tk.END)
            entry.config(foreground=self.COLORS["muted"])
            self._show_placeholder(entry, self._key_capture_placeholder)
            return "break"

        if keysym in {"SHIFT_L", "SHIFT_R", "CONTROL_L", "CONTROL_R", "ALT_L", "ALT_R", "TAB", "ESCAPE", "CAPS_LOCK", "ENTER", "DELETE", "UP", "DOWN", "LEFT", "RIGHT", "HOME", "END", "PAGE_UP", "PAGE_DOWN", "INSERT"}:
            return "break"

        allowed = self._key_capture_allowed_keys
        if allowed is not None:
            if keysym not in allowed:
                self._show_tooltip(entry, "Only F1-F12 are allowed.")
                return "break"
            key_value = keysym
        else:
            if event.char:
                key_value = event.char.upper()
            else:
                key_value = keysym

        entry.delete(0, tk.END)
        entry.insert(0, key_value)
        entry.config(foreground=self.COLORS["text"])
        self._hide_placeholder(entry)
        return "break"

    def _show_tooltip(self, widget, message):
        if hasattr(self, "_tooltip_window") and self._tooltip_window is not None:
            if self._tooltip_window.winfo_exists():
                self._tooltip_window.destroy()
        tooltip = tk.Toplevel(widget)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        tooltip.attributes("-topmost", True)
        label = tk.Label(
            tooltip,
            text=message,
            fg="#f2ece2",
            bg="#2b2c30",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            font=(self.FONT_FAMILY, 9),
        )
        label.pack()
        x = widget.winfo_rootx() + 12
        y = widget.winfo_rooty() + widget.winfo_height() + 8
        tooltip.geometry(f"+{x}+{y}")
        tooltip.deiconify()
        self._tooltip_window = tooltip
        self.root.after(1600, lambda: self._hide_tooltip())

    def _hide_tooltip(self):
        if hasattr(self, "_tooltip_window") and self._tooltip_window is not None:
            if self._tooltip_window.winfo_exists():
                self._tooltip_window.destroy()
            self._tooltip_window = None

    def clear_all_key_inputs(self):
        for entry in self.key_entries:
            entry.delete(0, tk.END)
            entry.config(foreground=self.COLORS["muted"])
            self._hide_placeholder(entry)

        self.toggle_entry.delete(0, tk.END)
        self.toggle_entry.config(foreground=self.COLORS["muted"])
        self._show_placeholder(self.toggle_entry, "Press F1-F12")

        self.autokey.set_keys([])
        self.current_toggle_key = "f1"
        self.toggle_entry.delete(0, tk.END)
        self.toggle_entry.insert(0, "F1")
        self.toggle_entry.config(foreground=self.COLORS["text"])
        self.toggle_entry.config(font=(self.FONT_FAMILY, 10))
        self._hide_placeholder(self.toggle_entry)

    def _get_key_entry_value(self, entry, placeholder):
        value = entry.get().strip()
        if not value or value.upper() == placeholder.upper():
            return ""
        return value.upper()

    @staticmethod
    def _sync_scrollbar(scrollbar, first, last):
        if float(first) <= 0 and float(last) >= 1:
            scrollbar.grid_remove()
        else:
            scrollbar.grid()
        scrollbar.set(first, last)

    def _enable_mousewheel(self, canvas):
        self.root.bind_all(
            "<MouseWheel>",
            lambda event, target=canvas: self._on_mousewheel(event, target),
        )

    def _on_mousewheel(self, event, canvas):
        self._wheel_remainder += event.delta
        units = int(-self._wheel_remainder / 120)
        if units:
            canvas.yview_scroll(units, "units")
            self._wheel_remainder += units * 120

    def _disable_mousewheel(self):
        self.root.unbind_all("<MouseWheel>")

    def _show_page(self, page):
        if page not in self.pages:
            raise ValueError(f"Unknown application page: {page}")

        for name, page_frame in self.pages.items():
            if name == page:
                page_frame.grid()
            else:
                page_frame.grid_remove()

        if page == "camera":
            self.nav_camera.configure(bg=self.COLORS["surface"], fg=self.COLORS["gold"], activebackground=self.COLORS["surface"], activeforeground=self.COLORS["gold"], font=self.emoji_font)
            self.nav_autokey.configure(bg=self.COLORS["background"], fg=self.COLORS["muted"], activebackground=self.COLORS["surface_alt"], activeforeground=self.COLORS["text"], font=self.emoji_font)
        else:
            self.nav_autokey.configure(bg=self.COLORS["surface"], fg=self.COLORS["gold"], activebackground=self.COLORS["surface"], activeforeground=self.COLORS["gold"], font=self.emoji_font)
            self.nav_camera.configure(bg=self.COLORS["background"], fg=self.COLORS["muted"], activebackground=self.COLORS["surface_alt"], activeforeground=self.COLORS["text"], font=self.emoji_font)

    def _build_autokey_tab(self):
        frame = self.tab_autokey
        ttk.Label(frame, text="KEYFORGE ⚒️", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            frame,
            text="Repeat selected keys at your preferred interval.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(3, 18))

        keys_card = ttk.Frame(frame, style="Surface.TFrame", padding=18)
        keys_card.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(keys_card, text="KEYS TO REPEAT", style="Section.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            keys_card,
            text="Leave unused slots blank.",
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
            entry = ttk.Entry(
                slot,
                width=7,
                justify="center",
                font=(self.FONT_FAMILY, 13),
            )
            self._apply_pointer_cursor(entry)
            entry.pack()
            entry.bind(
                "<FocusIn>",
                lambda _event, target=entry: self._start_key_capture(
                    target, "Press a key"
                ),
            )
            entry.bind("<FocusOut>", self._clear_key_capture)
            self.key_entries.append(entry)

        toggle_card = ttk.Frame(frame, style="Surface.TFrame", padding=18)
        toggle_card.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(toggle_card, text="TOGGLE HOTKEY", style="Section.TLabel").pack(
            anchor=tk.W
        )
        toggle_row = ttk.Frame(toggle_card, style="Surface.TFrame")
        toggle_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(
            toggle_row,
            text="Start or pause the AutoKeyer",
            style="Muted.Surface.TLabel",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.toggle_entry = ttk.Entry(
            toggle_row,
            width=12,
            justify="center",
            font=(self.FONT_FAMILY, 10),
        )
        self._apply_pointer_cursor(self.toggle_entry)
        self.toggle_entry.insert(0, self.current_toggle_key.upper())
        self.toggle_entry.config(foreground=self.COLORS["text"])
        self.toggle_entry.pack(side=tk.RIGHT)
        self.toggle_entry.bind(
            "<FocusIn>",
            lambda _event, target=self.toggle_entry: self._start_key_capture(
                target, "Press F1-F12", [f"F{i}" for i in range(1, 13)]
            ),
        )
        self.toggle_entry.bind("<FocusOut>", self._clear_key_capture)

        interval_row = ttk.Frame(toggle_card, style="Surface.TFrame")
        interval_row.pack(fill=tk.X, pady=(14, 0))
        interval_text = ttk.Frame(interval_row, style="Surface.TFrame")
        interval_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            interval_text,
            text="Interval between key presses",
            style="Surface.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            interval_text,
            text="From 100 to 5000 milliseconds",
            style="Muted.Surface.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))
        self.interval_entry = ttk.Spinbox(
            interval_row,
            from_=100,
            to=self.autokey.MAX_INTERVAL_MS,
            increment=10,
            width=9,
            justify="center",
        )
        self.interval_entry.set(str(self.autokey.interval_ms))
        self.interval_entry.pack(side=tk.RIGHT)

        self.clear_inputs_button = ttk.Button(
            frame,
            text="CLEAR INPUTS",
            style="TButton",
            command=self.clear_all_key_inputs,
        )
        self._apply_pointer_cursor(self.clear_inputs_button)
        self.clear_inputs_button.pack(anchor=tk.W, pady=(12, 0))

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X, pady=(4, 0))
        self.lbl_ak_status = tk.Label(
            action_row,
            text="●  INACTIVE",
            bg=self.COLORS["background"],
            fg=self.COLORS["muted"],
            font=(self.FONT_FAMILY, 10, "bold"),
        )
        self.lbl_ak_status.pack(side=tk.LEFT, pady=8)
        self.save_status_label = tk.Label(
            action_row,
            text="",
            bg=self.COLORS["background"],
            fg=self.COLORS["green"],
            font=(self.FONT_FAMILY, 9, "bold"),
        )
        self.save_status_label.pack(side=tk.LEFT, padx=(12, 0), pady=8)
        save_settings_button = ttk.Button(
            action_row,
            text="SAVE SETTINGS",
            style="Accent.TButton",
            command=self.apply_autokey,
        )
        self._apply_pointer_cursor(save_settings_button)
        save_settings_button.pack(side=tk.RIGHT)

    def _build_camera_tab(self):
        frame = self.tab_camera
        ttk.Label(frame, text="ZoomSettings 📷", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            frame,
            text="Adjust the camera framing and distance.",
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
            text="GAME CONNECTION",
            style="Section.TLabel",
        ).pack(anchor=tk.W)
        self.lbl_cam_status = tk.Label(
            connection_text,
            text="Waiting to connect to Diablo IV",
            bg=self.COLORS["surface"],
            fg=self.COLORS["muted"],
            font=(self.FONT_FAMILY, 9),
            anchor=tk.W,
        )
        self.lbl_cam_status.pack(anchor=tk.W, pady=(4, 0))
        self.attach_button = ttk.Button(
            connection_row,
            text="CONNECT",
            style="Accent.TButton",
            command=self.attach_and_scan,
        )
        self._apply_pointer_cursor(self.attach_button)
        self.attach_button.pack(side=tk.RIGHT, padx=(12, 0))

        preset_card = ttk.Frame(frame, style="Surface.TFrame", padding=15)
        preset_card.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(preset_card, text="PRESET", style="Section.TLabel").pack(
            anchor=tk.W
        )
        preset_row = ttk.Frame(preset_card, style="Surface.TFrame")
        preset_row.pack(fill=tk.X, pady=(9, 0))
        self.combo_presets = ttk.Combobox(preset_row, state="disabled")
        self.combo_presets.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._apply_pointer_cursor(self.combo_presets)
        self.combo_presets.bind("<Button-1>", lambda _event: self.combo_presets.selection_clear())
        self.combo_presets.bind("<<ComboboxSelected>>", self._on_preset_selected)
        self.apply_preset_button = ttk.Button(
            preset_row,
            text="APPLY",
            command=self.apply_preset,
            state=tk.DISABLED,
        )
        self._apply_pointer_cursor(self.apply_preset_button)
        self.apply_preset_button.pack(side=tk.RIGHT, padx=(9, 0))

        controls_card = ttk.Frame(frame, style="Surface.TFrame", padding=15)
        controls_card.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            controls_card,
            text="MANUAL ADJUSTMENTS",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 9))

        self.sliders = {}
        controls = [
            ("FOV", "Field of view", 0.0, 2.0),
            ("Zoom", "Zoom", 0.0, 2.0),
            ("Height", "Height", -10.0, 10.0),
            ("Angle", "Angle", 0.0, 25.0),
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

        self.save_camera_button = ttk.Button(
            controls_card,
            text="Save Settings",
            command=self.save_camera_settings,
            state=tk.DISABLED,
        )
        self._apply_pointer_cursor(self.save_camera_button)
        self.save_camera_button.pack(anchor=tk.E, pady=(12, 0))
        self.cam_save_status = tk.Label(
            controls_card,
            text="",
            bg=self.COLORS["surface"],
            fg=self.COLORS["green"],
            font=(self.FONT_FAMILY, 9, "bold"),
        )
        self.cam_save_status.pack(anchor=tk.E, pady=(6, 0))

    def _load_saved_settings(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Diablo IV Toolkit") as key:
                try:
                    interval = winreg.QueryValueEx(key, "interval_ms")[0]
                    interval = int(interval)
                    self.autokey.set_interval(interval)
                    self.interval_entry.set(str(interval))
                except FileNotFoundError:
                    pass

                for index, entry in enumerate(self.key_entries, start=1):
                    try:
                        value = winreg.QueryValueEx(key, f"slot_{index}")[0]
                    except FileNotFoundError:
                        continue
                    value = str(value).strip()
                    if value:
                        entry.delete(0, tk.END)
                        entry.insert(0, value.upper())
                        entry.config(foreground=self.COLORS["text"])

                try:
                    toggle_key = str(winreg.QueryValueEx(key, "toggle_key")[0]).strip()
                except FileNotFoundError:
                    toggle_key = ""
                if toggle_key:
                    self.current_toggle_key = toggle_key.lower()
                    self.toggle_entry.delete(0, tk.END)
                    self.toggle_entry.insert(0, self.current_toggle_key.upper())
                    self.toggle_entry.config(foreground=self.COLORS["text"])

                try:
                    values = winreg.QueryValueEx(key, "camera_values")[0]
                    if isinstance(values, str):
                        data = json.loads(values)
                        for name, value in data.items():
                            if name in self.sliders:
                                self.sliders[name].set(value)
                                self.slider_value_labels[name].config(text=f"{float(value):.2f}")
                except FileNotFoundError:
                    pass

                try:
                    preset_name = str(winreg.QueryValueEx(key, "camera_preset")[0])
                    if preset_name and preset_name in self.presets:
                        self.combo_presets.set(preset_name)
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            return

    def _save_settings(self, interval_ms, keys, toggle_key):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Diablo IV Toolkit") as key:
            winreg.SetValueEx(key, "interval_ms", 0, winreg.REG_DWORD, int(interval_ms))
            winreg.SetValueEx(key, "toggle_key", 0, winreg.REG_SZ, str(toggle_key).upper())
            for index, key_value in enumerate(keys, start=1):
                winreg.SetValueEx(key, f"slot_{index}", 0, winreg.REG_SZ, str(key_value).upper())

    def _save_camera_values(self):
        values = {}
        for name, variable in self.sliders.items():
            values[name] = float(variable.get())
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Diablo IV Toolkit") as key:
            winreg.SetValueEx(key, "camera_values", 0, winreg.REG_SZ, json.dumps(values))
            current = self.combo_presets.get()
            if current:
                winreg.SetValueEx(key, "camera_preset", 0, winreg.REG_SZ, str(current))

    def _on_preset_selected(self, _event=None):
        if self._applying_preset or not self.camera.is_attached:
            return
        selected = self.combo_presets.get()
        if selected and selected != "Custom":
            self.apply_preset()

    def _load_presets(self):
        preset_path = Path(__file__).resolve().parents[1] / "core" / "DiabloCameraPresets.json"
        try:
            with preset_path.open("r", encoding="utf-8-sig") as preset_file:
                data = json.load(preset_file)
        except (OSError, json.JSONDecodeError) as error:
            self.lbl_cam_status.config(
                text=f"Could not load presets: {error}",
                fg=self.COLORS["orange"],
            )
            return

        for preset in data.get("presets", []):
            self.presets[preset["name"]] = preset["values"]
        preset_names = list(self.presets.keys())
        if "Custom" not in preset_names:
            preset_names.insert(0, "Custom")
        self.combo_presets["values"] = preset_names
        if self.presets:
            self.combo_presets.current(0)

    def apply_autokey(self):
        try:
            interval_ms = int(self.interval_entry.get())
            self.autokey.set_interval(interval_ms)
        except ValueError as error:
            messagebox.showerror(
                "Invalid interval",
                str(error) or "Enter the interval in milliseconds.",
                parent=self.root,
            )
            self.interval_entry.focus_set()
            return

        keys = [self._get_key_entry_value(entry, "Press a key") for entry in self.key_entries]
        self.autokey.set_keys(keys)
        new_toggle = self._get_key_entry_value(self.toggle_entry, "Press F1-F12").lower()
        if not new_toggle:
            new_toggle = self.current_toggle_key
        if new_toggle and new_toggle != self.current_toggle_key:
            self.current_toggle_key = new_toggle
            self._register_hotkey()
        self._save_settings(interval_ms, keys, self.current_toggle_key)
        self.save_status_label.config(text="Saved")
        self.root.after(5000, lambda: self.save_status_label.config(text=""))

    def _register_hotkey(self):
        keyboard.unhook_all()
        keyboard.on_press_key(self.current_toggle_key, self.on_toggle)

    def on_toggle(self, event=None):
        is_active = self.autokey.toggle()
        self.root.after(0, self._update_autokey_status, is_active)

    def _update_autokey_status(self, is_active):
        self.lbl_ak_status.config(
            text="●  ACTIVE" if is_active else "●  INACTIVE",
            fg=self.COLORS["green"] if is_active else self.COLORS["muted"],
        )

    def attach_and_scan(self):
        self.attach_button.config(state=tk.DISABLED, text="CONNECTING...")
        self._set_camera_status("Looking for Diablo IV...", self.COLORS["orange"])
        if self.camera.attach():
            self._set_camera_status(
                "Connected. Scanning for camera data...",
                self.COLORS["orange"],
            )
            threading.Thread(target=self._scan_thread_worker, daemon=True).start()
        else:
            self._set_camera_status(
                "Diablo IV.exe process not found.",
                self.COLORS["red_hover"],
            )
            self.attach_button.config(state=tk.NORMAL, text="TRY AGAIN")

    def _scan_thread_worker(self):
        try:
            self.camera.scan_and_patch()
            self.camera.start_loop_writer()
            self.root.after(0, self._scan_success)
        except Exception as error:
            self.root.after(0, lambda err=error: self._scan_error(err))

    def _scan_success(self):
        self._set_camera_status(
            "Camera connected and ready.",
            self.COLORS["green"],
        )
        self.attach_button.config(state=tk.DISABLED, text="CONNECTED")
        for control in self.camera_controls:
            control.state(["!disabled"])
        if self.presets:
            self.apply_preset_button.config(state=tk.NORMAL)
        self.save_camera_button.config(state=tk.NORMAL)
        self.combo_presets.config(state="readonly")
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
        self.attach_button.config(state=tk.NORMAL, text="TRY AGAIN")
        self.combo_presets.config(state="disabled")
        self.apply_preset_button.config(state=tk.DISABLED)
        self.save_camera_button.config(state=tk.DISABLED)

    def _set_camera_status(self, text, color):
        self.lbl_cam_status.config(text=text, fg=color)

    def update_camera(self, name, value):
        try:
            self.camera.write_camera_value(name, value)
        except CameraPatcherError as error:
            self._set_camera_status(str(error), self.COLORS["red_hover"])
        if self._applying_preset or not self.camera.is_attached:
            return
        current = self.combo_presets.get()
        if current and current != "Custom" and current not in {"", None}:
            self._set_custom_preset()

    def _set_custom_preset(self):
        values = list(self.combo_presets["values"]) if self.combo_presets["values"] else []
        if "Custom" not in values:
            values.insert(0, "Custom")
            self.combo_presets["values"] = values
        self.combo_presets.set("Custom")

    def save_camera_settings(self):
        self._save_camera_values()
        self.cam_save_status.config(text="Saved")
        self.root.after(5000, lambda: self.cam_save_status.config(text=""))

    def apply_preset(self):
        selected = self.combo_presets.get()
        if selected in self.presets:
            self._applying_preset = True
            try:
                values = self.presets[selected]
                for key, value in values.items():
                    if key in self.sliders:
                        self.sliders[key].set(value)
                        self.slider_value_labels[key].config(text=f"{float(value):.2f}")
                        self.update_camera(key, value)
            finally:
                self._applying_preset = False

    def open_donation_page(self):
        if not webbrowser.open_new_tab("https://buymeacoffee.com/kren"):
            messagebox.showerror(
                "Could not open donation page",
                "Open https://buymeacoffee.com/kren in your browser.",
                parent=self.root,
            )

    def on_close(self):
        self.autokey.stop()
        self.camera.stop_loop_writer()
        keyboard.unhook_all()
        self.root.destroy()
        if not self._font_api.RemoveFontResourceExW(
            self._font_path, self.PRIVATE_FONT_FLAG, None
        ):
            error = ctypes.get_last_error()
            raise OSError(error, f"Could not unload bundled Roboto font: {self._font_path}")
