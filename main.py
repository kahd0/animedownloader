import sys
from PySide6.QtWidgets import QApplication
from app.ui.main_window import AnimeMonitorApp, create_app
from app.ui.design import stylesheet as ss
from app.ui.design.fonts import apply_default_font

if __name__ == "__main__":
    app, window = create_app()
    window.show()
    sys.exit(app.exec())
