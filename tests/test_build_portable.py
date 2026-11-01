from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pywintypes

import build_portable


class PortableBuildTests(unittest.TestCase):
    def exercise_install(self, already_running):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "_internal").mkdir()
        (root / "_internal" / "runtime.dll").write_bytes(b"old runtime")
        (root / "Voice2Text.exe").write_bytes(b"old executable")

        def compile_bundle(*args, **kwargs):
            bundle = root / ".build" / "dist" / "Voice2Text"
            (bundle / "_internal").mkdir(parents=True)
            (bundle / "_internal" / "runtime.dll").write_bytes(b"new runtime")
            (bundle / "Voice2Text.exe").write_bytes(b"new executable")

        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(build_portable, "__file__", str(root / "build_portable.py")))
        stack.enter_context(patch.object(build_portable.subprocess, "run", side_effect=compile_bundle))
        stack.enter_context(patch.object(build_portable.win32event, "OpenMutex",
                                        side_effect=pywintypes.error(2, "OpenMutex", "Not found")))
        stack.enter_context(patch.object(build_portable.win32event, "CreateMutex", return_value=123))
        stack.enter_context(patch.object(build_portable.win32api, "GetLastError", return_value=183 if already_running else 0))
        stack.enter_context(patch.object(build_portable.win32api, "CloseHandle"))
        return root

    def test_app_started_during_compilation_leaves_installed_files_unchanged(self):
        root = self.exercise_install(already_running=True)
        with self.assertRaises(RuntimeError):
            build_portable.main()
        self.assertEqual((root / "Voice2Text.exe").read_bytes(), b"old executable")
        self.assertEqual((root / "_internal" / "runtime.dll").read_bytes(), b"old runtime")

    def test_bundle_is_installed_at_project_root(self):
        root = self.exercise_install(already_running=False)
        with redirect_stdout(io.StringIO()):
            build_portable.main()
        self.assertEqual((root / "Voice2Text.exe").read_bytes(), b"new executable")
        self.assertEqual((root / "_internal" / "runtime.dll").read_bytes(), b"new runtime")
