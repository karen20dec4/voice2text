import ctypes
from ctypes import wintypes
import logging
import os
import threading
import time

import win32con
import win32gui
import win32process

from clipboard_guard import ClipboardGuard, UnsupportedClipboardFormat


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", INPUTUNION)]


user32 = ctypes.windll.user32
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


class WindowInjector:
    def __init__(self):
        self.last_target_hwnd = None
        self._target_lock = threading.Lock()
        self._injection_lock = threading.Lock()
        self._stopped = threading.Event()
        self._tracker_thread = threading.Thread(target=self._track_foreground_window, daemon=True)
        self._tracker_thread.start()

    @staticmethod
    def _is_external_window(hwnd):
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        return process_id != os.getpid() and bool(win32gui.GetWindowText(hwnd))

    def get_target_window(self):
        # Capture at dictation start; the tracker may change during inference.
        try:
            hwnd = win32gui.GetForegroundWindow()
            if self._is_external_window(hwnd):
                with self._target_lock:
                    self.last_target_hwnd = hwnd
        except Exception:
            logging.debug("Nu pot identifica fereastra activă", exc_info=True)
        with self._target_lock:
            return self.last_target_hwnd

    def _track_foreground_window(self):
        while not self._stopped.is_set():
            self.get_target_window()
            self._stopped.wait(0.1)

    def stop(self):
        self._stopped.set()
        # The UI must keep the process alive until keys and clipboard are restored.
        with self._injection_lock:
            pass
        self._tracker_thread.join(timeout=0.5)

    def _wait_for_modifiers(self, hwnd):
        for _ in range(50):
            self._check_target(hwnd)
            if not any(user32.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
                return
            time.sleep(0.02)
        raise RuntimeError("Eliberează tastele Shift, Ctrl, Alt și Windows înainte de inserare")

    def _check_target(self, hwnd):
        if self._stopped.is_set():
            raise RuntimeError("Voice2Text se închide")
        if win32gui.GetForegroundWindow() != hwnd:
            raise RuntimeError("Fereastra țintă nu este activă; inserarea a fost anulată")

    def _inject_unicode(self, text, hwnd):
        # Unicode input leaves images/files and all their clipboard formats intact.
        encoded = text.encode("utf-16-le")
        units = [int.from_bytes(encoded[index:index + 2], "little") for index in range(0, len(encoded), 2)]
        start = 0
        while start < len(units):
            self._wait_for_modifiers(hwnd)
            end = min(start + 128, len(units))
            if end < len(units) and 0xD800 <= units[end - 1] <= 0xDBFF:
                end -= 1
            chunk = units[start:end]
            events = (INPUT * (len(chunk) * 2))()
            for index, unit in enumerate(chunk):
                events[index * 2].type = events[index * 2 + 1].type = 1
                events[index * 2].ki = KEYBDINPUT(0, unit, 4, 0, 0)
                events[index * 2 + 1].ki = KEYBDINPUT(0, unit, 4 | 2, 0, 0)
            sent = user32.SendInput(len(events), events, ctypes.sizeof(INPUT))
            if sent != len(events):
                if sent > 0 and sent % 2:
                    release = INPUT(type=1)
                    release.ki = KEYBDINPUT(0, events[sent - 1].ki.wScan, 4 | 2, 0, 0)
                    try:
                        user32.SendInput(1, ctypes.pointer(release), ctypes.sizeof(INPUT))
                    except Exception:
                        logging.warning("Nu pot elibera ultima tastă Unicode", exc_info=True)
                raise RuntimeError("Nu pot introduce textul în fereastra activă; "
                                   "verifică drepturile aplicației și textul deja introdus")
            start = end

    def restore_and_inject(self, text, auto_enter=False, add_trailing_space=True, target_hwnd=None):
        if not text:
            return
        if add_trailing_space and not text.endswith((" ", "\n")):
            text += " "
        with self._injection_lock:
            hwnd = target_hwnd if target_hwnd is not None else self.last_target_hwnd
            if not hwnd or not win32gui.IsWindow(hwnd):
                raise RuntimeError("Fereastra țintă nu mai există")
            if self._stopped.is_set():
                raise RuntimeError("Voice2Text se închide")
            user32.ShowWindow(hwnd, win32con.SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            # Activation can be asynchronous; never paste unless it actually worked.
            for _ in range(10):
                if win32gui.GetForegroundWindow() == hwnd:
                    break
                time.sleep(0.02)
            self._check_target(hwnd)
            self._wait_for_modifiers(hwnd)

            try:
                with ClipboardGuard(text) as clipboard_guard:
                    try:
                        time.sleep(0.04)
                        self._check_target(hwnd)
                        clipboard_guard.ensure_unchanged()
                        try:
                            user32.keybd_event(0x11, 0, 0, 0)
                            user32.keybd_event(0x56, 0, 0, 0)
                            time.sleep(0.02)
                        finally:
                            user32.keybd_event(0x56, 0, 2, 0)
                            user32.keybd_event(0x11, 0, 2, 0)
                    finally:
                        time.sleep(0.4)
            except UnsupportedClipboardFormat:
                logging.info("Inserare Unicode directă; clipboardul este păstrat intact")
                self._inject_unicode(text, hwnd)
            if auto_enter:
                time.sleep(0.04)
                self._check_target(hwnd)
                self._wait_for_modifiers(hwnd)
                try:
                    user32.keybd_event(0x0D, 0, 0, 0)
                finally:
                    user32.keybd_event(0x0D, 0, 2, 0)
