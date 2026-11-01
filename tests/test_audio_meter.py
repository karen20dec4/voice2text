import unittest

import customtkinter as ctk

from audio_meter import AudioMeter
from audio_recorder import AudioStatus


class AudioMeterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        for timer in cls.root.tk.splitlist(cls.root.tk.call("after", "info")):
            cls.root.after_cancel(timer)
        cls.root.destroy()

    def setUp(self):
        self.meter = AudioMeter(self.root)
        self.addCleanup(self.meter.destroy)

    def test_level_bars_follow_measured_audio_and_return_to_idle(self):
        self.meter.update_audio(AudioStatus(rms=0.25, peak=0.3, callbacks=1,
                                           started_at=1, last_callback_at=2,
                                           device_name="Realtek"), True, now=2)
        active = [bar for bar in self.meter.bars if self.meter.canvas.itemcget(bar, "fill") == "#00d6ae"]
        self.assertGreater(len(active), 0)
        self.assertEqual(self.meter.latest_status.device_name, "Realtek")
        self.meter.update_audio(AudioStatus(callbacks=2, started_at=1, last_callback_at=3), True, now=3)
        self.assertTrue(all(self.meter.canvas.itemcget(bar, "fill") == "#343c46" for bar in self.meter.bars))
        self.assertIn("Fără semnal", self.meter.status_label.cget("text"))

    def test_running_recorder_without_callbacks_is_not_shown_as_capturing(self):
        self.meter.update_audio(AudioStatus(started_at=10), True, now=12)
        self.assertIn("Nu primesc audio", self.meter.message)

    def test_stalled_callback_is_reported(self):
        self.meter.update_audio(AudioStatus(rms=0.2, callbacks=1, started_at=10,
                                           last_callback_at=11), True, now=13)
        self.assertIn("Captură întreruptă", self.meter.message)

    def test_idle_poll_does_not_overwrite_processing_or_error_message(self):
        self.meter.set_message("Transcriu… 5 s")
        self.meter.update_audio(AudioStatus(), False, now=12)
        self.assertEqual(self.meter.status_label.cget("text"), "Transcriu… 5 s")

    def test_waveform_is_at_most_one_hundred_pixels_wide(self):
        self.assertLessEqual(self.meter.canvas.winfo_reqwidth(), 100)

    def test_long_diagnostic_does_not_expand_the_compact_panel(self):
        self.meter.pack()
        self.root.update_idletasks()
        before = (self.meter.winfo_reqwidth(), self.meter.winfo_reqheight())
        details = "Eroare: " + "microfon indisponibil " * 20
        self.meter.set_message(details)
        self.root.update_idletasks()
        self.assertEqual((self.meter.winfo_reqwidth(), self.meter.winfo_reqheight()), before)
        self.assertEqual(self.meter.message, details)
