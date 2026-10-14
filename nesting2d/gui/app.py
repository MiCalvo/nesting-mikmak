"""Arranque de la interfaz gráfica.

  python -m nesting2d gui [proyecto.json]
  nesting2d-gui [proyecto.json]        (tras `pip install -e .[gui]`)
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from . import gc_guard
    from .main_window import MainWindow

    argv = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(argv)
    gc_guard.install(app)
    app.setOrganizationName("nesting2d")
    app.setApplicationName("Nesting 2D")
    win = MainWindow()
    win.show()
    if len(argv) > 1:
        win.open_project(argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
