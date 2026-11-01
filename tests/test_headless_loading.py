import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class HeadlessLoadingTests(unittest.TestCase):
    def test_model_loader_can_use_hub_progress_without_a_console(self):
        """Exercise the real Hub/tqdm boundary in pythonw; never download a model."""
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="voice2text-headless-test-") as temporary:
            folder = Path(temporary)
            script = folder / "probe.py"
            result = folder / "result.json"
            script.write_text('''import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
from huggingface_hub.utils import enable_progress_bars, tqdm
from transcriber import WhisperTranscriber
enable_progress_bars()
def model_factory(*args, **kwargs):
    with tqdm(total=1, desc="Metadata transfer") as progress:
        progress.update(1)
    return object()
with patch("transcriber.WhisperModel", side_effect=model_factory):
    transcriber = WhisperTranscriber("medium")
    for _ in range(60):
        if transcriber.is_ready() or not transcriber._loading:
            break
        time.sleep(0.05)
    Path(sys.argv[1]).write_text(json.dumps({"ready": transcriber.is_ready(),
                                           "model": transcriber.model_size,
                                           "no_console": sys.stderr is None}))
''', encoding="utf-8")
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            environment = dict(os.environ, PYTHONPATH=str(root))
            environment.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
            process = subprocess.run([str(pythonw), str(script), str(result)],
                                     env=environment,
                                     creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            self.assertEqual(process.returncode, 0)
            self.assertTrue(result.exists(), "Headless loader did not report its state")
            state = json.loads(result.read_text())
            self.assertTrue(state["no_console"])
            self.assertTrue(state["ready"], "Hub progress crashed while no console stream existed")
            self.assertEqual(state["model"], "medium")
