import math
import time
import tkinter as tk

import customtkinter as ctk

from audio_recorder import AudioStatus


class AudioMeter(ctk.CTkFrame):
    """Compact activity indicator; full diagnostics are available in the dropdown."""
    def __init__(self, parent, hotkey="F9"):
        super().__init__(parent, fg_color="transparent", height=18)
        self.hotkey = hotkey
        self.latest_status = AudioStatus()
        self.message = f"{hotkey}: pornește / oprește dictarea"
        self.canvas = tk.Canvas(self, width=96, height=14, bg="#141b22",
                                highlightthickness=0, borderwidth=0)
        self.canvas.pack(side="left", padx=(8, 4), pady=1)
        self.bars = [self.canvas.create_line(2 + i * 4.8, 3, 2 + i * 4.8, 11,
                                             fill="#343c46", width=3, capstyle="round")
                     for i in range(20)]
        self._status_font = ctk.CTkFont(size=10)
        self.status_label = ctk.CTkLabel(self, text=f"Gata • {hotkey}",
                                       font=self._status_font, text_color="#aaaab2",
                                       width=84, height=16, anchor="w", wraplength=0)
        self.status_label.pack(side="right", padx=(0, 7))
        self._level = 0.0
        self._last_callbacks = -1
        self._was_recording = False

    def set_message(self, text, color="#aaaab2", summary=None):
        self.message = text
        if summary is None:
            if text.startswith("Eroare"):
                summary = "Eroare • detalii"
            elif text.startswith("Model pregătit"):
                summary = f"Gata • {self.hotkey}"
            elif text.startswith("Se încarcă"):
                summary = "Încarc modelul…"
            elif text.startswith("Text inserat"):
                summary = "Inserat ✓"
            else:
                summary = text
        # A long driver/model error must never enlarge the floating panel.
        if self._status_font.measure(summary) > 78:
            while summary and self._status_font.measure(summary + "…") > 78:
                summary = summary[:-1]
            summary += "…"
        self.status_label.configure(text=summary, text_color=color)

    def update_audio(self, status, recording, now=None):
        now = time.monotonic() if now is None else now
        self.latest_status = status
        if not recording:
            if self._was_recording:
                for bar in self.bars:
                    self.canvas.itemconfigure(bar, fill="#343c46")
            self._was_recording = False
            return
        if not self._was_recording:
            self._level = 0.0
            self._last_callbacks = -1
        self._was_recording = True
        stale = now - (status.last_callback_at or status.started_at) > 1.0
        if status.callbacks != self._last_callbacks:
            db = 20 * math.log10(max(status.rms, 1e-7))
            amplitude = min(1.0, max(0.0, (db + 70) / 70)) if not stale else 0.0
            self._level = amplitude
            self._last_callbacks = status.callbacks
        color = "#a6e3a1"
        if stale:
            message = "Captură întreruptă" if status.callbacks else "Nu primesc audio — verifică microfonul"
            short, color = "Fără audio", "#f38ba8"
        elif not status.callbacks:
            message, short = "Aștept primul semnal audio…", "Aștept audio"
        elif status.peak >= 0.98:
            message, short, color = "Semnal prea puternic", "Prea tare", "#f9e2af"
        elif status.rms < 1e-5:
            message, short, color = "Fără semnal — verifică microfonul", "Fără semnal", "#f9e2af"
        elif status.rms < 0.001:
            message, short, color = "Semnal slab", "Semnal slab", "#f9e2af"
        else:
            message, short = f"Captez audio • {self.hotkey} oprește", "Ascult"
        active = round((0.0 if stale else self._level) * len(self.bars))
        for index, bar in enumerate(self.bars):
            self.canvas.itemconfigure(bar, fill="#00d6ae" if index < active else "#343c46")
        self.set_message(f"{message} • {status.duration:.1f} s", color,
                         summary=f"{short} {status.duration:.0f}s")
