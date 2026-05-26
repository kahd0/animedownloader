"""PipelineRow — horizontal stage flow visualization widget."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRect, QSize, QPropertyAnimation, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QFont, QFontMetrics, QPen, QPainterPath
from PySide6.QtWidgets import QWidget

from app.ui.design import tokens as t


STAGES = [
    ("rss",       "RSS",     t.INFO),
    ("torrent",   "Torrent", t.DOWNLOADING),
    ("subtitle",  "Legenda", t.ACCENT),
    ("translate", "Trad.",   t.TRANSLATING),
    ("organize",  "Org.",    t.WARNING),
    ("ready",     "Pronto",  t.SUCCESS),
]

STAGE_KEYS = [s[0] for s in STAGES]


class PipelineRow(QWidget):
    clicked = Signal(object)  # emits the job object

    H = 90
    NODE_R = 10  # circle radius

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self._job = job
        self._stage_status: dict[str, str] = {}  # key → pending|active|done|failed
        self._stage_info: dict[str, str] = {}

        self.setFixedHeight(self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._hovered = False

        # Pulse animation for active stage
        self._pulse: float = 1.0
        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setStartValue(0.4)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setDuration(800)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.valueChanged.connect(self._on_pulse)

        self._infer_state_from_job(job)
        if self._has_active_stage():
            self._pulse_anim.start()

    def _infer_state_from_job(self, job) -> None:
        job_type = job.get("type", "") if isinstance(job, dict) else getattr(job, "type", "")
        status   = job.get("status", "pending") if isinstance(job, dict) else getattr(job, "status", "pending")

        # Map job type to pipeline stage
        type_to_stage = {
            "subtitle":     "subtitle",
            "translation":  "translate",
            "organization": "organize",
        }
        current_stage = type_to_stage.get(job_type, "torrent")

        idx = STAGE_KEYS.index(current_stage) if current_stage in STAGE_KEYS else 1

        for i, key in enumerate(STAGE_KEYS):
            if i < idx:
                self._stage_status[key] = "done"
            elif i == idx:
                self._stage_status[key] = status if status in ("running", "pending", "failed") else "active"
                if status == "running":
                    self._stage_status[key] = "active"
            else:
                self._stage_status[key] = "pending"

    def _has_active_stage(self) -> bool:
        return any(v == "active" for v in self._stage_status.values())

    def _on_pulse(self, value) -> None:
        self._pulse = float(value)
        self.update()

    def set_stage_status(self, stage: str, status: str) -> None:
        self._stage_status[stage] = status
        if self._has_active_stage():
            self._pulse_anim.start()
        else:
            self._pulse_anim.stop()
        self.update()

    def set_stage_info(self, stage: str, info: str) -> None:
        self._stage_info[stage] = info
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(600, self.H)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()

        # Background
        bg = QColor(t.BG_ELEVATED) if self._hovered else QColor(t.BG_SURFACE)
        path = QPainterPath()
        path.addRoundedRect(r, t.RADIUS_MD, t.RADIUS_MD)
        painter.fillPath(path, bg)

        # Bottom separator
        painter.setPen(QColor(t.BG_BORDER))
        painter.drawLine(16, r.height() - 1, r.width() - 16, r.height() - 1)

        # Job info (left side)
        job = self._job
        _g = lambda k, d: (job.get(k, d) if isinstance(job, dict) else getattr(job, k, d))
        job_type = _g("type", "?").upper()
        ep = _g("episode", "?")
        anime_id = _g("anime_id", 0)

        title_font = QFont()
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(t.TEXT_PRIMARY))
        painter.drawText(QRect(16, 8, 180, 20), Qt.AlignmentFlag.AlignVCenter, f"Anime #{anime_id}")

        sub_font = QFont()
        sub_font.setPixelSize(11)
        painter.setFont(sub_font)
        painter.setPen(QColor(t.TEXT_MUTED))
        status_val = _g("status", "?")
        painter.drawText(QRect(16, 28, 180, 18), Qt.AlignmentFlag.AlignVCenter, f"{job_type}  ·  EP {ep}  ·  {status_val.upper()}")

        # Stage pipeline (right side)
        stages_x_start = 200
        stages_width   = r.width() - stages_x_start - 16
        n = len(STAGES)
        slot_w = stages_width // n
        node_y = r.height() // 2 - 6

        for i, (key, label, color) in enumerate(STAGES):
            stage_state = self._stage_status.get(key, "pending")
            node_x = stages_x_start + i * slot_w + slot_w // 2
            nr = self.NODE_R

            # Connecting line (before this node)
            if i > 0:
                prev_x = stages_x_start + (i - 1) * slot_w + slot_w // 2
                prev_state = self._stage_status.get(STAGE_KEYS[i - 1], "pending")
                line_color = QColor(color if prev_state == "done" else t.BG_BORDER)
                pen = QPen(line_color, 2)
                painter.setPen(pen)
                painter.drawLine(prev_x + nr, node_y + nr, node_x - nr, node_y + nr)

            # Node circle
            painter.setPen(Qt.PenStyle.NoPen)
            if stage_state == "done":
                painter.setBrush(QColor(color))
                painter.drawEllipse(node_x - nr, node_y, nr * 2, nr * 2)
                # Checkmark
                painter.setPen(QPen(QColor("white"), 2))
                cx, cy = node_x, node_y + nr
                painter.drawLine(cx - 5, cy, cx - 2, cy + 3)
                painter.drawLine(cx - 2, cy + 3, cx + 5, cy - 4)

            elif stage_state == "active":
                alpha = int(self._pulse * 255)
                painter.setBrush(QColor(color))
                painter.setOpacity(self._pulse)
                painter.drawEllipse(node_x - nr - 4, node_y - 4, (nr + 4) * 2, (nr + 4) * 2)
                painter.setOpacity(1.0)
                painter.setBrush(QColor(color))
                painter.drawEllipse(node_x - nr, node_y, nr * 2, nr * 2)

            elif stage_state == "failed":
                painter.setBrush(QColor(t.ERROR))
                painter.drawEllipse(node_x - nr, node_y, nr * 2, nr * 2)
                painter.setPen(QPen(QColor("white"), 2))
                cx, cy = node_x, node_y + nr
                painter.drawLine(cx - 4, cy - 4, cx + 4, cy + 4)
                painter.drawLine(cx + 4, cy - 4, cx - 4, cy + 4)

            else:  # pending
                painter.setBrush(QColor(t.BG_OVERLAY))
                painter.setPen(QPen(QColor(t.BG_BORDER), 1))
                painter.drawEllipse(node_x - nr, node_y, nr * 2, nr * 2)

            # Stage label below node
            label_font = QFont()
            label_font.setPixelSize(10)
            painter.setFont(label_font)
            lc = QColor(color if stage_state in ("done", "active") else t.TEXT_MUTED)
            painter.setPen(lc)
            painter.setPen(Qt.PenStyle.NoPen) if stage_state == "pending" else None
            painter.setPen(lc)
            painter.drawText(QRect(node_x - 24, node_y + nr * 2 + 4, 48, 14),
                           Qt.AlignmentFlag.AlignCenter, label)

            # Info text (active stage)
            if stage_state == "active" and key in self._stage_info:
                info_font = QFont()
                info_font.setPixelSize(9)
                painter.setFont(info_font)
                painter.setPen(QColor(t.TEXT_MUTED))
                painter.drawText(QRect(stages_x_start, r.height() - 18, stages_width, 14),
                               Qt.AlignmentFlag.AlignCenter, self._stage_info[key])

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._job)
