import ctypes
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

import gpu_engine
from gpu_engine import VulkanWhisper, vulkan_device


class FakeLibrary:
    """Stands in for the DLL and records what Python sends it."""

    def __init__(self, text=b" Salut, lume!"):
        self.text = ctypes.create_string_buffer(text)
        self.calls = []
        self.prompts = []
        self.freed = 0
        self.unloaded = 0

    def v2t_load(self, path):
        return 7

    def v2t_unload(self, context):
        self.unloaded += 1

    def v2t_transcribe(self, context, samples, count, language, threads, prompt):
        self.calls.append((count, language))
        self.prompts.append(prompt)
        return ctypes.addressof(self.text)

    def v2t_free_text(self, text):
        self.freed += 1


class VulkanWhisperTests(unittest.TestCase):
    def engine(self, library):
        with patch("gpu_engine._load_library", return_value=library), patch(
                "gpu_engine._model_path", return_value="model.bin"):
            return VulkanWhisper("medium")

    def test_loading_warms_up_the_gpu(self):
        library = FakeLibrary()
        self.engine(library)
        self.assertEqual(library.calls, [(16000, b"en")])

    def test_speech_is_sent_and_text_is_released(self):
        library = FakeLibrary()
        engine = self.engine(library)
        with patch("gpu_engine._speech_only", return_value=np.zeros(4, dtype=np.float32)):
            self.assertEqual(engine.transcribe([0.1, 0.2], "ro"), "Salut, lume!")
        self.assertEqual(library.calls[-1], (4, b"ro"))
        self.assertEqual(library.freed, 2)

    def test_prompt_reaches_the_gpu_as_utf8(self):
        library = FakeLibrary()
        engine = self.engine(library)
        with patch("gpu_engine._speech_only", return_value=np.zeros(4, dtype=np.float32)):
            engine.transcribe([0.1], "ro", "Dictare cu diacritice: ă, ș, ț.")
        self.assertEqual(library.prompts, [None, "Dictare cu diacritice: ă, ș, ț.".encode("utf-8")])

    def test_silence_never_reaches_the_gpu(self):
        library = FakeLibrary()
        engine = self.engine(library)
        with patch("gpu_engine._speech_only", return_value=None):
            self.assertEqual(engine.transcribe([0.0], "ro"), "")
        self.assertEqual(len(library.calls), 1)

    def test_failed_load_is_an_error(self):
        library = FakeLibrary()
        library.v2t_load = lambda path: None
        with self.assertRaises(RuntimeError):
            self.engine(library)

    def test_failed_transcription_is_an_error(self):
        library = FakeLibrary()
        engine = self.engine(library)
        library.v2t_transcribe = lambda *args: None
        with self.assertRaises(RuntimeError):
            engine._run(np.zeros(4, dtype=np.float32), "ro")

    def test_released_engine_unloads_the_model(self):
        library = FakeLibrary()
        engine = self.engine(library)
        engine.__del__()
        self.assertEqual(library.unloaded, 1)


class ModelPathTests(unittest.TestCase):
    def test_every_size_has_a_gpu_model(self):
        self.assertEqual(set(gpu_engine.MODEL_FILES), {"tiny", "base", "small", "medium"})

    def test_existing_model_is_not_downloaded_again(self):
        with tempfile.TemporaryDirectory() as folder, patch(
                "gpu_engine.get_models_path", return_value=folder), patch("gpu_engine.hf_hub_download") as download:
            Path(folder, "ggml").mkdir()
            Path(folder, "ggml", "ggml-small-q5_1.bin").touch()
            self.assertTrue(gpu_engine._model_path("small").endswith("ggml-small-q5_1.bin"))
        download.assert_not_called()

    def test_missing_model_downloads_inside_the_project(self):
        with tempfile.TemporaryDirectory() as folder, patch(
                "gpu_engine.get_models_path", return_value=folder), patch("gpu_engine.hf_hub_download") as download:
            gpu_engine._model_path("medium")
        self.assertEqual(download.call_args.args[1], "ggml-medium-q5_0.bin")
        self.assertEqual(download.call_args.kwargs["local_dir"], str(Path(folder, "ggml")))


class DeviceTests(unittest.TestCase):
    def test_no_library_means_no_vulkan(self):
        with patch("gpu_engine._load_library", return_value=None):
            self.assertIsNone(vulkan_device())

    def test_unloadable_library_means_no_vulkan(self):
        with self.assertLogs(level="ERROR"), patch("gpu_engine._load_library", side_effect=OSError("no vulkan-1.dll")):
            self.assertIsNone(vulkan_device())

    def test_library_without_a_gpu_means_no_vulkan(self):
        library = Mock()
        library.v2t_gpu_name.return_value = 0
        with patch("gpu_engine._load_library", return_value=library):
            self.assertIsNone(vulkan_device())
