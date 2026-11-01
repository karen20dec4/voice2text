import sounddevice as sd
import numpy as np
import threading
import logging
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioStatus:
    rms: float = 0.0
    peak: float = 0.0
    session_peak: float = 0.0
    samples: int = 0
    duration: float = 0.0
    callbacks: int = 0
    callback_warnings: int = 0
    started_at: float = 0.0
    last_callback_at: float = 0.0
    device_name: str = "Microfon implicit"

class AudioRecorder:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.is_recording = False
        self._frames = []
        self._lock = threading.Lock()
        self._stream = None
        self._device_name = "Microfon implicit"
        self._reset_levels()

    def _reset_levels(self):
        self._rms = self._peak = self._session_peak = 0.0
        self._samples = self._callbacks = self._callback_warnings = 0
        self._started_at = self._last_callback_at = 0.0

    def get_status(self):
        with self._lock:
            return AudioStatus(
                rms=self._rms, peak=self._peak, session_peak=self._session_peak,
                samples=self._samples, duration=self._samples / self.sample_rate,
                callbacks=self._callbacks, callback_warnings=self._callback_warnings,
                started_at=self._started_at, last_callback_at=self._last_callback_at,
                device_name=self._device_name)

    def _audio_callback(self, indata, frames, time_info, status):
        with self._lock:
            if self.is_recording:
                self._frames.append(indata.copy())
                self._rms = float(np.sqrt(np.mean(np.square(indata)))) if indata.size else 0.0
                self._peak = float(np.max(np.abs(indata))) if indata.size else 0.0
                self._session_peak = max(self._session_peak, self._peak)
                self._samples += len(indata)
                self._callbacks += 1
                self._callback_warnings += bool(status)
                self._last_callback_at = time.monotonic()

    def start(self, device_index=None):
        if self.is_recording:
            return
        with self._lock:
            self._frames = []
            self._reset_levels()
            self._started_at = time.monotonic()
            self.is_recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=device_index,
                callback=self._audio_callback
            )
            actual_device = self._stream.device
            if isinstance(actual_device, int):
                try:
                    name = sd.query_devices(actual_device)["name"]
                    with self._lock:
                        self._device_name = f"[{actual_device}] {name}"
                except Exception:
                    logging.warning("Nu pot identifica numele microfonului")
            self._stream.start()
            logging.info("Captură pornită: microfon=%s rata=%s Hz", self._device_name, self.sample_rate)
        except Exception:
            with self._lock:
                self.is_recording = False
                self._frames = []
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    logging.exception("Eroare închidere microfon după pornire eșuată")
                finally:
                    self._stream = None
            raise

    def stop(self):
        if not self.is_recording:
            return None
        with self._lock:
            self.is_recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                logging.warning("Microfonul s-a deconectat în timpul opririi")
            finally:
                try:
                    self._stream.close()
                except Exception:
                    logging.exception("Eroare închidere microfon")
                finally:
                    self._stream = None

        with self._lock:
            if not self._frames:
                return None
            audio_data = np.concatenate(self._frames, axis=0)
            self._frames = []

        # audio_data is 2D (samples, 1). Flatten to 1D (samples,)
        audio_data = audio_data.flatten()
        status = self.get_status()
        logging.info("Captură oprită: durata=%.2f s mostre=%s vârf=%.5f avertismente=%s",
                     status.duration, status.samples, status.session_peak, status.callback_warnings)
        return audio_data

    @staticmethod
    def get_input_devices():
        devices = []
        try:
            device_list = sd.query_devices()
            for idx, dev in enumerate(device_list):
                if dev.get("max_input_channels", 0) > 0:
                    name = f"[{idx}] {dev.get('name')}"
                    devices.append((idx, name))
        except Exception as e:
            print("Eroare la detectare microfoane:", e)
        return devices
