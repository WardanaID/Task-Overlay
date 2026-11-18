import sys
import os
import signal
import datetime
import argparse

# Fix High DPI scaling di Windows
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from overlay_window import TaskOverlayWindow

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(APP_DIR, "overlay.pid")


def excepthook(exc_type, exc_value, exc_tb):
    """
    Global exception hook untuk menangkap unhandled exception di PyQt6 event loop
    dan mencatatnya ke err.log agar aplikasi tidak crash tertutup tanpa jejak.
    """
    import traceback
    err_path = os.path.join(APP_DIR, "err.log")
    try:
        with open(err_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] Unhandled Qt Exception:\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    except Exception:
        pass


def is_process_alive(pid: int) -> bool:
    """
    Mengecek apakah proses dengan PID tertentu masih berjalan di Windows.
    """
    if not pid or pid <= 0:
        return False
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        res = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        if not res:
            return False
        return exit_code.value == STILL_ACTIVE
    except Exception:
        return False


def stop_existing_instance():
    """
    Menghentikan instance overlay lama jika masih berjalan agar tidak terjadi duplikasi jendela.
    """
    if not os.path.exists(PID_FILE):
        return
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            old_pid = int(f.read().strip())
        if old_pid != os.getpid() and is_process_alive(old_pid):
            import ctypes
            PROCESS_TERMINATE = 0x0001
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, old_pid)
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 0)
                ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        pass


def write_pid_file():
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def remove_pid_file():
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r", encoding="utf-8") as f:
                saved_pid = int(f.read().strip())
            if saved_pid == os.getpid():
                os.remove(PID_FILE)
    except Exception:
        pass


def main():
    sys.excepthook = excepthook

    parser = argparse.ArgumentParser(description="Antigravity Task Overlay")
    parser.add_argument("--parent-pid", type=int, default=0, help="PID proses IDE induk untuk auto-close")
    args, unknown = parser.parse_known_args()

    stop_existing_instance()
    write_pid_file()

    # Set Windows App User Model ID agar icon dan window taskbar teridentifikasi dengan benar
    try:
        import ctypes
        myappid = 'antigravity.taskoverlay.app.v1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Antigravity Task Overlay")
        app.setQuitOnLastWindowClosed(False)
        app.aboutToQuit.connect(remove_pid_file)

        window = TaskOverlayWindow(parent_pid=args.parent_pid)
        window.show()

        # Watchdog Timer: Jika dijalankan dari IDE (--parent-pid), pantau apakah IDE masih terbuka
        if args.parent_pid > 0:
            watchdog = QTimer()
            def _check_parent():
                if getattr(window, "cfg_auto_close_with_ide", True):
                    if not is_process_alive(args.parent_pid):
                        window.save_config()
                        remove_pid_file()
                        app.quit()
            watchdog.timeout.connect(_check_parent)
            watchdog.start(1500)

        sys.exit(app.exec())
    except Exception:
        import traceback
        err_path = os.path.join(APP_DIR, "err.log")
        with open(err_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] Main Exception:\n")
            traceback.print_exc(file=f)
        remove_pid_file()
        raise


if __name__ == "__main__":
    main()
