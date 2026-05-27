"""Toast notifications with slide-in animation and auto-dismiss."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout

from app.ui.design import tokens as t


class ToastNotification(QWidget):
    TYPE_COLORS = {
        "success": t.SUCCESS,
        "error":   t.ERROR,
        "info":    t.INFO,
        "warning": t.WARNING,
    }
    TYPE_ICONS = {
        "success": "✓",
        "error":   "✕",
        "info":    "ℹ",
        "warning": "⚠",
    }

    W = 320
    H = 56

    def __init__(self, message: str, toast_type: str = "info", parent: QWidget = None):
        super().__init__(parent)
        self._type = toast_type
        self._color = self.TYPE_COLORS.get(toast_type, t.INFO)
        self._icon  = self.TYPE_ICONS.get(toast_type, "ℹ")

        self.setFixedSize(self.W, self.H)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(t.SP4, 0, t.SP4, 0)
        layout.setSpacing(t.SP3)

        icon_lbl = QLabel(self._icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setStyleSheet(f"color: {self._color}; font-size: 16px; background: transparent;")

        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 13px; background: transparent;")
        msg_lbl.setWordWrap(False)

        layout.addWidget(icon_lbl)
        layout.addWidget(msg_lbl, 1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(self.rect(), t.RADIUS_MD, t.RADIUS_MD)
        painter.fillPath(path, QColor(t.BG_OVERLAY))

        # Left accent bar
        bar_path = QPainterPath()
        bar_path.addRoundedRect(0, 0, 4, self.height(), 2, 2)
        painter.fillPath(bar_path, QColor(self._color))

        # Border
        painter.setPen(QColor(self._color + "66"))
        painter.drawPath(path)


class ToastManager:
    _instance: ToastManager | None = None

    def __init__(self, parent: QWidget):
        self._parent = parent
        self._queue: list[tuple[str, str]] = []
        self._active: list[ToastNotification] = []
        self._MAX_VISIBLE = 3

    @classmethod
    def init(cls, parent: QWidget) -> "ToastManager":
        cls._instance = cls(parent)
        return cls._instance

    @classmethod
    def instance(cls) -> "ToastManager":
        if cls._instance is None:
            raise RuntimeError("ToastManager not initialized — call ToastManager.init(parent) first")
        return cls._instance

    def show(self, message: str, toast_type: str = "info") -> None:
        self._queue.append((message, toast_type))
        self._process_queue()

    def _process_queue(self) -> None:
        while self._queue and len(self._active) < self._MAX_VISIBLE:
            message, toast_type = self._queue.pop(0)
            self._spawn(message, toast_type)

    def _spawn(self, message: str, toast_type: str) -> None:
        toast = ToastNotification(message, toast_type, self._parent)
        self._active.append(toast)
        self._position_all()

        # Capture end_rect from the geometry already set by _position_all,
        # then move toast to start position before show() so Qt initialises
        # the native window at the correct offset.
        end_rect = toast.geometry()
        start_rect = QRect(end_rect.x() + 60, end_rect.y(), end_rect.width(), end_rect.height())
        toast.setGeometry(start_rect)
        toast.show()
        toast.raise_()

        # Slide-in animation
        anim = QPropertyAnimation(toast, b"geometry")
        anim.setDuration(t.DUR_NORMAL)
        anim.setStartValue(start_rect)
        anim.setEndValue(end_rect)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        toast._anim = anim  # keep reference

        # Auto-dismiss after 4s
        QTimer.singleShot(4000, lambda: self._dismiss(toast))

    def _dismiss(self, toast: ToastNotification) -> None:
        if toast not in self._active:
            return
        self._active.remove(toast)

        r = toast.geometry()
        end_rect = QRect(r.x() + 60, r.y(), r.width(), r.height())
        anim = QPropertyAnimation(toast, b"geometry")
        anim.setDuration(t.DUR_NORMAL)
        anim.setStartValue(r)
        anim.setEndValue(end_rect)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(toast.deleteLater)
        anim.start()
        toast._dismiss_anim = anim

        self._position_all()
        self._process_queue()

    def _position_all(self) -> None:
        if not self._parent:
            return
        pr = self._parent.rect()
        right_margin = 20
        bottom_margin = 20

        for i, toast in enumerate(reversed(self._active)):
            local_x = pr.right() - ToastNotification.W - right_margin
            local_y = pr.bottom() - ToastNotification.H - bottom_margin - i * (ToastNotification.H + 8)
            # Toasts are top-level windows (Qt.Tool) — must use global screen coords
            from PySide6.QtCore import QPoint
            gpos = self._parent.mapToGlobal(QPoint(local_x, local_y))
            toast.setGeometry(gpos.x(), gpos.y(), ToastNotification.W, ToastNotification.H)
