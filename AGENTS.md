# Repository Guidelines

## Project Structure & Module Organization

Voice2Text is a Windows desktop dictation utility using CustomTkinter and faster-whisper. Source modules live at the repository root:

- `Voice2Text.pyw`: application lifecycle, floating controls, tray menu, and UI dispatch.
- `audio_recorder.py`, `transcriber.py`: capture and transcription (CUDA, then Vulkan, then CPU).
- `gpu_engine.py`, `native/`, `build_gpu_engine.py`: Vulkan transcription through a small DLL over whisper.cpp.
- `audio_meter.py`, `ui_controls.py`: compact audio display and image buttons.
- `injector.py`, `clipboard_guard.py`: target tracking and protected insertion. Terminals always get direct Unicode input, because a raw-mode CLI on a classic console receives `Ctrl+V` as byte `0x16`.
- `settings_window.py`, `config.py`: settings, validation, and portable paths.
- `assets/`, `icon.svg`, `icon_generator.py`: editable artwork and generated icons.
- `build_portable.py`: creates the root executable and its `_internal/` directory.

Regression tests live in `tests/`. Runtime models, personal configuration, logs, and generated bundles stay local and must remain ignored.

## Build, Test, and Development Commands

Use Windows PowerShell and Python 3.13, the verified interpreter version.

- `python -m venv .venv`: create the local environment.
- `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`: install runtime and packaging dependencies.
- `.\.venv\Scripts\python.exe Voice2Text.pyw`: run editable sources with console diagnostics.
- `.\Start-Voice2Text.bat`: prefer the root executable, falling back to Python sources.
- `python -m unittest discover -s tests -v`: run regression and hidden GUI tests.
- `python tests/native_clipboard_check.py`: verify native clipboard preservation on a private window station.
- `.\Build-Portable-EXE.bat`: build `Voice2Text.exe` and `_internal/` at the root.
- `.\Build-GPU-Engine.bat`: build `gpu/voice2text_whisper.dll`; needs Visual Studio Build Tools and Git.
- `.\Create-Desktop-Shortcut.ps1`: create the Desktop link with the project icon.

## Coding Style & Naming Conventions

Use four-space indentation, UTF-8, `snake_case` functions/modules, `PascalCase` classes, and uppercase constants. Preserve Romanian interface text. No formatter or linter is configured. Keep Tk operations on the main thread; workers use `_post_ui`. Recording starts only from an explicit user action, never at launch or from the tray icon's default click. Resolve model and log paths relative to the application, never a contributor's home directory.

## Testing Guidelines

Use standard-library `unittest`, `test_*.py` files, and `test_<behavior>` methods. No coverage percentage is enforced. Add focused regressions for bugs and races. Mock microphone capture, network downloads, OS key injection, and interactive clipboard access. Native clipboard checks must remain isolated from the user's desktop.

## Commit & Pull Request Guidelines

The repository starts with an initial import; use concise imperative subjects describing the resulting behavior. PRs should explain the trigger, change, validation commands, and limitations. Link issues and include screenshots for UI changes. Preserve the Apache 2.0 license. Never commit models, recordings, transcriptions, personal configuration, credentials, logs, or generated binaries.
