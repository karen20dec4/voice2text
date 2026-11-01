import logging
import threading
import sys

from faster_whisper import WhisperModel
from huggingface_hub.utils import disable_progress_bars
from config import get_models_path


class WhisperTranscriber:
    def __init__(self, model_size="small", status_callback=None):
        # pythonw/PyInstaller --noconsole have no stderr. Hub's per-file tqdm
        # bars otherwise crash while holding their shared lock and can stall
        # the remaining download workers. Progress belongs in the GUI here.
        if sys.stderr is None:
            disable_progress_bars()
        self.model_size = None  # Name of the model actually loaded.
        self.status_callback = status_callback
        self.model = None
        self._loading = False
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._request_id = 0
        self.load_model_async(model_size)

    def load_model_async(self, model_size):
        with self._lock:
            if not self._loading and self.model is not None and self.model_size == model_size:
                return
            self._request_id += 1
            request_id = self._request_id
            self._loading = True
        threading.Thread(target=self._load_model, args=(model_size, request_id),
                         name=f"whisper-load-{request_id}", daemon=True).start()

    def _load_model(self, model_size, request_id=None):
        if request_id is None:
            with self._lock:
                self._request_id += 1
                request_id = self._request_id
                self._loading = True
        with self._load_lock:
            with self._lock:
                if request_id != self._request_id:
                    return
            self._notify(f"Se încarcă Whisper ({model_size})...")
            logging.info("Încărcare Whisper începută: %s", model_size)
            try:
                model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=4,
                                     download_root=get_models_path())
            except Exception as error:
                logging.exception("Eroare încărcare model %s", model_size)
                with self._lock:
                    if request_id != self._request_id:
                        return
                    self._loading = False
                self._notify(f"Eroare încărcare {model_size}: {error}")
                return
            with self._lock:
                if request_id != self._request_id:
                    return
                self.model = model
                self.model_size = model_size
                self._loading = False
            logging.info("Model Whisper pregătit: %s", model_size)
            self._notify("Gata de dictare")

    def _notify(self, message):
        if self.status_callback:
            self.status_callback(message)

    def is_ready(self):
        with self._lock:
            return self.model is not None and not self._loading

    def transcribe(self, audio_data, language="ro"):
        if audio_data is None or len(audio_data) == 0:
            return ""
        with self._lock:
            model = self.model
            if model is None or self._loading:
                raise RuntimeError("Modelul Whisper nu este pregătit")
        # Keep a local reference while settings may replace self.model.
        segments, _ = model.transcribe(
            audio_data,
            language=None if language == "auto" else language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
