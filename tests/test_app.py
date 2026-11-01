from collections import deque
import importlib.machinery
import importlib.util
from pathlib import Path
import queue
import threading
import unittest
from unittest.mock import Mock, patch


loader = importlib.machinery.SourceFileLoader("voice2text_app", str(Path(__file__).resolve().parents[1] / "Voice2Text.pyw"))
spec = importlib.util.spec_from_loader(loader.name, loader)
app_module = importlib.util.module_from_spec(spec)
loader.exec_module(app_module)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.Voice2TextApp.__new__(app_module.Voice2TextApp)
        self.app.root = Mock()
        self.app.btn_dictate = Mock()
        self.app.audio_meter = Mock()
        self.app._ui_queue = queue.Queue()
        self.app._closing = threading.Event()
        self.app.is_recording = False
        self.app.is_processing = False
        self.app.current_hotkey = None
        self.app.config = {"hotkey": "f9"}
        self.app.recent_texts = deque(maxlen=app_module.RECENT_TEXTS)
        self.app._outside_claude = False
        self.app._recording_target = None
        self.app.pill_frame = Mock()
        self.app.injector = Mock()

    def panel_color(self):
        return self.app.pill_frame.configure.call_args.kwargs["fg_color"]

    def test_panel_turns_violet_outside_claude_and_back(self):
        self.app.injector.last_target_hwnd = 5
        self.app.injector.is_claude_window.return_value = False
        self.app._refresh_panel_color()
        self.assertEqual(self.panel_color(), app_module.PANEL_COLORS[True][0])
        self.app.injector.is_claude_window.return_value = True
        self.app._refresh_panel_color()
        self.assertEqual(self.panel_color(), app_module.PANEL_COLORS[False][0])

    def test_unchanged_target_does_not_redraw_the_panel(self):
        self.app.injector.last_target_hwnd = 5
        self.app.injector.is_claude_window.return_value = True
        self.app._refresh_panel_color()
        self.app.pill_frame.configure.assert_not_called()

    def test_no_target_keeps_the_normal_panel(self):
        self.app.injector.last_target_hwnd = None
        self.app._refresh_panel_color()
        self.app.pill_frame.configure.assert_not_called()

    def test_running_dictation_shows_its_own_target(self):
        self.app.is_recording = True
        self.app._recording_target = 7
        self.app.injector.last_target_hwnd = 8
        self.app.injector.is_claude_window.side_effect = lambda hwnd: hwnd == 7
        self.app._refresh_panel_color()
        self.app.pill_frame.configure.assert_not_called()

    def test_text_sent_outside_claude_stays_recoverable(self):
        self.app._outside_claude = True
        self.app._recording_target = 5
        self.app.injector.target_name.return_value = "firefox"
        self.app._finish_processing("Salut", None)
        self.assertEqual(list(self.app.recent_texts), ["Salut"])
        self.assertIn("firefox", self.app.audio_meter.set_message.call_args.args[0])

    def test_recent_texts_keep_newest_first_and_are_bounded(self):
        for index in range(app_module.RECENT_TEXTS + 2):
            self.app._finish_processing(f"text {index}", None)
        self.assertEqual(len(self.app.recent_texts), app_module.RECENT_TEXTS)
        self.assertEqual(self.app.recent_texts[0], f"text {app_module.RECENT_TEXTS + 1}")

    def test_empty_transcription_is_not_kept(self):
        self.app.recorder = Mock()
        self.app.recorder.get_status.return_value = Mock(samples=0)
        self.app._finish_processing("", None)
        self.assertEqual(len(self.app.recent_texts), 0)

    def test_background_status_never_calls_tk(self):
        thread = threading.Thread(target=self.app._on_whisper_status, args=("Gata de dictare",))
        thread.start()
        thread.join(2)
        self.app.root.after.assert_not_called()
        self.assertFalse(self.app._ui_queue.empty())

    def test_invalid_hotkey_keeps_existing_binding(self):
        self.app.current_hotkey = "old binding"
        with patch.object(app_module.keyboard, "add_hotkey", side_effect=ValueError("invalid")), patch.object(
                app_module.keyboard, "remove_hotkey") as remove:
            with self.assertRaises(ValueError):
                self.app._setup_hotkey()
        self.assertEqual(self.app.current_hotkey, "old binding")
        remove.assert_not_called()

    def test_delayed_reset_does_not_hide_active_recording(self):
        self.app.is_recording = True
        self.app._reset_button()
        self.app.btn_dictate.configure.assert_not_called()

    def test_hotkey_uses_ui_queue(self):
        self.app._hotkey_triggered()
        self.app.root.after.assert_not_called()
        self.assertFalse(self.app._ui_queue.empty())

    def test_real_keyboard_dispatch_triggers_once_on_each_f9_release(self):
        keyboard = app_module.keyboard
        listener = keyboard._KeyboardListener()
        with patch.object(keyboard._os_keyboard, "init"):
            listener.init()
        with patch.object(keyboard, "_listener", listener), patch.object(
                listener, "start_if_necessary"), patch.object(keyboard, "_pressed_events", {}), patch.object(
                keyboard, "_logically_pressed_keys", {}), patch.object(keyboard, "_hotkeys", {}), patch.object(
                keyboard, "is_modifier", return_value=False), patch.object(
                keyboard, "parse_hotkey_combinations", return_value=(((67,),),)):
            self.app._start_recording = Mock(side_effect=lambda: setattr(self.app, "is_recording", True))
            self.app._stop_recording_and_process = Mock(side_effect=lambda: setattr(self.app, "is_recording", False))
            self.app._setup_hotkey()
            for cycle in range(2):
                for event_type in (keyboard.KEY_DOWN, keyboard.KEY_UP):
                    event = keyboard.KeyboardEvent(event_type, 67, name="f9")
                    listener.direct_callback(event)
                    listener.pre_process_event(listener.queue.get_nowait())
                self.assertEqual(self.app._ui_queue.qsize(), 1)
                callback, args = self.app._ui_queue.get_nowait()
                callback(*args)
                self.assertEqual(self.app.is_recording, cycle == 0)
            self.app._start_recording.assert_called_once()
            self.app._stop_recording_and_process.assert_called_once()

    def test_close_releases_microphone_and_window_tracker(self):
        self.app.recorder = Mock()
        self.app.injector = Mock()
        self.app.tray_icon = None
        with patch.object(app_module.sys, "exit"):
            self.app.exit_app()
        self.assertTrue(self.app._closing.is_set())
        self.app.recorder.stop.assert_called_once()
        self.app.injector.stop.assert_called_once()

    def test_settings_cannot_reload_model_during_recording(self):
        self.app.is_recording = True
        with self.assertRaises(ValueError):
            self.app._on_settings_saved({"model_size": "medium", "hotkey": "f9"})

    def test_dragging_button_does_not_start_dictation(self):
        self.app._dragging = True
        self.app.toggle_dictation = Mock()
        self.app._on_dictate_click()
        self.app.toggle_dictation.assert_not_called()

    def test_second_instance_does_not_register_another_hotkey(self):
        with patch.object(app_module.win32event, "CreateMutex"), patch.object(
                app_module.win32api, "GetLastError", return_value=183), patch.object(
                app_module, "Voice2TextApp") as constructor, patch.object(app_module, "configure_logging"), patch.object(
                app_module.win32api, "CloseHandle"), patch.object(app_module, "show_running_instance") as show:
            app_module.main()
        constructor.assert_not_called()
        show.assert_called_once_with()

    def test_second_launch_opens_the_window_of_the_running_instance(self):
        self.app._show_event = object()
        self.app.show_floating = Mock()
        with patch.object(app_module.win32event, "WaitForSingleObject",
                          return_value=app_module.win32event.WAIT_OBJECT_0):
            self.app._drain_ui_queue()
        self.app.show_floating.assert_called_once_with()

    def test_tray_click_shows_window_and_never_starts_recording(self):
        self.app.toggle_floating = Mock()
        self.app.toggle_dictation = Mock()
        menu = self.app._tray_menu()
        default = [item for item in menu.items if item.default]
        self.assertEqual(len(default), 1)
        default[0](Mock())
        callback, args = self.app._ui_queue.get_nowait()
        callback(*args)
        self.app.toggle_floating.assert_called_once_with()
        self.app.toggle_dictation.assert_not_called()

    def test_recording_state_tints_the_dictate_button(self):
        self.app.transcriber = Mock()
        self.app.injector = Mock()
        self.app.recorder = Mock()
        self.app.btn_dictate.set_recording.reset_mock()
        self.app._start_recording()
        self.app.btn_dictate.set_recording.assert_called_once_with(True)
        self.app.btn_dictate.set_recording.reset_mock()
        with patch.object(app_module.threading, "Thread"):
            self.app._stop_recording_and_process()
        self.app.btn_dictate.set_recording.assert_called_once_with(False)

    def test_failed_microphone_start_leaves_button_untinted(self):
        self.app.transcriber = Mock()
        self.app.injector = Mock()
        self.app.recorder = Mock()
        self.app.recorder.start.side_effect = OSError("no microphone")
        with self.assertLogs(level="ERROR"), patch.object(app_module.messagebox, "showerror"):
            self.app._start_recording()
        self.app.btn_dictate.set_recording.assert_not_called()
        self.assertFalse(self.app.is_recording)

    def test_position_on_disconnected_monitor_returns_to_visible_default(self):
        with patch.object(app_module.win32api, "MonitorFromPoint", return_value=None):
            self.assertEqual(app_module.Voice2TextApp._visible_position(5000, 5000),
                             app_module.DEFAULT_WINDOW_POSITION)
        with patch.object(app_module.win32api, "MonitorFromPoint", return_value=1):
            self.assertEqual(app_module.Voice2TextApp._visible_position(1684, 400), (1684, 400))

    def test_saved_hotkey_updates_visible_status(self):
        self.app.transcriber = Mock()
        self.app.root = Mock()
        self.app.audio_meter = Mock()
        self.app.settings_win = None
        self.app._hotkey_value = "f9"
        self.app.current_hotkey = "binding"
        with patch.object(app_module, "save_config"), patch.object(self.app, "_setup_hotkey"):
            self.app._on_settings_saved({"hotkey": "f8", "model_size": "small"})
        self.assertEqual(self.app.audio_meter.hotkey, "F8")
        self.app.audio_meter.set_message.assert_called_once_with("Model pregătit • F8: start / stop")

    def test_insertion_failure_preserves_transcript_and_clears_busy_on_ui_thread(self):
        self.app._session_config = {"language": "ro"}
        self.app._recording_target = 123
        self.app.recorder = Mock()
        self.app.transcriber = Mock()
        self.app.transcriber.transcribe.return_value = "Salut, lume!"
        self.app.injector = Mock()
        self.app.injector.restore_and_inject.side_effect = RuntimeError("focus failed")
        self.app._show_uninserted_text = Mock()

        def start_immediately(*, target, **kwargs):
            return Mock(start=target)

        with self.assertLogs(level="ERROR"), patch.object(app_module.threading, "Thread", side_effect=start_immediately):
            self.app._stop_recording_and_process()
        self.assertTrue(self.app.is_processing)
        while not self.app._ui_queue.empty():
            callback, args = self.app._ui_queue.get_nowait()
            callback(*args)
        self.assertFalse(self.app.is_processing)
        self.assertEqual(self.app.last_transcription, "Salut, lume!")
        self.app._show_uninserted_text.assert_called_once_with("Salut, lume!", "focus failed")
        self.assertEqual(self.app.injector.restore_and_inject.call_args.kwargs["target_hwnd"], 123)


class GuiSmokeTests(unittest.TestCase):
    def test_real_hidden_gui_handles_early_status_and_shutdown(self):
        errors = []

        def fake_model(*, status_callback, **kwargs):
            thread = threading.Thread(target=status_callback, args=("Gata de dictare",))
            thread.start()
            thread.join(1)
            return Mock()

        with patch.object(app_module, "WhisperTranscriber", side_effect=fake_model), patch.object(
                app_module.Voice2TextApp, "_setup_hotkey"), patch.object(
                app_module.Voice2TextApp, "_setup_tray"), patch.object(
                app_module.AudioRecorder, "start") as start_microphone, patch.object(
                app_module, "load_config", return_value={"window_x": 100, "window_y": 100, "floating_visible": False,
                                                        "hotkey": "f9", "model_size": "small"}):
            app = app_module.Voice2TextApp()
            # Launching opens the panel even if it was hidden, without recording.
            self.assertTrue(app.config["floating_visible"])
            self.assertFalse(app.root._withdraw_called_before_window_exists)
            start_microphone.assert_not_called()
            self.assertFalse(app.is_recording)
            app.root.withdraw()
            app.root.report_callback_exception = lambda *args: errors.append(args)
            def shutdown():
                for timer in app.root.tk.splitlist(app.root.tk.call("after", "info")):
                    app.root.after_cancel(timer)
                app.exit_app()
            try:
                app.root.update_idletasks()
                scale = app.root._get_window_scaling()
                self.assertLessEqual(app.root.winfo_reqwidth() / scale, 220)
                self.assertLessEqual(app.root.winfo_reqheight() / scale, 75)
                app._apply_window_shape()
                region = app_module.win32gui.CreateRoundRectRgn(0, 0, 1, 1, 0, 0)
                try:
                    self.assertNotEqual(app_module.win32gui.GetWindowRgn(app._get_own_hwnd(), region), 0)
                    self.assertFalse(app_module.win32gui.PtInRegion(region, 0, 0))
                    left, top, right, bottom = app_module.win32gui.GetWindowRect(app._get_own_hwnd())
                    self.assertTrue(app_module.win32gui.PtInRegion(region, (right-left) // 2,
                                                                 (bottom-top) // 2))
                finally:
                    app_module.win32gui.DeleteObject(region)
                before = (app.root.winfo_reqwidth(), app.root.winfo_reqheight())
                with patch("tkinter.Menu.tk_popup"):
                    app._show_info_dropdown()
                self.assertTrue(app._info_menu.winfo_exists())
                self.assertEqual(app._info_menu.index("end"), 3)
                app.recent_texts.append("Salut")
                with patch("tkinter.Menu.tk_popup"):
                    app._show_info_dropdown()
                self.assertEqual(app._info_menu.index("end"), 5)
                app.recent_texts.clear()
                self.assertEqual((app.root.winfo_reqwidth(), app.root.winfo_reqheight()), before)
                # Generate Tk events only, on an invisible test window. No OS
                # mouse input, microphone capture, or external actions occur.
                app.root.attributes("-alpha", 0)
                app.root.deiconify()
                app.root.update()
                gear_action = Mock()
                dictate_action = Mock()
                app.btn_gear.configure(command=gear_action)
                app.btn_dictate.configure(command=dictate_action)
                with patch.object(app, "_persist_config"):
                    for widget in (app.audio_meter.canvas, app.audio_meter.status_label._label,
                                   app.btn_gear._canvas, app.btn_info._canvas, app.pill_frame._canvas,
                                   app.btn_dictate._canvas, app.btn_dictate._image_label,
                                   app.drag_handle._label):
                        # Prevent the info button's ordinary action during this
                        # drag test; the dropdown behavior is checked above.
                        app.btn_info.configure(command=Mock())
                        old_x, old_y = app.root.winfo_x(), app.root.winfo_y()
                        root_x, root_y = widget.winfo_rootx() + 3, widget.winfo_rooty() + 3
                        widget.event_generate("<Enter>")
                        widget.event_generate("<ButtonPress-1>", x=3, y=3, rootx=root_x, rooty=root_y)
                        widget.event_generate("<B1-Motion>", x=23, y=13,
                                              rootx=root_x + 20, rooty=root_y + 10, state=256)
                        widget.event_generate("<ButtonRelease-1>", x=23, y=13,
                                              rootx=root_x + 20, rooty=root_y + 10)
                        app.root.update()
                        self.assertEqual((app.root.winfo_x(), app.root.winfo_y()), (old_x + 20, old_y + 10))
                    gear_action.assert_not_called()
                    dictate_action.assert_not_called()
                    # Prove a simple click still reaches the button action.
                    app.btn_gear._canvas.event_generate("<Enter>")
                    app.btn_gear._canvas.event_generate("<ButtonPress-1>", x=5, y=5)
                    app.btn_gear._canvas.event_generate("<ButtonRelease-1>", x=5, y=5)
                    app.root.update()
                    gear_action.assert_called_once()
                plain = app.btn_dictate._skin_image.cget("dark_image")
                app.btn_dictate.set_recording(True)
                red, green, blue, _ = app.btn_dictate._skin_image.cget("dark_image").getpixel((plain.width // 2, 8))
                self.assertGreater(red, 200)
                self.assertGreater(red, blue + 40)
                self.assertGreater(red, green + 40)
                app.btn_dictate.set_recording(False)
                self.assertEqual(app.btn_dictate._skin_image.cget("dark_image").tobytes(), plain.tobytes())
                app.root.withdraw()
                app.open_settings()
                app.settings_win.withdraw()
                app.root.after(150, shutdown)
                app.run()
            finally:
                if not app._closing.is_set():
                    shutdown()
        self.assertEqual(errors, [])
