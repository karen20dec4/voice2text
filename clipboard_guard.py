from contextlib import contextmanager
import logging
import time

import pywintypes
import win32clipboard as clipboard
import win32con
import win32gui


class UnsupportedClipboardFormat(RuntimeError):
    """The clipboard cannot be cloned safely; callers may type without changing it."""


class ClipboardGuard:
    """Temporarily replace supported clipboard formats without losing newer copies."""
    # These formats contain handles or structured data, not reusable byte buffers.
    _UNSUPPORTED = {2, 3, 9, 14, 15, 0x80, 0x82, 0x83, 0x8E}

    def __init__(self, text):
        self.text = text
        self.original = {}
        self.sequence = None
        self.hwnd = None

    @contextmanager
    def _open(self):
        for attempt in range(20):
            try:
                clipboard.OpenClipboard(self.hwnd)
                break
            except pywintypes.error:
                if attempt == 19:
                    raise
                time.sleep(0.01)
        try:
            yield
        finally:
            clipboard.CloseClipboard()

    def _restore(self):
        clipboard.EmptyClipboard()
        for format, data in self.original.items():
            clipboard.SetClipboardData(format, data)

    def __enter__(self):
        # Clipboard writes need an owning HWND. A message-only window never appears.
        self.hwnd = win32gui.CreateWindowEx(0, "STATIC", "Voice2Text clipboard", 0,
                                           0, 0, 0, 0, win32con.HWND_MESSAGE, 0, 0, None)
        try:
            with self._open():
                format = clipboard.EnumClipboardFormats(0)
                while format:
                    if format in self._UNSUPPORTED or 0x200 <= format <= 0x3FF:
                        raise UnsupportedClipboardFormat("Clipboardul trebuie păstrat fără modificări")
                    data = clipboard.GetClipboardData(format)
                    if not isinstance(data, (str, bytes)):
                        raise UnsupportedClipboardFormat("Clipboardul trebuie păstrat fără modificări")
                    self.original[format] = data
                    format = clipboard.EnumClipboardFormats(format)
                try:
                    clipboard.EmptyClipboard()
                    clipboard.SetClipboardData(win32con.CF_UNICODETEXT, self.text)
                except Exception:
                    self._restore()
                    raise
            # Windows may advance this counter on CloseClipboard after a write.
            self.sequence = clipboard.GetClipboardSequenceNumber()
            return self
        except pywintypes.error as error:
            # Busy or unreadable clipboard: nothing was pasted, so typing is safe.
            win32gui.DestroyWindow(self.hwnd)
            raise UnsupportedClipboardFormat("Clipboardul nu poate fi accesat") from error
        except Exception:
            win32gui.DestroyWindow(self.hwnd)
            raise

    def ensure_unchanged(self):
        with self._open():
            if (clipboard.GetClipboardSequenceNumber() != self.sequence
                    or clipboard.GetClipboardOwner() != self.hwnd
                    or clipboard.GetClipboardData(win32con.CF_UNICODETEXT) != self.text):
                raise RuntimeError("Clipboardul s-a modificat; inserarea a fost anulată")

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            with self._open():
                # Both the ownership check and restore happen under the OS lock.
                if (clipboard.GetClipboardSequenceNumber() == self.sequence
                        and clipboard.GetClipboardOwner() == self.hwnd):
                    self._restore()
        except Exception:
            logging.warning("Nu pot restaura clipboard-ul", exc_info=True)
        finally:
            win32gui.DestroyWindow(self.hwnd)
