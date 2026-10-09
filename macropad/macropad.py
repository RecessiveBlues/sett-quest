#!/usr/bin/env python3
"""Simple controller for the generic 6-key + 1-knob USB macro pad.

These pads (CH57x chip, USB ID 1189:8890, 1189:8840 or 1189:8842) store
their key mapping and light setting on the device itself. This script:

  flash  - writes the key/knob mapping from config.json to the pad
  led    - sets the lights
  run    - listens for the pad's keys (F13-F18) and opens programs

For a window instead of commands, run macropad_gui.py.

flash and led use ch57x-keyboard-tool (https://github.com/kriomant/ch57x-keyboard-tool)
to talk to the pad. run only needs the pynput package.
"""

import argparse
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = HERE / "config.json"
TOOL = "ch57x-keyboard-tool"
TOOL_URL = "https://github.com/kriomant/ch57x-keyboard-tool/releases"

# The pad as it sits on the desk (knob at the bottom), top to bottom, left to right.
LAYOUT = [["f13", "f14"], ["f15", "f16"], ["f17", "f18"]]
KEYS = [key for row in LAYOUT for key in row]

# On Linux (X11), F13-F18 usually arrive as these XF86 keysyms instead.
X11_ALIASES = {
    0x1008FF81: "f13",  # XF86Tools
    0x1008FF45: "f14",  # XF86Launch5
    0x1008FF46: "f15",  # XF86Launch6
    0x1008FF47: "f16",  # XF86Launch7
    0x1008FF48: "f17",  # XF86Launch8
    0x1008FF49: "f18",  # XF86Launch9
}

LED_EFFECTS = ["off", "backlight", "press", "shock", "shock2"]
LED_COLORS = ["white", "red", "orange", "yellow", "green", "cyan", "blue", "purple"]

DEFAULTS = {
    "model": None,
    "knob": {"ccw": "volumedown", "press": "mute", "cw": "volumeup"},
    "led": {"effect": "backlight", "color": "cyan", "mode_number": 1},
}

# Windows: keep a console window from flashing up each time the tool runs.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class PadError(Exception):
    """Something went wrong; the message is meant for the user."""


class ToolMissing(PadError):
    pass


def load_config(path):
    """Read config.json, filling in anything missing with defaults."""
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}
    except json.JSONDecodeError as exc:
        raise PadError(f"{path} is not valid JSON: {exc}") from exc
    config.setdefault("model", DEFAULTS["model"])
    keys = config.setdefault("keys", {})
    for key in KEYS:
        keys.setdefault(key, {"label": "", "launch": None})
    for section in ("knob", "led"):
        config[section] = {**DEFAULTS[section], **config.get(section, {})}
    return config


def save_config(path, config):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def find_tool():
    """Locate ch57x-keyboard-tool on the PATH or next to this script."""
    tool = shutil.which(TOOL) or shutil.which(TOOL, path=str(HERE))
    if not tool:
        raise ToolMissing(
            f"{TOOL} was not found. Download it from {TOOL_URL} and put it "
            "on your PATH or in the same folder as macropad.py."
        )
    return tool


def run_tool(*args):
    """Run ch57x-keyboard-tool; return (succeeded, its output)."""
    result = subprocess.run(
        [find_tool(), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def build_device_yaml(config):
    """Translate config.json into the YAML file ch57x-keyboard-tool uploads."""
    knob = config["knob"]
    lines = [f"model: {config['model']}"] if config.get("model") else []
    lines += [
        # The tool counts rows and columns with the knob on the right.
        # 'clockwise' turns that so the knob is at the bottom, matching LAYOUT.
        "orientation: clockwise",
        "rows: 2",
        "columns: 3",
        "knobs: 1",
        "layers:",
        "  - buttons:",
    ]
    for row in LAYOUT:
        lines.append("      - [" + ", ".join(json.dumps(key) for key in row) + "]")
    lines += [
        "    knobs:",
        f"      - ccw: {json.dumps(knob['ccw'])}",
        f"        press: {json.dumps(knob['press'])}",
        f"        cw: {json.dumps(knob['cw'])}",
    ]
    return "\n".join(lines) + "\n"


def flash(config, log=print):
    """Write the key and knob mapping to the pad. Returns the pad model if known."""
    find_tool()
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(build_device_yaml(config))
    try:
        for command in ("validate", "upload"):
            ok, output = run_tool(command, f.name)
            if not ok:
                raise PadError(f"{TOOL} {command} failed:\n{output}")
            # Skip the tool's "add `model:` to your config" warning; we handle that.
            shown = "\n".join(line for line in output.splitlines() if "`model" not in line)
            if shown.strip():
                log(shown)
    finally:
        os.unlink(f.name)
    # When the config has no model yet, the tool's warning names the one it found.
    found = re.search(r"model: ([\w-]+)", output)
    return config.get("model") or (found.group(1) if found else None)


def led_attempts(led, model):
    """The tool's 'led' arguments differ by pad model; list (model, args) to try in order."""
    effect, color = led["effect"], led["color"]
    if effect not in LED_EFFECTS:
        raise PadError(f"Unknown light effect '{effect}'. Choose one of: {', '.join(LED_EFFECTS)}.")
    if color not in LED_COLORS:
        raise PadError(f"Unknown colour '{color}'. Choose one of: {', '.join(LED_COLORS)}.")
    if effect not in ("off", "backlight") and color == "white":
        raise PadError("White only works with the 'backlight' (always on) effect.")
    # Newer pads (ch57x-1): layer 0, then the effect and colour as one argument.
    newer = ["0", effect if effect == "off" else f"{effect} {color}"]
    # Older pads (ch57x-2): just a mode number, no colour.
    older = ["0" if effect == "off" else str(led["mode_number"])]
    if model == "ch57x-2":
        return [("ch57x-2", older)]
    if model:
        return [(model, newer)]
    return [("ch57x-1", newer), ("ch57x-2", older)]


def set_lights(led, model=None, log=print):
    """Apply the light settings. Returns the pad model whose command worked."""
    errors = []
    for candidate, args in led_attempts(led, model):
        ok, output = run_tool("led", *args)
        if ok:
            if output:
                log(output)
            return candidate
        if output not in errors:
            errors.append(output)
    raise PadError("Couldn't set the lights:\n" + "\n".join(errors))


def launch(target):
    """Open a program, file, folder or website. Raises OSError if it can't."""
    if re.match(r"https?://", target):
        webbrowser.open(target)
        return
    path = Path(target).expanduser()
    system = platform.system()
    if system == "Windows":
        if path.exists() or " " not in target:
            os.startfile(target)  # also finds programs by name, like notepad or calc
        else:
            subprocess.Popen(target)  # a program with arguments
    elif system == "Darwin":
        subprocess.Popen(["open", target] if path.exists() else ["open", "-a", target])
    elif path.is_dir() or (path.is_file() and not os.access(path, os.X_OK)):
        subprocess.Popen(["xdg-open", str(path)], start_new_session=True)
    else:
        subprocess.Popen(target, shell=True, start_new_session=True)


def open_key(config, key, log=print):
    """Open whatever config.json assigns to a pad key."""
    target = config["keys"].get(key, {}).get("launch")
    if not target:
        return
    log(f"{key.upper()}: opening {target}")
    try:
        launch(target)
    except OSError as exc:
        log(f"   couldn't open it: {exc}")


def key_name(key):
    """Name of a pynput key ('f13'), allowing for X11's names for F13-F18."""
    return getattr(key, "name", None) or X11_ALIASES.get(getattr(key, "vk", None))


def start_listener(on_key):
    """Call on_key('f13') etc. from a background thread whenever a pad key is pressed."""
    try:
        from pynput import keyboard
    except ImportError as exc:
        raise PadError(f"Listening for keys needs the pynput package (pip install pynput).\n\n{exc}") from exc

    def on_press(key):
        name = key_name(key)
        if name in KEYS:
            on_key(name)

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    return listener


def cmd_flash(args, config):
    if args.dry_run:
        print(build_device_yaml(config), end="")
        return
    config["model"] = flash(config)
    save_config(args.config, config)
    print("Pad programmed. Its keys now send F13-F18; run 'python macropad.py run' to use them.")


def cmd_led(args, config):
    led = config["led"]
    if args.effect:
        led["effect"] = args.effect
    if args.color:
        led["color"] = args.color
    if args.number is not None:
        led["mode_number"] = args.number
    config["model"] = set_lights(led, config["model"])
    save_config(args.config, config)
    print("Lights set.")


def cmd_run(args, config):
    pressed = queue.Queue()
    listener = start_listener(pressed.put)
    print("Listening for macro pad keys (Ctrl+C to stop):")
    for key in KEYS:
        entry = config["keys"][key]
        if entry.get("launch"):
            print(f"  {key.upper():4} {entry.get('label', ''):13} -> {entry['launch']}")
    try:
        while True:
            try:
                # Open things here rather than in the listener's thread, which must stay responsive.
                open_key(config, pressed.get(timeout=0.5))
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        listener.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to config.json")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("flash", help="write key/knob mapping to the pad")
    p.add_argument("--dry-run", action="store_true", help="print the device config instead of uploading")
    p.set_defaults(func=cmd_flash)

    p = sub.add_parser("led", help="set the lights (also saved in config.json)")
    p.add_argument("effect", nargs="?", choices=LED_EFFECTS, help="backlight = always on")
    p.add_argument("color", nargs="?", choices=LED_COLORS, help="white works with backlight only")
    p.add_argument("--number", type=int, help="light mode number for older pads (ch57x-2), which can't pick a colour")
    p.set_defaults(func=cmd_led)

    p = sub.add_parser("run", help="listen for pad keys and open programs")
    p.set_defaults(func=cmd_run)

    args = parser.parse_args()
    try:
        args.func(args, load_config(args.config))
    except PadError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
