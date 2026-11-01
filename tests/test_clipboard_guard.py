import unittest
from unittest.mock import patch

import pywintypes

from clipboard_fakes import FakeClipboard, isolate_clipboard
from clipboard_guard import ClipboardGuard, UnsupportedClipboardFormat


class ClipboardTests(unittest.TestCase):
    def test_restores_text_and_rich_formats(self):
        original = {13: "Original", 49300: b"{\\rtf1 Original}", 49301: b"<p>Original</p>"}
        backend = FakeClipboard(original)
        with isolate_clipboard(backend):
            with ClipboardGuard("dictated") as guard:
                self.assertEqual(backend.data, {13: "dictated"})
                guard.ensure_unchanged()
            self.assertEqual(backend.data, original)
        self.assertFalse(backend.opened)

    def test_new_user_copy_survives_restore(self):
        backend = FakeClipboard()
        with isolate_clipboard(backend), ClipboardGuard("dictated"):
            backend.user_copy({13: "New copy", 49300: b"new rich text"})
        self.assertEqual(backend.data, {13: "New copy", 49300: b"new rich text"})

    def test_unsupported_image_or_file_format_is_left_untouched(self):
        for original in ({2: 12345}, {15: ("C:/example.txt",)}, {49300: object()}):
            with self.subTest(formats=list(original)):
                backend = FakeClipboard(original)
                with isolate_clipboard(backend), self.assertRaises(RuntimeError):
                    with ClipboardGuard("dictated"):
                        self.fail("Unsupported clipboard format must abort before pasting")
                self.assertEqual(backend.data, original)
                self.assertFalse(backend.opened)

    def test_busy_clipboard_is_reported_as_unsupported_without_pasting(self):
        backend = FakeClipboard()
        error = pywintypes.error(5, "OpenClipboard", "Access is denied.")
        with isolate_clipboard(backend), patch("clipboard_guard.time.sleep"), patch.object(
                backend, "OpenClipboard", side_effect=error):
            with self.assertRaises(UnsupportedClipboardFormat):
                with ClipboardGuard("dictated"):
                    self.fail("A busy clipboard must abort before pasting")
        self.assertEqual(backend.data, {13: "original"})

    def test_failed_replacement_rolls_back_all_formats(self):
        original = {13: "Original", 49300: b"rich"}
        backend = FakeClipboard(original)
        real_set = backend.SetClipboardData

        def fail_dictated(format, data):
            if data == "dictated":
                raise OSError("write failed")
            real_set(format, data)

        with isolate_clipboard(backend), patch.object(backend, "SetClipboardData", side_effect=fail_dictated):
            with self.assertRaises(OSError):
                with ClipboardGuard("dictated"):
                    self.fail("Failed write must abort")
        self.assertEqual(backend.data, original)

    def test_changed_clipboard_before_paste_aborts(self):
        backend = FakeClipboard()
        with isolate_clipboard(backend), ClipboardGuard("dictated") as guard:
            backend.user_copy({13: "User copy"})
            with self.assertRaises(RuntimeError):
                guard.ensure_unchanged()
        self.assertEqual(backend.data, {13: "User copy"})
