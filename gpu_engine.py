"""Whisper on any Vulkan GPU, through gpu/voice2text_whisper.dll (see native/)."""
import ctypes
import logging
import os
import threading

from faster_whisper.vad import VadOptions, collect_chunks, get_speech_timestamps
from huggingface_hub import hf_hub_download
import numpy as np

from config import get_gpu_path, get_models_path

MODEL_REPOSITORY = "ggerganov/whisper.cpp"
MODEL_FILES = {
    "tiny": "ggml-tiny-q5_1.bin",
    "base": "ggml-base-q5_1.bin",
    "small": "ggml-small-q5_1.bin",
    "medium": "ggml-medium-q5_0.bin",
}
DECODER_THREADS = 4
PF_AVX2_INSTRUCTIONS_AVAILABLE = 40

_library = None


def _load_library():
    global _library
    if _library is not None:
        return _library
    path = os.path.join(get_gpu_path(), "voice2text_whisper.dll")
    # The DLL is built for AVX2; without it the first call ends the process.
    if not os.path.isfile(path) or not ctypes.windll.kernel32.IsProcessorFeaturePresent(
            PF_AVX2_INSTRUCTIONS_AVAILABLE):
        return None
    library = ctypes.CDLL(path)
    library.v2t_gpu_name.argtypes = [ctypes.c_char_p, ctypes.c_int]
    library.v2t_gpu_name.restype = ctypes.c_int
    library.v2t_load.argtypes = [ctypes.c_wchar_p]
    library.v2t_load.restype = ctypes.c_void_p
    library.v2t_unload.argtypes = [ctypes.c_void_p]
    library.v2t_unload.restype = None
    library.v2t_transcribe.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int,
                                       ctypes.c_char_p, ctypes.c_int]
    library.v2t_transcribe.restype = ctypes.c_void_p
    library.v2t_free_text.argtypes = [ctypes.c_void_p]
    library.v2t_free_text.restype = None
    _library = library
    return library


def vulkan_device():
    """Name of the usable GPU, or None."""
    try:
        library = _load_library()
        if library is None:
            return None
        name = ctypes.create_string_buffer(256)
        if not library.v2t_gpu_name(name, len(name)):
            return None
        return name.value.decode("utf-8", errors="replace")
    except Exception:
        logging.exception("Verificare Vulkan eșuată")
        return None


def _model_path(model_size):
    folder = os.path.join(get_models_path(), "ggml")
    path = os.path.join(folder, MODEL_FILES[model_size])
    if not os.path.isfile(path):
        hf_hub_download(MODEL_REPOSITORY, MODEL_FILES[model_size], local_dir=folder)
    return path


def _speech_only(audio):
    # whisper.cpp's own VAD dropped whole phrases in tests; keep the CPU path's filter.
    options = VadOptions(min_silence_duration_ms=500, max_speech_duration_s=30)
    speech = get_speech_timestamps(audio, options)
    if not speech:
        return None
    chunks, _ = collect_chunks(audio, speech)
    return np.concatenate(chunks)


class VulkanWhisper:
    def __init__(self, model_size):
        self._lock = threading.Lock()
        self._context = None
        self._library = _load_library()
        path = _model_path(model_size)
        self._context = self._library.v2t_load(path)
        if not self._context:
            raise RuntimeError(f"whisper.cpp nu a putut încărca {path}")
        # The first run compiles shaders; do it now, not on the first dictation.
        self._run(np.zeros(16000, dtype=np.float32), "en")

    def __del__(self):
        if self._context:
            self._library.v2t_unload(self._context)

    def _run(self, audio, language):
        samples = audio.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        with self._lock:
            result = self._library.v2t_transcribe(self._context, samples, len(audio),
                                                  language.encode("ascii"), DECODER_THREADS)
        if not result:
            raise RuntimeError("Transcriere Vulkan eșuată")
        try:
            return ctypes.string_at(result).decode("utf-8", errors="replace").strip()
        finally:
            self._library.v2t_free_text(result)

    def transcribe(self, audio, language):
        speech = _speech_only(np.asarray(audio, dtype=np.float32))
        if speech is None:
            return ""
        return self._run(speech, language)
