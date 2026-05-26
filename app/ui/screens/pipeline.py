"""Pipeline screen — real-time episode automation visualization."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSplitter, QSizePolicy,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async


class PipelineScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setFixedHeight(56)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)

        title = QLabel("Pipeline")
        title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 22px; font-weight: 700; background: transparent;")
        tbl.addWidget(title)
        tbl.addStretch(1)

        self._stats_label = QLabel("Carregando...")
        self._stats_label.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 13px; background: transparent;")
        tbl.addWidget(self._stats_label)
        root.addWidget(topbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        root.addWidget(sep)

        # Main split: left = active pipelines, right = detail
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Left — active pipeline rows
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(t.CONTENT_PAD_H, t.SP6, t.SP6, t.SP6)
        ll.setSpacing(t.SP4)

        active_label = QLabel("PIPELINES ATIVOS")
        active_label.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px; background: transparent;")
        ll.addWidget(active_label)

        self._pipeline_scroll = QScrollArea()
        self._pipeline_scroll.setWidgetResizable(True)
        self._pipeline_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._pipeline_container = QWidget()
        self._pipeline_container.setStyleSheet("background: transparent;")
        self._pipeline_vlayout = QVBoxLayout(self._pipeline_container)
        self._pipeline_vlayout.setContentsMargins(0, 0, 0, 0)
        self._pipeline_vlayout.setSpacing(t.SP3)
        self._pipeline_vlayout.addStretch(1)
        self._pipeline_scroll.setWidget(self._pipeline_container)
        ll.addWidget(self._pipeline_scroll, 1)

        # Recent strip label
        recent_label = QLabel("RECENTES (últimas 24h)")
        recent_label.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px; background: transparent;")
        ll.addWidget(recent_label)

        self._recent_strip = QScrollArea()
        self._recent_strip.setFixedHeight(52)
        self._recent_strip.setWidgetResizable(True)
        self._recent_strip.setFrameShape(QFrame.Shape.NoFrame)
        self._recent_strip.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        recent_w = QWidget()
        recent_w.setStyleSheet("background: transparent;")
        self._recent_layout = QHBoxLayout(recent_w)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(t.SP2)
        self._recent_layout.addStretch(1)
        self._recent_strip.setWidget(recent_w)
        ll.addWidget(self._recent_strip)

        # Right — detail panel
        self._detail_panel = _PipelineDetailPanel()

        splitter.addWidget(left)
        splitter.addWidget(self._detail_panel)
        splitter.setSizes([700, 320])

        root.addWidget(splitter, 1)

        # Refresh timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(3000)

        QTimer.singleShot(0, self._poll)

    def _poll(self) -> None:
        run_async(self._fetch_jobs(), on_done=self._on_jobs)
        run_async(self._fetch_recent(), on_done=self._on_recent)

    async def _fetch_jobs(self):
        from app.core.jobs.queue import job_queue
        return await job_queue.get_status()

    async def _fetch_recent(self):
        import aiosqlite
        from app.core.config import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT j.id, j.anime_id, j.episode, j.type, j.status, "
                "j.retries, j.error, m.official_title "
                "FROM jobs j "
                "LEFT JOIN monitored m ON j.anime_id = m.id "
                "WHERE j.status IN ('done','failed') "
                "AND j.updated_at > datetime('now','-24 hours') "
                "ORDER BY j.updated_at DESC LIMIT 20"
            ) as cur:
                return await cur.fetchall()

    def _on_jobs(self, result) -> None:
        if isinstance(result, Exception):
            return
        jobs = result or []
        running = [j for j in jobs if j.get("status") in ("running", "pending")]
        done = len([j for j in jobs if j.get("status") == "done"])
        failed = len([j for j in jobs if j.get("status") == "failed"])
        self._stats_label.setText(f"Ativos: {len(running)}  ·  Concluídos: {done}  ·  Falhas: {failed}")
        self._rebuild_pipeline_rows(running)

    def _on_recent(self, result) -> None:
        if isinstance(result, Exception):
            return
        # Clear and repopulate recent strip
        layout = self._recent_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for row in (result or []):
            chip = _RecentChip(row)
            layout.insertWidget(layout.count() - 1, chip)

    def _rebuild_pipeline_rows(self, jobs) -> None:
        from app.ui.components.pipeline_row import PipelineRow
        layout = self._pipeline_vlayout
        # Remove old rows (keep stretch at end)
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not jobs:
            empty = QLabel("Nenhum pipeline ativo.\nO Anime Monitor iniciará automaticamente ao detectar novos episódios.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 14px; background: transparent;")
            empty.setWordWrap(True)
            layout.insertWidget(0, empty)
            return

        for job in jobs:
            row = PipelineRow(job, self._pipeline_container)
            row.clicked.connect(self._detail_panel.show_job)
            layout.insertWidget(layout.count() - 1, row)

    def showEvent(self, event):
        super().showEvent(event)
        self._poll()


class _PipelineDetailPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SP6, t.SP6, t.CONTENT_PAD_H, t.SP6)
        layout.setSpacing(t.SP4)

        self._title = QLabel("Selecione um pipeline")
        self._title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; background: transparent;")
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._meta = QLabel("")
        self._meta.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 12px; background: transparent;")
        layout.addWidget(self._meta)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        layout.addWidget(sep)

        layout.addStretch(1)

    def show_job(self, job: dict) -> None:
        title = f"{job.get('type', '').upper()} — EP {job.get('episode', '?')}"
        self._title.setText(title)
        meta = f"Status: {job.get('status', '?')}  ·  Tentativas: {job.get('retries', 0)}"
        if job.get("error"):
            meta += f"\n⚠ {job['error']}"
        self._meta.setText(meta)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t.BG_SURFACE))
        painter.setPen(QColor(t.BG_BORDER))
        painter.drawLine(0, 0, 0, self.height())


class _RecentChip(QWidget):
    def __init__(self, row, parent=None):
        super().__init__(parent)
        self._row = row
        # row: id(0), anime_id(1), episode(2), type(3), status(4), retries(5), error(6), official_title(7)
        status = row[4] if len(row) > 4 else "?"
        title = row[7] or f"Anime {row[1]}" if len(row) > 7 else "?"
        ep = row[2] if len(row) > 2 else "?"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(t.SP3, 0, t.SP3, 0)

        color = t.SUCCESS if status == "done" else t.ERROR
        icon = "✓" if status == "done" else "✕"
        lbl = QLabel(f"{icon} {title} EP{ep:02d}" if isinstance(ep, int) else f"{icon} {title}")
        lbl.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent;")
        layout.addWidget(lbl)

        self.setFixedHeight(36)
        self.setStyleSheet(f"""
            QWidget {{
                background: {t.BG_ELEVATED};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_MD}px;
            }}
        """)
