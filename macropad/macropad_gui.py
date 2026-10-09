#!/usr/bin/env python3
"""Window for setting up the 6-key + knob macro pad.

Click a key on the picture to choose what it opens, set the knob and the
lights, then press "Send to pad". "Start listening" makes the keys open
things while this window is open (macropad.py run does the same without it).
"""

import copy
import math
import os
import platform
import queue
import re
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import macropad as mp

KEY_TITLES = {
    "f13": "Top-left key",
    "f14": "Top-right key",
    "f15": "Middle-left key",
    "f16": "Middle-right key",
    "f17": "Bottom-left key",
    "f18": "Bottom-right key",
}

PROGRAM = "Open a program, file or folder"
WEBSITE = "Open a website"
NOTHING = "Do nothing"

PROGRAM_EXAMPLES = {"Windows": "notepad or calc", "Darwin": "Safari or Calculator"}.get(
    platform.system(), "firefox or gnome-calculator"
)

# Tool action -> (menu text, short text drawn beside the knob)
KNOB_ACTIONS = {
    "volumedown": ("Volume down", "Vol −"),
    "volumeup": ("Volume up", "Vol +"),
    "mute": ("Mute", "Mute"),
    "play": ("Play / pause", "Play"),
    "next": ("Next track", "Next"),
    "prev": ("Previous track", "Prev"),
    "stop": ("Stop", "Stop"),
    "wheelup": ("Scroll up", "Scroll ↑"),
    "wheeldown": ("Scroll down", "Scroll ↓"),
    "screenbrightnessup": ("Screen brighter", "Bright +"),
    "screenbrightnessdown": ("Screen dimmer", "Bright −"),
    "calculator": ("Open calculator", "Calc"),
    "screenlock": ("Lock screen", "Lock"),
}

LED_EFFECT_NAMES = {
    "off": "Off",
    "backlight": "Always on",
    "press": "Light up the key you press",
    "shock": "Flash when a key is pressed",
    "shock2": "Flash (style 2) when pressed",
}

SWATCHES = {
    "white": "#f4f4f4",
    "red": "#ff453a",
    "orange": "#ff9f0a",
    "yellow": "#ffd60a",
    "green": "#30d158",
    "cyan": "#40c8e0",
    "blue": "#0a84ff",
    "purple": "#bf5af2",
}

# Colours for the drawing of the pad.
BODY, EDGE, CAP, CAP_TOP = "#17171a", "#3c3c44", "#222227", "#2f2f36"
TEXT, DIM, SCREW, ACCENT = "#f2f2f5", "#8a8a96", "#b9bcc4", "#4c8dff"
GRAY = "#6b6b75"

# Drawing layout, in pixels at 100% screen scaling.
CANVAS_W, CANVAS_H = 254, 452
CAP_SIZE, CAP_STEP, CAPS_X, CAPS_Y = 80, 94, 40, 44
KNOB_X, KNOB_Y, KNOB_R = 127, 374, 40


def blend(color, other, amount):
    """Mix two #rrggbb colours; amount 0 gives color, 1 gives other."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def short_name(target):
    """A few words to print on a key that has no name of its own."""
    if not target:
        return ""
    if "://" in target:
        return target.split("://", 1)[1].split("/")[0].removeprefix("www.")
    return Path(target.rstrip("/\\")).stem or target


class App:
    def __init__(self, root, config_path):
        self.root = root
        self.path = Path(config_path)
        self.config = mp.load_config(self.path)
        self.selected = mp.KEYS[0]
        self.lit_key = None  # key briefly lit after a press while listening
        self.knob_lit = False
        self.listener = None
        self.dirty = False
        self.busy = False
        self.loading = False
        self.events = queue.Queue()
        self.scale = root.winfo_fpixels("1i") / 96

        base = tkfont.nametofont("TkDefaultFont")
        size = base.actual("size")
        self.font_small = base.copy()
        self.font_small.configure(size=max(size - 1, 7))
        self.font_bold = base.copy()
        self.font_bold.configure(weight="bold")
        self.font_small_bold = self.font_small.copy()
        self.font_small_bold.configure(weight="bold")
        self.font_title = base.copy()
        self.font_title.configure(size=size + 2, weight="bold")

        self.build_ui()
        self.select_key(self.selected)
        self.load_knob_and_lights()
        self.update_title()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind_all("<Control-s>", lambda e: self.save())
        root.after(50, self.drain_events)
        self.log(f"Loaded {self.path.name}. Click a key on the pad to set it up.")

    # ---- layout -----------------------------------------------------------

    def build_ui(self):
        style = ttk.Style()
        if style.theme_use() == "default":
            style.theme_use("clam")
        style.configure("Bold.TButton", font=self.font_bold)
        bg = style.lookup("TFrame", "background") or self.root.cget("background")
        self.root.configure(background=bg)
        # bg may be a colour name (Windows: SystemButtonFace); blend() needs #rrggbb.
        self.bg_hex = "#" + "".join(f"{v // 256:02x}" for v in self.root.winfo_rgb(bg))

        main = ttk.Frame(self.root, padding=12)
        main.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="n", padx=(0, 14))
        self.canvas = tk.Canvas(
            left, width=self.px(CANVAS_W), height=self.px(CANVAS_H), background=bg, highlightthickness=0
        )
        self.canvas.grid(row=0, column=0)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        for tag in ("key", "knob"):
            self.canvas.tag_bind(tag, "<Enter>", lambda e: self.canvas.configure(cursor="hand2"))
            self.canvas.tag_bind(tag, "<Leave>", lambda e: self.canvas.configure(cursor=""))
        ttk.Label(left, text="Click a key or the knob to change it.", foreground=GRAY).grid(row=1, column=0, pady=(6, 0))

        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure((0, 1), weight=1, uniform="half")
        self.build_key_panel(right).grid(row=0, column=0, columnspan=2, sticky="ew")
        self.build_knob_panel(right).grid(row=1, column=0, sticky="nsew", pady=(10, 0), padx=(0, 10))
        self.build_lights_panel(right, bg).grid(row=1, column=1, sticky="nsew", pady=(10, 0))

        bar = ttk.Frame(main)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 6))
        bar.columnconfigure(2, weight=1)
        self.save_button = ttk.Button(bar, text="Save", command=self.save)
        self.save_button.grid(row=0, column=0)
        self.send_button = ttk.Button(bar, text="Send to pad", style="Bold.TButton", command=self.send_to_pad)
        self.send_button.grid(row=0, column=1, padx=8)
        self.listen_dot = tk.Canvas(bar, width=self.px(12), height=self.px(12), background=bg, highlightthickness=0)
        self.listen_dot.grid(row=0, column=3)
        self.listen_status = ttk.Label(bar)
        self.listen_status.grid(row=0, column=4, padx=(6, 10))
        self.listen_button = ttk.Button(bar, command=self.toggle_listening)
        self.listen_button.grid(row=0, column=5)
        self.update_listen_status()

        logs = ttk.Frame(main)
        logs.grid(row=2, column=0, columnspan=2, sticky="nsew")
        logs.columnconfigure(0, weight=1)
        logs.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            logs, height=3, wrap="word", state="disabled", font=self.font_small,
            relief="flat", padx=8, pady=6, background="#ffffff", foreground="#222222",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(logs, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    def build_key_panel(self, parent):
        panel = ttk.LabelFrame(parent, text=" Key ", padding=(12, 6, 12, 10))
        panel.columnconfigure(1, weight=1)
        header = ttk.Frame(panel)
        header.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.key_title = ttk.Label(header, font=self.font_title)
        self.key_title.grid(row=0, column=0)
        self.key_sub = ttk.Label(header, foreground=GRAY)
        self.key_sub.grid(row=0, column=1, sticky="s", padx=(10, 0))

        self.name_var = tk.StringVar()
        self.kind_var = tk.StringVar()
        self.target_var = tk.StringVar()
        ttk.Label(panel, text="Name on key").grid(row=2, column=0, sticky="w", pady=3, padx=(0, 10))
        ttk.Entry(panel, textvariable=self.name_var).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(panel, text="When pressed").grid(row=3, column=0, sticky="w", pady=3, padx=(0, 10))
        ttk.Combobox(
            panel, textvariable=self.kind_var, values=[PROGRAM, WEBSITE, NOTHING], state="readonly"
        ).grid(row=3, column=1, sticky="ew", pady=3)
        self.target_label = ttk.Label(panel)
        self.target_label.grid(row=4, column=0, sticky="w", pady=3, padx=(0, 10))
        self.target_entry = ttk.Entry(panel, textvariable=self.target_var)
        self.target_entry.grid(row=4, column=1, sticky="ew", pady=3)

        buttons = ttk.Frame(panel)
        buttons.grid(row=5, column=1, sticky="w", pady=(4, 0))
        self.file_button = ttk.Button(buttons, text="Choose file…", command=self.choose_file)
        self.file_button.grid(row=0, column=0)
        self.folder_button = ttk.Button(buttons, text="Choose folder…", command=self.choose_folder)
        self.folder_button.grid(row=0, column=1, padx=6)
        self.try_button = ttk.Button(buttons, text="Try it", command=self.try_key)
        self.try_button.grid(row=0, column=2)
        self.key_hint = ttk.Label(panel, foreground=GRAY, wraplength=self.px(700))
        self.key_hint.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.name_var.trace_add("write", lambda *a: self.store_key())
        self.kind_var.trace_add("write", lambda *a: (self.update_key_controls(), self.store_key()))
        self.target_var.trace_add("write", lambda *a: self.store_key())
        return panel

    def build_knob_panel(self, parent):
        panel = ttk.LabelFrame(parent, text=" Knob ", padding=(12, 6, 12, 10))
        panel.columnconfigure(1, weight=1)
        self.knob_boxes = {}
        for row, (part, text) in enumerate([("ccw", "Turn left"), ("press", "Press"), ("cw", "Turn right")]):
            ttk.Label(panel, text=text).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 10))
            box = ttk.Combobox(panel, state="readonly")
            box.grid(row=row, column=1, sticky="ew", pady=3)
            box.bind("<<ComboboxSelected>>", lambda e, p=part: self.store_knob(p))
            self.knob_boxes[part] = box
        ttk.Label(
            panel, foreground=GRAY, wraplength=self.px(250),
            text="The knob works by itself once it's on the pad; it doesn't need listening.",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        return panel

    def build_lights_panel(self, parent, bg):
        panel = ttk.LabelFrame(parent, text=" Lights ", padding=(12, 6, 12, 10))
        panel.columnconfigure(1, weight=1)
        ttk.Label(panel, text="Effect").grid(row=0, column=0, sticky="w", pady=3, padx=(0, 10))
        self.effect_box = ttk.Combobox(panel, state="readonly", width=24, values=list(LED_EFFECT_NAMES.values()))
        self.effect_box.grid(row=0, column=1, sticky="ew", pady=3)
        self.effect_box.bind("<<ComboboxSelected>>", lambda e: self.store_effect())

        ttk.Label(panel, text="Colour").grid(row=1, column=0, sticky="w", pady=3, padx=(0, 10))
        row = ttk.Frame(panel)
        row.grid(row=1, column=1, sticky="w", pady=3)
        self.swatches = {}
        for i, color in enumerate(mp.LED_COLORS):
            swatch = tk.Canvas(row, width=self.px(28), height=self.px(28), background=bg, highlightthickness=0)
            swatch.grid(row=0, column=i, padx=(0, 2))
            swatch.bind("<Button-1>", lambda e, c=color: self.store_color(c))
            self.swatches[color] = swatch

        self.mode_label = ttk.Label(panel, text="Mode number")
        self.mode_label.grid(row=2, column=0, sticky="w", pady=3, padx=(0, 10))
        self.mode_var = tk.StringVar()
        self.mode_spin = ttk.Spinbox(panel, from_=1, to=9, width=4, textvariable=self.mode_var)
        self.mode_spin.grid(row=2, column=1, sticky="w", pady=3)
        self.mode_var.trace_add("write", lambda *a: self.store_mode())

        self.lights_note = ttk.Label(panel, foreground=GRAY, wraplength=self.px(260))
        self.lights_note.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        bottom = ttk.Frame(panel)
        bottom.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        bottom.columnconfigure(0, weight=1)
        self.model_label = ttk.Label(bottom, foreground=GRAY)
        self.model_label.grid(row=0, column=0, sticky="w")
        self.lights_button = ttk.Button(bottom, text="Apply lights", command=self.apply_lights)
        self.lights_button.grid(row=0, column=1)
        return panel

    def px(self, value):
        return round(value * self.scale)

    # ---- drawing ------------------------------------------------------------

    def rounded(self, x0, y0, x1, y1, r, **kw):
        x0, y0, x1, y1, r = (self.px(v) for v in (x0, y0, x1, y1, r))
        points = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
                  x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.canvas.create_polygon(points, smooth=True, **kw)

    def circle(self, x, y, r, **kw):
        return self.canvas.create_oval(self.px(x - r), self.px(y - r), self.px(x + r), self.px(y + r), **kw)

    def draw_pad(self):
        c = self.canvas
        c.delete("all")
        self.rounded(14, 14, CANVAS_W - 14, CANVAS_H - 14, 20, fill=BODY, outline=EDGE, width=self.px(2))
        for x, y in ((27, 27), (CANVAS_W - 27, 27), (27, CANVAS_H - 27), (CANVAS_W - 27, CANVAS_H - 27)):
            self.circle(x, y, 5, fill=SCREW, outline="#7d8089")
            c.create_line(self.px(x - 3), self.px(y - 3), self.px(x + 3), self.px(y + 3), fill="#7d8089")

        led = self.config["led"]
        glow = SWATCHES["white"] if self.config.get("model") == "ch57x-2" else SWATCHES.get(led["color"], SWATCHES["white"])
        for row, keys in enumerate(mp.LAYOUT):
            for col, key in enumerate(keys):
                x, y = CAPS_X + col * CAP_STEP, CAPS_Y + row * CAP_STEP
                lit = led["effect"] == "backlight" or (led["effect"] != "off" and key in (self.selected, self.lit_key))
                self.draw_key(key, x, y, glow if lit else None)
        self.draw_knob()

    def draw_key(self, key, x, y, glow):
        c, tags = self.canvas, ("key", f"key:{key}")
        x1, y1 = x + CAP_SIZE, y + CAP_SIZE
        if glow:
            for spread, fade in ((9, 0.8), (6, 0.55), (3, 0.25)):
                self.rounded(x - spread, y - spread, x1 + spread, y1 + spread, 12 + spread,
                             fill=blend(glow, BODY, fade), outline="", tags=tags)
        top = blend(ACCENT, CAP_TOP, 0.3) if key == self.lit_key else CAP_TOP
        self.rounded(x, y, x1, y1, 12, fill=CAP, outline="#0d0d10", tags=tags)
        self.rounded(x + 7, y + 5, x1 - 7, y1 - 11, 10, fill=top, outline="", tags=tags)
        c.create_text(self.px(x + 13), self.px(y + 10), text=key.upper(), anchor="nw",
                      fill=DIM, font=self.font_small, tags=tags)
        entry = self.config["keys"][key]
        name = (entry.get("label") or short_name(entry.get("launch")))[:28]
        room = self.px(CAP_SIZE - 16)
        # Drop to a smaller font rather than split a long word across lines.
        fits = all(self.font_bold.measure(word) <= room for word in name.split())
        c.create_text(self.px(x + CAP_SIZE / 2), self.px(y + CAP_SIZE / 2 + 2), text=name or "—",
                      width=room, justify="center", fill=TEXT if name else DIM,
                      font=self.font_bold if fits else self.font_small_bold, tags=tags)
        if key == self.selected:
            self.rounded(x - 4, y - 4, x1 + 4, y1 + 4, 15, fill="", outline=ACCENT, width=self.px(3), tags=tags)

    def draw_knob(self):
        c, tags = self.canvas, ("knob",)
        knob = self.config["knob"]
        short = {action: names[1] for action, names in KNOB_ACTIONS.items()}
        self.circle(KNOB_X, KNOB_Y, KNOB_R, fill="#1f1f23", outline="#4a4a52", width=self.px(2), tags=tags)
        for i in range(28):
            dx, dy = math.cos(i * math.tau / 28), math.sin(i * math.tau / 28)
            c.create_line(self.px(KNOB_X + dx * (KNOB_R - 6)), self.px(KNOB_Y + dy * (KNOB_R - 6)),
                          self.px(KNOB_X + dx * KNOB_R), self.px(KNOB_Y + dy * KNOB_R),
                          fill="#3a3a41", width=self.px(2), tags=tags)
        self.circle(KNOB_X, KNOB_Y, KNOB_R - 9, fill="#2c2c31", outline="#55555e", tags=tags)
        for r in (KNOB_R - 15, KNOB_R - 21, KNOB_R - 27):
            self.circle(KNOB_X, KNOB_Y, r, outline="#34343a", tags=tags)
        c.create_text(self.px(KNOB_X), self.px(KNOB_Y), text=short.get(knob["press"], knob["press"])[:10],
                      fill=TEXT, font=self.font_small, tags=tags)
        for side, arrow, part in ((-1, "↺", "ccw"), (1, "↻", "cw")):
            c.create_text(self.px(KNOB_X + side * (KNOB_R + 30)), self.px(KNOB_Y),
                          text=f"{arrow}\n{short.get(knob[part], knob[part])[:10]}",
                          justify="center", fill=DIM, font=self.font_small, tags=tags)
        if self.knob_lit:
            self.circle(KNOB_X, KNOB_Y, KNOB_R + 5, outline=ACCENT, width=self.px(3), tags=tags)

    def on_canvas_click(self, event):
        tags = self.canvas.gettags("current")
        key = next((t.split(":", 1)[1] for t in tags if t.startswith("key:")), None)
        if key:
            self.select_key(key)
        elif "knob" in tags:
            self.knob_boxes["ccw"].focus_set()
            self.knob_lit = True
            self.draw_pad()
            self.root.after(600, self.unlight_knob)

    def unlight_knob(self):
        self.knob_lit = False
        self.draw_pad()

    def light_key(self, key):
        self.lit_key = key
        self.draw_pad()
        self.root.after(250, self.unlight_key, key)

    def unlight_key(self, key):
        if self.lit_key == key:
            self.lit_key = None
            self.draw_pad()

    # ---- key settings -------------------------------------------------------

    def select_key(self, key):
        self.selected = key
        entry = self.config["keys"][key]
        target = entry.get("launch") or ""
        self.loading = True
        self.name_var.set(entry.get("label", ""))
        self.target_var.set(target)
        self.kind_var.set(NOTHING if not target else WEBSITE if re.match(r"https?://", target) else PROGRAM)
        self.loading = False
        self.key_title.configure(text=KEY_TITLES[key])
        self.key_sub.configure(text=f"sends {key.upper()} to your computer")
        self.update_key_controls()
        self.draw_pad()

    def update_key_controls(self):
        kind = self.kind_var.get()
        files = "normal" if kind == PROGRAM else "disabled"
        self.file_button.configure(state=files)
        self.folder_button.configure(state=files)
        self.target_entry.configure(state="disabled" if kind == NOTHING else "normal")
        self.try_button.configure(state="disabled" if kind == NOTHING else "normal")
        self.target_label.configure(text="Website" if kind == WEBSITE else "Open")
        self.key_hint.configure(text={
            PROGRAM: f"Type a program name such as {PROGRAM_EXAMPLES}, or choose a file or folder.",
            WEBSITE: "For example www.youtube.com",
            NOTHING: "This key won't do anything.",
        }.get(kind, ""))

    def current_target(self):
        kind, target = self.kind_var.get(), self.target_var.get().strip()
        if kind == NOTHING or not target:
            return None
        if kind == WEBSITE and "://" not in target:
            return "https://" + target
        return target

    def store_key(self):
        if self.loading:
            return
        entry = self.config["keys"][self.selected]
        entry["label"] = self.name_var.get().strip()
        entry["launch"] = self.current_target()
        self.mark_dirty()
        self.draw_pad()

    def choose_file(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose a program or file")
        if path:
            self.target_var.set(os.path.normpath(path))

    def choose_folder(self):
        path = filedialog.askdirectory(parent=self.root, title="Choose a folder")
        if path:
            self.target_var.set(os.path.normpath(path))

    def try_key(self):
        self.light_key(self.selected)
        mp.open_key(self.config, self.selected, self.log)

    # ---- knob and lights ----------------------------------------------------

    def load_knob_and_lights(self):
        for part, box in self.knob_boxes.items():
            current = self.config["knob"][part]
            names = [names[0] for names in KNOB_ACTIONS.values()]
            if current not in KNOB_ACTIONS:
                names.append(current)  # something typed into config.json by hand
            box.configure(values=names)
            box.set(KNOB_ACTIONS[current][0] if current in KNOB_ACTIONS else current)
        led = self.config["led"]
        self.effect_box.set(LED_EFFECT_NAMES.get(led["effect"], led["effect"]))
        self.loading = True
        self.mode_var.set(str(led["mode_number"]))
        self.loading = False
        self.update_light_controls()

    def store_knob(self, part):
        text = self.knob_boxes[part].get()
        self.config["knob"][part] = next((a for a, names in KNOB_ACTIONS.items() if names[0] == text), text)
        self.mark_dirty()
        self.draw_pad()

    def store_effect(self):
        led = self.config["led"]
        led["effect"] = next(e for e, name in LED_EFFECT_NAMES.items() if name == self.effect_box.get())
        if led["effect"] not in ("off", "backlight") and led["color"] == "white":
            led["color"] = "cyan"  # white only works when the lights stay on
        self.mark_dirty()
        self.update_light_controls()

    def store_color(self, color):
        if not self.color_allowed(color):
            return
        self.config["led"]["color"] = color
        self.mark_dirty()
        self.update_light_controls()

    def store_mode(self):
        if self.loading:
            return
        try:
            self.config["led"]["mode_number"] = max(0, min(255, int(self.mode_var.get())))
        except ValueError:
            return
        self.mark_dirty()

    def color_allowed(self, color):
        led = self.config["led"]
        if self.config.get("model") == "ch57x-2" or led["effect"] == "off":
            return False
        return color != "white" or led["effect"] == "backlight"

    def update_light_controls(self):
        model = self.config.get("model")
        for color, swatch in self.swatches.items():
            swatch.delete("all")
            allowed = self.color_allowed(color)
            fill = SWATCHES[color] if allowed else blend(SWATCHES[color], self.bg_hex, 0.75)
            if color == self.config["led"]["color"] and allowed:
                swatch.create_oval(self.px(1), self.px(1), self.px(27), self.px(27), outline="#333333", width=self.px(2))
            swatch.create_oval(self.px(5), self.px(5), self.px(23), self.px(23), fill=fill, outline="#9a9aa2")
            swatch.configure(cursor="hand2" if allowed else "")
        if model and model != "ch57x-2":
            self.mode_label.grid_remove()
            self.mode_spin.grid_remove()
            note = ""
        else:
            self.mode_label.grid()
            self.mode_spin.grid()
            note = (
                "Your pad can't choose a colour. Try mode numbers to find a pattern you like."
                if model else
                "Older pads can't choose a colour; they use the mode number instead."
            )
        self.lights_note.configure(text=note)
        if note:
            self.lights_note.grid()
        else:
            self.lights_note.grid_remove()
        self.model_label.configure(text=f"Pad type: {model}" if model else "Pad type: found on first send")
        self.draw_pad()

    # ---- talking to the pad -------------------------------------------------

    def send_to_pad(self):
        def job(config, log):
            model = mp.flash(config, log)
            log("Keys and knob are on the pad.")
            return mp.set_lights(config["led"], model, log)

        self.run_job("Sending to the pad…", job, "Done. Press “Start listening” to use the keys.")

    def apply_lights(self):
        self.run_job("Setting the lights…", lambda config, log: mp.set_lights(config["led"], config.get("model"), log),
                     "Lights set.")

    def run_job(self, start_message, job, done_message):
        """Save, then run a pad command in the background so the window stays responsive."""
        if self.busy or not self.save(quiet=True):
            return
        self.set_busy(True)
        self.log(start_message)
        config = copy.deepcopy(self.config)

        def work():
            try:
                model = job(config, lambda line: self.post(self.log, line))
            except mp.PadError as exc:
                self.post(self.job_failed, exc)
            except Exception as exc:  # report anything else instead of leaving the window busy
                self.post(self.job_failed, mp.PadError(f"Unexpected error: {exc!r}"))
            else:
                self.post(self.job_done, model, done_message)

        threading.Thread(target=work, daemon=True).start()

    def job_done(self, model, message):
        self.set_busy(False)
        if model and model != self.config.get("model"):
            self.config["model"] = model
            self.log(f"Pad type detected: {model}")
            self.save(quiet=True)
            self.update_light_controls()
        self.log(message)

    def job_failed(self, error):
        self.set_busy(False)
        self.log(str(error))
        if isinstance(error, mp.ToolMissing):
            if messagebox.askyesno("Pad tool needed", f"{error}\n\nOpen the download page now?", parent=self.root):
                webbrowser.open(mp.TOOL_URL)
            return
        text = str(error)
        if "find USB device" in text:
            text += "\n\nCheck the pad is plugged in with a USB cable."
            if sys.platform == "win32":
                text += " On Windows the tool also needs UsbDk installed (see the README)."
        elif "Access denied" in text or "insufficient permissions" in text:
            text += "\n\nOn Linux, run with sudo or add the udev rule from the README."
        messagebox.showerror("Couldn't reach the pad", text, parent=self.root)

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for button in (self.send_button, self.lights_button, self.save_button):
            button.configure(state=state)
        self.root.configure(cursor="watch" if busy else "")

    # ---- listening ----------------------------------------------------------

    def toggle_listening(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
            self.log("Stopped listening.")
        else:
            try:
                self.listener = mp.start_listener(lambda key: self.post(self.on_pad_key, key))
            except mp.PadError as exc:
                messagebox.showerror("Can't listen for keys", str(exc), parent=self.root)
                return
            self.log("Listening. Press a key on the pad.")
        self.update_listen_status()

    def on_pad_key(self, key):
        self.light_key(key)
        mp.open_key(self.config, key, self.log)

    def update_listen_status(self):
        on = self.listener is not None
        self.listen_dot.delete("all")
        self.listen_dot.create_oval(self.px(1), self.px(1), self.px(11), self.px(11),
                                    fill="#30d158" if on else "#b0b0b8", outline="")
        self.listen_status.configure(text="Listening for the pad" if on else "Not listening")
        self.listen_button.configure(text="Stop listening" if on else "Start listening")

    # ---- plumbing -----------------------------------------------------------

    def post(self, fn, *args):
        """Run fn(*args) on the window's thread; safe to call from any thread."""
        self.events.put((fn, args))

    def drain_events(self):
        while True:
            try:
                fn, args = self.events.get_nowait()
            except queue.Empty:
                break
            fn(*args)
        self.root.after(50, self.drain_events)

    def log(self, message):
        message = "".join(ch for ch in str(message) if ord(ch) <= 0xFFFF)  # Tk can't draw emoji
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.update_title()

    def update_title(self):
        self.root.title("Macro Pad" + (" *" if self.dirty else ""))

    def save(self, quiet=False):
        try:
            mp.save_config(self.path, self.config)
        except OSError as exc:
            messagebox.showerror("Couldn't save", str(exc), parent=self.root)
            return False
        self.dirty = False
        self.update_title()
        if not quiet:
            self.log(f"Saved to {self.path.name}.")
        return True

    def on_close(self):
        if self.dirty:
            answer = messagebox.askyesnocancel("Save changes?", "Save your changes before closing?", parent=self.root)
            if answer is None or (answer and not self.save()):
                return
        if self.listener:
            self.listener.stop()
        self.root.destroy()


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else mp.DEFAULT_CONFIG_PATH
    if sys.platform == "win32":
        try:  # sharp text on high-resolution screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    try:
        App(root, path)
    except mp.PadError as exc:
        messagebox.showerror("Macro Pad", str(exc))
        return
    root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
    root.mainloop()


if __name__ == "__main__":
    main()
