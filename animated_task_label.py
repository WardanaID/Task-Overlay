import time
from typing import Optional
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QFont, QColor, QLinearGradient, QBrush, QPen, QFontMetrics

class AnimatedTaskLabel(QWidget):
    """
    Label khusus untuk task realtime dengan:
    1. Transisi halus (fade & slide) saat teks task berganti.
    2. Marquee auto-scroll jika teks (+ indikator diff) melebihi lebar tampilan.
    3. Animasi glow swipe / shimmer gradient bergerak saat proses sedang berjalan.
    4. Indikator perubahan baris (+baris hijau / -baris merah) di samping nama proses.
    5. Hemat resource: Timer animasi berhenti otomatis saat idle & tidak overflow.
    """
    def __init__(self, parent=None, base_color: str = "#94a3b8"):
        super().__init__(parent)
        self.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.setFixedHeight(18)

        self.base_color: str = base_color
        self.current_text: str = "Menunggu task..."
        self.prev_text: str = ""
        self.is_running: bool = False
        self.is_waiting_input: bool = False

        # Diff baris (+baris / -baris) saat membuat/mengedit/menghapus baris file
        self.diff_added: Optional[int] = None
        self.diff_removed: Optional[int] = None
        self.prev_diff_added: Optional[int] = None
        self.prev_diff_removed: Optional[int] = None

        # Transisi Teks (0.0 -> 1.0)
        self.transition_progress: float = 1.0
        self.transition_start_time: float = 0.0
        self.transition_duration: float = 0.22  # 220 ms

        # Marquee Scroll State
        self.scroll_x: float = 0.0
        self.marquee_state: str = "PAUSE_START"  # PAUSE_START, SCROLL_FWD, PAUSE_END, SCROLL_BACK
        self.state_start_time: float = time.time()
        self.scroll_speed: float = 42.0  # pixel per detik

        # Shimmer Glow Swipe State
        self.shimmer_phase: float = 0.0
        self.shimmer_speed: float = 0.6  # siklus per detik

        # Animasi Timer (30 FPS / ~33ms)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(33)
        self.anim_timer.timeout.connect(self.on_anim_frame)

    def set_base_color(self, color: str):
        if self.base_color != color:
            self.base_color = color
            self.update()

    def set_diff_stats(self, added: Optional[int] = None, removed: Optional[int] = None):
        if self.diff_added != added or self.diff_removed != removed:
            self.diff_added = added
            self.diff_removed = removed
            self.start_timer_if_needed()
            self.update()

    def set_text(self, text: str, diff_added: Optional[int] = None, diff_removed: Optional[int] = None):
        text = text.strip()
        if not text:
            return

        if text == self.current_text:
            # Teks sama, namun mungkin statistik +baris -baris baru saja diterapkan
            if self.diff_added != diff_added or self.diff_removed != diff_removed:
                self.diff_added = diff_added
                self.diff_removed = diff_removed
                self.start_timer_if_needed()
                self.update()
            return

        self.prev_text = self.current_text
        self.prev_diff_added = self.diff_added
        self.prev_diff_removed = self.diff_removed

        self.current_text = text
        self.diff_added = diff_added
        self.diff_removed = diff_removed
        self.setToolTip(text)

        # Mulai transisi teks baru
        self.transition_progress = 0.0
        self.transition_start_time = time.time()

        # Reset marquee
        self.scroll_x = 0.0
        self.marquee_state = "PAUSE_START"
        self.state_start_time = time.time()

        self.start_timer_if_needed()
        self.update()

    def set_running(self, running: bool):
        if self.is_running != running:
            self.is_running = running
            if running:
                self.shimmer_phase = 0.0
            self.start_timer_if_needed()
            self.update()

    def set_waiting_input(self, waiting: bool):
        if self.is_waiting_input != waiting:
            self.is_waiting_input = waiting
            if waiting:
                self.shimmer_phase = 0.0
            self.start_timer_if_needed()
            self.update()

    def start_timer_if_needed(self):
        if not self.anim_timer.isActive():
            self.anim_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.start_timer_if_needed()
        self.update()

    def _compute_total_width(self, fm: QFontMetrics, text: str, added: Optional[int], removed: Optional[int]) -> int:
        total_w = fm.horizontalAdvance(text)
        if added is not None or removed is not None:
            plus_str = f"+{added or 0}"
            minus_str = f"-{removed or 0}"
            total_w += 8 + fm.horizontalAdvance(plus_str) + 5 + fm.horizontalAdvance(minus_str)
        return total_w

    def on_anim_frame(self):
        now = time.time()
        needs_redraw = False

        # 1. Update Transisi Teks
        if self.transition_progress < 1.0:
            elapsed = now - self.transition_start_time
            self.transition_progress = min(1.0, elapsed / self.transition_duration)
            needs_redraw = True
            if self.transition_progress >= 1.0:
                self.prev_text = ""
                self.prev_diff_added = None
                self.prev_diff_removed = None
                self.state_start_time = now

        # 2. Update Shimmer Swipe (saat running atau waiting input)
        if self.is_running or self.is_waiting_input:
            self.shimmer_phase = (self.shimmer_phase + (33 / 1000.0) * self.shimmer_speed) % 1.0
            needs_redraw = True

        # 3. Update Marquee Auto-Scroll jika overflow
        fm = QFontMetrics(self.font())
        text_w = self._compute_total_width(fm, self.current_text, self.diff_added, self.diff_removed)
        avail_w = self.width()

        if text_w > avail_w and self.transition_progress >= 1.0:
            max_scroll = text_w - avail_w + 20
            dt = 0.033

            if self.marquee_state == "PAUSE_START":
                if now - self.state_start_time > 1.3:
                    self.marquee_state = "SCROLL_FWD"
                    self.state_start_time = now
            elif self.marquee_state == "SCROLL_FWD":
                self.scroll_x += self.scroll_speed * dt
                needs_redraw = True
                if self.scroll_x >= max_scroll:
                    self.scroll_x = max_scroll
                    self.marquee_state = "PAUSE_END"
                    self.state_start_time = now
            elif self.marquee_state == "PAUSE_END":
                if now - self.state_start_time > 1.2:
                    self.marquee_state = "SCROLL_BACK"
                    self.state_start_time = now
            elif self.marquee_state == "SCROLL_BACK":
                self.scroll_x -= self.scroll_speed * 1.5 * dt
                needs_redraw = True
                if self.scroll_x <= 0.0:
                    self.scroll_x = 0.0
                    self.marquee_state = "PAUSE_START"
                    self.state_start_time = now
        else:
            if self.scroll_x != 0.0:
                self.scroll_x = 0.0
                needs_redraw = True

        # Stop timer jika tidak ada lagi yang perlu dianimasikan
        if not self.is_running and not self.is_waiting_input and self.transition_progress >= 1.0 and (text_w <= avail_w):
            self.anim_timer.stop()

        if needs_redraw:
            self.update()

    def _draw_row_content(
        self,
        painter: QPainter,
        x: int,
        y: int,
        text: str,
        main_pen: QPen,
        added: Optional[int],
        removed: Optional[int]
    ):
        painter.setPen(main_pen)
        painter.drawText(x, y, text)

        if added is not None or removed is not None:
            fm = painter.fontMetrics()
            cur_x = x + fm.horizontalAdvance(text) + 8
            plus_str = f"+{added or 0}"
            minus_str = f"-{removed or 0}"

            diff_font = QFont(self.font())
            diff_font.setWeight(QFont.Weight.Bold)
            painter.setFont(diff_font)

            # +baris (Hijau Emerald)
            painter.setPen(QColor("#34d399"))
            painter.drawText(cur_x, y, plus_str)
            cur_x += QFontMetrics(diff_font).horizontalAdvance(plus_str) + 5

            # -baris (Merah Coral)
            painter.setPen(QColor("#f87171"))
            painter.drawText(cur_x, y, minus_str)

            painter.setFont(self.font())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())

        w = self.width()
        h = self.height()
        fm = self.fontMetrics()
        base_y = (h + fm.ascent() - fm.descent()) // 2

        # 1. Menentukan Warna & Shimmer Gradient
        if self.is_waiting_input:
            sweep_width = max(100.0, w * 0.5)
            glow_center = -sweep_width + self.shimmer_phase * (w + 2 * sweep_width)

            grad = QLinearGradient(glow_center - sweep_width / 2, 0, glow_center + sweep_width / 2, 0)
            grad.setColorAt(0.0, QColor("#f59e0b"))
            grad.setColorAt(0.5, QColor("#ffffff"))
            grad.setColorAt(1.0, QColor("#fbbf24"))
            pen = QPen(QBrush(grad), 1)
        elif self.is_running:
            sweep_width = max(100.0, w * 0.5)
            glow_center = -sweep_width + self.shimmer_phase * (w + 2 * sweep_width)

            grad = QLinearGradient(glow_center - sweep_width / 2, 0, glow_center + sweep_width / 2, 0)
            grad.setColorAt(0.0, QColor("#38bdf8"))
            grad.setColorAt(0.5, QColor("#ffffff"))
            grad.setColorAt(1.0, QColor("#38bdf8"))
            pen = QPen(QBrush(grad), 1)
        else:
            pen = QPen(QColor(self.base_color))

        # Clip ke boundary widget agar tidak tumpah saat scroll
        painter.setClipRect(self.rect())

        # 2. Gambar saat Transisi Teks
        if self.transition_progress < 1.0 and self.prev_text:
            old_opacity = max(0.0, 1.0 - self.transition_progress)
            old_y_offset = -self.transition_progress * 14.0
            painter.setOpacity(old_opacity)
            self._draw_row_content(
                painter, 0, int(base_y + old_y_offset),
                self.prev_text, pen, self.prev_diff_added, self.prev_diff_removed
            )

            new_opacity = min(1.0, self.transition_progress)
            new_y_offset = (1.0 - self.transition_progress) * 14.0
            painter.setOpacity(new_opacity)
            self._draw_row_content(
                painter, 0, int(base_y + new_y_offset),
                self.current_text, pen, self.diff_added, self.diff_removed
            )
        else:
            # Teks Normal / Marquee
            painter.setOpacity(1.0)
            draw_x = int(-self.scroll_x)
            self._draw_row_content(
                painter, draw_x, base_y,
                self.current_text, pen, self.diff_added, self.diff_removed
            )

        painter.end()
