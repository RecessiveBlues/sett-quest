# Macro pad controller

Set up the generic 6-key + knob USB‑C macro pad: choose what each key opens,
what the knob does, and the light colour.

## How it works

1. **Send to pad** programs the pad so each key sends an extra function key (F13–F18).
   Normal keyboards don't have these keys, so they never clash with anything.
   The knob is programmed directly (volume, media keys and so on) and works on its own.
2. **Listening** watches for F13–F18 and opens the program, file, folder or
   website you chose for that key.

## Setup

1. Install Python 3.9 or newer. On Windows, get it from [python.org](https://www.python.org/downloads/)
   and tick "Add python.exe to PATH". On Linux, also install `python3-tk`.
2. `pip install pynput`
3. Download [ch57x-keyboard-tool](https://github.com/kriomant/ch57x-keyboard-tool/releases)
   and put it in this folder (or anywhere on your PATH). It sends the settings to the pad over USB.
   - Windows: it also needs [UsbDk](https://github.com/daynix/UsbDk/releases) installed.
   - Linux: run with `sudo`, or add the udev rule from the tool's README.

## The window

```bash
python macropad_gui.py
```

On Windows you can also double-click `macropad_gui.py`. Rename it to `macropad_gui.pyw`
to stop a console window opening alongside it.

- Click a key in the picture, give it a name, and choose what it opens:
  a program (`notepad`, `calc`), a file or folder (**Choose file…** / **Choose folder…**),
  or a website. **Try it** opens it straight away.
- Pick what turning and pressing the knob does.
- Pick a light effect and colour. **Apply lights** changes only the lights.
- **Send to pad** saves everything to the pad. The first time, it also works out your
  pad type and remembers it.
- **Start listening** makes the keys open things while the window is open.

Settings are kept in `config.json` next to the scripts.

## Without the window

```bash
python macropad.py flash --dry-run    # preview what will be written to the pad
python macropad.py flash              # program the keys and knob
python macropad.py led backlight red  # lights: off, backlight, press, shock or shock2
python macropad.py led --number 2     # older pads that can't pick a colour use a mode number
python macropad.py run                # open programs when the pad's keys are pressed
```

To have the keys work whenever you're logged in, start `python macropad.py run` with your
computer (Windows: put a shortcut to it in `shell:startup`).

## Limits

- The lights cover the whole pad; you can't give each key its own colour.
  Newer pads (type ch57x-1) can pick a colour. Older ones (ch57x-2, USB ID 1189:8890) only
  take a mode number, so try a few numbers to find a pattern you like. Some pads have no lights.
- On macOS, listening needs Accessibility permission for your terminal or Python
  (System Settings → Privacy & Security → Accessibility).
- If the pad isn't found, it may use a chip the tool doesn't support. The maker's
  "MINI KEYBOARD" app can do the same job: map the keys to F13–F18 there, and
  listening will still work.
