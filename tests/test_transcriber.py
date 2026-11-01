import threading
import unittest
from unittest.mock import Mock, patch

from transcriber import WhisperTranscriber


class TranscriberTests(unittest.TestCase):
    def test_model_downloads_use_the_project_cache(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small")
        local_cache = "H:/_Proiecte/Voice2Text/models"
        with patch("transcriber.get_models_path", return_value=local_cache), patch("transcriber.WhisperModel") as factory:
            transcriber._load_model("small")
        self.assertEqual(factory.call_args.kwargs["download_root"], local_cache)

    def test_failed_reload_preserves_actual_model_name(self):
        old = Mock()
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small")
        with patch("transcriber.WhisperModel", return_value=old):
            transcriber._load_model("small")
        with self.assertLogs(level="ERROR"), patch("transcriber.WhisperModel", side_effect=RuntimeError("offline")):
            transcriber._load_model("medium")
        self.assertEqual(transcriber.model_size, "small")
        self.assertIs(transcriber.model, old)
        self.assertTrue(transcriber.is_ready())

    def test_pending_load_immediately_blocks_recording(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small")
            transcriber.model = Mock()
            transcriber._loading = False
            transcriber.load_model_async("medium")
            self.assertFalse(transcriber.is_ready())

    def test_transcription_error_is_not_reported_as_silence(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small")
        transcriber.model = Mock()
        transcriber.model.transcribe.side_effect = RuntimeError("inference failed")
        transcriber._loading = False
        with self.assertRaisesRegex(RuntimeError, "inference failed"):
            transcriber.transcribe([0.1, 0.2])

    def test_auto_language_and_segment_text(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small")
        transcriber.model = Mock()
        transcriber._loading = False
        transcriber.model.transcribe.return_value = ([Mock(text=" Salut "), Mock(text=" "), Mock(text="lume!")], None)
        self.assertEqual(transcriber.transcribe([0.1], language="auto"), "Salut lume!")
        self.assertIsNone(transcriber.model.transcribe.call_args.kwargs["language"])

    def test_latest_model_request_wins_when_loading_is_slow(self):
        started, release = threading.Event(), threading.Event()
        models = {"small": Mock(), "base": Mock()}
        loaded = []

        def factory(size, **kwargs):
            loaded.append(size)
            if size == "small":
                started.set()
                if not release.wait(3):
                    raise RuntimeError("test loader timed out")
            return models[size]

        with patch("transcriber.WhisperModel", side_effect=factory):
            transcriber = WhisperTranscriber("small")
            try:
                self.assertTrue(started.wait(2))
                transcriber.load_model_async("medium")
                transcriber.load_model_async("base")
            finally:
                release.set()
                for thread in threading.enumerate():
                    if thread.name.startswith("whisper-load-"):
                        thread.join(3)
        self.assertEqual(loaded, ["small", "base"])
        self.assertEqual(transcriber.model_size, "base")
        self.assertIs(transcriber.model, models["base"])
        self.assertTrue(transcriber.is_ready())
