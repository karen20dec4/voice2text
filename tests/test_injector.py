import os
import threading
import ctypes
import unittest
from unittest.mock import Mock, patch

import pywintypes

from clipboard_fakes import FakeClipboard, isolate_clipboard
import injector


class ClaudeWindowTests(unittest.TestCase):
    # Window owner is process 10; explorer (1) started its shell, which started Claude.
    CONSOLE_WITH_CLAUDE = {1: (0, "explorer.exe"), 10: (1, "pwsh.exe"), 11: (10, "claude.exe")}

    def check(self, processes, window_class="ConsoleWindowClass"):
        with patch("injector._process_table", return_value=processes), patch(
                "injector.win32process.GetWindowThreadProcessId", return_value=(0, 10)), patch(
                "injector.win32gui.GetClassName", return_value=window_class):
            return injector.WindowInjector._hosts_claude(123)

    def test_console_running_claude_code(self):
        self.assertTrue(self.check(self.CONSOLE_WITH_CLAUDE))

    def test_claude_desktop_application(self):
        self.assertTrue(self.check({10: (1, "claude.exe")}, "Chrome_WidgetWin_1"))

    def test_plain_console_is_not_claude(self):
        self.assertFalse(self.check({10: (1, "pwsh.exe"), 20: (1, "pwsh.exe"), 21: (20, "claude.exe")}))

    def test_browser_that_launched_claude_is_not_claude(self):
        self.assertFalse(self.check(self.CONSOLE_WITH_CLAUDE, "MozillaWindowClass"))

    def test_process_loop_ends(self):
        self.assertFalse(self.check({10: (1, "pwsh.exe"), 30: (31, "claude.exe"), 31: (30, "x.exe")}))

    def test_unreadable_processes_read_as_not_claude(self):
        with patch("injector._process_table", side_effect=OSError("denied")), patch(
                "injector.win32process.GetWindowThreadProcessId", return_value=(0, 10)):
            self.assertFalse(injector.WindowInjector._hosts_claude(123))

    def test_answer_is_cached_for_the_same_window(self):
        with patch("injector.threading.Thread"):
            typer = injector.WindowInjector()
        with patch.object(injector.WindowInjector, "_hosts_claude", return_value=True) as hosts:
            self.assertTrue(typer.is_claude_window(5))
            self.assertTrue(typer.is_claude_window(5))
            typer.is_claude_window(6)
        self.assertEqual(hosts.call_count, 2)

    def test_real_process_table_contains_this_process(self):
        self.assertTrue(injector._process_table()[os.getpid()][1].endswith(".exe"))


class InjectorTests(unittest.TestCase):
    def setUp(self):
        with patch("injector.threading.Thread"):
            self.injector = injector.WindowInjector()
        self.injector.last_target_hwnd = 123
        self.user32 = Mock()
        self.user32.GetAsyncKeyState.return_value = 0
        self.clipboard = FakeClipboard()
        stack = isolate_clipboard(self.clipboard)
        self.addCleanup(stack.close)
        self.patches = [
            patch("injector.user32", self.user32),
            patch("injector.win32gui.IsWindow", return_value=True),
            patch("injector.win32gui.GetForegroundWindow", return_value=999),
            patch("injector.time.sleep"),
            patch("injector.win32gui.IsIconic", return_value=False),
            patch("injector.win32gui.GetClassName", return_value="Notepad"),
        ]
        _, self.is_window, self.foreground, self.sleep, self.iconic, self.window_class = [
            p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def _accept_unicode(self):
        typed = []

        def accept_input(count, events, size):
            typed.extend(event.ki.wScan for event in events if not event.ki.dwFlags & 2)
            return count

        self.user32.SendInput.side_effect = accept_input
        return typed

    def test_terminals_get_unicode_input_because_raw_cli_ignores_ctrl_v(self):
        self.foreground.return_value = 123
        typed = self._accept_unicode()
        for window_class in ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"):
            with self.subTest(window_class=window_class):
                typed.clear()
                self.window_class.return_value = window_class
                self.injector.restore_and_inject("țară", add_trailing_space=False, target_hwnd=123)
                self.assertEqual("".join(map(chr, typed)), "țară")
                self.user32.keybd_event.assert_not_called()
                self.assertEqual(self.clipboard.data, {13: "original"})
                self.assertEqual(self.clipboard.sequence, 1)

    def test_auto_enter_in_terminal_follows_typed_text(self):
        self.foreground.return_value = 123
        self.window_class.return_value = "ConsoleWindowClass"
        typed = self._accept_unicode()
        self.injector.restore_and_inject("ok", auto_enter=True, add_trailing_space=False, target_hwnd=123)
        self.assertEqual("".join(map(chr, typed)), "ok")
        self.assertEqual([call.args[0] for call in self.user32.keybd_event.call_args_list], [0x0D, 0x0D])

    def test_unreadable_clipboard_falls_back_to_unicode_input(self):
        self.foreground.return_value = 123
        typed = self._accept_unicode()
        with patch.object(self.clipboard, "OpenClipboard", side_effect=pywintypes.error(5, "Open", "denied")), \
                patch("clipboard_guard.time.sleep"):
            self.injector.restore_and_inject("text", add_trailing_space=False, target_hwnd=123)
        self.assertEqual("".join(map(chr, typed)), "text")

    def test_maximized_target_is_not_restored_to_smaller_size(self):
        self.foreground.return_value = 123
        self.injector.restore_and_inject("text", target_hwnd=123)
        self.user32.ShowWindow.assert_not_called()

    def test_minimized_target_is_restored_before_insertion(self):
        self.foreground.return_value = 123
        self.iconic.return_value = True
        self.injector.restore_and_inject("text", target_hwnd=123)
        self.user32.ShowWindow.assert_called_once_with(123, injector.win32con.SW_RESTORE)

    def test_failed_focus_never_pastes_into_unrelated_window(self):
        with self.assertRaises(RuntimeError):
            self.injector.restore_and_inject("dictated")
        self.user32.keybd_event.assert_not_called()
        self.assertEqual(self.clipboard.data, {13: "original"})

    def test_destroyed_target_never_pastes(self):
        self.is_window.return_value = False
        with self.assertRaises(RuntimeError):
            self.injector.restore_and_inject("dictated")
        self.user32.keybd_event.assert_not_called()

    def test_screenshot_is_preserved_while_unicode_text_is_inserted(self):
        self.foreground.return_value = 123
        screenshot = {2: 12345, 8: b"screenshot DIB", 49300: b"PNG bytes"}
        self.clipboard.user_copy(screenshot)
        original_sequence = self.clipboard.sequence
        down_units = []

        def accept_input(count, events, size):
            self.assertEqual(size, ctypes.sizeof(injector.INPUT))
            self.assertEqual(size, 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
            self.assertEqual(len(events) % 2, 0)
            for index in range(0, len(events), 2):
                self.assertEqual(events[index].ki.dwFlags, 4)
                self.assertEqual(events[index + 1].ki.dwFlags, 6)
                self.assertEqual(events[index].ki.wScan, events[index + 1].ki.wScan)
            for event in events:
                self.assertEqual(event.type, 1)
                self.assertEqual(event.ki.wVk, 0)
                self.assertTrue(event.ki.dwFlags & 4)
                if not event.ki.dwFlags & 2:
                    down_units.append(event.ki.wScan)
            return count

        self.user32.SendInput.side_effect = accept_input
        self.injector.restore_and_inject("Țară 🙂", add_trailing_space=False)
        encoded = b"".join(unit.to_bytes(2, "little") for unit in down_units)
        self.assertEqual(encoded.decode("utf-16-le"), "Țară 🙂")
        self.assertEqual(self.clipboard.data, screenshot)
        self.assertEqual(self.clipboard.sequence, original_sequence)
        self.user32.keybd_event.assert_not_called()

    def test_failed_unicode_insertion_is_reported_without_losing_files(self):
        self.foreground.return_value = 123
        original = {15: ("C:/capture.png",)}
        self.clipboard.user_copy(original)
        self.user32.SendInput.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "introduce textul"):
            self.injector.restore_and_inject("Test", add_trailing_space=False)
        self.assertEqual(self.clipboard.data, original)

    def test_partial_unicode_send_releases_last_key_without_typing_remainder(self):
        self.foreground.return_value = 123
        self.clipboard.user_copy({2: 12345})
        accepted = []
        def accept_one(count, events, size):
            accepted.append((events[0].ki.wScan, events[0].ki.dwFlags))
            return 1
        self.user32.SendInput.side_effect = accept_one
        with self.assertRaises(RuntimeError):
            self.injector.restore_and_inject("Țară", add_trailing_space=False)
        self.assertEqual(accepted, [(ord("Ț"), 4), (ord("Ț"), 6)])

    def test_unicode_chunks_never_split_a_surrogate_pair(self):
        self.foreground.return_value = 123
        self.clipboard.user_copy({2: 12345})
        chunks = []
        def accept_input(count, events, size):
            units = [event.ki.wScan for event in events if not event.ki.dwFlags & 2]
            self.assertFalse(0xD800 <= units[-1] <= 0xDBFF)
            self.assertFalse(0xDC00 <= units[0] <= 0xDFFF)
            chunks.extend(units)
            return count
        self.user32.SendInput.side_effect = accept_input
        text = "a" * 127 + "🙂b"
        self.injector.restore_and_inject(text, add_trailing_space=False)
        self.assertEqual(b"".join(unit.to_bytes(2, "little") for unit in chunks).decode("utf-16-le"), text)

    def test_clipboard_changed_by_user_is_not_overwritten(self):
        self.foreground.return_value = 123

        def user_copies_after_paste(duration):
            if duration == 0.4:
                self.clipboard.user_copy({13: "new user copy"})

        self.sleep.side_effect = user_copies_after_paste
        self.injector.restore_and_inject("dictated", add_trailing_space=False)
        self.assertEqual(self.clipboard.data, {13: "new user copy"})

    def test_explicit_target_does_not_follow_foreground_tracker(self):
        self.injector.last_target_hwnd = 456
        self.user32.SetForegroundWindow.side_effect = lambda hwnd: setattr(self.foreground, "return_value", hwnd)
        self.injector.restore_and_inject("text", target_hwnd=123)
        self.user32.SetForegroundWindow.assert_called_once_with(123)
        self.assertEqual(self.clipboard.data, {13: "original"})

    def test_held_modifier_aborts_without_sending_keys(self):
        self.foreground.return_value = 123
        self.user32.GetAsyncKeyState.return_value = 0x8000
        with self.assertRaises(RuntimeError):
            self.injector.restore_and_inject("text")
        self.user32.keybd_event.assert_not_called()
        self.assertEqual(self.clipboard.data, {13: "original"})

    def test_live_insertion_waits_while_the_user_works_in_another_window(self):
        self.foreground.return_value = 999
        with patch("injector.win32process.GetWindowThreadProcessId", return_value=(0, os.getpid() + 1)):
            self.assertFalse(self.injector.can_insert_now(123))

    def test_live_insertion_proceeds_in_the_target_window(self):
        self.foreground.return_value = 123
        self.assertTrue(self.injector.can_insert_now(123))

    def test_click_on_our_own_panel_does_not_hold_live_text(self):
        self.foreground.return_value = 999
        with patch("injector.win32process.GetWindowThreadProcessId", return_value=(0, os.getpid())):
            self.assertTrue(self.injector.can_insert_now(123))

    def test_live_insertion_waits_for_held_modifiers(self):
        self.foreground.return_value = 123
        self.user32.GetAsyncKeyState.return_value = 0x8000
        self.assertFalse(self.injector.can_insert_now(123))

    def test_unknown_foreground_window_holds_live_text(self):
        self.foreground.return_value = 0
        with patch("injector.win32process.GetWindowThreadProcessId", side_effect=OSError("invalid")):
            self.assertFalse(self.injector.can_insert_now(123))

    def test_enter_alone_closes_a_dictation_already_inserted(self):
        self.foreground.return_value = 123
        self.injector.restore_and_inject("", auto_enter=True, target_hwnd=123)
        self.assertEqual([call.args[0] for call in self.user32.keybd_event.call_args_list], [0x0D, 0x0D])
        self.assertEqual(self.clipboard.data, {13: "original"})
        self.user32.SendInput.assert_not_called()

    def test_empty_text_without_enter_never_touches_the_window(self):
        self.injector.restore_and_inject("", target_hwnd=123)
        self.user32.SetForegroundWindow.assert_not_called()
        self.user32.keybd_event.assert_not_called()

    def test_stop_waits_for_active_injection_cleanup(self):
        finished = threading.Event()
        self.injector._injection_lock.acquire()
        stopping = threading.Thread(target=lambda: (self.injector.stop(), finished.set()))
        stopping.start()
        try:
            self.assertTrue(self.injector._stopped.wait(1))
            self.assertFalse(finished.wait(0.05))
        finally:
            self.injector._injection_lock.release()
            stopping.join(2)
        self.assertTrue(finished.is_set())
