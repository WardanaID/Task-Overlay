import sys
import os
import signal
import argparse

# Fix High DPI scaling di Windows
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

from paths import get_pid_path, log_exception


def excepthook(exc_type, exc_value, exc_tb):
    """
    Global exception hook untuk menangkap unhandled exception di PyQt6 event loop
    dan mencatatnya ke err.log agar aplikasi tidak crash tertutup tanpa jejak.
    """
    log_exception("Unhandled Qt Exception", exc_type, exc_value, exc_tb)


def is_process_alive(pid: int) -> bool:
    """
    Mengecek apakah proses dengan PID tertentu masih berjalan.
    """
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
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
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def stop_existing_instance():
    """
    Menghentikan instance overlay lama jika masih berjalan agar tidak terjadi duplikasi jendela.
    """
    pid_file = get_pid_path()
    if not os.path.exists(pid_file):
        return
    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            old_pid = int(f.read().strip())
        if old_pid != os.getpid() and is_process_alive(old_pid):
            if sys.platform == "win32":
                import ctypes
                PROCESS_TERMINATE = 0x0001
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, old_pid)
                if handle:
                    ctypes.windll.kernel32.TerminateProcess(handle, 0)
                    ctypes.windll.kernel32.CloseHandle(handle)
            else:
                os.kill(old_pid, signal.SIGTERM)
    except Exception:
        pass


def write_pid_file():
    try:
        with open(get_pid_path(), "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def remove_pid_file(force: bool = False):
    try:
        pid_file = get_pid_path()
        if os.path.exists(pid_file):
            if force:
                os.remove(pid_file)
                return
            with open(pid_file, "r", encoding="utf-8") as f:
                saved_pid = int(f.read().strip())
            if saved_pid == os.getpid():
                os.remove(pid_file)
    except Exception:
        pass


def main():
    sys.excepthook = excepthook

    parser = argparse.ArgumentParser(description="Antigravity Task Overlay")
    parser.add_argument("--parent-pid", type=int, default=0, help="PID proses IDE induk untuk auto-close")
    parser.add_argument("--data-dir", type=str, default="", help="Direktori data persisten pengguna")
    parser.add_argument("--stop", action="store_true", help="Hentikan instance overlay yang sedang berjalan")
    args, unknown = parser.parse_known_args()

    if args.data_dir:
        os.environ["TASK_OVERLAY_DATA_DIR"] = args.data_dir

    if args.stop:
        stop_existing_instance()
        remove_pid_file(force=True)
        return

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from overlay_window import TaskOverlayWindow

    stop_existing_instance()
    write_pid_file()

    # Set Windows App User Model ID agar icon dan window taskbar teridentifikasi dengan benar
    if sys.platform == "win32":
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
        log_exception("Main Exception")
        remove_pid_file()
        raise


if __name__ == "__main__":
    main()
