"""Run separately on Windows: python tests/native_clipboard_check.py.

Creates a private window station and desktop before touching the clipboard.
The interactive user's clipboard is never read or modified.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import struct


def main():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateWindowStationW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user32.CreateWindowStationW.restype = wintypes.HANDLE
    user32.SetProcessWindowStation.argtypes = [wintypes.HANDLE]
    user32.SetProcessWindowStation.restype = wintypes.BOOL
    user32.CreateDesktopW.argtypes = [wintypes.LPWSTR, wintypes.LPWSTR, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    user32.SetThreadDesktop.restype = wintypes.BOOL
    station = user32.CreateWindowStationW(None, 0, 0x37F, None)  # WINSTA_ALL_ACCESS
    if not station or not user32.SetProcessWindowStation(station):
        raise ctypes.WinError(ctypes.get_last_error())
    desktop = user32.CreateDesktopW("Voice2TextAudit", None, None, 0, 0x01FF, None)
    if not desktop or not user32.SetThreadDesktop(desktop):
        raise ctypes.WinError(ctypes.get_last_error())

    # All clipboard access below is confined to the new noninteractive station.
    import win32clipboard as clipboard
    import win32con
    import win32gui

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from clipboard_guard import ClipboardGuard

    owner = win32gui.CreateWindowEx(0, "STATIC", "audit owner", 0, 0, 0, 0, 0,
                                    win32con.HWND_MESSAGE, 0, 0, None)
    rich_format = clipboard.RegisterClipboardFormat("Voice2Text audit rich text")
    clipboard.OpenClipboard(owner)
    try:
        clipboard.EmptyClipboard()
        clipboard.SetClipboardData(13, "Original șțâîă")
        clipboard.SetClipboardData(rich_format, b"<p>original</p>\x00")
    finally:
        clipboard.CloseClipboard()
    with ClipboardGuard("Dictated ășț") as guard:
        guard.ensure_unchanged()
        clipboard.OpenClipboard(owner)
        try:
            assert clipboard.GetClipboardData(13) == "Dictated ășț"
        finally:
            clipboard.CloseClipboard()
    clipboard.OpenClipboard(owner)
    try:
        assert clipboard.GetClipboardData(13) == "Original șțâîă"
        assert clipboard.GetClipboardData(rich_format).startswith(b"<p>original</p>")
    finally:
        clipboard.CloseClipboard()

    # Reproduce Print Screen using an actual DIB/bitmap on this private station.
    # SendInput itself is replaced: this test never sends real keyboard input.
    from unittest.mock import Mock, patch
    import injector

    dib = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 32, 0, 16, 0, 0, 0, 0) + bytes([40, 80, 120, 255]) * 4
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
    gdi32.CreateBitmap.restype = wintypes.HBITMAP
    pixels = ctypes.create_string_buffer(bytes([40, 80, 120, 255]) * 4)
    clipboard.OpenClipboard(owner)
    try:
        clipboard.EmptyClipboard()
        bitmap = gdi32.CreateBitmap(2, 2, 1, 32, pixels)
        if not bitmap:
            raise ctypes.WinError(ctypes.get_last_error())
        clipboard.SetClipboardData(win32con.CF_BITMAP, bitmap)
        clipboard.SetClipboardData(win32con.CF_DIB, dib)
        assert clipboard.IsClipboardFormatAvailable(win32con.CF_BITMAP)
        clipboard.GetClipboardDataHandle(win32con.CF_BITMAP)
        original_image = clipboard.GetClipboardData(win32con.CF_DIB)
    finally:
        clipboard.CloseClipboard()
    units = []
    def accept_input(count, events, size):
        units.extend(event.ki.wScan for event in events if not event.ki.dwFlags & 2)
        return count
    fake_user32 = Mock()
    fake_user32.GetAsyncKeyState.return_value = 0
    fake_user32.SendInput.side_effect = accept_input
    with patch("injector.threading.Thread"):
        typer = injector.WindowInjector()
    typer.last_target_hwnd = owner
    with patch("injector.user32", fake_user32), patch("injector.win32gui.GetForegroundWindow", return_value=owner), patch("injector.time.sleep"):
        typer.restore_and_inject("Țară și captură", add_trailing_space=False)
    actual_text = b"".join(unit.to_bytes(2, "little") for unit in units).decode("utf-16-le")
    assert actual_text == "Țară și captură"
    clipboard.OpenClipboard(owner)
    try:
        assert clipboard.GetClipboardData(win32con.CF_DIB) == original_image
        assert clipboard.IsClipboardFormatAvailable(win32con.CF_BITMAP)
    finally:
        clipboard.CloseClipboard()
        win32gui.DestroyWindow(owner)
    print("Native clipboard checks passed: rich text and Print Screen bitmap preserved on private station.")


if __name__ == "__main__":
    main()
