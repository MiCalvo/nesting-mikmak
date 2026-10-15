"""Aspecto común de la interfaz: paleta, hoja de estilo (QSS) y piezas pequeñas
(tarjetas, títulos, insignias, botones principales/secundarios).

Se usa el estilo «Fusion» de Qt con una paleta clara: se ve igual en Windows y en
Linux y respeta los controles nativos (flechas de los campos numéricos, listas
desplegables). La hoja de estilo solo toca lo que Fusion no resuelve: tarjetas,
botones, la barra de pasos y las tablas. Los campos numéricos y las listas no se
estilan con QSS a propósito: al ponerles borde con QSS, Qt deja de dibujar sus
flechas con el estilo base.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

# --- colores ------------------------------------------------------------------
BG = "#f2f4f7"           # fondo de la ventana
SURFACE = "#ffffff"      # tarjetas
BORDER = "#dde2ea"
TEXT = "#1f2933"
MUTED = "#667085"
ACCENT = "#1f6feb"
ACCENT_DARK = "#1858c4"
ACCENT_SOFT = "#e8f0fe"
OK = "#1a7f37"
OK_SOFT = "#e6f4ea"
WARN = "#9a6700"
WARN_SOFT = "#fff4d6"
BAD = "#c62828"
BAD_SOFT = "#fdecea"
SIDEBAR = "#18212f"
SIDEBAR_TEXT = "#c3cad5"
SIDEBAR_MUTED = "#7d8899"
SIDEBAR_ACTIVE = "#243044"

# lienzo de las vistas (piezas y planchas)
CANVAS = QColor("#e7ebf0")
SHEET = QColor("#fdfcf8")
SHEET_EDGE = QColor("#4a5565")

QSS = f"""
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#page {{ background: {BG}; }}
QScrollArea#pageScroll, QScrollArea#pageScroll > QWidget > QWidget {{ background: {BG}; border: none; }}

/* tarjetas */
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame#card QLabel {{ background: transparent; }}
QLabel#cardTitle {{ font-weight: 600; color: {TEXT}; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#pageTitle {{ font-size: 15pt; font-weight: 600; color: {TEXT}; }}
QLabel#pageSubtitle {{ color: {MUTED}; }}
QLabel#kpiValue {{ font-size: 15pt; font-weight: 600; color: {TEXT}; }}
QLabel#kpiLabel {{ color: {MUTED}; font-size: 8.5pt; }}
QFrame#dropZone {{ background: #fafbfc; border: 2px dashed #c3cbd8; border-radius: 10px; }}
QFrame#dropZone QLabel {{ background: transparent; }}
QLabel#emptyTitle {{ font-size: 14pt; font-weight: 600; color: {TEXT}; }}

/* cuadros de grupo como tarjetas (pestaña de parámetros y diálogos) */
QGroupBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
             margin-top: 14px; padding: 14px 10px 10px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px;
                    padding: 0 4px; color: {TEXT}; }}
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton {{ font-weight: normal; }}

/* botones */
QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid #c9d0db; border-radius: 6px;
               padding: 5px 12px; min-height: 18px; }}
QPushButton:hover {{ background: #f5f7fa; border-color: #aeb7c4; }}
QPushButton:pressed {{ background: #e9edf2; }}
QPushButton:disabled {{ color: #a3abb7; border-color: #e1e5eb; background: #f7f8fa; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {ACCENT_DARK}; border-color: {ACCENT_DARK}; }}
QPushButton[kind="primary"]:disabled {{ background: #a9c4f5; border-color: #a9c4f5; color: #eef3fd; }}
QPushButton[kind="danger"] {{ color: {BAD}; }}
QPushButton[kind="danger"]:hover {{ background: {BAD_SOFT}; border-color: #e3a3a0; }}
QPushButton[kind="flat"] {{ background: transparent; border: none; color: {ACCENT}; padding: 4px 6px; }}
QPushButton[kind="flat"]:hover {{ background: {ACCENT_SOFT}; }}
QPushButton[kind="flat"]:disabled {{ color: #a3abb7; background: transparent; }}

/* tablas y listas */
QTableView, QTableWidget, QListWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;
               gridline-color: #edf0f4; selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
               alternate-background-color: #f8fafc; }}
QHeaderView::section {{ background: #f6f8fa; color: {MUTED}; border: none;
               border-bottom: 1px solid {BORDER}; padding: 6px 8px; font-weight: 600; }}
QTableCornerButton::section {{ background: #f6f8fa; border: none; }}

/* barra lateral de pasos */
QWidget#sidebar {{ background: {SIDEBAR}; }}
QWidget#sidebar QLabel {{ color: {SIDEBAR_TEXT}; background: transparent; }}
QLabel#appName {{ color: white; font-size: 13pt; font-weight: 700; }}
QLabel#projectName {{ color: {SIDEBAR_MUTED}; }}
QLabel#sideSection {{ color: {SIDEBAR_MUTED}; font-size: 8pt; font-weight: 600; }}
QWidget#sidebar QPushButton[kind="side"] {{ background: transparent; color: {SIDEBAR_TEXT};
               border: 1px solid #344157; border-radius: 6px; padding: 4px 8px; }}
QWidget#sidebar QPushButton[kind="side"]:hover {{ background: {SIDEBAR_ACTIVE}; color: white; }}
QWidget#sidebar QPushButton[kind="side"]:disabled {{ color: #556074; border-color: #2a3447; }}
QWidget#sidebar QProgressBar {{ background: #2a3447; border: none; border-radius: 3px; max-height: 6px; }}
QWidget#sidebar QProgressBar::chunk {{ background: #58a6ff; border-radius: 3px; }}

/* cabecera y pie de página */
QWidget#header {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
QWidget#footer {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}

/* avisos */
QLabel#banner {{ background: {WARN_SOFT}; color: #5c4400; border: 1px solid #ecd18a; border-radius: 6px;
               padding: 8px 10px; }}
QStatusBar {{ background: {SURFACE}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar QPushButton {{ padding: 2px 10px; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 4px 6px; }}
QDockWidget::title {{ background: #e9edf2; padding: 4px 8px; }}
QSplitter::handle {{ background: transparent; }}
"""


def apply(app: QApplication) -> None:
    """Estilo Fusion con paleta clara + hoja de estilo. Llamar una vez tras crear la app."""
    app.setStyle("Fusion")
    pal = QPalette()
    R = QPalette.ColorRole
    for role, color in [(R.Window, BG), (R.WindowText, TEXT), (R.Base, SURFACE), (R.AlternateBase, "#f8fafc"),
                        (R.Text, TEXT), (R.Button, SURFACE), (R.ButtonText, TEXT), (R.Highlight, ACCENT),
                        (R.HighlightedText, "#ffffff"), (R.ToolTipBase, TEXT), (R.ToolTipText, "#ffffff"),
                        (R.PlaceholderText, "#98a2b3"), (R.Link, ACCENT), (R.Mid, BORDER), (R.Midlight, "#eef1f5")]:
        pal.setColor(role, QColor(color))
    for role in (R.WindowText, R.Text, R.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor("#a3abb7"))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


# --- piezas reutilizables --------------------------------------------------------
def set_kind(button: QPushButton, kind: str) -> QPushButton:
    """primary · danger · flat · side (o "" para el botón normal)."""
    button.setProperty("kind", kind)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def button(text: str, kind: str = "", slot=None, tip: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if slot is not None:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


class Card(QFrame):
    """Tarjeta blanca con título opcional. Añadir contenido a `body` (QVBoxLayout)."""

    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(8)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.title = label(title, "cardTitle")
        self.header.addWidget(self.title)
        self.header.addStretch(1)
        if title:
            outer.addLayout(self.header)
        if subtitle:
            outer.addWidget(label(subtitle, "muted", wrap=True))
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body)


class Badge(QLabel):
    """Etiqueta de estado coloreada: ok · warn · bad · info · neutral."""

    COLORS = {"ok": (OK, OK_SOFT), "warn": (WARN, WARN_SOFT), "bad": (BAD, BAD_SOFT),
              "info": (ACCENT, ACCENT_SOFT), "neutral": (MUTED, "#eef1f5")}

    def __init__(self, text: str = "", kind: str = "neutral", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)   # nunca se recorta
        self.set(text, kind)

    def set(self, text: str, kind: str = "neutral") -> None:
        fg, bg = self.COLORS.get(kind, self.COLORS["neutral"])
        self.kind = kind
        self.setText(text)
        self.setStyleSheet(f"background: {bg}; color: {fg}; border-radius: 10px; padding: 3px 10px; "
                           "font-weight: 600;")


class Kpi(QFrame):
    """Indicador: valor grande + rótulo pequeño."""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.value = label("—", "kpiValue")
        self.caption = label(caption.upper(), "kpiLabel")
        lay.addWidget(self.caption)
        lay.addWidget(self.value)

    def set(self, value: str, color: str | None = None) -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")


def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color: {BORDER}; background: {BORDER}; max-height: 1px; border: none;")
    return f


def page_scroll(content: QWidget) -> QWidget:
    """Envuelve el contenido de una página en un área con desplazamiento (pantallas bajas)."""
    from PySide6.QtWidgets import QScrollArea
    sa = QScrollArea()
    sa.setObjectName("pageScroll")
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content.setObjectName("page")
    sa.setWidget(content)
    return sa
