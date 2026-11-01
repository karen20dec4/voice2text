import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"
        self.override = patch.object(config, "CONFIG_FILE", str(self.path))
        self.override.start()
        self.addCleanup(self.override.stop)

    def test_invalid_values_fall_back_without_losing_valid_settings(self):
        self.path.write_text(json.dumps({"model_size": "bogus", "language": "en",
                                         "window_x": "oops", "auto_enter": "false",
                                         "device_index": -1}), encoding="utf-8")
        loaded = config.load_config()
        self.assertEqual(loaded["model_size"], "small")
        self.assertEqual(loaded["language"], "en")
        self.assertEqual(loaded["window_x"], 100)
        self.assertIs(loaded["auto_enter"], False)
        self.assertIsNone(loaded["device_index"])

    def test_non_object_json_uses_defaults(self):
        self.path.write_text('[1, 2]', encoding="utf-8")
        with self.assertLogs(level="WARNING"):
            self.assertEqual(config.load_config(), config.DEFAULT_CONFIG)

    def test_failed_write_preserves_previous_config_and_reports_error(self):
        config.save_config({"language": "ro"})
        with patch.object(config.json, "dump", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                config.save_config({"language": "en"})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"language": "ro"})

    def test_frozen_config_is_next_to_executable(self):
        with patch.object(config.sys, "frozen", True, create=True), patch.object(
                config.sys, "executable", str(Path(self.temp.name) / "Voice2Text.exe")):
            self.assertEqual(config.get_config_path(), str(self.path))

    def test_frozen_models_are_next_to_executable(self):
        with patch.object(config.sys, "frozen", True, create=True), patch.object(
                config.sys, "executable", str(Path(self.temp.name) / "Voice2Text.exe")):
            self.assertEqual(config.get_models_path(), str(Path(self.temp.name) / "models"))

    def test_source_models_are_project_local(self):
        with patch.object(config.sys, "frozen", False, create=True):
            self.assertEqual(config.get_models_path(), str(Path(config.__file__).resolve().parent / "models"))
