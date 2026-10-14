"""Modelo de pieza y utilidades geométricas.

Todas las medidas en milímetros. Las geometrías son polígonos de shapely
(contorno exterior + huecos).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from shapely.affinity import scale as _scale
from shapely.affinity import translate
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


@dataclass
class Part:
    """Una pieza importada.

    `shape` es la geometría tal como se importó (mm, escala 1:1 del archivo).
    La escala, el espejo y las rotaciones se aplican al pedir `geometry()`,
    así que el original nunca se modifica.
    """

    name: str
    shape: Polygon
    source: str = ""
    page: int | None = None
    scale: float = 1.0
    quantity: int = 1
    # None = usar las rotaciones del proyecto; lista = ángulos permitidos (grados)
    rotations: list[float] | None = None
    mirror: bool = False
    extra: dict = field(default_factory=dict)

    def geometry(self) -> Polygon:
        """Geometría efectiva (escala uniforme + espejo), con su esquina inferior
        izquierda en (0, 0) y orientación CCW."""
        g = self.shape
        if self.scale != 1.0:
            g = _scale(g, self.scale, self.scale, origin=(0, 0))
        if self.mirror:
            g = _scale(g, -1.0, 1.0, origin=(0, 0))
        return normalize(g)

    @property
    def size(self) -> tuple[float, float]:
        minx, miny, maxx, maxy = self.geometry().bounds
        return maxx - minx, maxy - miny

    @property
    def area(self) -> float:
        return self.geometry().area


def normalize(g: Polygon) -> Polygon:
    """Lleva la esquina inferior izquierda del contorno a (0, 0) y orienta CCW."""
    minx, miny, _, _ = g.bounds
    return orient(translate(g, -minx, -miny), 1.0)


def scale_from_measure(measured: float, real: float) -> float:
    """Escala uniforme a partir de una cota: escala = real / medida."""
    if measured <= 0 or real <= 0:
        raise ValueError("La medida y el valor real deben ser positivos")
    return real / measured
