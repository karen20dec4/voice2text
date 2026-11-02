import unittest
from unittest.mock import Mock, patch

import numpy as np

from audio_recorder import AudioRecorder


class RecorderTests(unittest.TestCase):
    def test_settings_list_only_microphones_that_accept_16_khz(self):
        devices = [{"name": "MME mic", "max_input_channels": 1},
                   {"name": "Speakers", "max_input_channels": 0},
                   {"name": "WASAPI mic", "max_input_channels": 2}]

        def check(device, **settings):
            self.assertEqual(settings["samplerate"], 16000)
            if device == 2:
                raise ValueError("Invalid sample rate")

        with patch("audio_recorder.sd.query_devices", return_value=devices), patch(
                "audio_recorder.sd.check_input_settings", side_effect=check):
            self.assertEqual(AudioRecorder.get_input_devices(), [(0, "[0] MME mic")])

    def test_meter_measures_real_samples_and_silence(self):
        recorder = AudioRecorder()
        with patch("audio_recorder.sd.InputStream", return_value=Mock()), patch("audio_recorder.time.monotonic", return_value=10):
            recorder.start()
            recorder._audio_callback(np.full((160, 1), 0.25, dtype=np.float32), 160, None, None)
            status = recorder.get_status()
            self.assertAlmostEqual(status.rms, 0.25)
            self.assertAlmostEqual(status.peak, 0.25)
            self.assertAlmostEqual(status.duration, 0.01)
            self.assertEqual(status.callbacks, 1)
            self.assertEqual(status.last_callback_at, 10)
            recorder._audio_callback(np.zeros((160, 1), dtype=np.float32), 160, None, None)
            self.assertEqual(recorder.get_status().rms, 0)
            self.assertEqual(recorder.get_status().session_peak, 0.25)
            recorder.stop()

    def test_new_recording_resets_previous_levels(self):
        recorder = AudioRecorder()
        with patch("audio_recorder.sd.InputStream", return_value=Mock()):
            recorder.start()
            recorder._audio_callback(np.ones((160, 1), dtype=np.float32), 160, None, None)
            recorder.stop()
            recorder.start()
            status = recorder.get_status()
            self.assertEqual(status.rms, 0)
            self.assertEqual(status.samples, 0)
            self.assertEqual(status.callbacks, 0)
            recorder.stop()

    def test_failed_start_closes_device_and_allows_retry(self):
        failed, good = Mock(), Mock()
        failed.start.side_effect = RuntimeError("device lost")
        recorder = AudioRecorder()
        with patch("audio_recorder.sd.InputStream", side_effect=[failed, good]):
            with self.assertRaises(RuntimeError):
                recorder.start()
            self.assertFalse(recorder.is_recording)
            self.assertIsNone(recorder._stream)
            failed.close.assert_called_once()
            recorder.start()
            self.assertTrue(recorder.is_recording)
            recorder.stop()

    def test_stop_closes_device_even_when_stop_raises(self):
        stream = Mock()
        stream.stop.side_effect = RuntimeError("unplugged")
        recorder = AudioRecorder()
        with patch("audio_recorder.sd.InputStream", return_value=stream):
            recorder.start()
            recorder._audio_callback(np.array([[0.1], [0.2]], dtype=np.float32), 2, None, None)
            with self.assertLogs(level="WARNING"):
                audio = recorder.stop()
        stream.close.assert_called_once()
        np.testing.assert_allclose(audio, [0.1, 0.2])
        self.assertFalse(recorder.is_recording)
        self.assertIsNone(recorder._stream)

    def test_audio_taken_during_recording_is_not_returned_again(self):
        recorder = AudioRecorder()
        with patch("audio_recorder.sd.InputStream", return_value=Mock()):
            recorder.start()
            self.assertEqual(len(recorder.take_audio()), 0)
            recorder._audio_callback(np.array([[0.1], [0.2]], dtype=np.float32), 2, None, None)
            recorder._audio_callback(np.array([[0.3]], dtype=np.float32), 1, None, None)
            np.testing.assert_allclose(recorder.take_audio(), [0.1, 0.2, 0.3])
            self.assertEqual(len(recorder.take_audio()), 0)
            recorder._audio_callback(np.array([[0.4]], dtype=np.float32), 1, None, None)
            np.testing.assert_allclose(recorder.stop(), [0.4])
        self.assertEqual(recorder.get_status().samples, 4)

    def test_stop_after_all_audio_was_taken_returns_nothing(self):
        recorder = AudioRecorder()
        with patch("audio_recorder.sd.InputStream", return_value=Mock()):
            recorder.start()
            recorder._audio_callback(np.array([[0.1]], dtype=np.float32), 1, None, None)
            recorder.take_audio()
            self.assertIsNone(recorder.stop())

    def test_callback_after_stop_does_not_leak_into_next_recording(self):
        recorder = AudioRecorder()
        recorder._audio_callback(np.ones((2, 1)), 2, None, None)
        self.assertEqual(recorder._frames, [])
