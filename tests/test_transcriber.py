import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch

from gpu_engine import VulkanWhisper
from transcriber import CUDA_LIBRARIES, WhisperTranscriber, _cuda_ready


class TranscriberTests(unittest.TestCase):
    def setUp(self):
        no_vulkan = patch("transcriber.vulkan_device", return_value=None)
        no_vulkan.start()
        self.addCleanup(no_vulkan.stop)

    def test_model_downloads_use_the_project_cache(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small")
        local_cache = "H:/_Proiecte/Voice2Text/models"
        with patch("transcriber.get_models_path", return_value=local_cache), patch("transcriber.WhisperModel") as factory:
            transcriber._load_model("small")
        self.assertEqual(factory.call_args.kwargs["download_root"], local_cache)

    def test_cuda_is_used_when_ready(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small")
        model = Mock()
        model.transcribe.return_value = ([], None)
        with patch("transcriber._cuda_ready", return_value=True), patch(
                "transcriber.WhisperModel", return_value=model) as factory:
            transcriber._load_model("small")
        self.assertEqual(factory.call_args.kwargs["device"], "cuda")
        self.assertEqual(factory.call_args.kwargs["compute_type"], "float16")
        self.assertEqual(transcriber.device, "cuda")

    def test_failed_cuda_run_falls_back_to_cpu(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small")
        broken, working = Mock(), Mock()
        broken.transcribe.side_effect = RuntimeError("Library cublas64_12.dll is not found")
        with self.assertLogs(level="ERROR"), patch("transcriber._cuda_ready", return_value=True), patch(
                "transcriber.WhisperModel", side_effect=[broken, working]) as factory:
            transcriber._load_model("small")
        self.assertEqual(factory.call_args.kwargs["device"], "cpu")
        self.assertIs(transcriber.model, working)
        self.assertEqual(transcriber.device, "cpu")
        self.assertTrue(transcriber.is_ready())

    def test_cpu_setting_never_touches_the_gpu(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small", compute_device="cpu")
        with patch("transcriber._cuda_ready", return_value=True) as ready, patch(
                "transcriber.vulkan_device", return_value="Radeon") as vulkan, patch("transcriber.WhisperModel"):
            transcriber._load_model("small")
        ready.assert_not_called()
        vulkan.assert_not_called()
        self.assertEqual(transcriber.device, "cpu")

    def test_vulkan_is_used_without_cuda(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("medium")
        with patch("transcriber._cuda_ready", return_value=False), patch(
                "transcriber.vulkan_device", return_value="Radeon"), patch(
                "transcriber.VulkanWhisper") as engine, patch("transcriber.WhisperModel") as cpu:
            transcriber._load_model("medium")
        engine.assert_called_once_with("medium")
        cpu.assert_not_called()
        self.assertEqual(transcriber.device, "vulkan")

    def test_failed_vulkan_falls_back_to_cpu(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("medium")
        with self.assertLogs(level="ERROR"), patch("transcriber._cuda_ready", return_value=False), patch(
                "transcriber.vulkan_device", return_value="Radeon"), patch(
                "transcriber.VulkanWhisper", side_effect=RuntimeError("no memory")), patch("transcriber.WhisperModel"):
            transcriber._load_model("medium")
        self.assertEqual(transcriber.device, "cpu")
        self.assertTrue(transcriber.is_ready())

    def test_failed_cuda_still_tries_vulkan(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("medium")
        with self.assertLogs(level="ERROR"), patch("transcriber._cuda_ready", return_value=True), patch(
                "transcriber._load_on_cuda", side_effect=RuntimeError("no cuBLAS")), patch(
                "transcriber.vulkan_device", return_value="GeForce"), patch("transcriber.VulkanWhisper"):
            transcriber._load_model("medium")
        self.assertEqual(transcriber.device, "vulkan")

    def test_vulkan_model_receives_the_language(self):
        with patch("transcriber.threading.Thread"):
            transcriber = WhisperTranscriber("small")
        engine = Mock(spec=VulkanWhisper)
        engine.transcribe.return_value = "Salut"
        transcriber.model = engine
        transcriber._loading = False
        self.assertEqual(transcriber.transcribe([0.1], language="en"), "Salut")
        engine.transcribe.assert_called_once_with([0.1], "en")

    def test_missing_nvidia_libraries_block_cuda_before_inference(self):
        with TemporaryDirectory() as empty, patch("transcriber.ctranslate2.get_cuda_device_count", return_value=1), patch(
                "transcriber.get_cuda_path", return_value=empty), patch.dict(os.environ, {"PATH": empty}):
            with self.assertLogs(level="WARNING"):
                self.assertFalse(_cuda_ready())
            for name in CUDA_LIBRARIES:
                Path(empty, name).touch()
            self.assertTrue(_cuda_ready())

    def test_no_nvidia_card_means_no_cuda(self):
        with patch("transcriber.ctranslate2.get_cuda_device_count", return_value=0):
            self.assertFalse(_cuda_ready())

    def test_changing_the_setting_reloads_the_same_model(self):
        with patch("transcriber.threading.Thread") as thread:
            transcriber = WhisperTranscriber("small")
            with patch("transcriber.WhisperModel"):
                transcriber._load_model("small")
            thread.reset_mock()
            transcriber.load_model_async("small")
            thread.assert_not_called()
            transcriber.load_model_async("small", "cpu")
            thread.assert_called_once()

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
