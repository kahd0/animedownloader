"""Custom frameless title bar widget."""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from app.ui.design import tokens as t


class _WinButton(QPushButton):
    """Minimalist window control button (close/max/min)."""

    def __init__(self, symbol: str, hover_color: str, parent=None):
        super().__init__(symbol, parent)
        self._hover_color = hover_color
        self.setFixedSize(40, t.TITLEBAR_HEIGHT)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._hovered = False
        font = QFont()
        font.setPixelSize(11)
        self.setFont(font)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._hovered:
            painter.fillRect(self.rect(), QColor(self._hover_color))

        painter.setPen(QColor(t.TEXT_SECONDARY if not self._hovered else t.TEXT_PRIMARY))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class CustomTitleBar(QWidget):
    """Frameless draggable title bar with window controls."""

    def __init__(self, parent: QWidget, title: str = "Anime Monitor"):
        super().__init__(parent)
        self._parent_win = parent
        self._drag_pos: QPoint | None = None
        self._is_maximized = False

        self.setFixedHeight(t.TITLEBAR_HEIGHT)
        self.setObjectName("titleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo area (same width as sidebar so content aligns)
        self._logo = QLabel("  ◈  Anime Monitor")
        self._logo.setFixedWidth(t.SIDEBAR_WIDTH)
        self._logo.setStyleSheet(f"""
            color: {t.TEXT_PRIMARY};
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            background: transparent;
        """)

        # Drag area — stretches to fill
        self._drag_area = QWidget()
        self._drag_area.setSizePolicy(
            self._drag_area.sizePolicy().horizontalPolicy(),
            self._drag_area.sizePolicy().verticalPolicy(),
        )

        # Window controls
        self._btn_min   = _WinButton("─", t.BG_ELEVATED)
        self._btn_max   = _WinButton("□", t.BG_ELEVATED)
        self._btn_close = _WinButton("✕", "#C0392B")

        self._btn_min.clicked.connect(parent.showMinimized)
        self._btn_max.clicked.connect(self._toggle_max)
        self._btn_close.clicked.connect(parent.close)

        layout.addWidget(self._logo)
        layout.addWidget(self._drag_area, 1)
        layout.addWidget(self._btn_min)
        layout.addWidget(self._btn_max)
        layout.addWidget(self._btn_close)

    def _toggle_max(self):
        if self._is_maximized:
            self._parent_win.showNormal()
            self._btn_max.setText("□")
        else:
            self._parent_win.showMaximized()
            self._btn_max.setText("❐")
        self._is_maximized = not self._is_maximized

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t.BG_SURFACE))
        # Bottom separator line
        painter.setPen(QColor(t.BG_BORDER))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

    # ── Dragging ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._parent_win.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            if self._is_maximized:
                # Unmaximize on drag
                self._parent_win.showNormal()
                self._is_maximized = False
                self._btn_max.setText("□")
                self._drag_pos = QPoint(self._parent_win.width() // 2, t.TITLEBAR_HEIGHT // 2)
            self._parent_win.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()
