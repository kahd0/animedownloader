"""Main application window — PySide6 frameless QMainWindow."""
from __future__ import annotations

import sys
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QApplication, QSizePolicy,
)

from app.ui.design import stylesheet as ss
from app.ui.design.fonts import apply_default_font
from app.ui.titlebar.title_bar import CustomTitleBar
from app.ui.sidebar.sidebar_widget import Sidebar
from app.ui.components.toast import ToastManager


class AnimeMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anime Monitor")
        self.setMinimumSize(1100, 680)
        self.resize(1340, 820)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Custom title bar
        self._title_bar = CustomTitleBar(self)
        root.addWidget(self._title_bar)

        # Body: sidebar + content stack
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._sidebar = Sidebar(self)
        self._sidebar.nav_changed.connect(self._navigate)
        body_layout.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        body_layout.addWidget(self._stack, 1)

        root.addWidget(body, 1)

        # Instantiate all screens
        self._screens: dict[str, QWidget] = {}
        self._build_screens()

        # Toast manager
        ToastManager.init(central)

        # Wire qt_app_state
        QTimer.singleShot(200, self._init_state)

        # Start backend
        QTimer.singleShot(500, self._start_backend)

    def _build_screens(self) -> None:
        from app.ui.screens.dashboard  import DashboardScreen
        from app.ui.screens.library    import LibraryScreen
        from app.ui.screens.downloads  import DownloadsScreen
        from app.ui.screens.subtitles  import SubtitlesScreen
        from app.ui.screens.pipeline   import PipelineScreen
        from app.ui.screens.logs       import LogsScreen
        from app.ui.screens.settings   import SettingsScreen

        screens = [
            ("dashboard",  DashboardScreen()),
            ("library",    LibraryScreen()),
            ("downloads",  DownloadsScreen()),
            ("subtitles",  SubtitlesScreen()),
            ("pipeline",   PipelineScreen()),
            ("logs",       LogsScreen()),
            ("settings",   SettingsScreen()),
        ]

        for key, screen in screens:
            self._screens[key] = screen
            self._stack.addWidget(screen)

        # Add anime overlay (lives on top of central widget)
        from app.ui.screens.add_anime import AddAnimeOverlay
        self._add_overlay = AddAnimeOverlay(self.centralWidget())
        self._add_overlay.anime_added.connect(self._on_anime_added)

        self._navigate("dashboard")

    def _navigate(self, key: str) -> None:
        if key not in self._screens:
            return
        self._sidebar.set_active(key)
        self._stack.setCurrentWidget(self._screens[key])

    def _init_state(self) -> None:
        try:
            from app.ui.state.qt_app_state import init_qt_app_state
            self._qt_state = init_qt_app_state()

            # Wire episode_ready to dashboard refresh
            dashboard = self._screens.get("dashboard")
            if dashboard:
                self._qt_state.episode_ready.connect(
                    lambda anime_id, ep, title: dashboard.refresh_card(anime_id)
                )

            # Wire episode_ready to toast
            self._qt_state.episode_ready.connect(
                lambda anime_id, ep, title: ToastManager.instance().show(
                    f"EP {ep:02d} pronto — {title}", "success"
                )
            )
            self._qt_state.pipeline_failed.connect(
                lambda anime_id, ep, step, error: ToastManager.instance().show(
                    f"Erro em {step} EP{ep:02d}", "error"
                )
            )
        except Exception as e:
            print(f"State init error: {e}")

    def _start_backend(self) -> None:
        from app.utils.async_bridge import run_async
        run_async(self._init_backend())

    async def _init_backend(self):
        try:
            from app.core.database import init_db
            await init_db()
        except Exception as e:
            print(f"DB init error: {e}")

        try:
            from app.core.jobs.queue import job_queue
            from app.core.pipeline.episode_pipeline import EpisodePipeline
            pipeline = EpisodePipeline()
            pipeline.setup()         # sync — subscribes to events, registers handlers
            job_queue.start()        # sync — launches background task
        except Exception as e:
            print(f"Pipeline/Queue start error: {e}")

        try:
            from app.watchers.torrent_watcher import TorrentWatcher
            from app.providers.torrents.qbittorrent import QBittorrentProvider
            from app.core.config import get_qbittorrent_config
            cfg = get_qbittorrent_config()
            provider = QBittorrentProvider(
                host=cfg["host"], port=cfg["port"],
                username=cfg["username"], password=cfg["password"],
            )
            watcher = TorrentWatcher(provider)
            watcher.start()          # sync — launches polling task
        except Exception as e:
            print(f"Watcher start error: {e}")

    def _on_anime_added(self, title: str) -> None:
        dashboard = self._screens.get("dashboard")
        if dashboard:
            dashboard.refresh()
        self._navigate("dashboard")

    def show_add_anime(self) -> None:
        self._add_overlay.open_overlay()

    def closeEvent(self, event):
        from app.utils.async_bridge import stop_loop
        stop_loop()
        super().closeEvent(event)


def create_app() -> tuple[QApplication, AnimeMonitorApp]:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(ss.get())
    apply_default_font(app)
    window = AnimeMonitorApp()
    return app, window
