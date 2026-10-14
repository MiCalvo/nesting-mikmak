"""Utilidades de Qt comunes a la interfaz.

Convención de coordenadas: los datos están en mm con Y hacia ARRIBA; en las
escenas de Qt la Y va hacia abajo, así que se dibuja en (x, −y).
"""
from __future__ import annotations

from PySide6.QtCore import QLocale, QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from shapely.geometry import Polygon


def fmt(value: float, decimals: int = 1) -> str:
    """Número con el separador decimal del idioma del sistema (coma en español)."""
    return QLocale().toString(float(value), "f", decimals)


def polygon_path(poly: Polygon) -> QPainterPath:
    """Contorno + huecos como un QPainterPath (regla par-impar), en (x, −y)."""
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    for ring in [poly.exterior, *poly.interiors]:
        pts = list(ring.coords)
        path.moveTo(pts[0][0], -pts[0][1])
        for x, y in pts[1:]:
            path.lineTo(x, -y)
        path.closeSubpath()
    return path


def to_scene(x: float, y: float) -> QPointF:
    return QPointF(x, -y)


def from_scene(p: QPointF) -> tuple[float, float]:
    return p.x(), -p.y()


def part_color(index: int) -> QColor:
    """Colores bien separados para distinguir piezas (ángulo áureo en el tono)."""
    hue = int((index * 137.508) % 360)
    return QColor.fromHsv(hue, 110, 235)


def shape_icon(poly: Polygon, size: int = 48) -> QIcon:
    """Miniatura de la silueta con sus huecos."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    minx, miny, maxx, maxy = poly.bounds
    w, h = maxx - minx, maxy - miny
    if w > 0 and h > 0:
        k = (size - 4) / max(w, h)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(size / 2, size / 2)
        p.scale(k, k)
        p.translate(-(minx + maxx) / 2, (miny + maxy) / 2)
        pen = QPen(QColor(40, 40, 40))
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(QColor(120, 160, 210))
        p.drawPath(polygon_path(poly))
        p.end()
    return QIcon(pm)
