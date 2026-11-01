import unittest
from unittest.mock import Mock, patch

import settings_window


class SettingsTests(unittest.TestCase):
    def make_form(self, hotkey="f9"):
        form = Mock()
        form.config = {"hotkey": "f8", "model_size": "small"}
        form.models_map = {"Small": "small"}
        form.lang_map = {"Română": "ro"}
        form.dev_map = {"Default": None}
        for name, value in [("cb_model", "Small"), ("cb_lang", "Română"), ("cb_mic", "Default"),
                            ("entry_hotkey", hotkey), ("var_floating", True), ("var_space", True),
                            ("var_enter", False)]:
            getattr(form, name).get.return_value = value
        return form

    def test_failed_save_leaves_configuration_and_dialog_intact(self):
        form = self.make_form()
        form.on_save_callback.side_effect = OSError("read only")
        with patch.object(settings_window, "save_config"), patch.object(settings_window.messagebox, "showerror"):
            settings_window.SettingsWindow._save(form)
        self.assertEqual(form.config, {"hotkey": "f8", "model_size": "small"})
        form.destroy.assert_not_called()

    def test_invalid_shortcut_is_not_applied(self):
        form = self.make_form("not-a-real-key")
        with patch.object(settings_window, "save_config"), patch.object(settings_window.messagebox, "showerror"):
            settings_window.SettingsWindow._save(form)
        self.assertEqual(form.config["hotkey"], "f8")
        form.on_save_callback.assert_not_called()
        form.destroy.assert_not_called()
