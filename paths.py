import datetime
import os
import shutil
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def get_data_dir() -> str:
    """
    Mengembalikan direktori penyimpanan data persisten pengguna
    (config.json, overlay.pid, err.log, dan venv).
    """
    env_dir = os.environ.get("TASK_OVERLAY_DATA_DIR", "").strip()
    data_dir = env_dir if env_dir else os.path.join(os.path.expanduser("~"), ".antigravity-task-overlay")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_config_path() -> str:
    """
    Mengembalikan path config.json di direktori data pengguna.
    Jika belum ada tetapi config.json lama ada di APP_DIR, salin sekali sebagai awal.
    """
    cfg_path = os.path.join(get_data_dir(), "config.json")
    if not os.path.exists(cfg_path):
        legacy_cfg = os.path.join(APP_DIR, "config.json")
        if os.path.exists(legacy_cfg) and os.path.abspath(legacy_cfg) != os.path.abspath(cfg_path):
            try:
                shutil.copy2(legacy_cfg, cfg_path)
            except Exception:
                pass
    return cfg_path


def get_pid_path() -> str:
    return os.path.join(get_data_dir(), "overlay.pid")


def get_err_log_path() -> str:
    return os.path.join(get_data_dir(), "err.log")


def log_exception(context_label: str, exc_type=None, exc_value=None, exc_tb=None) -> None:
    """Menulis exception ke err.log di direktori data pengguna."""
    try:
        with open(get_err_log_path(), "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] {context_label}:\n")
            if exc_type is not None:
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
            else:
                traceback.print_exc(file=f)
    except Exception:
        pass
