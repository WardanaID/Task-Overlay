import os
import sys
import json
import time
import datetime
import re
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QComboBox, QGraphicsDropShadowEffect,
    QSizePolicy, QApplication
)
from PyQt6.QtCore import (
    Qt, QPoint, QTimer, QSize, QPropertyAnimation, QParallelAnimationGroup,
    QEasingCurve, pyqtProperty, QRectF, QEvent
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QCursor, QPainter, QBrush, QPen

from monitor import AntigravityMonitor, TaskEvent
from quota_widget import CircularQuotaRing
from animated_task_label import AnimatedTaskLabel
from model_badge import AnimatedModelBadge
from icons import get_svg_icon, get_svg_pixmap
from styles import DARK_THEME_QSS
from paths import get_config_path, log_exception

CONFIG_FILE = get_config_path()

# Konfigurasi Dimensi Dinamis (Mendukung 2, 3, hingga 4 baris + Resizable Width/Height)
BASE_PILL_HEIGHT = 38          # Tinggi dasar untuk 2 baris (Row 1 Header + Row 2 Task)
EXTRA_ROW_HEIGHT = 20          # Tambahan tinggi per baris ekstra (Row 3 / Row 4)
BASE_COLLAPSED_WIN_HEIGHT = 72 # Tinggi window collapsed untuk 2 baris
DEFAULT_EXPANDED_HEIGHT = 380
MIN_EXPANDED_HEIGHT = 250
MAX_EXPANDED_HEIGHT = 820

DEFAULT_WINDOW_WIDTH = 560
MIN_WINDOW_WIDTH = 360
MAX_WINDOW_WIDTH = 1200
RESIZE_MARGIN = 12


class LogItemWidget(QFrame):
    def __init__(self, event: TaskEvent, parent=None, on_command_clicked=None):
        super().__init__(parent)
        self.setObjectName("LogItem")
        self.event = event
        self.on_command_clicked = on_command_clicked

        if event.category == "command":
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(8)

        icon_meta = {
            "thinking": ("brain", "#c084fc"),
            "decision": ("help_circle", "#f59e0b"),
            "command": ("terminal", "#38bdf8"),
            "read": ("file_text", "#fbbf24"),
            "edit": ("edit", "#34d399"),
            "write": ("file_plus", "#a78bfa"),
            "search": ("search", "#60a5fa"),
            "mcp": ("tool", "#f472b6"),
            "user": ("user", "#94a3b8"),
            "summary": ("sparkles", "#38bdf8"),
            "other": ("tool", "#38bdf8")
        }
        icon_name, icon_color = icon_meta.get(event.category, ("tool", "#38bdf8"))

        icon_lbl = QLabel(self)
        icon_lbl.setObjectName("LogCategoryIcon")
        icon_lbl.setPixmap(get_svg_pixmap(icon_name, 14, icon_color))
        icon_lbl.setFixedWidth(16)
        layout.addWidget(icon_lbl)

        self.text_lbl = QLabel(self)
        self.text_lbl.setObjectName("LogItemText")
        self.text_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.text_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.refresh()
        if event.category != "command":
            self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        else:
            self.text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.text_lbl, 1)

        chev_lbl = QLabel(self)
        chev_lbl.setPixmap(get_svg_pixmap("chevron_right", 11, "#475569"))
        chev_lbl.setFixedWidth(11)
        layout.addWidget(chev_lbl)

    def refresh(self):
        ev = self.event
        self.text_lbl.setText(self._format_text(ev))
        tip = ev.text
        if ev.command_str:
            tip += f"\nCommand: {ev.command_str}"
        elif ev.detail:
            tip += f"\n{ev.detail}"
        if ev.response_str:
            tip += f"\nOutput: {ev.response_str}"
        if ev.applied and (ev.lines_added is not None or ev.lines_removed is not None):
            tip += f"\nPerubahan baris: +{ev.lines_added or 0} / -{ev.lines_removed or 0}"
        if ev.category == "command":
            tip += "\n(Klik untuk melihat sekilas command & response di baris atas)"
        self.setToolTip(tip)
        self.text_lbl.setToolTip(tip)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.event.category == "command":
            if callable(self.on_command_clicked):
                self.on_command_clicked(self.event)
                event.accept()
                return
        super().mousePressEvent(event)

    def _format_diff_html(self, ev: TaskEvent) -> str:
        if ev.applied and (ev.lines_added is not None or ev.lines_removed is not None):
            add_v = ev.lines_added or 0
            rem_v = ev.lines_removed or 0
            return (
                f'&nbsp;&nbsp;<span style="color:#34d399; font-weight:700;">+{add_v}</span>'
                f'&nbsp;<span style="color:#f87171; font-weight:700;">-{rem_v}</span>'
            )
        return ""

    def _format_text(self, ev: TaskEvent) -> str:
        txt = ev.text
        diff_html = self._format_diff_html(ev)

        if ev.category == "read":
            m = re.match(r"Analyzed (?:\[([A-Z0-9]+)\]\s+)?([^\s#]+)(?:\s+(#L\S+))?", txt)
            if m:
                ext_tag = m.group(1) or ""
                fname = m.group(2) or ""
                lines = m.group(3) or ""
                ext = os.path.splitext(fname)[1].lower().lstrip(".")
                badge_html = ""
                if ext in ("html", "htm"):
                    badge_html = '<span style="color:#f97316; font-weight:700;">&lt;/&gt;</span> '
                elif ext in ("js", "jsx", "ts", "tsx", "mjs"):
                    badge_html = '<span style="color:#eab308; font-weight:700;">JS</span> '
                elif ext in ("css", "scss", "sass", "less"):
                    badge_html = '<span style="color:#38bdf8; font-weight:700;">{}</span> '
                elif ext == "py":
                    badge_html = '<span style="color:#60a5fa; font-weight:700;">PY</span> '
                elif ext in ("json", "yaml", "yml"):
                    badge_html = '<span style="color:#fbbf24; font-weight:700;">{}</span> '
                elif ext in ("md", "txt"):
                    badge_html = '<span style="color:#a78bfa; font-weight:700;">MD</span> '
                elif ext_tag:
                    badge_html = f'<span style="color:#94a3b8; font-weight:700;">{ext_tag}</span> '

                line_html = f' <span style="color:#64748b;">{lines}</span>' if lines else ""
                return f'<span style="color:#94a3b8;">Analyzed</span> {badge_html}<span style="color:#e2e8f0; font-weight:500;">{fname}</span>{line_html}'

        elif ev.category == "command":
            if txt.startswith("Ran "):
                cmd_text = txt[4:]
                return f'<span style="color:#94a3b8;">Ran</span> <span style="color:#e2e8f0; font-weight:500;">{cmd_text}</span>'

        elif ev.category == "edit":
            if txt.startswith("Edited "):
                file_text = txt[7:]
                return f'<span style="color:#34d399; font-weight:600;">Edited</span> <span style="color:#e2e8f0; font-weight:500;">{file_text}</span>{diff_html}'

        elif ev.category == "write":
            if txt.startswith("Created "):
                file_text = txt[8:]
                return f'<span style="color:#a78bfa; font-weight:600;">Created</span> <span style="color:#e2e8f0; font-weight:500;">{file_text}</span>{diff_html}'

        elif ev.category == "thinking":
            return '<span style="color:#c084fc; font-weight:600;">Thinking...</span>'

        elif ev.category == "summary":
            return f'<span style="color:#38bdf8; font-weight:700;">Ringkasan:</span> <span style="color:#e2e8f0; font-weight:500;">{txt}</span>'

        elif ev.category == "decision":
            title = ev.text
            if title.startswith("Membutuhkan input user: "):
                dec_title = title[len("Membutuhkan input user: "):]
                return f'<span style="color:#f59e0b; font-weight:700;">Membutuhkan input user:</span> <span style="color:#fef08a; font-weight:600;">{dec_title}</span>'
            return f'<span style="color:#f59e0b; font-weight:600;">{title}</span>'

        return f'<span style="color:#cbd5e1;">{txt}</span>{diff_html}'


class AnimatedCmdResponseWidget(QWidget):
    """
    Baris 3 Dinamis: Menampilkan sekilas Response / Output dari proses Running Command
    saat baris command diklik. Jika saat bersamaan ada Background Process aktif,
    indikator Background Process otomatis bergeser ke Baris 4.
    """
    def __init__(self, parent_window, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.setObjectName("CmdResponseWidget")
        self._row_height = 0
        self.setFixedHeight(0)
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Icon output response (14x17 - sejajar 100% dengan baris 2)
        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(14, 17)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setPixmap(get_svg_pixmap("corner_down_right", 12, "#34d399"))
        layout.addWidget(self.icon_lbl)

        # 2. Animated scrolling label untuk menampilkan response command secara dinamis
        self.resp_lbl = AnimatedTaskLabel(self, base_color="#cbd5e1")
        self.resp_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.resp_lbl.setFixedHeight(17)
        self.resp_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.resp_lbl, 1)

        # 3. Mini close button
        self.close_btn = QPushButton(self)
        self.close_btn.setObjectName("CmdCloseBtn")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.close_btn.setIcon(get_svg_icon("close", 10, "#94a3b8"))
        self.close_btn.setIconSize(QSize(10, 10))
        self.close_btn.setToolTip("Tutup tampilan response command")
        self.close_btn.clicked.connect(self.parent_window.hide_cmd_response_glance)
        layout.addWidget(self.close_btn)

    @pyqtProperty(int)
    def row_height(self) -> int:
        return self._row_height

    @row_height.setter
    def row_height(self, h: int):
        self._row_height = h
        self.setFixedHeight(h)

    def set_response_data(self, cmd_str: str, resp_str: str):
        clean_resp = resp_str.strip()
        display = f"Output: {clean_resp}"
        self.resp_lbl.set_base_color("#34d399" if not clean_resp.lower().startswith("error") else "#f87171")
        self.resp_lbl.set_text(display, None, None)
        self.resp_lbl.setToolTip(f"Command: {cmd_str}\nResponse: {clean_resp}")


class AnimatedBgProcessWidget(QWidget):
    """
    Baris 3 / Baris 4 Dinamis: Background Process indicator dengan animasi slide & fade.
    Berada di Baris 3 saat normal, dan otomatis bergeser ke Baris 4 ketika Baris 3
    sedang menampilkan sekilas response dari command.
    """
    def __init__(self, parent_window, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.setObjectName("BgProcessWidget")
        self._row_height = 0
        self.setFixedHeight(0)
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Icon terminal (14x17 - ukuran & perataan persis baris 2)
        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(14, 17)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setPixmap(get_svg_pixmap("terminal", 12, "#c084fc"))
        layout.addWidget(self.icon_lbl)

        # 2. Animated label (mendukung marquee otomatis jika lebar window diperkecil)
        self.text_lbl = AnimatedTaskLabel(self, base_color="#c084fc")
        self.text_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.text_lbl.setFixedHeight(17)
        self.text_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.text_lbl, 1)

        # 3. Mini close/dismiss button
        self.close_btn = QPushButton(self)
        self.close_btn.setObjectName("BgCloseBtn")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.close_btn.setIcon(get_svg_icon("close", 10, "#94a3b8"))
        self.close_btn.setIconSize(QSize(10, 10))
        self.close_btn.setToolTip("Tutup / Abaikan info proses latar belakang ini")
        self.close_btn.clicked.connect(self.parent_window.dismiss_bg_process)
        layout.addWidget(self.close_btn)

    @pyqtProperty(int)
    def row_height(self) -> int:
        return self._row_height

    @row_height.setter
    def row_height(self, h: int):
        self._row_height = h
        self.setFixedHeight(h)

    def set_data(self, bg_info: dict):
        self.text_lbl.set_text(bg_info["display_text"], None, None)
        self.text_lbl.setToolTip(
            f"Proses Latar Belakang: {bg_info['proc_name']}\n"
            f"Perintah: {bg_info['command']}\n"
            f"ID Task: {bg_info['task_id']}"
        )
        ico_col = "#38bdf8" if "powershell" in bg_info["proc_name"].lower() else "#c084fc"
        self.icon_lbl.setPixmap(get_svg_pixmap("terminal", 12, ico_col))


class ActionButtonsCard(QFrame):
    """
    Card melayang berisi 3 tombol aksi (Pin, Dropdown/Expand, Close)
    yang muncul dengan animasi saat cursor hover di atas pill.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionButtonsCard")
        self._opacity = 0.0
        self.setVisible(False)
        self.anim = None
        self.setFixedSize(98, 32)

        self.card_layout = QHBoxLayout(self)
        self.card_layout.setContentsMargins(4, 3, 4, 3)
        self.card_layout.setSpacing(3)

    @pyqtProperty(float)
    def opacity(self) -> float:
        return self._opacity

    @opacity.setter
    def opacity(self, val: float):
        self._opacity = max(0.0, min(1.0, val))
        self.update()

    def show_card(self):
        self.setVisible(True)
        self.raise_()
        if self.anim and self.anim.state() == QPropertyAnimation.State.Running:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"opacity")
        self.anim.setDuration(160)
        self.anim.setStartValue(self._opacity)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

    def hide_card(self):
        if self.anim and self.anim.state() == QPropertyAnimation.State.Running:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"opacity")
        self.anim.setDuration(180)
        self.anim.setStartValue(self._opacity)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim.finished.connect(self._on_hide_done)
        self.anim.start()

    def _on_hide_done(self):
        if self._opacity <= 0.01:
            self.setVisible(False)
            if self.parentWidget():
                self.parentWidget().update()

    def paintEvent(self, event):
        if self._opacity <= 0.005:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg = QColor(22, 24, 34, int(248 * self._opacity))
        border = QColor(255, 255, 255, int(45 * self._opacity))

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1))
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.drawRoundedRect(rect, 14, 14)
        painter.end()


class TaskOverlayWindow(QWidget):
    def __init__(self, parent_pid: int = 0):
        super().__init__()
        self.parent_pid = parent_pid
        self.monitor = AntigravityMonitor()
        self.is_expanded = False
        self.selected_conv_id = None
        self.drag_position = QPoint()
        self.is_pinned = True
        self.was_running = False

        # Konfigurasi Dinamis yang Dapat Disetel dari Panel Ekstensi IDE
        self.cfg_auto_start: bool = True
        self.cfg_auto_close_with_ide: bool = True
        self.cfg_window_opacity: int = 95
        self.cfg_show_quota_ring: bool = True
        self.cfg_show_duration_timer: bool = True
        self.cfg_show_model_badge: bool = True
        self.cfg_show_diff_stats: bool = True
        self.cfg_show_bg_process: bool = True
        self.cfg_show_completion_summary: bool = True
        self.cfg_marquee_speed: int = 42
        self.cfg_model_badge_duration_ms: int = 4500
        self.cfg_summary_duration_ms: int = 6500
        self.cfg_cmd_glance_duration_ms: int = 5500
        self.cfg_poll_interval_active_ms: int = 320
        self._last_config_mtime: float = 0.0

        # Dimensi Dinamis & Resize State
        self._user_width = DEFAULT_WINDOW_WIDTH
        self._user_expanded_height = DEFAULT_EXPANDED_HEIGHT
        self._current_height = BASE_COLLAPSED_WIN_HEIGHT
        self._resize_mode: Optional[str] = None
        self._resize_start_pos = QPoint()
        self._resize_start_geom = None

        # State 4 Baris Dinamis
        self._has_cmd_resp_visible = False
        self._has_bg_visible = False
        self.rows_anim_group = None
        self.expand_anim_group = None
        self.thinking_log_widget = None
        self._full_session_title = "Antigravity Agent"

        # State Glance Command (Baris 2) & Response (Baris 3)
        self._cmd_glance_active: bool = False
        self._cmd_glance_event: Optional[TaskEvent] = None
        self._awaiting_response_event: Optional[TaskEvent] = None

        self.cmd_glance_row2_timer = QTimer(self)
        self.cmd_glance_row2_timer.setSingleShot(True)
        self.cmd_glance_row2_timer.timeout.connect(self._on_cmd_glance_row2_timeout)

        self.cmd_response_hide_timer = QTimer(self)
        self.cmd_response_hide_timer.setSingleShot(True)
        self.cmd_response_hide_timer.timeout.connect(self.hide_cmd_response_glance)

        # Completion Summary Transition Sequence
        self.completion_summary_timer = QTimer(self)
        self.completion_summary_timer.setSingleShot(True)
        self.completion_summary_timer.timeout.connect(self._show_completion_summary)

        self.completion_return_timer = QTimer(self)
        self.completion_return_timer.setSingleShot(True)
        self.completion_return_timer.timeout.connect(self._show_completion_finished)

        self._completion_seq_active: bool = False
        self._last_completed_summary: str = ""
        self._last_detected_model: str = ""

        # Timer untuk debounce hover leave
        self.hover_leave_timer = QTimer(self)
        self.hover_leave_timer.setSingleShot(True)
        self.hover_leave_timer.timeout.connect(self.on_hover_leave_timeout)

        self.init_window_flags()
        self.init_ui()
        self.apply_drop_shadow()
        self.load_config()

        # Install event filter pada aplikasi agar cursor resize tepi selalu responsif
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        # Polling realtime
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.on_poll_tick)
        self.poll_timer.start(400)

        self.on_poll_tick()

        # Tampilkan badge model dengan animasi saat aplikasi baru dibuka
        QTimer.singleShot(350, lambda: self.model_badge.trigger_display(self.monitor.model_name, 4500))

    def init_window_flags(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setStyleSheet(DARK_THEME_QSS)

    def apply_drop_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 6)
        self.main_container.setGraphicsEffect(shadow)

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(0)

        # Main background container
        self.main_container = QWidget(self)
        self.main_container.setObjectName("MainWidget")
        self.main_container.setProperty("class", "collapsed")
        self.main_container.setMouseTracking(True)
        root_layout.addWidget(self.main_container)

        self.main_box = QVBoxLayout(self.main_container)
        self.main_box.setContentsMargins(12, 7, 12, 7)
        self.main_box.setSpacing(6)

        # --- PILL AREA (MENDUKUNG KONSEP DINAMIS 4 BARIS) ---
        self.pill_row = QWidget(self.main_container)
        self.pill_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pill_row.setFixedHeight(BASE_PILL_HEIGHT)
        self.pill_row.setMouseTracking(True)

        pill_layout = QHBoxLayout(self.pill_row)
        pill_layout.setContentsMargins(0, 0, 0, 0)
        pill_layout.setSpacing(10)

        # 1. Status Dot Indicator
        self.status_dot = QLabel(self.pill_row)
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setProperty("class", "idle")
        pill_layout.addWidget(self.status_dot)

        # 2. Kontainer Vertikal Dinamis 4 Baris:
        #    Baris 1: Judul Sesi + Model Badge
        #    Baris 2: Proses Realtime (+baris -baris / Command glance)
        #    Baris 3: Response Command Sekilas (AnimatedCmdResponseWidget)
        #    Baris 4: Background Process Indicator (AnimatedBgProcessWidget - berada di posisi Baris 3 jika Baris 3 kosong, dan bergeser ke Baris 4 jika Baris 3 tampil)
        self.content_vbox = QVBoxLayout()
        self.content_vbox.setContentsMargins(0, 0, 0, 0)
        self.content_vbox.setSpacing(3)

        # --- BARIS 1: HEADER JUDUL SESI & MODEL BADGE ---
        line1_row = QHBoxLayout()
        line1_row.setContentsMargins(0, 0, 0, 0)
        line1_row.setSpacing(6)

        self.title_lbl = QLabel("Antigravity Agent", self.pill_row)
        self.title_lbl.setObjectName("TitleLabel")
        self.title_lbl.setFixedHeight(17)
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.title_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.title_lbl.mousePressEvent = lambda e: self.model_badge.trigger_display(self.monitor.model_name, 4500)
        line1_row.addWidget(self.title_lbl)

        self.model_badge = AnimatedModelBadge(self.pill_row)
        line1_row.addWidget(self.model_badge)

        line1_row.addStretch(1)
        self.content_vbox.addLayout(line1_row)

        # --- BARIS 2: PROSES REALTIME (+BARIS -BARIS / GLANCE COMMAND) ---
        line2_row = QHBoxLayout()
        line2_row.setContentsMargins(0, 0, 0, 0)
        line2_row.setSpacing(6)

        self.task_icon_lbl = QLabel(self.pill_row)
        self.task_icon_lbl.setFixedSize(14, 17)
        self.task_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.task_icon_lbl.setPixmap(get_svg_pixmap("terminal", 12, "#38bdf8"))
        self.task_icon_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.task_icon_lbl.mousePressEvent = self.on_task_label_clicked
        line2_row.addWidget(self.task_icon_lbl)

        self.task_lbl = AnimatedTaskLabel(self.pill_row)
        self.task_lbl.setFixedHeight(17)
        self.task_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.task_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.task_lbl.mousePressEvent = self.on_task_label_clicked
        line2_row.addWidget(self.task_lbl, 1)

        self.content_vbox.addLayout(line2_row)

        # --- BARIS 3: RESPONSE COMMAND SEKILAS ---
        self.cmd_response_widget = AnimatedCmdResponseWidget(self, self.pill_row)
        self.content_vbox.addWidget(self.cmd_response_widget)

        # --- BARIS 4 (ATAU BARIS 3 SAAT RESPONSE TIDAK AKTIF): BACKGROUND PROCESS ---
        self.bg_process_widget = AnimatedBgProcessWidget(self, self.pill_row)
        self.content_vbox.addWidget(self.bg_process_widget)

        pill_layout.addLayout(self.content_vbox, 1)

        # 3. Lingkaran Sisa Kuota Model
        self.quota_ring = CircularQuotaRing(self.pill_row, size=34)
        pill_layout.addWidget(self.quota_ring)

        # 4. Duration Badge
        self.duration_container = QWidget(self.pill_row)
        dur_layout = QHBoxLayout(self.duration_container)
        dur_layout.setContentsMargins(5, 2, 6, 2)
        dur_layout.setSpacing(4)

        self.clock_icon = QLabel(self.duration_container)
        self.clock_icon.setPixmap(get_svg_pixmap("clock", 12, "#38bdf8"))
        self.clock_icon.setFixedWidth(13)
        dur_layout.addWidget(self.clock_icon)

        self.duration_lbl = QLabel("0s", self.duration_container)
        self.duration_lbl.setObjectName("DurationLabel")
        dur_layout.addWidget(self.duration_lbl)

        self.duration_container.setVisible(False)
        pill_layout.addWidget(self.duration_container)

        self.main_box.addWidget(self.pill_row, 0, Qt.AlignmentFlag.AlignTop)

        # --- FLOATING ACTION BUTTONS CARD (HOVER ONLY) ---
        self.action_card = ActionButtonsCard(self.pill_row)

        self.pin_btn = QPushButton(self.action_card)
        self.pin_btn.setObjectName("IconBtn")
        self.pin_btn.setIcon(get_svg_icon("pin", 15, "#cbd5e1"))
        self.pin_btn.setIconSize(QSize(15, 15))
        self.pin_btn.setToolTip("Always On Top (Aktif)")
        self.pin_btn.clicked.connect(self.toggle_pin)
        self.action_card.card_layout.addWidget(self.pin_btn)

        self.expand_btn = QPushButton(self.action_card)
        self.expand_btn.setObjectName("IconBtn")
        self.expand_btn.setIcon(get_svg_icon("chevron_down", 16, "#cbd5e1"))
        self.expand_btn.setIconSize(QSize(16, 16))
        self.expand_btn.setToolTip("Buka / Tutup Riwayat Log")
        self.expand_btn.clicked.connect(self.toggle_expand)
        self.action_card.card_layout.addWidget(self.expand_btn)

        self.close_btn = QPushButton(self.action_card)
        self.close_btn.setObjectName("IconBtn")
        self.close_btn.setProperty("class", "CloseBtn")
        self.close_btn.setIcon(get_svg_icon("close", 14, "#94a3b8"))
        self.close_btn.setIconSize(QSize(14, 14))
        self.close_btn.setToolTip("Tutup Overlay")
        self.close_btn.clicked.connect(self.close)
        self.action_card.card_layout.addWidget(self.close_btn)

        # --- DETAIL FLYOUT CONTAINER (EXPANDED LOGS) ---
        self.detail_container = QWidget(self.main_container)
        self.detail_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.detail_container.setVisible(False)

        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(0, 4, 0, 2)
        self.detail_layout.setSpacing(4)

        divider = QFrame(self.detail_container)
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        self.detail_layout.addWidget(divider)

        session_row = QWidget(self.detail_container)
        session_row.setFixedHeight(28)
        session_layout = QHBoxLayout(session_row)
        session_layout.setContentsMargins(4, 1, 4, 1)
        session_layout.setSpacing(8)

        session_tag_lbl = QLabel("Sesi:", session_row)
        session_tag_lbl.setObjectName("SessionTagLabel")
        session_layout.addWidget(session_tag_lbl)

        self.session_combo = QComboBox(session_row)
        self.session_combo.setObjectName("SessionSelector")
        self.session_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.session_combo.currentIndexChanged.connect(self.on_session_changed)
        session_layout.addWidget(self.session_combo, 1)

        self.task_count_badge = QLabel("0 tasks", session_row)
        self.task_count_badge.setObjectName("TaskCountBadge")
        session_layout.addWidget(self.task_count_badge)

        self.detail_layout.addWidget(session_row)

        cat_header_row = QWidget(self.detail_container)
        cat_header_row.setFixedHeight(22)
        cat_layout = QHBoxLayout(cat_header_row)
        cat_layout.setContentsMargins(6, 2, 6, 2)
        cat_layout.setSpacing(6)

        self.cat_arrow_icon = QLabel(cat_header_row)
        self.cat_arrow_icon.setPixmap(get_svg_pixmap("chevron_down", 11, "#38bdf8"))
        self.cat_arrow_icon.setFixedWidth(12)
        cat_layout.addWidget(self.cat_arrow_icon)

        self.category_summary_lbl = QLabel("Explored files, ran commands, edited files", cat_header_row)
        self.category_summary_lbl.setObjectName("SubSummaryHeader")
        cat_layout.addWidget(self.category_summary_lbl, 1)

        self.detail_layout.addWidget(cat_header_row)

        self.scroll_area = QScrollArea(self.detail_container)
        self.scroll_area.setObjectName("LogScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.log_content = QWidget()
        self.log_content.setObjectName("LogScrollContent")
        self.log_box = QVBoxLayout(self.log_content)
        self.log_box.setContentsMargins(14, 2, 6, 2)
        self.log_box.setSpacing(3)
        self.log_box.addStretch()

        self.scroll_area.setWidget(self.log_content)
        self.detail_layout.addWidget(self.scroll_area, 1)

        self.main_box.addWidget(self.detail_container, 1)

        # Ukuran awal (Mendukung perubahan lebar secara dinamis oleh pengguna)
        self.setMinimumWidth(MIN_WINDOW_WIDTH)
        self.setMaximumWidth(MAX_WINDOW_WIDTH)
        self.resize(self._user_width, BASE_COLLAPSED_WIN_HEIGHT)
        self.setFixedHeight(BASE_COLLAPSED_WIN_HEIGHT)

    # --- JUDUL SESI DINAMIS (TANPA TRUNCATE KAKU) ---
    def update_title_elide(self):
        if not hasattr(self, "title_lbl") or not hasattr(self, "pill_row"):
            return
        full_title = self._full_session_title or "Antigravity Agent"
        pill_w = max(260, self.width() - 44)

        # Hitung ruang yang terpakai di sisi kiri (status dot) dan kanan (quota ring, duration, model badge)
        used_w = 24 + 44  # status_dot + quota_ring + spacing
        if hasattr(self, "duration_container") and self.duration_container.isVisible():
            used_w += max(54, self.duration_container.width()) + 10
        if hasattr(self, "model_badge") and self.model_badge.isVisible():
            used_w += self.model_badge.width() + 8

        avail_w = max(110, pill_w - used_w)
        fm = QFontMetrics(self.title_lbl.font())
        elided = fm.elidedText(full_title, Qt.TextElideMode.ElideRight, avail_w)
        self.title_lbl.setText(elided)

    # --- HOVER OVERLAY CARD BEHAVIOR ---
    def enterEvent(self, event):
        if self.hover_leave_timer.isActive():
            self.hover_leave_timer.stop()
        self.reposition_action_card()
        self.action_card.show_card()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_leave_timer.start(140)
        super().leaveEvent(event)

    def on_hover_leave_timeout(self):
        cursor_pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(cursor_pos):
            self.action_card.hide_card()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reposition_action_card()
        self.update_title_elide()

    def reposition_action_card(self):
        if hasattr(self, "action_card") and hasattr(self, "pill_row"):
            card_w = self.action_card.width()
            card_h = self.action_card.height()
            target_x = self.pill_row.width() - card_w - 2
            target_y = (self.pill_row.height() - card_h) // 2
            self.action_card.move(target_x, target_y)

    # --- KONSEP DINAMIS 4 BARIS & KALKULASI TINGGI OTOMATIS ---
    @pyqtProperty(int)
    def pill_height(self) -> int:
        return self.pill_row.height()

    @pill_height.setter
    def pill_height(self, h: int):
        self.pill_row.setFixedHeight(h)
        self.reposition_action_card()

    @pyqtProperty(int)
    def window_height(self) -> int:
        return self._current_height

    @window_height.setter
    def window_height(self, h: int):
        self._current_height = h
        self.setFixedHeight(h)
        self.resize(self._user_width, h)

    def _get_active_extra_rows_count(self) -> int:
        count = 0
        if self._has_cmd_resp_visible:
            count += 1
        if self._has_bg_visible:
            count += 1
        return count

    def get_target_pill_height(self) -> int:
        return BASE_PILL_HEIGHT + (self._get_active_extra_rows_count() * EXTRA_ROW_HEIGHT)

    def get_collapsed_height(self) -> int:
        return BASE_COLLAPSED_WIN_HEIGHT + (self._get_active_extra_rows_count() * EXTRA_ROW_HEIGHT)

    def get_expanded_height(self) -> int:
        return self._user_expanded_height + (self._get_active_extra_rows_count() * EXTRA_ROW_HEIGHT)

    def animate_dynamic_rows(self):
        """
        Mengatur animasi transisi mulus untuk Baris 3 (Command Response) dan Baris 4 (Background Process)
        sehingga mendukung penuh konsep dinamis 2, 3, hingga 4 baris secara simultan.
        """
        if self.rows_anim_group and self.rows_anim_group.state() == QPropertyAnimation.State.Running:
            self.rows_anim_group.stop()

        self.rows_anim_group = QParallelAnimationGroup(self)

        # 1. Animasi Baris 3: Command Response Glance (0 <-> 17px)
        if self._has_cmd_resp_visible:
            self.cmd_response_widget.setVisible(True)
        anim_cmd_row = QPropertyAnimation(self.cmd_response_widget, b"row_height")
        anim_cmd_row.setDuration(220)
        anim_cmd_row.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_cmd_row.setStartValue(self.cmd_response_widget.height())
        anim_cmd_row.setEndValue(17 if self._has_cmd_resp_visible else 0)
        self.rows_anim_group.addAnimation(anim_cmd_row)

        # 2. Animasi Baris 4 (atau Baris 3 jika Response kosong): Background Process (0 <-> 17px)
        if self._has_bg_visible:
            self.bg_process_widget.setVisible(True)
        anim_bg_row = QPropertyAnimation(self.bg_process_widget, b"row_height")
        anim_bg_row.setDuration(220)
        anim_bg_row.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_bg_row.setStartValue(self.bg_process_widget.height())
        anim_bg_row.setEndValue(17 if self._has_bg_visible else 0)
        self.rows_anim_group.addAnimation(anim_bg_row)

        # 3. Animasi tinggi pill_row (38 / 58 / 78px)
        anim_pill = QPropertyAnimation(self, b"pill_height")
        anim_pill.setDuration(220)
        anim_pill.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_pill.setStartValue(self.pill_row.height())
        anim_pill.setEndValue(self.get_target_pill_height())
        self.rows_anim_group.addAnimation(anim_pill)

        # 4. Animasi tinggi keseluruhan window
        target_win_h = self.get_expanded_height() if self.is_expanded else self.get_collapsed_height()
        anim_win = QPropertyAnimation(self, b"window_height")
        anim_win.setDuration(220)
        anim_win.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_win.setStartValue(self.height())
        anim_win.setEndValue(target_win_h)
        self.rows_anim_group.addAnimation(anim_win)

        def _on_rows_anim_finished():
            if not self._has_cmd_resp_visible:
                self.cmd_response_widget.setVisible(False)
            if not self._has_bg_visible:
                self.bg_process_widget.setVisible(False)

        self.rows_anim_group.finished.connect(_on_rows_anim_finished)
        self.rows_anim_group.start()

    def set_bg_process_visibility(self, show: bool):
        if self._has_bg_visible != show:
            self._has_bg_visible = show
            self.animate_dynamic_rows()

    def dismiss_bg_process(self):
        self.monitor.dismiss_background_task()
        if self._has_bg_visible:
            self.set_bg_process_visibility(False)

    # --- FITUR KLIK RUNNING COMMAND: GLANCE COMMAND (BARIS 2) & RESPONSE (BARIS 3) ---
    def trigger_command_glance(self, ev: TaskEvent):
        """
        Saat proses running command diklik:
        1. Tampilkan sekilas command yang dijalankan pada Baris 2.
        2. Jika ada response-nya (atau begitu response tersedia), tampilkan di Baris 3 sekilas.
           Jika saat itu ada Background Process aktif, otomatis bergeser ke Baris 4.
        """
        if not ev or ev.category != "command":
            return

        self._stop_completion_sequence()
        self._cmd_glance_active = True
        self._cmd_glance_event = ev

        cmd_text = (ev.command_str or ev.detail or ev.text).strip()
        # Bersihkan newline pada command multiline agar rapi dalam 1 baris marquee
        clean_cmd = " ; ".join(ln.strip() for ln in cmd_text.splitlines() if ln.strip())

        self.task_icon_lbl.setPixmap(get_svg_pixmap("terminal", 13, "#fbbf24"))
        self.task_lbl.set_waiting_input(False)
        self.task_lbl.set_running(False)
        self.task_lbl.set_base_color("#fde68a")
        self.task_lbl.set_text(f"Cmd: {clean_cmd}", None, None)
        self.task_lbl.setToolTip(f"Command yang dijalankan:\n{cmd_text}")

        # Tampilkan command sekilas di Baris 2
        self.cmd_glance_row2_timer.start(max(2000, self.cfg_cmd_glance_duration_ms - 1000))

        # Jika sudah ada response, tampilkan di Baris 3 setelah jeda transisi pendek 220ms
        if ev.response_str:
            self._awaiting_response_event = None
            QTimer.singleShot(220, lambda: self.show_cmd_response_glance(ev))
        else:
            # Jika command masih berjalan dan belum ada response, tunggu hingga response tiba
            self._awaiting_response_event = ev

    def _on_cmd_glance_row2_timeout(self):
        self._cmd_glance_active = False
        self._cmd_glance_event = None
        self.task_lbl.set_base_color("#94a3b8")
        self.on_poll_tick()

    def show_cmd_response_glance(self, ev: TaskEvent):
        if not ev or not ev.response_str:
            return
        cmd_text = (ev.command_str or ev.detail or ev.text).strip()
        self.cmd_response_widget.set_response_data(cmd_text, ev.response_str)
        if not self._has_cmd_resp_visible:
            self._has_cmd_resp_visible = True
            self.animate_dynamic_rows()
        # Tampilkan sekilas sesuai durasi konfigurasi lalu sembunyikan otomatis
        self.cmd_response_hide_timer.start(self.cfg_cmd_glance_duration_ms)

    def hide_cmd_response_glance(self):
        if self.cmd_response_hide_timer.isActive():
            self.cmd_response_hide_timer.stop()
        self._awaiting_response_event = None
        if self._has_cmd_resp_visible:
            self._has_cmd_resp_visible = False
            self.animate_dynamic_rows()

    def toggle_expand(self):
        self.is_expanded = not self.is_expanded

        if self.expand_anim_group and self.expand_anim_group.state() == QPropertyAnimation.State.Running:
            self.expand_anim_group.stop()

        self.expand_anim_group = QPropertyAnimation(self, b"window_height")

        if self.is_expanded:
            self.expand_btn.setIcon(get_svg_icon("chevron_up", 16, "#cbd5e1"))
            self.detail_container.setVisible(True)
            self.main_container.setProperty("class", "expanded")
            self.main_container.style().unpolish(self.main_container)
            self.main_container.style().polish(self.main_container)
            self.populate_all_logs()

            self.expand_anim_group.setDuration(240)
            self.expand_anim_group.setStartValue(self.height())
            self.expand_anim_group.setEndValue(self.get_expanded_height())
            self.expand_anim_group.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.expand_anim_group.start()
        else:
            self.expand_btn.setIcon(get_svg_icon("chevron_down", 16, "#cbd5e1"))

            self.expand_anim_group.setDuration(220)
            self.expand_anim_group.setStartValue(self.height())
            self.expand_anim_group.setEndValue(self.get_collapsed_height())
            self.expand_anim_group.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.expand_anim_group.finished.connect(self._on_collapse_finished)
            self.expand_anim_group.start()

    def _on_collapse_finished(self):
        if not self.is_expanded:
            self.detail_container.setVisible(False)
            self.main_container.setProperty("class", "collapsed")
            self.main_container.style().unpolish(self.main_container)
            self.main_container.style().polish(self.main_container)

    def toggle_pin(self):
        self.is_pinned = not self.is_pinned
        self.cfg_always_on_top = self.is_pinned
        if self.is_pinned:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.pin_btn.setIcon(get_svg_icon("pin", 15, "#cbd5e1"))
            self.pin_btn.setToolTip("Always On Top (Aktif)")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.pin_btn.setIcon(get_svg_icon("pin_off", 15, "#64748b"))
            self.pin_btn.setToolTip("Always On Top (Nonaktif)")
        self.show()
        self.save_config()

    def start_completion_sequence(self):
        """
        Memulai sekuens transisi penyelesaian task:
        1. Ikon centang hijau + 'Tugas selesai' (2.6s)
        2. Ikon sparkles + 'Ringkasan: <ringkasan singkat>' (durasi sesuai cfg_summary_duration_ms)
        3. Kembali ke ikon centang hijau + 'Tugas selesai'
        """
        try:
            self._stop_completion_sequence()
            summary = self.monitor.get_last_completion_summary()
            self._last_completed_summary = summary

            self.task_icon_lbl.setPixmap(get_svg_pixmap("circle_check", 13, "#10b981"))
            self.task_lbl.set_waiting_input(False)
            self.task_lbl.set_running(False)
            self.task_lbl.set_base_color("#94a3b8")
            self.task_lbl.set_text("Tugas selesai", None, None)
            self.task_lbl.setToolTip(f"Tugas selesai\nRingkasan: {summary}\n(Klik teks untuk memutar ulang ringkasan)")

            if self.cfg_show_completion_summary:
                self._completion_seq_active = True
                self.completion_summary_timer.start(2600)
        except Exception:
            log_exception("Exception in start_completion_sequence")

    def _show_completion_summary(self):
        try:
            if self.was_running or self.monitor.get_pending_decision_info():
                self._stop_completion_sequence()
                return

            summary = self._last_completed_summary or self.monitor.get_last_completion_summary()
            display_text = f"Ringkasan: {summary}"

            self.task_icon_lbl.setPixmap(get_svg_pixmap("sparkles", 13, "#38bdf8"))
            self.task_lbl.set_waiting_input(False)
            self.task_lbl.set_running(False)
            self.task_lbl.set_base_color("#94a3b8")
            self.task_lbl.set_text(display_text, None, None)
            self.task_lbl.setToolTip(f"Ringkasan Penyelesaian:\n{summary}\n\n(Klik teks untuk memutar ulang ringkasan)")

            self.completion_return_timer.start(self.cfg_summary_duration_ms)
        except Exception:
            self._stop_completion_sequence()

    def _show_completion_finished(self):
        try:
            self._completion_seq_active = False
            if self.was_running or self.monitor.get_pending_decision_info():
                return

            self.task_icon_lbl.setPixmap(get_svg_pixmap("circle_check", 13, "#10b981"))
            self.task_lbl.set_waiting_input(False)
            self.task_lbl.set_running(False)
            self.task_lbl.set_base_color("#94a3b8")
            self.task_lbl.set_text("Tugas selesai", None, None)
            summary = self._last_completed_summary or self.monitor.get_last_completion_summary()
            self.task_lbl.setToolTip(f"Tugas selesai\nRingkasan: {summary}\n\n(Klik teks untuk memutar ulang ringkasan)")
        except Exception:
            self._completion_seq_active = False

    def _stop_completion_sequence(self):
        self._completion_seq_active = False
        if hasattr(self, "completion_summary_timer") and self.completion_summary_timer.isActive():
            self.completion_summary_timer.stop()
        if hasattr(self, "completion_return_timer") and self.completion_return_timer.isActive():
            self.completion_return_timer.stop()

    def on_task_label_clicked(self, event):
        """
        Interaksi klik pada Baris 2 (Task Realtime):
        1. Jika saat ini sedang menampilkan proses command (atau task aktif adalah command),
           tampilkan sekilas command yang dijalankan di Baris 2 dan response-nya di Baris 3.
        2. Jika sedang idle ('Tugas selesai'), putar ulang ringkasan penyelesaian tugas
           (atau jika diklik lagi saat ringkasan tampil dan task terakhir adalah command, tampilkan command glance).
        """
        try:
            cur_ev = self.monitor.get_current_task_event()
            if self._cmd_glance_active:
                # Jika sedang menampilkan glance command, klik lagi untuk langsung menutupnya
                self.cmd_glance_row2_timer.stop()
                self._on_cmd_glance_row2_timeout()
                return

            if self.was_running:
                # Saat proses sedang berjalan: jika task saat ini adalah command (atau baru saja menjalankan command),
                # tampilkan sekilas command & response-nya!
                target_cmd_ev = None
                if cur_ev and cur_ev.category == "command":
                    target_cmd_ev = cur_ev
                else:
                    for ev in reversed(self.monitor.turn_tool_events):
                        if ev.category == "command":
                            target_cmd_ev = ev
                            break
                if target_cmd_ev:
                    self.trigger_command_glance(target_cmd_ev)
                return

            # Saat idle / selesai:
            if not self.monitor.get_pending_decision_info():
                last_cmd_ev = None
                if cur_ev and cur_ev.category == "command":
                    last_cmd_ev = cur_ev
                else:
                    for ev in reversed(self.monitor.events):
                        if ev.category == "command":
                            last_cmd_ev = ev
                            break

                # Jika ada command terakhir dan belum sedang menampilkan glance command,
                # tampilkan sekilas command di Baris 2 & response di Baris 3
                if last_cmd_ev and not getattr(self, "_last_idle_click_was_cmd", False):
                    self._last_idle_click_was_cmd = True
                    self.trigger_command_glance(last_cmd_ev)
                else:
                    self._last_idle_click_was_cmd = False
                    self._stop_completion_sequence()
                    self._completion_seq_active = True
                    self._show_completion_summary()
        except Exception:
            pass

    def on_poll_tick(self):
        try:
            self.check_config_hot_reload()
            is_running, conv_id, title, status = self.monitor.check_active_session(self.selected_conv_id)

            # 1. BACA DATA TERBARU DARI TRANSCRIPT TERLEBIH DAHULU
            new_events = self.monitor.poll_transcript()
            decision_info = self.monitor.get_pending_decision_info()

            # Jika ada event existing yang baru saja mendapat hasil (misal +baris -baris atau response command),
            # segarkan item log di dropdown dan cek apakah ada response command yang sedang ditunggu
            if self.monitor.recently_updated_events:
                if self.is_expanded:
                    self.refresh_visible_log_items()
                if self._awaiting_response_event in self.monitor.recently_updated_events:
                    ev_ready = self._awaiting_response_event
                    self._awaiting_response_event = None
                    if ev_ready and ev_ready.response_str:
                        self.show_cmd_response_glance(ev_ready)

            if new_events and self.is_expanded:
                if self.thinking_log_widget:
                    self.log_box.removeWidget(self.thinking_log_widget)
                    self.thinking_log_widget.deleteLater()
                    self.thinking_log_widget = None

                for ev in new_events:
                    if ev.category != "user":
                        self.append_log_item(ev)
                self.update_category_summary()
                self.scroll_to_bottom()

            # Animasi Model Badge & reset giliran saat proses baru dimulai (False -> True) atau turn baru dimulai
            if (is_running and not self.was_running) or getattr(self.monitor, "new_turn_started", False):
                self.monitor.new_turn_started = False
                self.monitor.on_run_started()
                _, _, _, model_name = self.monitor.get_quota_info()
                self._last_detected_model = model_name
                if self.cfg_show_model_badge:
                    self.model_badge.trigger_display(model_name, duration_ms=self.cfg_model_badge_duration_ms)
                self._stop_completion_sequence()

            # Cek jika model aktif berganti (misal user switch model di tengah sesi)
            current_model = self.monitor.model_name
            if current_model and current_model != getattr(self, "_last_detected_model", ""):
                self._last_detected_model = current_model
                if self.cfg_show_model_badge:
                    self.model_badge.trigger_display(current_model, duration_ms=self.cfg_model_badge_duration_ms)

            # Deteksi transisi selesai tugas (True -> False) dan tidak sedang butuh input user
            just_completed = (self.was_running and not is_running and not decision_info)
            self.was_running = is_running

            if just_completed:
                self.start_completion_sequence()

            # Update Judul Sesi secara Dinamis (Mengikuti lebar jendela tanpa terpotong 28 karakter)
            self._full_session_title = title
            self.update_title_elide()
            self.title_lbl.setToolTip(f"Sesi: {title}\nID: {conv_id}\nModel: {self.monitor.model_name}")

            # Update Status Dot Style
            if decision_info:
                is_running_class = "waiting"
            elif is_running:
                is_running_class = "running"
            else:
                is_running_class = "idle"

            if self.status_dot.property("class") != is_running_class:
                self.status_dot.setProperty("class", is_running_class)
                self.status_dot.style().unpolish(self.status_dot)
                self.status_dot.style().polish(self.status_dot)

            # Update Duration Timer
            dur = self.monitor.get_active_duration_string(is_running) if self.cfg_show_duration_timer else ""
            if dur:
                self.duration_lbl.setText(dur)
                if not self.duration_container.isVisible():
                    self.duration_container.setVisible(True)
                    self.update_title_elide()
                self.clock_icon.setPixmap(get_svg_pixmap("clock", 12, "#38bdf8" if is_running else "#64748b"))
            else:
                if self.duration_container.isVisible():
                    self.duration_container.setVisible(False)
                    self.update_title_elide()

            self.reposition_action_card()

            # Update Background Process Line (Baris 3 atau bergeser ke Baris 4 jika Response Command aktif)
            bg_info = self.monitor.get_background_process_info() if self.cfg_show_bg_process else None
            has_bg = (bg_info is not None)
            if has_bg:
                self.bg_process_widget.set_data(bg_info)
                if not self._has_bg_visible:
                    self.set_bg_process_visibility(True)
            else:
                if self._has_bg_visible:
                    self.set_bg_process_visibility(False)

            # 2. EVALUASI STATE THINKING VS WORKING PADA BARIS 2
            is_thinking = self.monitor.is_agent_thinking(is_running)
            current_task = self.monitor.get_current_task_event()

            icon_map = {
                "thinking": ("brain", "#c084fc"),
                "decision": ("help_circle", "#f59e0b"),
                "command": ("terminal", "#38bdf8"),
                "read": ("file_text", "#fbbf24"),
                "edit": ("edit", "#34d399"),
                "write": ("file_plus", "#a78bfa"),
                "search": ("search", "#60a5fa"),
                "mcp": ("tool", "#f472b6"),
                "other": ("tool", "#38bdf8")
            }

            # Jika user sedang melihat glance command di Baris 2, jangan timpa dulu sampai timer selesai
            if not self._cmd_glance_active:
                self.task_lbl.set_base_color("#94a3b8")

                # KASUS 0: MEMBUTUHKAN KEPUTUSAN / INPUT USER
                if decision_info:
                    self._stop_completion_sequence()
                    if self.thinking_log_widget:
                        self.log_box.removeWidget(self.thinking_log_widget)
                        self.thinking_log_widget.deleteLater()
                        self.thinking_log_widget = None

                    dec_title = decision_info.get("title", "Keputusan diperlukan")
                    self.task_icon_lbl.setPixmap(get_svg_pixmap("help_circle", 13, "#f59e0b"))
                    self.task_lbl.set_waiting_input(True)
                    self.task_lbl.set_running(False)
                    self.task_lbl.set_text(f"Membutuhkan input user: {dec_title}", None, None)
                    tooltip_detail = f"Membutuhkan Keputusan / Input User:\n{dec_title}"
                    if decision_info.get("detail"):
                        tooltip_detail += f"\n\n{decision_info['detail']}"
                    self.task_lbl.setToolTip(tooltip_detail)

                # KASUS A: AGEN SEDANG THINKING (Baik di awal prompt maupun di sela antar tool!)
                elif is_thinking:
                    self._stop_completion_sequence()
                    self.task_lbl.set_waiting_input(False)
                    self.task_lbl.set_running(True)
                    self.task_icon_lbl.setPixmap(get_svg_pixmap("brain", 13, "#c084fc"))
                    self.task_lbl.set_text("Thinking...", None, None)
                    self.task_lbl.setToolTip("Model sedang berpikir / menganalisis langkah berikutnya...")

                    if self.is_expanded and not self.thinking_log_widget:
                        self.thinking_log_widget = LogItemWidget(
                            TaskEvent(-1, "thinking", "Thinking...", "Model sedang memproses pemikiran", ""),
                            self.log_content
                        )
                        count = self.log_box.count()
                        self.log_box.insertWidget(max(0, count - 1), self.thinking_log_widget)
                        self.scroll_to_bottom()

                # KASUS B: AGEN SEDANG WORKING (Menjalankan tool aktif / menampilkan hasil penerapan tool terbaru)
                elif is_running:
                    self._stop_completion_sequence()
                    self.task_lbl.set_waiting_input(False)
                    self.task_lbl.set_running(True)
                    if self.thinking_log_widget:
                        self.log_box.removeWidget(self.thinking_log_widget)
                        self.thinking_log_widget.deleteLater()
                        self.thinking_log_widget = None

                    if current_task:
                        task_text = current_task.text
                        diff_add = current_task.lines_added if (current_task.applied and self.cfg_show_diff_stats) else None
                        diff_rem = current_task.lines_removed if (current_task.applied and self.cfg_show_diff_stats) else None
                        self.task_lbl.set_text(task_text, diff_add, diff_rem)

                        tip = f"{current_task.text}\n{current_task.detail}"
                        if current_task.category == "command":
                            tip += "\n(Klik untuk melihat sekilas command & response)"
                        self.task_lbl.setToolTip(tip)
                        ico, col = icon_map.get(current_task.category, ("terminal", "#38bdf8"))
                        self.task_icon_lbl.setPixmap(get_svg_pixmap(ico, 12, col))
                    else:
                        self.task_icon_lbl.setPixmap(get_svg_pixmap("terminal", 12, "#38bdf8"))
                        self.task_lbl.set_text("Working...", None, None)
                        self.task_lbl.setToolTip("Sedang memproses tugas...")

                # KASUS C: TASK SELESAI / IDLE
                else:
                    self.task_lbl.set_waiting_input(False)
                    self.task_lbl.set_running(False)
                    if self.thinking_log_widget:
                        self.log_box.removeWidget(self.thinking_log_widget)
                        self.thinking_log_widget.deleteLater()
                        self.thinking_log_widget = None

                    if not self._completion_seq_active:
                        last_task = self.monitor.get_last_tool_event()
                        if last_task or self.monitor.events:
                            self.task_icon_lbl.setPixmap(get_svg_pixmap("circle_check", 13, "#10b981"))
                            self.task_lbl.set_text("Tugas selesai", None, None)
                            summary = self._last_completed_summary or self.monitor.get_last_completion_summary()
                            self.task_lbl.setToolTip(f"Tugas selesai\nRingkasan: {summary}\n\n(Klik teks untuk memutar ulang ringkasan)")
                        else:
                            self.task_icon_lbl.setPixmap(get_svg_pixmap("terminal", 12, "#38bdf8"))
                            self.task_lbl.set_text("Standby / Menunggu task...", None, None)
                            self.task_lbl.setToolTip("Menunggu instruksi tugas...")

            # Update Kuota Model Ring
            pct, used_tokens, total_tokens, model_name = self.monitor.get_quota_info()
            self.quota_ring.set_quota_data(pct, used_tokens, total_tokens, model_name)

            # Update Session Selector ComboBox
            self.update_session_dropdown()

            # Dynamic Polling Interval
            desired_interval = self.cfg_poll_interval_active_ms if (is_running or decision_info) else 1100
            if self.poll_timer.interval() != desired_interval:
                self.poll_timer.setInterval(desired_interval)
        except Exception:
            log_exception("Exception in on_poll_tick")

    def refresh_visible_log_items(self):
        for i in range(self.log_box.count()):
            item = self.log_box.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, LogItemWidget):
                w.refresh()

    def append_log_item(self, ev: TaskEvent):
        item_w = LogItemWidget(ev, self.log_content, on_command_clicked=self.trigger_command_glance)
        count = self.log_box.count()
        self.log_box.insertWidget(max(0, count - 1), item_w)

    def populate_all_logs(self):
        while self.log_box.count() > 1:
            child = self.log_box.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.thinking_log_widget = None

        for ev in self.monitor.events:
            if ev.category != "user":
                item_w = LogItemWidget(ev, self.log_content, on_command_clicked=self.trigger_command_glance)
                count = self.log_box.count()
                self.log_box.insertWidget(max(0, count - 1), item_w)

        is_running = (self.monitor.current_status == "RUNNING")
        if self.monitor.is_agent_thinking(is_running):
            self.thinking_log_widget = LogItemWidget(
                TaskEvent(-1, "thinking", "Thinking...", "Model sedang memproses pemikiran", ""),
                self.log_content
            )
            count = self.log_box.count()
            self.log_box.insertWidget(max(0, count - 1), self.thinking_log_widget)

        self.update_category_summary()
        self.scroll_to_bottom()

    def update_category_summary(self):
        categories = set(e.category for e in self.monitor.events)
        parts = []
        if "read" in categories or "search" in categories:
            parts.append("Explored files")
        if "command" in categories:
            parts.append("ran commands")
        if "edit" in categories or "write" in categories:
            parts.append("edited files")
        if "mcp" in categories:
            parts.append("called tools")
        if "decision" in categories:
            parts.append("decisions requested")

        if parts:
            summary = ", ".join(parts).capitalize()
            self.category_summary_lbl.setText(summary)
        else:
            self.category_summary_lbl.setText("Active progress logs")

        count = len(self.monitor.events)
        if hasattr(self, "task_count_badge"):
            self.task_count_badge.setText(f"{count} tasks" if count != 1 else "1 task")

    def update_session_dropdown(self):
        sessions = self.monitor.active_sessions
        if not sessions:
            return

        current_items = [(self.session_combo.itemData(i), self.session_combo.itemText(i)) for i in range(self.session_combo.count())]
        new_items = []
        for s in sessions:
            c_id, title, status = s
            prefix = "[RUNNING] " if status == "RUNNING" else ""
            display = f"{prefix}{title}"
            new_items.append((c_id, display, status))

        if current_items != [(x[0], x[1]) for x in new_items]:
            self.session_combo.blockSignals(True)
            self.session_combo.clear()
            for c_id, display, status in new_items:
                ico_col = "#10b981" if status == "RUNNING" else "#64748b"
                self.session_combo.addItem(get_svg_icon("dot", 10, ico_col), display, c_id)

            idx = self.session_combo.findData(self.monitor.current_conv_id)
            if idx >= 0:
                self.session_combo.setCurrentIndex(idx)
            self.session_combo.blockSignals(False)

    def on_session_changed(self, idx: int):
        c_id = self.session_combo.itemData(idx)
        if c_id and c_id != self.selected_conv_id:
            self.selected_conv_id = c_id
            self.monitor.check_active_session(preferred_conv_id=c_id)
            self.populate_all_logs()

    def scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    # --- RESIZE PANJANG / LEBAR JENDELA & DRAG WINDOW SECARA DINAMIS ---
    def _detect_resize_edge(self, local_pos: QPoint) -> Optional[str]:
        w = self.width()
        h = self.height()
        x = local_pos.x()
        y = local_pos.y()

        # Jangan tangkap resize jika kursor sedang berada di atas tombol ActionCard (Pin/Expand/Close)
        if hasattr(self, "action_card") and self.action_card.isVisible():
            card_pos = self.action_card.mapFromGlobal(self.mapToGlobal(local_pos))
            if self.action_card.rect().contains(card_pos):
                return None

        # Margin 10px dari root_layout + 10px area dalam border main_container (4..20px)
        on_left = (4 <= x <= 20)
        on_right = (w - 20 <= x <= w - 4)
        on_bottom = self.is_expanded and (h - 20 <= y <= h - 4)

        if on_right and on_bottom:
            return "bottom-right"
        if on_left and on_bottom:
            return "bottom-left"
        if on_right:
            return "right"
        if on_left:
            return "left"
        if on_bottom:
            return "bottom"
        return None

    def _update_cursor_for_edge(self, edge: Optional[str]):
        if edge in ("left", "right"):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif edge == "bottom":
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        elif edge == "bottom-right":
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif edge == "bottom-left":
            self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        else:
            self.unsetCursor()

    def _perform_live_resize(self, global_pt: QPoint):
        delta = global_pt - self._resize_start_pos
        g = self._resize_start_geom

        new_x = g.x()
        new_y = g.y()
        new_w = g.width()

        if "right" in self._resize_mode:
            new_w = max(MIN_WINDOW_WIDTH, min(MAX_WINDOW_WIDTH, g.width() + delta.x()))
        elif "left" in self._resize_mode:
            proposed_w = max(MIN_WINDOW_WIDTH, min(MAX_WINDOW_WIDTH, g.width() - delta.x()))
            new_x = g.right() - proposed_w + 1
            new_w = proposed_w

        if "bottom" in self._resize_mode and self.is_expanded:
            extra_rows_h = self._get_active_extra_rows_count() * EXTRA_ROW_HEIGHT
            proposed_exp_h = max(MIN_EXPANDED_HEIGHT, min(MAX_EXPANDED_HEIGHT, (g.height() - extra_rows_h) + delta.y()))
            self._user_expanded_height = proposed_exp_h
            new_h = proposed_exp_h + extra_rows_h
            self._current_height = new_h
            self.setFixedHeight(new_h)

        self._user_width = new_w
        self.setGeometry(new_x, new_y, new_w, self._current_height)
        self.reposition_action_card()
        self.update_title_elide()

    def eventFilter(self, obj, event):
        if self.isVisible() and isinstance(obj, QWidget) and (obj is self or self.isAncestorOf(obj)):
            etype = event.type()
            if etype == QEvent.Type.MouseMove:
                global_pt = QCursor.pos()
                if self._resize_mode:
                    self._perform_live_resize(global_pt)
                    return True
                if self.drag_position.isNull():
                    local_pt = self.mapFromGlobal(global_pt)
                    if self.rect().contains(local_pt):
                        edge = self._detect_resize_edge(local_pt)
                        self._update_cursor_for_edge(edge)
            elif etype == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                global_pt = QCursor.pos()
                local_pt = self.mapFromGlobal(global_pt)
                edge = self._detect_resize_edge(local_pt)
                if edge:
                    self._resize_mode = edge
                    self._resize_start_pos = global_pt
                    self._resize_start_geom = self.geometry()
                    return True
            elif etype == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                if self._resize_mode:
                    self._resize_mode = None
                    self._update_cursor_for_edge(None)
                    self.save_config()
                    return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            local_pt = event.position().toPoint()
            edge = self._detect_resize_edge(local_pt)
            if edge:
                self._resize_mode = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
                event.accept()
                return

            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        global_pt = event.globalPosition().toPoint()

        if self._resize_mode and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = global_pt - self._resize_start_pos
            g = self._resize_start_geom

            new_x = g.x()
            new_y = g.y()
            new_w = g.width()
            new_h = g.height()

            if "right" in self._resize_mode:
                new_w = max(MIN_WINDOW_WIDTH, min(MAX_WINDOW_WIDTH, g.width() + delta.x()))
            elif "left" in self._resize_mode:
                proposed_w = max(MIN_WINDOW_WIDTH, min(MAX_WINDOW_WIDTH, g.width() - delta.x()))
                new_x = g.right() - proposed_w + 1
                new_w = proposed_w

            if "bottom" in self._resize_mode and self.is_expanded:
                extra_rows_h = self._get_active_extra_rows_count() * EXTRA_ROW_HEIGHT
                proposed_exp_h = max(MIN_EXPANDED_HEIGHT, min(MAX_EXPANDED_HEIGHT, (g.height() - extra_rows_h) + delta.y()))
                self._user_expanded_height = proposed_exp_h
                new_h = proposed_exp_h + extra_rows_h
                self._current_height = new_h
                self.setFixedHeight(new_h)

            self._user_width = new_w
            self.setGeometry(new_x, new_y, new_w, self._current_height)
            self.reposition_action_card()
            self.update_title_elide()
            event.accept()
            return

        if event.buttons() == Qt.MouseButton.LeftButton and not self.drag_position.isNull():
            self.move(global_pt - self.drag_position)
            event.accept()
            return

        edge = self._detect_resize_edge(event.position().toPoint())
        self._update_cursor_for_edge(edge)

    def mouseReleaseEvent(self, event):
        self._resize_mode = None
        self.drag_position = QPoint()
        self.save_config()

    def check_config_hot_reload(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            mtime = os.path.getmtime(CONFIG_FILE)
            if mtime > self._config_last_mtime:
                self._config_last_mtime = mtime
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.apply_live_config(cfg, is_hot_reload=True)
        except Exception:
            pass

    def snap_to_preset(self, preset: str):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        w = self._user_width
        h = self._current_height
        margin_x = 20
        margin_y = 30

        if preset == "top-left":
            new_x, new_y = geom.left() + margin_x, geom.top() + margin_y
        elif preset == "top-center":
            new_x, new_y = geom.left() + (geom.width() - w) // 2, geom.top() + margin_y
        elif preset == "bottom-left":
            new_x, new_y = geom.left() + margin_x, geom.bottom() - h - margin_y
        elif preset == "bottom-right":
            new_x, new_y = geom.right() - w - margin_x, geom.bottom() - h - margin_y
        else:  # "top-right"
            new_x, new_y = geom.right() - w - margin_x, geom.top() + margin_y

        self.move(new_x, new_y)

    def apply_live_config(self, cfg: dict, is_hot_reload: bool = False):
        if not isinstance(cfg, dict):
            return

        # 1. Dimensi Panjang/Lebar & Tinggi Expanded
        w = cfg.get("width")
        exp_h = cfg.get("expanded_height")
        geom_changed = False
        if isinstance(w, int) and MIN_WINDOW_WIDTH <= w <= MAX_WINDOW_WIDTH and w != self._user_width:
            self._user_width = w
            geom_changed = True
        if isinstance(exp_h, int) and MIN_EXPANDED_HEIGHT <= exp_h <= MAX_EXPANDED_HEIGHT and exp_h != self._user_expanded_height:
            self._user_expanded_height = exp_h
            geom_changed = True

        if geom_changed and not self._resize_mode:
            target_h = self._calculate_target_height()
            self._current_height = target_h
            self.setFixedHeight(target_h)
            self.resize(self._user_width, target_h)
            self.reposition_action_card()
            self.update_title_elide()

        # 2. Posisi Layar atau Snap Preset dari IDE Extension
        snap_preset = cfg.get("snap_preset")
        if snap_preset:
            self.snap_to_preset(str(snap_preset))
            # Hapus flag one-shot snap_preset dan simpan koordinat barunya
            self.save_config()
        else:
            x = cfg.get("x")
            y = cfg.get("y")
            if isinstance(x, int) and isinstance(y, int):
                if not is_hot_reload or (abs(x - self.x()) > 2 or abs(y - self.y()) > 2):
                    if self.drag_position.isNull() and not self._resize_mode:
                        self.move(x, y)

        # 3. Opacity & Always On Top
        opacity = cfg.get("window_opacity")
        if isinstance(opacity, (int, float)):
            opacity_clamped = max(40, min(100, int(opacity)))
            if opacity_clamped != self.cfg_window_opacity:
                self.cfg_window_opacity = opacity_clamped
                self.setWindowOpacity(self.cfg_window_opacity / 100.0)

        always_on_top = cfg.get("always_on_top")
        if isinstance(always_on_top, bool) and always_on_top != self.is_pinned:
            self.is_pinned = always_on_top
            self.cfg_always_on_top = always_on_top
            if self.is_pinned:
                self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                self.pin_btn.setIcon(get_svg_icon("pin", 15, "#cbd5e1"))
                self.pin_btn.setToolTip("Always On Top (Aktif)")
            else:
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
                self.pin_btn.setIcon(get_svg_icon("pin_off", 15, "#64748b"))
                self.pin_btn.setToolTip("Always On Top (Nonaktif)")
            if self.isVisible():
                self.show()

        # 4. Toggles Komponen UI
        if isinstance(cfg.get("show_quota_ring"), bool):
            self.cfg_show_quota_ring = cfg["show_quota_ring"]
            self.quota_ring.setVisible(self.cfg_show_quota_ring)
            self.update_title_elide()

        if isinstance(cfg.get("show_duration_timer"), bool):
            self.cfg_show_duration_timer = cfg["show_duration_timer"]
            if not self.cfg_show_duration_timer and self.duration_container.isVisible():
                self.duration_container.setVisible(False)
                self.update_title_elide()

        if isinstance(cfg.get("show_model_badge"), bool):
            self.cfg_show_model_badge = cfg["show_model_badge"]
            if not self.cfg_show_model_badge:
                self.model_badge.setVisible(False)

        if isinstance(cfg.get("show_diff_stats"), bool):
            self.cfg_show_diff_stats = cfg["show_diff_stats"]

        if isinstance(cfg.get("show_bg_process"), bool):
            self.cfg_show_bg_process = cfg["show_bg_process"]
            if not self.cfg_show_bg_process and self._has_bg_visible:
                self.set_bg_process_visibility(False)

        if isinstance(cfg.get("show_completion_summary"), bool):
            self.cfg_show_completion_summary = cfg["show_completion_summary"]

        # 5. Parameter Kecepatan & Durasi
        if isinstance(cfg.get("marquee_speed"), (int, float)):
            self.cfg_marquee_speed = max(1, min(6, int(cfg["marquee_speed"])))
            self.task_lbl.scroll_speed = float(self.cfg_marquee_speed)

        if isinstance(cfg.get("model_badge_duration_ms"), int):
            self.cfg_model_badge_duration_ms = max(1500, min(15000, cfg["model_badge_duration_ms"]))

        if isinstance(cfg.get("summary_duration_ms"), int):
            self.cfg_summary_duration_ms = max(2000, min(20000, cfg["summary_duration_ms"]))

        if isinstance(cfg.get("cmd_glance_duration_ms"), int):
            self.cfg_cmd_glance_duration_ms = max(2000, min(20000, cfg["cmd_glance_duration_ms"]))

        if isinstance(cfg.get("poll_interval_active_ms"), int):
            self.cfg_poll_interval_active_ms = max(150, min(2000, cfg["poll_interval_active_ms"]))

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                self._config_last_mtime = os.path.getmtime(CONFIG_FILE)
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.apply_live_config(cfg, is_hot_reload=False)
                if cfg.get("x") is not None and cfg.get("y") is not None:
                    return
            except Exception:
                pass

        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            self.resize(self._user_width, self._current_height)
            self.move(geom.right() - self._user_width - 20, geom.top() + 30)
            self.save_config()

    def save_config(self):
        try:
            existing = {}
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = {}

            existing.update({
                "x": self.x(),
                "y": self.y(),
                "width": self._user_width,
                "expanded_height": self._user_expanded_height,
                "always_on_top": self.is_pinned,
                "window_opacity": self.cfg_window_opacity,
                "show_quota_ring": self.cfg_show_quota_ring,
                "show_duration_timer": self.cfg_show_duration_timer,
                "show_model_badge": self.cfg_show_model_badge,
                "show_diff_stats": self.cfg_show_diff_stats,
                "show_bg_process": self.cfg_show_bg_process,
                "show_completion_summary": self.cfg_show_completion_summary,
                "marquee_speed": self.cfg_marquee_speed,
                "model_badge_duration_ms": self.cfg_model_badge_duration_ms,
                "summary_duration_ms": self.cfg_summary_duration_ms,
                "cmd_glance_duration_ms": self.cfg_cmd_glance_duration_ms,
                "poll_interval_active_ms": self.cfg_poll_interval_active_ms,
            })
            existing.pop("snap_preset", None)
            if "auto_start" not in existing:
                existing["auto_start"] = True
            if "auto_close_with_ide" not in existing:
                existing["auto_close_with_ide"] = True

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
            self._config_last_mtime = os.path.getmtime(CONFIG_FILE)
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_config()
        super().closeEvent(event)
        app = QApplication.instance()
        if app:
            app.quit()
