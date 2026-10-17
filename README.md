# Diablo IV Toolkit

Diablo IV Toolkit is a Windows desktop utility designed for Diablo IV players who want more control over the gameplay experience without modifying the game through normal in-game menus alone. The project combines two practical tools in one interface:

- an AutoKey macro system that repeatedly sends selected keys at a configurable interval
- a camera patching tool that connects to the Diablo IV process and adjusts camera values such as FOV, zoom, height, angle, and fog

The application is built with Python and Tkinter and is focused on Windows use, where it interacts with the Diablo IV window and process memory.

## What the project does

### 1. AutoKey macro tool

The AutoKey feature lets you configure up to four keys to be spammed automatically. You can:

- choose which keys to repeat
- set the repeat interval from 100 ms up to 5000 ms
- define a toggle hotkey to turn the macro on and off
- save the current configuration for later use

This is useful for repetitive gameplay actions where repeating a key press is easier than manual input.

### 2. Camera control and memory patching

The camera system connects to the running Diablo IV process and searches memory for known camera-related values. Once attached, it can:

- read the active camera configuration
- apply a patch to update values such as FOV, Zoom, Height, Angle, and Fog
- adjust these values through sliders or predefined presets
- save and restore named preset configurations

Included presets include Close, Medium, and Far camera styles, making it easy to switch framing quickly without manually tuning every value.

## Features

- Windows-only desktop UI
- Keyboard hotkey toggle for the AutoKey macro
- Four configurable key slots
- Adjustable repeat timing
- Game-process detection and connection
- Memory scanning and patching for Diablo IV camera values
- Preset-based camera profiles
- Manual camera tuning controls

## Project structure

- `main.py` — application entry point
- `core/autokey.py` — hotkey automation service
- `core/camera_patcher.py` — process memory scanning and camera patching logic
- `gui/app_window.py` — Tkinter-based interface
- `core/DiabloCameraPresets.json` — saved camera preset definitions
- `assets/` — fonts, images, and bundled resources

## Requirements

This project targets Windows systems and depends on the following:

- Windows 10 or newer
- Diablo IV running in a visible window
- Python 3.x
- `psutil`
- `keyboard`
- `pywin32`

If you are building the app into an executable, the repository also includes a PyInstaller specification file (`Diablo4Toolkit.spec`).

## Getting started

1. Install the required Python dependencies:

   ```bash
   pip install psutil keyboard pywin32
   ```

2. Start Diablo IV.

3. Run the toolkit:

   ```bash
   python main.py
   ```

4. In the application UI:
   - configure the AutoKey macro on the AutoKey tab
   - connect to the running Diablo IV process on the Camera tab
   - adjust camera values or apply a preset

## Notes

This project is designed for personal customization and experimentation. It interacts directly with operating-system input and the Diablo IV process memory, so it should be used carefully and only in environments where it is permitted.

The toolkit is not an official Blizzard product and is intended as a community utility for personal use.
