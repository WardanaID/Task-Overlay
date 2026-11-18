from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, pyqtProperty, QRectF, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QBrush, QPen

class AnimatedModelBadge(QWidget):
    """
    Badge model animasi mandiri menggunakan QPainter murni (tanpa QGraphicsOpacityEffect)
    sehingga 100% bebas dari bug ghosting / artefak sisa piksel di Windows transparent window.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelBadge")
        self.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.setFixedHeight(18)

        self._text: str = ""
        self._opacity: float = 0.0
        self._current_width: int = 0
        self._target_width: int = 0

        # Inisialisasi awal tersembunyi
        self.setFixedWidth(0)
        self.setVisible(False)

        # Animation Group
        self.anim_group = None

        # Timer auto hide
        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.hide_badge)

    @pyqtProperty(float)
    def opacity(self) -> float:
        return self._opacity

    @opacity.setter
    def opacity(self, val: float):
        self._opacity = max(0.0, min(1.0, val))
        self.update()

    @pyqtProperty(int)
    def badge_width(self) -> int:
        return self._current_width

    @badge_width.setter
    def badge_width(self, w: int):
        self._current_width = max(0, w)
        self.setFixedWidth(self._current_width)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._current_width, 18)

    def trigger_display(self, model_name: str, duration_ms: int = 4500):
        if not model_name:
            model_name = "Gemini 3.8 Flash"

        import re
        display_name = re.sub(r"\(.*?\)", "", model_name).strip(" `'\"")
        if not display_name:
            display_name = model_name

        self._text = display_name
        fm = QFontMetrics(self.font())
        self._target_width = fm.horizontalAdvance(display_name) + 16

        self.setVisible(True)

        if self.anim_group and self.anim_group.state() == QParallelAnimationGroup.State.Running:
            self.anim_group.stop()

        # Animasi Fade In (via _opacity) & Width Expand (via badge_width / setFixedWidth)
        self.anim_group = QParallelAnimationGroup(self)

        anim_opacity = QPropertyAnimation(self, b"opacity")
        anim_opacity.setDuration(280)
        anim_opacity.setStartValue(self._opacity)
        anim_opacity.setEndValue(1.0)
        anim_opacity.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim_width = QPropertyAnimation(self, b"badge_width")
        anim_width.setDuration(300)
        anim_width.setStartValue(self._current_width)
        anim_width.setEndValue(self._target_width)
        anim_width.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_group.addAnimation(anim_opacity)
        self.anim_group.addAnimation(anim_width)
        self.anim_group.start()

        self.auto_hide_timer.start(duration_ms)

    def hide_badge(self):
        if self.anim_group and self.anim_group.state() == QParallelAnimationGroup.State.Running:
            self.anim_group.stop()

        self.anim_group = QParallelAnimationGroup(self)

        anim_opacity = QPropertyAnimation(self, b"opacity")
        anim_opacity.setDuration(280)
        anim_opacity.setStartValue(self._opacity)
        anim_opacity.setEndValue(0.0)
        anim_opacity.setEasingCurve(QEasingCurve.Type.InCubic)

        anim_width = QPropertyAnimation(self, b"badge_width")
        anim_width.setDuration(300)
        anim_width.setStartValue(self._current_width)
        anim_width.setEndValue(0)
        anim_width.setEasingCurve(QEasingCurve.Type.InCubic)

        self.anim_group.addAnimation(anim_opacity)
        self.anim_group.addAnimation(anim_width)
        self.anim_group.finished.connect(self._on_hide_finished)
        self.anim_group.start()

    def _on_hide_finished(self):
        if self._opacity <= 0.01:
            self.setVisible(False)
            if self.parentWidget():
                self.parentWidget().update()

    def paintEvent(self, event):
        if self._opacity <= 0.005 or self.width() <= 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        # Background Pill dengan warna cyan cerah yang kontras & jelas terbaca
        bg_alpha = int(45 * self._opacity)
        bg_color = QColor(56, 189, 248, bg_alpha)

        # Border
        border_alpha = int(120 * self._opacity)
        border_color = QColor(56, 189, 248, border_alpha)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(rect, 4, 4)

        # Text
        text_alpha = int(255 * self._opacity)
        text_color = QColor(56, 189, 248, text_alpha)
        painter.setPen(text_color)
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)

        painter.end()
