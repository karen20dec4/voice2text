import logging
import os
import threading
import sys

import ctranslate2
import numpy as np
from faster_whisper import WhisperModel
from huggingface_hub.utils import disable_progress_bars
from config import get_cuda_path, get_models_path
from gpu_engine import VulkanWhisper, vulkan_device

CUDA_LIBRARIES = ("cublas64_12.dll", "cudnn_ops64_9.dll")
# More threads got slower on a 16-core Ryzen: 8 beat both 4 and 16.
CPU_THREADS = max(4, min(8, (os.cpu_count() or 8) // 2))


def _add_cuda_folder_to_path():
    folder = get_cuda_path()
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if os.path.isdir(folder) and folder not in entries:
        os.environ["PATH"] = os.pathsep.join([folder, *entries])


def _cuda_ready():
    _add_cuda_folder_to_path()
    try:
        if ctranslate2.get_cuda_device_count() < 1:
            return False
    except Exception:
        logging.exception("Verificare CUDA eșuată")
        return False
    # A missing cuDNN ends the whole process during inference, beyond any except.
    entries = os.environ.get("PATH", "").split(os.pathsep)
    missing = [name for name in CUDA_LIBRARIES
               if not any(os.path.isfile(os.path.join(entry, name)) for entry in entries if entry)]
    if missing:
        logging.warning("Placă NVIDIA găsită, dar lipsesc %s; rulează Install-CUDA-Libs.ps1", missing)
    return not missing


def _load_on_cuda(model_size):
    model = WhisperModel(model_size, device="cuda", compute_type="float16",
                         download_root=get_models_path())
    # cuBLAS loads lazily, so only a real run proves this GPU can transcribe.
    segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language="en",
                                   beam_size=1, vad_filter=False)
    list(segments)
    return model


class WhisperTranscriber:
    def __init__(self, model_size="small", status_callback=None, compute_device="gpu"):
        # pythonw/PyInstaller --noconsole have no stderr. Hub's per-file tqdm
        # bars otherwise crash while holding their shared lock and can stall
        # the remaining download workers. Progress belongs in the GUI here.
        if sys.stderr is None:
            disable_progress_bars()
        self.model_size = None  # Name of the model actually loaded.
        self.device = None  # Where it runs: "cuda", "vulkan" or "cpu".
        self.compute_device = compute_device  # Latest setting: "gpu" or "cpu".
        self._loaded_setting = None
        self.status_callback = status_callback
        self.model = None
        self._loading = False
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._request_id = 0
        self.load_model_async(model_size)

    def load_model_async(self, model_size, compute_device=None):
        with self._lock:
            compute_device = compute_device or self.compute_device
            self.compute_device = compute_device
            if (not self._loading and self.model is not None and self.model_size == model_size
                    and self._loaded_setting == compute_device):
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
            with self._lock:
                setting = self.compute_device
            self._notify(f"Se încarcă Whisper ({model_size})...")
            logging.info("Încărcare Whisper începută: %s", model_size)
            try:
                model, device = self._create_model(model_size, setting)
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
                self.device = device
                self._loaded_setting = setting
                self._loading = False
            logging.info("Model Whisper pregătit: %s pe %s", model_size, device)
            self._notify("Gata de dictare")

    @staticmethod
    def _create_model(model_size, setting):
        if setting != "cpu" and _cuda_ready():
            try:
                return _load_on_cuda(model_size), "cuda"
            except Exception:
                logging.exception("CUDA a eșuat pentru %s", model_size)
        gpu_name = vulkan_device() if setting != "cpu" else None
        if gpu_name:
            try:
                model = VulkanWhisper(model_size)
                logging.info("Vulkan pe %s", gpu_name)
                return model, "vulkan"
            except Exception:
                logging.exception("Vulkan a eșuat pentru %s; continui pe CPU", model_size)
        model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=CPU_THREADS,
                             download_root=get_models_path())
        return model, "cpu"

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
        if isinstance(model, VulkanWhisper):
            return model.transcribe(audio_data, language)
        segments, _ = model.transcribe(
            audio_data,
            language=None if language == "auto" else language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
