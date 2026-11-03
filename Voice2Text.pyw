import os
import sys
import threading
import logging
from collections import deque
from logging.handlers import RotatingFileHandler
import queue
import time
from tkinter import messagebox
import win32api
import win32event
import win32gui
import win32con
from PIL import Image
import pystray
import pyperclip
import customtkinter as ctk

from config import get_app_dir, load_config, save_config
from audio_recorder import AudioRecorder
from audio_meter import AudioMeter
from ui_controls import ImageButton
from transcriber import WhisperTranscriber
from injector import WindowInjector, strip_diacritics
from hotkey import GlobalHotkey
from live_transcription import LiveTranscription
from settings_window import SettingsWindow
from version import VERSION

SHOW_WINDOW_EVENT = "Local\\Voice2Text.Show"
DEFAULT_WINDOW_POSITION = (120, 120)
RECENT_TEXTS = 10
PANEL_COLORS = {False: ("#141b22", "#2a3540"),  # Text goes to Claude.
                True: ("#b9a3f5", "#dacffb")}  # Light violet: text goes elsewhere.


class Voice2TextApp:
    def __init__(self):
        self.config = load_config()
        # Launching means opening the panel, even after hiding it last time.
        self.config["floating_visible"] = True

        # State
        self.is_recording = False
        self.is_processing = False
        self.current_hotkey = None
        self.tray_icon = None
        self.settings_win = None
        self._ui_queue = queue.Queue()
        self._closing = threading.Event()
        self._hotkey_value = None
        self._ui_after_id = None
        self._recording_target = None
        self._session_config = None
        self._live = None
        self.last_transcription = ""
        # A paste into a window without a text field fails silently. Kept in
        # memory only: transcriptions are never written to disk.
        self.recent_texts = deque(maxlen=RECENT_TEXTS)
        self._outside_claude = False
        self._meter_after_id = None
        self._processing_started_at = 0.0
        self._processing_stage = "Transcriu"
        self._shape_after_id = None
        self._window_shape = None
        self._info_menu = None

        # Dragging support
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._dragging = False
        self._drag_origin = (0, 0)

        # UI Setup
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Voice2Text")
        self.root.iconbitmap(os.path.join(os.path.dirname(__file__), "icon.ico"))
        self.root.configure(fg_color="#010203")
        self.root.attributes("-transparentcolor", "#010203")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        # Audio & AI services
        self.recorder = AudioRecorder()
        self.transcriber = WhisperTranscriber(
            model_size=self.config.get("model_size", "small"),
            status_callback=self._on_whisper_status,
            compute_device=self.config.get("compute_device", "gpu")
        )
        self.injector = WindowInjector()

        # Apply position
        wx, wy = self._visible_position(self.config.get("window_x", 120), self.config.get("window_y", 120))
        self.root.geometry(f"+{wx}+{wy}")

        self._show_event = win32event.CreateEvent(None, False, False, SHOW_WINDOW_EVENT)
        self._build_floating_pill()
        self._setup_win32_toolwindow()
        try:
            self._setup_hotkey()
        except Exception:
            logging.exception("Shortcut invalid sau ocupat; revenire la F9")
            self.config["hotkey"] = "f9"
            try:
                self._setup_hotkey()
            except Exception:
                # Another application owns F9; the panel button still works.
                logging.exception("F9 este ocupat; dictarea pornește doar din panou")
        self._setup_tray()
        self._drain_ui_queue()
        self._refresh_audio_meter()

        # Handle close cleanly
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

    @staticmethod
    def _visible_position(x, y):
        # The saved position can belong to a monitor that is no longer connected.
        try:
            if win32api.MonitorFromPoint((x + 20, y + 20), win32con.MONITOR_DEFAULTTONULL):
                return x, y
        except Exception:
            logging.warning("Nu pot verifica poziția ferestrei", exc_info=True)
        return DEFAULT_WINDOW_POSITION

    def _get_own_hwnd(self):
        try:
            return win32gui.GetAncestor(self.root.winfo_id(), win32con.GA_ROOT)
        except Exception:
            return None

    def _setup_win32_toolwindow(self):
        try:
            self.root.update_idletasks()
            hwnd = self._get_own_hwnd()
            if hwnd:
                # Add WS_EX_TOOLWINDOW (0x80) so it doesn't show on taskbar/Alt-Tab
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_TOOLWINDOW)
                self._apply_window_shape()
        except Exception as e:
            logging.warning("Eroare setare toolwindow: %s", e)

    def _build_floating_pill(self):
        self.pill_frame = ctk.CTkFrame(
            self.root, corner_radius=16, fg_color="#141b22",
            border_width=1, border_color="#2a3540")
        self.pill_frame.pack(padx=0, pady=0)
        controls = ctk.CTkFrame(self.pill_frame, fg_color="transparent", height=32)
        controls.pack(fill="x", padx=5, pady=(4, 0))

        self._ui_images = {}
        for name, size in (("mic", (13, 13)), ("chevron", (11, 11)),
                           ("settings", (14, 14)), ("grip", (9, 14))):
            path = os.path.join(os.path.dirname(__file__), "assets", f"{name}.png")
            with Image.open(path) as source:
                rgba = source.convert("RGBA")
            self._ui_images[name] = ctk.CTkImage(light_image=rgba, dark_image=rgba, size=size)
        self.drag_handle = ctk.CTkLabel(controls, text="", image=self._ui_images["grip"],
                                       width=10, height=24, cursor="fleur")
        self.drag_handle.pack(side="left", padx=(0, 3))

        def control(text, image, width, command, padx=1):
            button = ImageButton(controls, text=text, icon=image, width=width, command=command)
            button.pack(side="left", padx=padx, pady=1)
            return button

        self.btn_dictate = control("Dictează", "mic", 98, self._on_dictate_click, padx=2)
        self.version_label = ctk.CTkLabel(controls, text=f"v{VERSION}", font=ctk.CTkFont(size=10),
                                          text_color="#7d8792", width=44, height=24)
        self.version_label.pack(side="left", padx=(2, 2))
        self.btn_info = control("", "chevron", 24, self._show_info_dropdown)
        self.btn_gear = control("", "settings", 24, self.open_settings)
        self.btn_close = control("", "close", 24, self._on_close_click)
        self.audio_meter = AudioMeter(self.pill_frame, hotkey=self.config.get("hotkey", "f9").upper())
        self.audio_meter.pack(fill="x", padx=2, pady=(0, 4))
        self.audio_meter.status_label.configure(cursor="hand2")
        self.audio_meter.status_label.bind("<ButtonRelease-1>", lambda event: self._show_info_dropdown(), add="+")

        self._install_drag_bindings()
        self.root.bind("<Configure>", self._on_root_configure, add="+")

    def _install_drag_bindings(self):
        import tkinter as tk
        # Process a drag before CTk's release command, on every descendant,
        # including the buttons' private labels/canvases and the audio strip.
        tag = f"Voice2TextDrag{self.root.winfo_id()}"
        self.root.bind_class(tag, "<ButtonPress-1>", self._on_drag_press)
        self.root.bind_class(tag, "<B1-Motion>", self._on_drag_motion)
        self.root.bind_class(tag, "<ButtonRelease-1>", self._on_drag_release)
        self.root.bind_class(tag, "<Button-3>", self._on_right_click)
        def install(widget):
            widget.bindtags((tag,) + widget.bindtags())
            # CTkFrame.winfo_children deliberately hides its drawing canvas.
            # The base Tk implementation includes every actual mouse surface.
            for child in tk.Misc.winfo_children(widget):
                install(child)
        install(self.root)

    def _show_info_dropdown(self):
        import tkinter as tk
        if self._info_menu is not None:
            self._info_menu.destroy()
        status = self.audio_meter.latest_status
        model = self.transcriber.model_size or self.config.get("model_size", "small")
        language = {"ro": "Română", "en": "Engleză", "auto": "Auto"}.get(self.config.get("language"), "Română")
        device = {"cuda": "GPU CUDA", "vulkan": "GPU Vulkan"}.get(self.transcriber.device, "CPU")
        target = self._current_target()
        if not target:
            destination = "nicio fereastră"
        elif self.injector.is_claude_window(target):
            destination = "Claude"
        else:
            destination = self.injector.target_name(target) or "altă aplicație"
        menu = tk.Menu(self.root, tearoff=0, bg="#242428", fg="#f5f5f7",
                       disabledforeground="#dddde4", borderwidth=1, font=("Segoe UI", 10))
        self._info_menu = menu
        lines = [
            f"Microfon: {status.device_name}",
            f"Whisper {model} · {device} · {language} · {self.config.get('hotkey', 'f9').upper()}",
            f"Trimit în: {destination}",
            self.audio_meter.message,
        ]
        for line in lines:
            menu.add_command(label=line[:160], state="disabled")
        if self.recent_texts:
            menu.add_separator()
            for text in self.recent_texts:
                menu.add_command(label=f"📋 {text[:60]}", command=lambda text=text: self._show_saved_text(text))
        try:
            menu.tk_popup(self.btn_info.winfo_rootx(), self.btn_info.winfo_rooty() + self.btn_info.winfo_height() + 4)
        finally:
            menu.grab_release()

    def _on_root_configure(self, event):
        if event.widget is self.root and not self._closing.is_set() and self._shape_after_id is None:
            self._shape_after_id = self.root.after_idle(self._apply_window_shape)

    def _apply_window_shape(self):
        self._shape_after_id = None
        if self._closing.is_set():
            return
        try:
            hwnd = self._get_own_hwnd()
            if not hwnd:
                return
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width, height = right - left, bottom - top
            shape = (hwnd, width, height)
            if width < 2 or height < 2 or shape == self._window_shape:
                return
            diameter = max(2, round(32 * self.root._get_window_scaling()))
            region = win32gui.CreateRoundRectRgn(0, 0, width, height, diameter, diameter)
            try:
                if win32gui.SetWindowRgn(hwnd, region, True) == 0:
                    raise OSError("SetWindowRgn a eșuat")
            except Exception:
                win32gui.DeleteObject(region)
                raise
            # Windows owns the region after SetWindowRgn succeeds.
            self._window_shape = shape
        except Exception:
            logging.warning("Nu pot aplica forma rotunjită a ferestrei", exc_info=True)

    def _on_drag_press(self, event):
        self._dragging = False
        self._drag_origin = (event.x_root, event.y_root)
        self._drag_start_x = event.x_root - self.root.winfo_x()
        self._drag_start_y = event.y_root - self.root.winfo_y()

    def _on_drag_motion(self, event):
        if not self._dragging and max(abs(event.x_root - self._drag_origin[0]), abs(event.y_root - self._drag_origin[1])) < 4:
            return
        self._dragging = True
        new_x = event.x_root - self._drag_start_x
        new_y = event.y_root - self._drag_start_y
        self.root.geometry(f"+{new_x}+{new_y}")

    def _on_drag_release(self, event):
        if self._dragging:
            self.config["window_x"] = self.root.winfo_x()
            self.config["window_y"] = self.root.winfo_y()
            self._persist_config()
            return "break"

    def _on_dictate_click(self):
        if not self._dragging:
            self.toggle_dictation()

    def _on_close_click(self):
        # The button sits beside the gear: a stray click must not lose a dictation.
        if ((self.is_recording or self.is_processing) and not messagebox.askyesno(
                "Închide Voice2Text", "Dictarea este în curs și textul netranscris se pierde. Închid aplicația?",
                parent=self.root)):
            return
        self.exit_app()

    def _on_right_click(self, event):
        import tkinter as tk
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="⚙️ Setări...", command=self.open_settings)
        m.add_command(label="👁️ Ascunde butonul (rămâne în bară)", command=self.hide_floating)
        m.add_separator()
        m.add_command(label="❌ Închide Voice2Text", command=self.exit_app)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _on_whisper_status(self, msg):
        def update():
            if not self.is_recording and not self.is_processing:
                if "Eroare" in msg:
                    self.btn_dictate.configure(text="Eroare AI", fg_color="#f38ba8")
                    self.audio_meter.set_message(msg, "#f38ba8")
                elif "Se încarcă" in msg:
                    self.btn_dictate.configure(text="Încarc AI…", fg_color="#f9e2af", text_color="#11111b")
                    self.audio_meter.set_message(msg, "#f9e2af")
                else:
                    self.btn_dictate.configure(text="Dictează", fg_color="#313244", text_color="#cdd6f4")
                    self.audio_meter.set_message(f"Model pregătit • {self.config.get('hotkey', 'f9').upper()}: start / stop")
        self._post_ui(update)

    def _refresh_audio_meter(self):
        if self._closing.is_set():
            return
        self.audio_meter.update_audio(self.recorder.get_status(), self.is_recording)
        self._refresh_panel_color()
        if self.is_processing:
            elapsed = time.monotonic() - self._processing_started_at
            self.audio_meter.set_message(f"{self._processing_stage}… {elapsed:.0f} s", "#f9e2af")
        self._meter_after_id = self.root.after(50, self._refresh_audio_meter)

    def _current_target(self):
        # A running dictation goes to the window captured when it started.
        if self.is_recording or self.is_processing:
            return self._recording_target
        return self.injector.last_target_hwnd

    def _refresh_panel_color(self):
        target = self._current_target()
        outside = bool(target) and not self.injector.is_claude_window(target)
        if outside != self._outside_claude:
            self._outside_claude = outside
            fill, border = PANEL_COLORS[outside]
            self.pill_frame.configure(fg_color=fill, border_color=border)

    def _set_processing_stage(self, stage):
        if self.is_processing:
            self._processing_stage = stage

    def _post_ui(self, callback, *args):
        if not self._closing.is_set():
            self._ui_queue.put((callback, args))

    def _drain_ui_queue(self):
        if self._closing.is_set():
            return
        if win32event.WaitForSingleObject(self._show_event, 0) == win32event.WAIT_OBJECT_0:
            self.show_floating()
        for _ in range(100):
            try:
                callback, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception:
                logging.exception("Eroare actualizare interfață")
            if self._closing.is_set():
                return
        self._ui_after_id = self.root.after(30, self._drain_ui_queue)

    def _setup_hotkey(self, hotkey=None):
        hotkey = hotkey or self.config.get("hotkey", "f9")
        if self.current_hotkey and self.current_hotkey.same_keys(hotkey):
            self._hotkey_value = hotkey
            return
        # Register first: an invalid or taken replacement must not disable the old binding.
        handle = GlobalHotkey(hotkey, self._hotkey_triggered)
        if self.current_hotkey:
            self.current_hotkey.stop()
        self.current_hotkey = handle
        self._hotkey_value = hotkey

    def _hotkey_triggered(self):
        # Trigger on UI thread
        logging.info("Shortcut dictare primit")
        self._post_ui(self.toggle_dictation)

    def toggle_dictation(self):
        logging.info("Comutare dictare: recording=%s processing=%s", self.is_recording, self.is_processing)
        if self.is_processing or self._closing.is_set():
            return

        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording_and_process()

    def _start_recording(self):
        if not self.transcriber.is_ready():
            self.btn_dictate.configure(text="Aștept AI…", fg_color="#f9e2af", text_color="#11111b")
            return

        try:
            self._recording_target = self.injector.get_target_window()
            if not self._recording_target:
                raise RuntimeError("Selectează întâi fereastra în care vrei să dictezi")
            self._session_config = self.config.copy()
            device_idx = self.config.get("device_index")
            self.recorder.start(device_index=device_idx)
            self._live = self._create_live_transcription()
            self._live.start()
            self.is_recording = True
            self.btn_dictate.set_recording(True)
            self.btn_dictate.configure(
                text="● Ascult…",
                fg_color="#f38ba8",
                text_color="#11111b"
            )
        except Exception as e:
            logging.exception("Eroare pornire dictare")
            self.btn_dictate.configure(text="Microfon?", fg_color="#f38ba8")
            messagebox.showerror("Nu pot porni dictarea", str(e), parent=self.root)
            self.root.after(2000, self._reset_button)

    def _create_live_transcription(self):
        settings = self._session_config
        target = self._recording_target
        language = settings.get("language", "ro")
        trailing_space = settings.get("add_trailing_space", True)
        plain_text = settings.get("strip_diacritics", False)

        def transcribe(audio):
            return self.transcriber.transcribe(audio, language=language)

        def insert(text, final):
            if final:
                self._post_ui(self._set_processing_stage, "Inserez textul")
            # Only the typed copy loses diacritics; history and recovery keep the transcript.
            self.injector.restore_and_inject(
                strip_diacritics(text) if plain_text else text,
                auto_enter=final and settings.get("auto_enter", False),
                add_trailing_space=trailing_space, target_hwnd=target)

        def finished(text, error, uninserted):
            self._post_ui(self._finish_processing, text, error, uninserted)

        return LiveTranscription(
            self.recorder.take_audio, transcribe, insert,
            lambda: self.injector.can_insert_now(target), finished,
            separator="" if trailing_space else " ")

    def _stop_recording_and_process(self):
        self.is_recording = False
        self.is_processing = True
        self._processing_started_at = time.monotonic()
        self._processing_stage = "Transcriu"

        self.btn_dictate.set_recording(False)
        self.btn_dictate.configure(
            text="Transcriu…",
            fg_color="#f9e2af",
            text_color="#11111b"
        )

        try:
            self._live.finish(self.recorder.stop())
        except Exception as error:
            logging.exception("Eroare oprire înregistrare")
            self._live.finish(error=str(error))

    def _finish_processing(self, text, error, uninserted=None):
        uninserted = text if uninserted is None else uninserted
        self.is_processing = False
        self.last_transcription = text
        if text:
            self.recent_texts.appendleft(text)
        if error:
            self.audio_meter.set_message(f"Eroare: {error}", "#f38ba8")
            self.btn_dictate.configure(text="Eroare", fg_color="#f38ba8", text_color="#11111b")
            if uninserted:
                self._show_uninserted_text(uninserted, error)
            else:
                messagebox.showerror("Eroare dictare", error, parent=self.root)
        elif text and self._outside_claude:
            # Only the target application knows whether a text field took the paste.
            name = self.injector.target_name(self._recording_target) or "altă aplicație"
            self.btn_dictate.configure(text="✓ Trimis", fg_color="#a6e3a1", text_color="#11111b")
            self.audio_meter.set_message(f"Trimis în {name} • textul rămâne în ⌄", "#a6e3a1",
                                         summary="Trimis • vezi ⌄")
        elif text:
            self.btn_dictate.configure(text="✓ Inserat!", fg_color="#a6e3a1", text_color="#11111b")
            self.audio_meter.set_message("Text inserat • gata pentru următoarea dictare", "#a6e3a1")
        else:
            self.btn_dictate.configure(text="Nimic", fg_color="#585b70", text_color="#cdd6f4")
            status = self.recorder.get_status()
            if not status.samples:
                message = "Nu am primit audio — verifică microfonul din ⚙"
            elif status.session_peak < 0.001:
                message = "Semnal foarte slab — verifică microfonul din ⚙"
            else:
                message = "Audio captat, dar fără vorbire recunoscută"
            self.audio_meter.set_message(message, "#f9e2af")
        self.root.after(1200, self._reset_button)

    def _show_uninserted_text(self, text, error):
        self._show_text_window("Text ne-inserat - Voice2Text", f"Inserarea a eșuat: {error}", text)

    def _show_saved_text(self, text):
        self._show_text_window("Text dictat - Voice2Text", "Textul rămâne în ⌄ până închizi aplicația.", text)

    def _show_text_window(self, title, message, text):
        window = ctk.CTkToplevel(self.root)
        window.title(title)
        window.geometry("560x360")
        window.attributes("-topmost", True)
        ctk.CTkLabel(window, text=message, wraplength=520).pack(padx=20, pady=15)
        textbox = ctk.CTkTextbox(window, wrap="word")
        textbox.pack(fill="both", expand=True, padx=20)
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")
        ctk.CTkButton(window, text="Copiază textul", command=lambda: pyperclip.copy(text)).pack(pady=15)

    def _reset_button(self):
        if self.is_recording or self.is_processing or self._closing.is_set():
            return
        self.btn_dictate.configure(
            text="Dictează",
            fg_color="#313244",
            text_color="#cdd6f4"
        )

    def open_settings(self):
        if self.settings_win is None or not self.settings_win.winfo_exists():
            self.settings_win = SettingsWindow(
                self.root,
                self.config,
                on_save_callback=self._on_settings_saved
            )
        else:
            self.settings_win.focus()

    def _on_settings_saved(self, new_config):
        if self.is_recording or self.is_processing:
            raise ValueError("Oprește dictarea și așteaptă transcrierea înainte de a aplica setările")
        old_hotkey = self.config.get("hotkey", "f9")
        self._setup_hotkey(new_config.get("hotkey", "f9"))
        try:
            save_config(new_config)
        except Exception:
            self._setup_hotkey(old_hotkey)
            raise
        self.config = new_config
        self.audio_meter.hotkey = self.config.get("hotkey", "f9").upper()
        self.audio_meter.set_message(f"Model pregătit • {self.audio_meter.hotkey}: start / stop")

        # Update model if changed
        desired_model = self.config.get("model_size", "small")
        self.transcriber.load_model_async(desired_model, self.config.get("compute_device", "gpu"))

        # Floating window visibility
        if self.config.get("floating_visible", True):
            self.root.deiconify()
        else:
            self.root.withdraw()

    def toggle_floating(self):
        if self.root.winfo_viewable():
            self.hide_floating()
        else:
            self.show_floating()

    def show_floating(self):
        x, y = self._visible_position(self.root.winfo_x(), self.root.winfo_y())
        self.root.geometry(f"+{x}+{y}")
        self.root.deiconify()
        self.root.lift()
        self.config["floating_visible"] = True
        self._persist_config()

    def hide_floating(self):
        self.root.withdraw()
        self.config["floating_visible"] = False
        self._persist_config()

    def _persist_config(self):
        try:
            save_config(self.config)
        except OSError:
            logging.exception("Configurația nu poate fi salvată")

    def _setup_tray(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            img = Image.open(icon_path)
        else:
            img = Image.new("RGBA", (64, 64), (31, 111, 235, 255))

        self.tray_icon = pystray.Icon("Voice2Text", img, "Voice2Text - Dictare Vocală", self._tray_menu())
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _tray_menu(self):
        # A click on the tray icon runs the default item; it must never start the microphone.
        return pystray.Menu(
            pystray.MenuItem("🎙️ Dictare (Start/Stop)", lambda: self._post_ui(self.toggle_dictation)),
            pystray.MenuItem("👁️ Arată / Ascunde Butonul", lambda: self._post_ui(self.toggle_floating), default=True),
            pystray.MenuItem("⚙️ Setări...", lambda: self._post_ui(self.open_settings)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Închide Voice2Text", lambda: self._post_ui(self.exit_app))
        )

    def exit_app(self):
        if self._closing.is_set():
            return
        self._closing.set()
        self.injector.stop()
        self.recorder.stop()
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            if self.current_hotkey:
                self.current_hotkey.stop()
        except Exception:
            pass
        if getattr(self, "_ui_after_id", None) is not None:
            self.root.after_cancel(self._ui_after_id)
        if getattr(self, "_meter_after_id", None) is not None:
            self.root.after_cancel(self._meter_after_id)
        if getattr(self, "_shape_after_id", None) is not None:
            self.root.after_cancel(self._shape_after_id)
        self.root.destroy()

    def run(self):
        self.root.mainloop()

def configure_logging():
    directory = os.path.join(get_app_dir(), "logs")
    os.makedirs(directory, exist_ok=True)
    handler = RotatingFileHandler(os.path.join(directory, "voice2text.log"), maxBytes=1_000_000,
                                  backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(message)s")


def show_running_instance():
    try:
        event = win32event.OpenEvent(win32event.EVENT_MODIFY_STATE, False, SHOW_WINDOW_EVENT)
        win32event.SetEvent(event)
    except Exception:
        logging.warning("Nu pot afișa fereastra instanței pornite", exc_info=True)


def main():
    configure_logging()
    mutex = win32event.CreateMutex(None, False, "Local\\Voice2Text")
    try:
        if win32api.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            logging.info("Voice2Text rulează deja")
            show_running_instance()
            return
        app = Voice2TextApp()
        app.run()
    except Exception:
        logging.exception("Eroare fatală Voice2Text")
        raise
    finally:
        win32api.CloseHandle(mutex)


if __name__ == "__main__":
    main()
