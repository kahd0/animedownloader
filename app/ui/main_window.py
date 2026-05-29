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

        # Periodic episode check — fires after 60 s then every check_interval minutes
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._run_episode_check)
        QTimer.singleShot(60_000, self._start_check_timer)

    def _build_screens(self) -> None:
        from app.ui.screens.dashboard  import DashboardScreen
        from app.ui.screens.library    import LibraryScreen
        from app.ui.screens.downloads  import DownloadsScreen
        from app.ui.screens.pipeline   import PipelineScreen
        from app.ui.screens.logs       import LogsScreen
        from app.ui.screens.settings   import SettingsScreen

        screens = [
            ("dashboard",  DashboardScreen()),
            ("library",    LibraryScreen()),
            ("downloads",  DownloadsScreen()),
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
            from app.watchers.torrent_watcher import TorrentWatcher
            from app.providers.torrents.qbittorrent import QBittorrentProvider
            from app.core.config import get_qbittorrent_config

            cfg = get_qbittorrent_config()
            provider = QBittorrentProvider(
                host=cfg["host"], port=cfg["port"],
                username=cfg["username"], password=cfg["password"],
            )
            watcher = TorrentWatcher(provider)

            pipeline = EpisodePipeline()
            pipeline.setup(qbittorrent_provider=provider, watcher=watcher)
            job_queue.start()
            watcher.start()
        except Exception as e:
            print(f"Pipeline/Queue/Watcher start error: {e}")

    def _start_check_timer(self) -> None:
        from app.core.config import get_check_interval
        self._check_timer.start(get_check_interval())  # already in ms
        self._run_episode_check()

    def _run_episode_check(self) -> None:
        from app.utils.async_bridge import run_async

        async def _check():
            from app.core.downloader import check_for_updates
            return await check_for_updates()

        def _done(result):
            if isinstance(result, Exception):
                return
            triggered = result or []
            # Refresh library if visible
            lib = self._screens.get("library")
            if lib:
                lib.refresh()
            # Dashboard cards already refreshed via episode_ready signal

        run_async(_check(), on_done=_done)

    def _on_anime_added(self, title: str) -> None:
        self._navigate("dashboard")

        async def _fetch_meta_and_refresh():
            from app.core.database import get_monitored_animes
            from app.core.downloader import refresh_single_metadata
            rows = await get_monitored_animes()
            anime = next((r for r in rows if r[1] == title), None)
            if anime:
                await refresh_single_metadata(anime[0], anime[1])

        def _done(_):
            dashboard = self._screens.get("dashboard")
            if dashboard:
                dashboard.refresh()

        from app.utils.async_bridge import run_async
        run_async(_fetch_meta_and_refresh(), on_done=_done)

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
