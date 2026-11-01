from contextlib import ExitStack
from unittest.mock import patch


class FakeClipboard:
    """Stateful OS boundary: no tests read or write the user's clipboard."""
    def __init__(self, data=None):
        self.data = dict(data or {13: "original"})
        self.sequence = 1
        self.opened = False
        self.owner = None
        self.opener = None
        self.dirty = False

    def OpenClipboard(self, hwnd=0):
        assert not self.opened
        self.opened = True
        self.opener = hwnd

    def CloseClipboard(self):
        assert self.opened
        self.opened = False
        # Windows can advance the sequence when a writing session closes.
        if self.dirty:
            self.sequence += 1
            self.dirty = False

    def EnumClipboardFormats(self, previous):
        assert self.opened
        formats = list(self.data)
        index = formats.index(previous) + 1 if previous else 0
        return formats[index] if index < len(formats) else 0

    def GetClipboardData(self, format):
        assert self.opened
        return self.data[format]

    def EmptyClipboard(self):
        assert self.opened
        self.data.clear()
        self.owner = self.opener
        self.dirty = True
        self.sequence += 1

    def SetClipboardData(self, format, data):
        assert self.opened
        self.data[format] = data
        self.dirty = True
        self.sequence += 1

    def GetClipboardSequenceNumber(self):
        return self.sequence

    def GetClipboardOwner(self):
        return self.owner

    def user_copy(self, data):
        assert not self.opened
        self.data = dict(data)
        self.owner = 999
        self.sequence += 1


def isolate_clipboard(backend):
    stack = ExitStack()
    stack.enter_context(patch("clipboard_guard.clipboard", backend))
    stack.enter_context(patch("clipboard_guard.win32gui.CreateWindowEx", return_value=777))
    stack.enter_context(patch("clipboard_guard.win32gui.DestroyWindow"))
    return stack
