"""Base class for all screens providing common layout helpers."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)

from app.ui.design import tokens as t


class BaseScreen(QWidget):
    """Base screen with a standard top-bar (title + actions) and content area."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        # Top bar
        self._topbar = QWidget()
        self._topbar.setFixedHeight(56)
        self._topbar.setObjectName("screenTopbar")
        tb_layout = QHBoxLayout(self._topbar)
        tb_layout.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)
        tb_layout.setSpacing(t.SP4)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(f"""
            color: {t.TEXT_PRIMARY};
            font-size: 22px;
            font-weight: 700;
            background: transparent;
        """)
        tb_layout.addWidget(self._title_label)
        tb_layout.addStretch(1)

        self._action_area = QWidget()
        self._action_layout = QHBoxLayout(self._action_area)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(t.SP2)
        tb_layout.addWidget(self._action_area)

        self._root.addWidget(self._topbar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        self._root.addWidget(sep)

        # Scrollable content area
        from PySide6.QtWidgets import QScrollArea
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(t.CONTENT_PAD_H, t.CONTENT_PAD_V, t.CONTENT_PAD_H, t.CONTENT_PAD_V)
        self._content_layout.setSpacing(t.SP6)
        self._scroll.setWidget(self._content)
        self._root.addWidget(self._scroll, 1)

    def add_action(self, widget: QWidget) -> None:
        """Add a widget to the top-bar action area."""
        self._action_layout.addWidget(widget)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t.BG_DEEP))
