"""Global shortcut through RegisterHotKey.

A low-level keyboard hook runs Python for every key in the system; Windows
silently removes such a hook once it misses LowLevelHooksTimeout, which left
F9 dead until restart. WM_HOTKEY needs no timely answer, so it cannot expire.
"""
import ctypes
from ctypes import wintypes
import logging
import threading

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short
kernel32 = ctypes.WinDLL("kernel32")
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

MODIFIERS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8, "windows": 0x8}
NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "insert": 0x2D, "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23,
    "page up": 0x21, "pageup": 0x21, "page down": 0x22, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "pause": 0x13, "scroll lock": 0x91, "caps lock": 0x14, "num lock": 0x90,
    **{f"f{number}": 0x6F + number for number in range(1, 25)},
}


def parse_hotkey(text):
    """Return (modifiers, virtual key) for "f9", "ctrl+alt+space", ...; ValueError if invalid."""
    if not isinstance(text, str) or "," in text:
        raise ValueError("Shortcutul trebuie să fie o singură combinație, de ex. f9 sau ctrl+alt+space")
    modifiers, keys = 0, []
    for part in text.lower().split("+"):
        name = " ".join(part.split())
        if name in MODIFIERS:
            modifiers |= MODIFIERS[name]
        elif name:
            keys.append(name)
    if len(keys) != 1:
        raise ValueError(f"Shortcut invalid: {text!r}; folosește o singură tastă, cu modificatori opționali")
    key = keys[0]
    if key in NAMED_KEYS:
        return modifiers, NAMED_KEYS[key]
    if len(key) == 1:
        scan = user32.VkKeyScanW(key)
        # The high byte holds the shift state the character needs on this layout.
        if scan != -1 and not scan & 0xFF00:
            return modifiers, scan & 0xFF
    raise ValueError(f"Tastă necunoscută în shortcut: {key!r}")


class GlobalHotkey:
    """One registered shortcut; its callback runs on the hotkey's own thread."""

    def __init__(self, text, callback):
        self.modifiers, self.vk = parse_hotkey(text)
        self._callback = callback
        self._ready = threading.Event()
        self._error = None
        self._thread_id = None
        self._thread = threading.Thread(target=self._run, name="voice2text-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error:
            self._thread.join()
            raise self._error

    def _run(self):
        message = wintypes.MSG()
        # The queue must exist before stop() can post WM_QUIT to this thread.
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, self.modifiers | MOD_NOREPEAT, self.vk):
            code = ctypes.get_last_error()
            if code == ERROR_HOTKEY_ALREADY_REGISTERED:
                self._error = OSError(code, "Shortcutul este deja folosit de altă aplicație")
            else:
                self._error = ctypes.WinError(code)
            self._ready.set()
            return
        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY:
                    # An exception here would end the loop and the shortcut with it.
                    try:
                        self._callback()
                    except Exception:
                        logging.exception("Eroare în handlerul shortcutului")
        finally:
            user32.UnregisterHotKey(None, 1)

    def same_keys(self, text):
        try:
            return parse_hotkey(text) == (self.modifiers, self.vk)
        except ValueError:
            return False

    def stop(self):
        if self._thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=1)
