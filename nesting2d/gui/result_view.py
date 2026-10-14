"""Pestaña Resultado: dibujo de cada plancha, métricas y avisos.

Solo muestra el resultado; la edición manual es la fase 3.
"""
from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QTransform
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGraphicsItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from shapely.geometry import Polygon, box
from shapely.ops import polylabel

from ..engine.nester import Layout
from ..validate import Issue
from .qt_util import fmt, part_color, polygon_path

SHEET_FILL = QColor("#f4f1ea")
FREE_FILL = QColor(60, 170, 90, 45)


def free_rect(layout: Layout, sheet: int) -> tuple[float, float, float, float] | None:
    """Retal libre de la plancha como (x0, y0, x1, y1) en mm, o None si no queda.

    Es la misma zona que mide `Layout.stats`: desde un margen más allá de la última
    pieza (en la dirección de compactación) hasta el borde de la plancha, a todo
    el ancho de la plancha.
    """
    pl = layout.on_sheet(sheet)
    if not pl:
        return None
    p = layout.params
    W, H, m = p.sheet_width, p.sheet_height, p.margin
    minx = min(q.polygon.bounds[0] for q in pl)
    miny = min(q.polygon.bounds[1] for q in pl)
    maxx = max(q.polygon.bounds[2] for q in pl)
    maxy = max(q.polygon.bounds[3] for q in pl)
    r = {"izquierda": (maxx + m, 0.0, W, H), "derecha": (0.0, 0.0, minx - m, H),
         "abajo": (0.0, maxy + m, W, H), "arriba": (0.0, 0.0, W, miny - m)}[p.compact_side]
    if r[2] - r[0] <= 0 or r[3] - r[1] <= 0:
        return None
    return r


def _centered_text(text: str, x: float, y: float, color: QColor, point_size: float | None = None):
    """Texto de tamaño fijo en pantalla, centrado en el punto de escena (x, y)."""
    t = QGraphicsSimpleTextItem(text)
    t.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    t.setBrush(color)
    if point_size:
        f = t.font()
        f.setPointSizeF(point_size)
        t.setFont(f)
    br = t.boundingRect()
    # la transformación propia sí se aplica (solo se ignoran las heredadas de la vista)
    t.setTransform(QTransform.fromTranslate(-br.width() / 2, -br.height() / 2))
    t.setPos(x, y)
    t.setZValue(2)
    return t


def _pen(color, width=0.0, style=Qt.PenStyle.SolidLine) -> QPen:
    pen = QPen(QColor(color), width, style)
    pen.setCosmetic(True)
    return pen


class SheetView(QGraphicsView):
    """Vista de una plancha. Los nombres solo se muestran si caben dentro de su
    pieza al zoom actual; así no se amontonan al ver la plancha entera."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # (texto, contorno exterior de la pieza, punto del texto en mm)
        self.labels: list[tuple[QGraphicsSimpleTextItem, Polygon, tuple[float, float]]] = []
        self.auto_fit = True   # se reajusta al cambiar de tamaño hasta que el usuario hace zoom
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#d9d9d9"))

    def fit(self):
        self.auto_fit = True
        if not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.update_labels()

    def zoom(self, k: float):
        self.auto_fit = False
        self.scale(k, k)
        self.update_labels()

    def update_labels(self):
        k = abs(self.transform().m11()) or 1.0   # píxeles por mm
        for t, poly, (x, y) in self.labels:
            br = t.boundingRect()
            w, h = br.width() / k, br.height() / k
            t.setVisible(poly.contains(box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.auto_fit:
            self.fit()

    def wheelEvent(self, e):
        self.zoom(1.25 if e.angleDelta().y() > 0 else 0.8)


class ResultPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout_: Layout | None = None
        self.issues: list[Issue] = []
        self._colors: dict[str, QColor] = {}

        self.stale = QLabel("El resultado no corresponde a los datos actuales: has cambiado piezas o "
                            "parámetros después de calcular. Vuelve a calcular (F5).")
        self.stale.setWordWrap(True)
        self.stale.setStyleSheet("background: #fff3c4; color: #5c4400; padding: 6px; border: 1px solid #e0c060;")
        self.stale.hide()

        self.sheet_combo = QComboBox()
        self.sheet_combo.currentIndexChanged.connect(self._draw)
        self.labels = QCheckBox("Nombres")
        self.labels.setChecked(True)
        self.labels.toggled.connect(self._draw)
        self.show_free = QCheckBox("Retal libre")
        self.show_free.setChecked(True)
        self.show_free.toggled.connect(self._draw)
        fit = QPushButton("Ajustar a la ventana")
        self.view = SheetView()
        fit.clicked.connect(self.view.fit)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Plancha:"))
        bar.addWidget(self.sheet_combo)
        bar.addSpacing(12)
        bar.addWidget(self.labels)
        bar.addWidget(self.show_free)
        bar.addStretch(1)
        bar.addWidget(fit)

        self.summary = QLabel("Todavía no hay resultado. Importa piezas y pulsa «Calcular» (F5).")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Pieza", "En esta plancha"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.summary)
        sl.addWidget(self.table, 1)

        split = QSplitter()
        split.addWidget(self.view)
        split.addWidget(side)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([1000, 320])

        lay = QVBoxLayout(self)
        lay.addWidget(self.stale)
        lay.addLayout(bar)
        lay.addWidget(split, 1)

    # --- API ------------------------------------------------------------------
    def set_layout(self, layout: Layout | None, issues: list[Issue] | None = None) -> None:
        self.layout_ = layout
        self.issues = issues or []
        self.stale.hide()
        names = sorted({q.part for q in layout.placements}) if layout else []
        self._colors = {n: part_color(i) for i, n in enumerate(names)}
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        if layout:
            for s in range(layout.sheets):
                self.sheet_combo.addItem(f"{s + 1} de {layout.sheets}", s)
        self.sheet_combo.blockSignals(False)
        self._draw()
        self.view.fit()

    def set_stale(self, stale: bool) -> None:
        self.stale.setVisible(stale and self.layout_ is not None)

    def current_sheet(self) -> int:
        return max(0, self.sheet_combo.currentIndex())

    # --- dibujo ---------------------------------------------------------------
    def _bad_items(self, sheet: int) -> set[int]:
        L = self.layout_
        return {i for iss in self.issues for i in iss.items if L.placements[i].sheet == sheet}

    def _draw(self, *_):
        sc = self.view.scene()
        sc.clear()
        self.view.labels = []
        L = self.layout_
        if L is None or L.sheets == 0:
            sc.setSceneRect(QRectF())
            self._update_summary()
            return
        s = self.current_sheet()
        p = L.params
        W, H, m = p.sheet_width, p.sheet_height, p.margin
        sc.addRect(QRectF(0, -H, W, H), _pen("#000000", 1.5), QBrush(SHEET_FILL))
        if m > 0:
            sc.addRect(QRectF(m, -(H - m), W - 2 * m, H - 2 * m), _pen("#909090", 1, Qt.PenStyle.DotLine))
        if self.show_free.isChecked():
            fr = free_rect(L, s)
            if fr:
                x0, y0, x1, y1 = fr
                sc.addRect(QRectF(x0, -y1, x1 - x0, y1 - y0), _pen("#3a9a5a", 1, Qt.PenStyle.DashLine),
                           QBrush(FREE_FILL))
                sc.addItem(_centered_text(f"Retal libre {fmt(x1 - x0, 0)} × {fmt(y1 - y0, 0)} mm",
                                          (x0 + x1) / 2, -(y0 + y1) / 2, QColor("#2a6a3a")))

        bad = self._bad_items(s)
        for i, q in enumerate(L.placements):
            if q.sheet != s:
                continue
            is_bad = i in bad
            item = sc.addPath(polygon_path(q.polygon),
                              _pen("#d00000", 2.5) if is_bad else _pen("#202020", 0.8),
                              QBrush(self._colors.get(q.part, QColor("gray"))))
            where = f"dentro de {L.placements[q.host].part}" if q.host is not None else ""
            item.setToolTip(f"{q.part}\ngiro {q.angle:g}° {where}".strip()
                            + ("\nINCUMPLE separación, margen o solapa" if is_bad else ""))
            if self.labels.isChecked():
                # el texto puede pisar huecos, pero no salirse del contorno exterior; se
                # coloca en el polo de inaccesibilidad (punto más alejado del borde)
                shell = Polygon(q.polygon.exterior)
                c = polylabel(shell, 0.5)
                t = _centered_text(q.part, c.x, -c.y, QColor("#000000"), 7.5)
                sc.addItem(t)
                self.view.labels.append((t, shell, (c.x, c.y)))
        pad = 0.03 * max(W, H)
        sc.setSceneRect(QRectF(-pad, -H - pad, W + 2 * pad, H + 2 * pad))
        self.view.update_labels()
        self._update_summary()

    def _update_summary(self):
        L = self.layout_
        self.table.setRowCount(0)
        if L is None:
            self.summary.setText("Todavía no hay resultado. Importa piezas y pulsa «Calcular» (F5).")
            return
        lines = []
        total = len(L.placements)
        lines.append(f"<b>{total} piezas en {L.sheets} plancha{'s' if L.sheets != 1 else ''}</b>")
        if L.sheets:
            s = self.current_sheet()
            st = L.stats(s)
            fw, fh = st["free"]
            lines.append(f"Plancha {s + 1}: {len(L.on_sheet(s))} piezas<br>"
                         f"Largo ocupado: {fmt(st['used_length'])} mm<br>"
                         f"Retal libre: {fmt(fw, 0)} × {fmt(fh, 0)} mm<br>"
                         f"Aprovechamiento: {fmt(100 * st['utilization'])} %")
            counts = Counter(q.part for q in L.on_sheet(s))
            self.table.setRowCount(len(counts))
            for r, (name, n) in enumerate(sorted(counts.items())):
                it = QTableWidgetItem(name)
                it.setBackground(self._colors.get(name, QColor("white")))
                self.table.setItem(r, 0, it)
                num = QTableWidgetItem(str(n))
                num.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, 1, num)
        if L.unplaced:
            left = ", ".join(f"{n} × {k}" for k, n in sorted(L.unplaced.items()))
            lines.append(f"<span style='color:#b00000'><b>Sin colocar:</b> {left}</span>")
        if self.issues:
            lines.append(f"<span style='color:#b00000'><b>Validación: {len(self.issues)} problemas</b> "
                         "(piezas con borde rojo)</span>")
        else:
            lines.append("<span style='color:#2a6a3a'>Validación: sin solapes; separación y margen respetados.</span>")
        self.summary.setText("<br><br>".join(lines))
