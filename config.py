import json
import os
import logging
import math
import sys
import tempfile

DEFAULT_CONFIG = {
    "model_size": "small",         # "tiny", "base", "small", "medium"
    "compute_device": "gpu",       # "gpu" = CUDA or Vulkan when usable, else CPU; "cpu"
    "language": "ro",              # "ro", "en", "auto"
    "hotkey": "f9",                # e.g., "f9", "ctrl+alt+space", "alt+d"
    "device_index": None,          # None = default mic
    "auto_enter": False,           # press enter after typing
    "add_trailing_space": True,    # add space after dictated text
    "window_x": 100,
    "window_y": 100,
    "floating_visible": True,
    "window_scale": 1.0
}

def get_app_dir():
    # PyInstaller's __file__ points inside _internal, not beside the EXE.
    base = sys.executable if getattr(sys, "frozen", False) else __file__
    return os.path.dirname(os.path.abspath(base))


def get_config_path():
    return os.path.join(get_app_dir(), "config.json")


def get_models_path():
    return os.path.join(get_app_dir(), "models")


def get_cuda_path():
    return os.path.join(get_app_dir(), "cuda")


def get_gpu_path():
    return os.path.join(get_app_dir(), "gpu")


CONFIG_FILE = get_config_path()


def _valid_value(key, value):
    if key == "model_size":
        return value in ("tiny", "base", "small", "medium")
    if key == "compute_device":
        return value in ("gpu", "cpu")
    if key == "language":
        return value in ("ro", "en", "auto")
    if key == "hotkey":
        return isinstance(value, str) and bool(value.strip()) and len(value) <= 100
    if key == "device_index":
        return value is None or (type(value) is int and value >= 0)
    if key in ("window_x", "window_y"):
        return type(value) is int
    if key == "window_scale":
        return type(value) in (int, float) and math.isfinite(value) and 0.5 <= value <= 3
    return type(value) is bool

def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                if not isinstance(user_cfg, dict):
                    raise ValueError("Configurația trebuie să fie un obiect JSON")
                for key in DEFAULT_CONFIG:
                    if key in user_cfg and _valid_value(key, user_cfg[key]):
                        config[key] = user_cfg[key]
        except Exception as e:
            logging.warning("Eroare citire config: %s", e)
    return config

def save_config(config):
    directory = os.path.dirname(os.path.abspath(CONFIG_FILE))
    fd, temporary = tempfile.mkstemp(prefix=".voice2text-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, CONFIG_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
