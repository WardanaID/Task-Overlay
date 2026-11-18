from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont

class CircularQuotaRing(QWidget):
    """
    Lingkaran indikator sisa kuota penggunaan model aktif (Context & Model Quota Ring).
    """
    def __init__(self, parent=None, size=34):
        super().__init__(parent)
        self.ring_size = size
        self.setFixedSize(size, size)
        
        self.remaining_pct: float = 100.0
        self.used_tokens: int = 0
        self.total_tokens: int = 1_000_000
        self.model_name: str = "Gemini"
        self.show_percentage_text: bool = True
        self.is_hovered: bool = False

        self.update_tooltip()

    def set_quota_data(self, remaining_pct: float, used_tokens: int, total_tokens: int, model_name: str = ""):
        self.remaining_pct = max(0.0, min(100.0, float(remaining_pct)))
        self.used_tokens = used_tokens
        self.total_tokens = max(1, total_tokens)
        if model_name:
            self.model_name = model_name
        self.update_tooltip()
        self.update()

    def update_tooltip(self):
        used_k = f"{self.used_tokens / 1000:.1f}k" if self.used_tokens >= 1000 else str(self.used_tokens)
        total_k = f"{self.total_tokens / 1000:.0f}k" if self.total_tokens < 1_000_000 else f"{self.total_tokens / 1_000_000:.1f}M"
        rem_tokens = max(0, self.total_tokens - self.used_tokens)
        rem_k = f"{rem_tokens / 1000:.1f}k" if rem_tokens >= 1000 else str(rem_tokens)

        tip = (
            f"<b>Sisa Kuota Model: {self.remaining_pct:.1f}%</b><br>"
            f"Model: {self.model_name}<br>"
            f"Token Terpakai: {used_k} / {total_k}<br>"
            f"Token Tersisa: {rem_k}<br>"
            f"<i>(Klik untuk ganti tampilan % / token)</i>"
        )
        self.setToolTip(tip)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_percentage_text = not self.show_percentage_text
            self.update()
            event.accept()

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 3.5
        rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)

        # 1. Background ring track
        track_color = QColor(255, 255, 255, 35 if not self.is_hovered else 50)
        track_pen = QPen(track_color, 2.8)
        painter.setPen(track_pen)
        painter.drawEllipse(rect)

        # 2. Foreground progress arc (Sisa Kuota)
        # Warna dinamis berdasarkan persentase sisa
        if self.remaining_pct > 50.0:
            arc_color = QColor(16, 185, 129)  # Emerald green
        elif self.remaining_pct > 20.0:
            arc_color = QColor(245, 158, 11)  # Amber orange
        else:
            arc_color = QColor(239, 68, 68)   # Danger red

        arc_pen = QPen(arc_color, 3.2)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)

        # Start from top (90 degrees in QPainter coordinates = 90 * 16)
        # Span clockwise (negative angle)
        start_angle = 90 * 16
        span_angle = -int((self.remaining_pct / 100.0) * 360 * 16)
        painter.drawArc(rect, start_angle, span_angle)

        # 3. Center Text
        painter.setPen(QColor(241, 245, 249))
        
        if self.show_percentage_text:
            text = f"{int(self.remaining_pct)}%" if self.remaining_pct < 100 else "100"
            font_size = 7 if len(text) >= 3 else 8
        else:
            # Tampilkan token used
            text = f"{self.used_tokens // 1000}k" if self.used_tokens >= 1000 else str(self.used_tokens)
            font_size = 7

        font = QFont("Segoe UI", font_size, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)

        painter.end()

