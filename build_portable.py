"""Build the Windows bundle and place Voice2Text.exe at the project root."""
from pathlib import Path
import shutil
import subprocess
import sys

import win32api
import win32con
import win32event
import winerror


def main():
    root = Path(__file__).resolve().parent
    try:
        handle = win32event.OpenMutex(win32con.SYNCHRONIZE, False, "Local\\Voice2Text")
    except Exception as error:
        if getattr(error, "winerror", None) != winerror.ERROR_FILE_NOT_FOUND:
            raise
    else:
        win32api.CloseHandle(handle)
        raise RuntimeError("Închide Voice2Text înainte de a regenera executabilul")

    stage = root / ".build"
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--noconsole", "--onedir",
        "--name", "Voice2Text", "--icon", str(root / "icon.ico"),
        "--add-data", f"{root / 'icon.png'};.", "--add-data", f"{root / 'icon.ico'};.",
        "--add-data", f"{root / 'assets'};assets", "--collect-data", "customtkinter",
        "--collect-data", "faster_whisper", "--collect-binaries", "ctranslate2",
        "--exclude-module", "ctranslate2.converters", "--exclude-module", "ctranslate2.specs",
        "--exclude-module", "torch", "--exclude-module", "transformers",
        "--distpath", str(stage / "dist"), "--workpath", str(stage / "work"),
        "--specpath", str(stage), str(root / "Voice2Text.pyw"),
    ]
    subprocess.run(command, cwd=root, check=True)
    bundle = stage / "dist" / "Voice2Text"
    # Recheck after compilation and reserve the application's instance name
    # throughout installation, so it cannot start midway through the copy.
    installation = win32event.CreateMutex(None, False, "Local\\Voice2Text")
    try:
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            raise RuntimeError("Voice2Text a pornit în timpul compilării; închide aplicația și reia buildul")
        shutil.copytree(bundle / "_internal", root / "_internal", dirs_exist_ok=True)
        shutil.copy2(bundle / "Voice2Text.exe", root / "Voice2Text.exe")
    finally:
        win32api.CloseHandle(installation)
    print(f"Executabil pregătit: {root / 'Voice2Text.exe'}")
    print("Păstrează _internal lângă executabil; modelele sunt în models.")


if __name__ == "__main__":
    main()
