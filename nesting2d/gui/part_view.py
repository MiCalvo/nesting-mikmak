"""Vista ampliada de una pieza, con la herramienta de acotar.

Acotar (ver especificación, «Pestaña Piezas»):
- «Dos puntos»: dos clics, con enganche a centros de círculo, vértices y aristas.
- «Arista recta»: un clic sobre una arista recta mide su longitud.
Al terminar emite `measured(distancia_mm)`; quien la recibe pide la medida real
y calcula la escala (escala = real / medida).

Se mide sobre `Part.geometry()`, es decir, con la escala actual ya aplicada.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from ..geometry import Part
from .qt_util import fmt, from_scene, polygon_path, to_scene
from .snapping import Edge, Snap, SnapTargets

SNAP_PX = 10          # radio de enganche en píxeles de pantalla
MODE_NONE, MODE_POINTS, MODE_EDGE = "", "puntos", "arista"


def _pen(color, width=0.0, style=Qt.PenStyle.SolidLine) -> QPen:
    p = QPen(QColor(color), width, style)
    p.setCosmetic(True)  # grosor en píxeles, no en mm
    return p


class PartView(QGraphicsView):
    measured = Signal(float)
    hint = Signal(str)          # texto de ayuda para la barra de estado

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#fafafa"))
        self.part: Part | None = None
        self.targets: SnapTargets | None = None
        self.mode = MODE_NONE
        self._first: tuple[float, float] | None = None
        self._snap: Snap | None = None
        self._edge: Edge | None = None
        self._cursor: tuple[float, float] | None = None
        self.auto_fit = True   # se reajusta al cambiar de tamaño hasta que el usuario hace zoom

    # --- API ------------------------------------------------------------------
    def set_part(self, part: Part | None) -> None:
        self.part = part
        self.targets = None
        self._first = self._snap = self._edge = None
        sc = self.scene()
        sc.clear()
        if part is None:
            sc.setSceneRect(QRectF())
            return
        g = part.geometry()
        self.targets = SnapTargets(g)
        item = sc.addPath(polygon_path(g), _pen("#303030"), QBrush(QColor(120, 160, 210, 140)))
        item.setZValue(0)
        minx, miny, maxx, maxy = g.bounds
        pad = 0.08 * max(maxx - minx, maxy - miny, 1.0)
        sc.setSceneRect(QRectF(minx - pad, -maxy - pad, maxx - minx + 2 * pad, maxy - miny + 2 * pad))
        self.fit()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._first = self._snap = self._edge = None
        self.setCursor(Qt.CursorShape.CrossCursor if mode else Qt.CursorShape.ArrowCursor)
        if mode == MODE_POINTS:
            self.hint.emit("Acotar: haz clic en el primer punto (engancha a centros, vértices y aristas). Esc cancela.")
        elif mode == MODE_EDGE:
            self.hint.emit("Acotar: haz clic sobre una arista recta. Esc cancela.")
        self.viewport().update()

    def fit(self) -> None:
        self.auto_fit = True
        if not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # --- eventos --------------------------------------------------------------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.auto_fit:
            self.fit()

    def wheelEvent(self, e):
        self.auto_fit = False
        k = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.scale(k, k)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.mode:
            self.set_mode(MODE_NONE)
            self.hint.emit("")
            return
        super().keyPressEvent(e)

    def _radius_mm(self) -> float:
        k = self.transform().m11() or 1.0
        return SNAP_PX / abs(k)

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        if not self.targets or not self.mode:
            return
        x, y = from_scene(self.mapToScene(e.position().toPoint()))
        self._cursor = (x, y)
        if self.mode == MODE_POINTS:
            self._snap = self.targets.snap(x, y, self._radius_mm())
        else:
            self._edge = self.targets.edge_at(x, y, self._radius_mm())
        self.viewport().update()

    def mousePressEvent(self, e):
        if not self.targets or not self.mode or e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        x, y = from_scene(self.mapToScene(e.position().toPoint()))
        if self.mode == MODE_EDGE:
            edge = self.targets.edge_at(x, y, self._radius_mm())
            if edge is None:
                self.hint.emit("No hay ninguna arista recta cerca del clic.")
                return
            self.set_mode(MODE_NONE)
            self.measured.emit(edge.length)
            return
        snap = self.targets.snap(x, y, self._radius_mm())
        pt = snap.point if snap else (x, y)
        if self._first is None:
            self._first = pt
            self.hint.emit("Acotar: haz clic en el segundo punto.")
            self.viewport().update()
            return
        a = self._first
        dist = ((pt[0] - a[0]) ** 2 + (pt[1] - a[1]) ** 2) ** 0.5
        if dist <= 0:
            self.hint.emit("Los dos puntos coinciden; elige otro segundo punto.")
            return
        self.set_mode(MODE_NONE)
        self.measured.emit(dist)

    # --- dibujo de la herramienta ----------------------------------------------
    def drawForeground(self, painter: QPainter, rect):
        super().drawForeground(painter, rect)
        if not self.mode:
            return
        r = self._radius_mm() * 0.6
        if self.mode == MODE_EDGE and self._edge is not None:
            painter.setPen(_pen("#d00000", 3))
            painter.drawLine(to_scene(*self._edge.a), to_scene(*self._edge.b))
            self._label(painter, self._edge.a, self._edge.b, self._edge.length)
            return
        cur = self._snap.point if self._snap else self._cursor
        if self._first is not None and cur is not None:
            painter.setPen(_pen("#d00000", 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(to_scene(*self._first), to_scene(*cur))
            d = ((cur[0] - self._first[0]) ** 2 + (cur[1] - self._first[1]) ** 2) ** 0.5
            self._label(painter, self._first, cur, d)
            self._marker(painter, "vertice", self._first, r)
        if self._snap is not None:
            self._marker(painter, self._snap.kind, self._snap.point, r)

    def _marker(self, painter: QPainter, kind: str, pt, r: float):
        painter.setPen(_pen("#d00000", 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        c = to_scene(*pt)
        if kind == "centro":
            painter.drawEllipse(c, r, r)
            painter.drawLine(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))
            painter.drawLine(QPointF(c.x(), c.y() - r), QPointF(c.x(), c.y() + r))
        elif kind == "vertice":
            painter.drawRect(QRectF(c.x() - r / 2, c.y() - r / 2, r, r))
        else:  # punto sobre arista
            painter.drawLine(QPointF(c.x() - r / 2, c.y() - r / 2), QPointF(c.x() + r / 2, c.y() + r / 2))
            painter.drawLine(QPointF(c.x() - r / 2, c.y() + r / 2), QPointF(c.x() + r / 2, c.y() - r / 2))

    def _label(self, painter: QPainter, a, b, dist: float):
        """Texto con la distancia junto al punto medio, a tamaño fijo en pantalla."""
        mid = self.mapFromScene(to_scene((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        painter.save()
        painter.resetTransform()
        painter.setPen(QColor("#d00000"))
        painter.drawText(mid.x() + 8, mid.y() - 8, f"{fmt(dist, 3)} mm")
        painter.restore()
