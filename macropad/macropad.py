#!/usr/bin/env python3
"""Simple controller for the generic 6-key + 1-knob USB macro pad.

These pads (CH552/CH57x chip, USB ID 1189:8890 or similar) store their
key mapping and LED setting on the device itself. This script:

  flash  - writes the key/knob mapping from config.json to the pad
  led    - sets the backlight mode/colour
  run    - listens for the pad's keys (F13-F18) and opens programs

flash and led use ch57x-keyboard-tool (https://github.com/kriomant/ch57x-keyboard-tool)
to talk to the pad. run only needs the pynput package.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "config.json"
TOOL = "ch57x-keyboard-tool"

# Physical layout of the pad, top to bottom, left to right.
LAYOUT = [["f13", "f14"], ["f15", "f16"], ["f17", "f18"]]


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_tool():
    tool = shutil.which(TOOL)
    if not tool:
        sys.exit(
            f"'{TOOL}' was not found on your PATH.\n"
            "Install it from https://github.com/kriomant/ch57x-keyboard-tool/releases\n"
            "(or: cargo install ch57x-keyboard-tool) and try again."
        )
    return tool


def build_device_yaml(config):
    """Translate config.json into the YAML layout ch57x-keyboard-tool expects."""
    knob = config.get("knob", {})
    lines = [
        "orientation: normal",
        f"rows: {len(LAYOUT)}",
        f"columns: {len(LAYOUT[0])}",
        "knobs: 1",
        "layers:",
        "  - buttons:",
    ]
    for row in LAYOUT:
        lines.append("      - [" + ", ".join(f'"{k}"' for k in row) + "]")
    lines += [
        "    knobs:",
        f'      - ccw: "{knob.get("ccw", "volumedown")}"',
        f'        press: "{knob.get("press", "mute")}"',
        f'        cw: "{knob.get("cw", "volumeup")}"',
    ]
    return "\n".join(lines) + "\n"


def cmd_flash(args):
    config = load_config(args.config)
    yaml_text = build_device_yaml(config)
    if args.dry_run:
        print(yaml_text)
        return
    tool = find_tool()
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_text)
        yaml_path = f.name
    try:
        subprocess.run([tool, "validate", yaml_path], check=True)
        subprocess.run([tool, "upload", yaml_path], check=True)
    finally:
        os.unlink(yaml_path)
    print("Pad programmed. Keys now send F13-F18; run 'python macropad.py run' to use them.")


def cmd_led(args):
    config = load_config(args.config)
    led = config.get("led", {})
    mode = args.mode if args.mode is not None else led.get("mode", 1)
    color = args.color if args.color is not None else led.get("color")
    command = [find_tool(), "led", str(mode)]
    if color:
        command.append(color)
    print("Running:", " ".join(command))
    result = subprocess.run(command)
    if result.returncode != 0:
        print(
            "\nThe LED command was rejected. Supported modes/colours depend on your pad's chip;\n"
            f"run '{TOOL} led --help' to see what yours accepts."
        )
        sys.exit(result.returncode)


def launch(target):
    """Open a program, file, folder or URL."""
    print(f"-> opening {target}")
    if target.startswith(("http://", "https://")):
        webbrowser.open(target)
        return
    system = platform.system()
    if system == "Windows":
        # 'start' handles both program names (notepad) and file paths.
        subprocess.Popen(f'start "" "{target}"', shell=True)
    elif system == "Darwin":
        if Path(target).exists():
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["open", "-a", target])
    else:
        subprocess.Popen(target, shell=True, start_new_session=True)


def cmd_run(args):
    try:
        from pynput import keyboard
    except ImportError:
        sys.exit("The 'run' command needs pynput: pip install pynput")

    config = load_config(args.config)
    actions = {k: v.get("launch") for k, v in config["keys"].items() if v.get("launch")}

    def on_press(key):
        name = getattr(key, "name", None)  # e.g. "f13"
        if name in actions:
            try:
                launch(actions[name])
            except Exception as exc:  # keep listening even if one launch fails
                print(f"   failed: {exc}")

    print("Listening for macro pad keys (Ctrl+C to stop):")
    for key, target in actions.items():
        label = config["keys"][key].get("label", "")
        print(f"  {key.upper():4} {label:13} -> {target}")
    with keyboard.Listener(on_press=on_press) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="path to config.json")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("flash", help="write key/knob mapping to the pad")
    p.add_argument("--dry-run", action="store_true", help="print the device config instead of uploading")
    p.set_defaults(func=cmd_flash)

    p = sub.add_parser("led", help="set backlight mode and colour")
    p.add_argument("mode", nargs="?", type=int, help="LED mode number (0 = off)")
    p.add_argument("color", nargs="?", help="e.g. red, orange, yellow, green, cyan, blue, purple")
    p.set_defaults(func=cmd_led)

    p = sub.add_parser("run", help="listen for pad keys and open programs")
    p.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
