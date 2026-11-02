import threading
import unittest

import hotkey

# Unusual combinations, so the tests never collide with a real shortcut.
TEST_HOTKEY = "ctrl+alt+shift+f23"


class ParseHotkeyTests(unittest.TestCase):
    def test_named_keys_and_modifiers(self):
        self.assertEqual(hotkey.parse_hotkey("f9"), (0, 0x78))
        self.assertEqual(hotkey.parse_hotkey("ctrl+alt+space"), (0x2 | 0x1, 0x20))
        self.assertEqual(hotkey.parse_hotkey(" Control + Shift + Page Down "), (0x2 | 0x4, 0x22))
        self.assertEqual(hotkey.parse_hotkey("win+f24"), (0x8, 0x87))

    def test_letter_uses_its_virtual_key(self):
        self.assertEqual(hotkey.parse_hotkey("alt+d"), (0x1, ord("D")))

    def test_invalid_shortcuts_are_rejected(self):
        for text in ("", "ctrl", "ctrl+a+b", "not-a-real-key", "f25", "ctrl+a, b", None):
            with self.subTest(text=text), self.assertRaises(ValueError):
                hotkey.parse_hotkey(text)


class GlobalHotkeyTests(unittest.TestCase):
    def post_hotkey(self, binding):
        hotkey.user32.PostThreadMessageW(binding._thread_id, hotkey.WM_HOTKEY, 1, 0)

    def test_hotkey_message_runs_callback_on_its_thread(self):
        fired = threading.Event()
        binding = hotkey.GlobalHotkey(TEST_HOTKEY, fired.set)
        self.addCleanup(binding.stop)
        self.post_hotkey(binding)
        self.assertTrue(fired.wait(2))

    def test_callback_error_does_not_end_the_shortcut(self):
        calls = []

        def callback():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")

        binding = hotkey.GlobalHotkey(TEST_HOTKEY, callback)
        self.addCleanup(binding.stop)
        with self.assertLogs(level="ERROR"):
            self.post_hotkey(binding)
            binding._thread.join(0.3)
        self.post_hotkey(binding)
        binding._thread.join(0.3)
        self.assertEqual(len(calls), 2)
        self.assertTrue(binding._thread.is_alive())

    def test_taken_shortcut_raises_and_stop_releases_it(self):
        first = hotkey.GlobalHotkey(TEST_HOTKEY, lambda: None)
        with self.assertRaises(OSError):
            hotkey.GlobalHotkey(TEST_HOTKEY, lambda: None)
        first.stop()
        self.assertFalse(first._thread.is_alive())
        second = hotkey.GlobalHotkey(TEST_HOTKEY, lambda: None)
        second.stop()

    def test_same_keys_ignores_spelling(self):
        binding = hotkey.GlobalHotkey(TEST_HOTKEY, lambda: None)
        self.addCleanup(binding.stop)
        self.assertTrue(binding.same_keys("Shift+Control+Alt+F23"))
        self.assertFalse(binding.same_keys("f23"))
        self.assertFalse(binding.same_keys("bogus"))


if __name__ == "__main__":
    unittest.main()
