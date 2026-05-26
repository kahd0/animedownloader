"""Global QSS stylesheet generated from design tokens."""

from app.ui.design import tokens as t


def build() -> str:
    return f"""
/* ── Global ───────────────────────────────────────────────────────── */
* {{
    outline: none;
}}

QMainWindow, QWidget {{
    background-color: {t.BG_DEEP};
    color: {t.TEXT_PRIMARY};
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 13px;
}}

/* ── ScrollBar ────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {t.BG_SURFACE};
    width: 6px;
    border: none;
    border-radius: 3px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t.BG_BORDER};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t.TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {t.BG_SURFACE};
    height: 6px;
    border: none;
    border-radius: 3px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {t.BG_BORDER};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t.TEXT_MUTED};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── QLineEdit ────────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {t.BG_ELEVATED};
    border: 1px solid {t.BG_BORDER};
    border-radius: {t.RADIUS_MD}px;
    padding: {t.SP2}px {t.SP3}px;
    color: {t.TEXT_PRIMARY};
    font-size: 13px;
    selection-background-color: {t.ACCENT_MUTED};
}}
QLineEdit:focus {{
    border-color: {t.ACCENT};
}}
QLineEdit::placeholder {{
    color: {t.TEXT_MUTED};
}}

/* ── QPushButton (default) ────────────────────────────────────────── */
QPushButton {{
    background-color: {t.BG_ELEVATED};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BG_BORDER};
    border-radius: {t.RADIUS_MD}px;
    padding: {t.SP2}px {t.SP4}px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {t.BG_OVERLAY};
    border-color: {t.ACCENT};
}}
QPushButton:pressed {{
    background-color: {t.ACCENT_MUTED};
}}
QPushButton:disabled {{
    color: {t.TEXT_DISABLED};
    border-color: {t.BG_BORDER};
}}

/* ── Primary button ───────────────────────────────────────────────── */
QPushButton[class="primary"] {{
    background-color: {t.ACCENT};
    color: white;
    border: none;
    font-weight: 600;
}}
QPushButton[class="primary"]:hover {{
    background-color: {t.ACCENT_HOVER};
}}
QPushButton[class="primary"]:pressed {{
    background-color: {t.ACCENT_MUTED};
}}

/* ── Danger button ────────────────────────────────────────────────── */
QPushButton[class="danger"] {{
    background-color: transparent;
    color: {t.ERROR};
    border: 1px solid {t.ERROR};
}}
QPushButton[class="danger"]:hover {{
    background-color: {t.ERROR_GLOW};
}}

/* ── QComboBox ────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {t.BG_ELEVATED};
    border: 1px solid {t.BG_BORDER};
    border-radius: {t.RADIUS_MD}px;
    padding: {t.SP2}px {t.SP3}px;
    color: {t.TEXT_PRIMARY};
    font-size: 13px;
    min-width: 80px;
}}
QComboBox:hover {{ border-color: {t.ACCENT}; }}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t.TEXT_SECONDARY};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {t.BG_OVERLAY};
    border: 1px solid {t.BG_BORDER};
    border-radius: {t.RADIUS_MD}px;
    color: {t.TEXT_PRIMARY};
    selection-background-color: {t.ACCENT_MUTED};
    padding: {t.SP1}px;
}}

/* ── QSpinBox ─────────────────────────────────────────────────────── */
QSpinBox {{
    background-color: {t.BG_ELEVATED};
    border: 1px solid {t.BG_BORDER};
    border-radius: {t.RADIUS_MD}px;
    padding: {t.SP2}px {t.SP3}px;
    color: {t.TEXT_PRIMARY};
}}
QSpinBox:focus {{ border-color: {t.ACCENT}; }}
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 18px;
}}

/* ── QCheckBox ────────────────────────────────────────────────────── */
QCheckBox {{
    color: {t.TEXT_PRIMARY};
    spacing: {t.SP2}px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {t.BG_BORDER};
    background: {t.BG_ELEVATED};
}}
QCheckBox::indicator:checked {{
    background: {t.ACCENT};
    border-color: {t.ACCENT};
}}

/* ── QToolTip ─────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {t.BG_OVERLAY};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BG_BORDER};
    border-radius: {t.RADIUS_SM}px;
    padding: {t.SP1}px {t.SP2}px;
    font-size: 12px;
}}

/* ── QMenu ────────────────────────────────────────────────────────── */
QMenu {{
    background-color: {t.BG_OVERLAY};
    border: 1px solid {t.BG_BORDER};
    border-radius: {t.RADIUS_MD}px;
    padding: {t.SP1}px;
    color: {t.TEXT_PRIMARY};
}}
QMenu::item {{
    padding: {t.SP2}px {t.SP4}px;
    border-radius: {t.RADIUS_SM}px;
}}
QMenu::item:selected {{
    background-color: {t.BG_ELEVATED};
}}
QMenu::separator {{
    height: 1px;
    background: {t.BG_BORDER};
    margin: {t.SP1}px {t.SP2}px;
}}

/* ── QTabBar (for settings) ───────────────────────────────────────── */
QTabBar::tab {{
    background: transparent;
    color: {t.TEXT_SECONDARY};
    padding: {t.SP2}px {t.SP4}px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {t.TEXT_PRIMARY};
    border-bottom-color: {t.ACCENT};
}}
QTabBar::tab:hover {{
    color: {t.TEXT_PRIMARY};
}}

/* ── QTableView ───────────────────────────────────────────────────── */
QTableView {{
    background-color: transparent;
    gridline-color: {t.BG_BORDER};
    border: none;
    color: {t.TEXT_PRIMARY};
    selection-background-color: {t.BG_ELEVATED};
    selection-color: {t.TEXT_PRIMARY};
}}
QTableView::item {{
    padding: {t.SP2}px {t.SP3}px;
    border: none;
}}
QTableView::item:selected {{
    background-color: {t.BG_ELEVATED};
}}
QHeaderView::section {{
    background-color: {t.BG_SURFACE};
    color: {t.TEXT_SECONDARY};
    padding: {t.SP2}px {t.SP3}px;
    border: none;
    border-bottom: 1px solid {t.BG_BORDER};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QHeaderView::section:hover {{
    background-color: {t.BG_ELEVATED};
    color: {t.TEXT_PRIMARY};
}}

/* ── QListView ────────────────────────────────────────────────────── */
QListView {{
    background-color: transparent;
    border: none;
    color: {t.TEXT_PRIMARY};
    selection-background-color: {t.BG_ELEVATED};
    outline: none;
}}
QListView::item {{
    border-radius: {t.RADIUS_MD}px;
    padding: 0;
}}
QListView::item:selected {{
    background-color: {t.BG_ELEVATED};
}}

/* ── QSplitter ────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {t.BG_BORDER};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}

/* ── QScrollArea ──────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
"""


_STYLESHEET: str | None = None


def get() -> str:
    global _STYLESHEET
    if _STYLESHEET is None:
        _STYLESHEET = build()
    return _STYLESHEET
