# Macro pad controller

A small Python script for the generic 6-key + knob USB‑C macro pad.

## How it works

1. **`flash`** programs the pad so each key sends an extra function key (F13–F18).
   Normal keyboards don't have these keys, so they never clash with anything.
   The knob is set to volume down / mute / volume up.
2. **`run`** stays in the background, watches for F13–F18 and opens the program,
   file, folder or website you chose in `config.json`.
3. **`led`** sets the backlight mode and colour.

## Setup

```bash
pip install pynput
```

For `flash` and `led`, install
[ch57x-keyboard-tool](https://github.com/kriomant/ch57x-keyboard-tool/releases)
and make sure it's on your PATH. It talks to the pad over USB.
On Windows you may need to follow its README's driver notes; on Linux you may need `sudo`
or a udev rule.

## Usage

Edit `config.json`, then:

```bash
python macropad.py flash --dry-run   # preview what will be written
python macropad.py flash             # program the pad (one time)
python macropad.py led 1 cyan        # set the backlight (0 = off)
python macropad.py run               # start opening programs on key press
```

Examples for `"launch"`:

| Windows                                   | macOS             | Linux        |
|-------------------------------------------|-------------------|--------------|
| `notepad`, `calc`, `explorer`             | `Safari`, `Notes` | `firefox`    |
| `"C:\\Program Files\\App\\app.exe"`       | `Calculator`      | `gnome-calculator` |
| `https://...` (opens in your browser)     | `https://...`     | `https://...` |

To start the listener with your computer, add `python macropad.py run` to your
startup apps (Windows: put a shortcut in `shell:startup`).

## Limits

- These pads light the whole board with one mode/colour; there is no per-key colour
  control. Which modes and colours work depends on the chip; `ch57x-keyboard-tool led --help`
  lists what yours supports. Some versions of this pad have no LEDs at all.
- If `flash` can't find the pad, it may use a different chip. The vendor's
  "MINI KEYBOARD" app can do the same job: map the keys to F13–F18 there and
  `run` will still work.
