"""Enganche para acotar una pieza (sin dependencias de Qt, para poder probarlo).

Objetivos de enganche, por prioridad:
1. Centros de círculo (contornos casi circulares: huecos de tornillo, etc.).
2. Vértices del contorno. Ojo: las curvas importadas están discretizadas, así
   que en un arco cada punto de la discretización también es un vértice.
3. Cualquier punto de una arista (el más cercano del contorno).

Además se pueden elegir aristas rectas: tramos de segmentos consecutivos con la
misma dirección, unidos en una sola arista.

Coordenadas en mm, las mismas que `Part.geometry()`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

CIRCLE_MIN_POINTS = 12      # menos puntos: no se considera círculo
CIRCLE_REL_TOL = 0.01       # desviación del radio admitida (1 %)
EDGE_ANGLE_TOL = 0.05       # grados: segmentos dentro de esta desviación forman una arista


@dataclass
class Snap:
    kind: str                    # "centro" | "vertice" | "arista"
    point: tuple[float, float]


@dataclass
class Edge:
    a: tuple[float, float]
    b: tuple[float, float]

    @property
    def length(self) -> float:
        return math.dist(self.a, self.b)


def _circle(ring_coords: np.ndarray):
    """(cx, cy, r) si el anillo es casi un círculo; si no, None."""
    pts = ring_coords[:-1]
    if len(pts) < CIRCLE_MIN_POINTS:
        return None
    poly = Polygon(ring_coords)
    c = poly.centroid
    d = np.hypot(pts[:, 0] - c.x, pts[:, 1] - c.y)
    r = float(d.mean())
    if r <= 0 or (d.max() - d.min()) > CIRCLE_REL_TOL * r:
        return None
    # Un rectángulo con esquinas redondeadas tiene todos sus vértices en las
    # esquinas, a la misma distancia del centro: el área lo descarta.
    if abs(poly.area - math.pi * r * r) > 2 * CIRCLE_REL_TOL * math.pi * r * r:
        return None
    return c.x, c.y, r


def _angle_diff(a: float, b: float) -> float:
    """Diferencia entre dos direcciones de recta (sin sentido), en grados, 0..90."""
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _straight_edges(ring_coords: np.ndarray) -> list[Edge]:
    pts = [(float(x), float(y)) for x, y in ring_coords[:-1]]
    n = len(pts)
    if n < 3:
        return []

    def direction(p, q):
        return math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))

    seg_dir = [direction(pts[i], pts[(i + 1) % n]) for i in range(n)]
    # empezar en una esquina para no partir una arista en dos al cerrar el anillo
    start = next((i for i in range(n) if _angle_diff(seg_dir[i - 1], seg_dir[i]) > EDGE_ANGLE_TOL), None)
    if start is None:
        return []
    edges: list[Edge] = []
    a = pts[start]
    for k in range(1, n + 1):
        i = (start + k) % n
        b = pts[i]
        nxt = pts[(i + 1) % n]
        # ¿el siguiente segmento sigue la dirección del tramo a→b?
        if k < n and _angle_diff(direction(a, b), direction(b, nxt)) <= EDGE_ANGLE_TOL:
            continue
        edges.append(Edge(a, b))
        a = b
    return edges


class SnapTargets:
    def __init__(self, poly: Polygon):
        self.poly = poly
        rings = [np.asarray(poly.exterior.coords)] + [np.asarray(r.coords) for r in poly.interiors]
        self.vertices = np.vstack([r[:-1] for r in rings])
        self.circles = [c for c in (_circle(r) for r in rings) if c is not None]
        self.edges = [e for r in rings for e in _straight_edges(r)]
        self._boundary = poly.boundary

    def snap(self, x: float, y: float, radius: float) -> Snap | None:
        """Mejor punto de enganche a menos de `radius` mm de (x, y)."""
        best = None
        for cx, cy, _ in self.circles:
            d = math.hypot(cx - x, cy - y)
            if d <= radius and (best is None or d < best[0]):
                best = (d, (cx, cy))
        if best:
            return Snap("centro", best[1])

        d = np.hypot(self.vertices[:, 0] - x, self.vertices[:, 1] - y)
        i = int(d.argmin())
        if d[i] <= radius:
            return Snap("vertice", (float(self.vertices[i, 0]), float(self.vertices[i, 1])))

        p = nearest_points(self._boundary, Point(x, y))[0]
        if math.hypot(p.x - x, p.y - y) <= radius:
            return Snap("arista", (p.x, p.y))
        return None

    def edge_at(self, x: float, y: float, radius: float) -> Edge | None:
        """Arista recta más cercana a (x, y), si está a menos de `radius` mm."""
        best, best_d = None, radius
        for e in self.edges:
            d = _dist_point_segment((x, y), e.a, e.b)
            if d <= best_d:
                best, best_d = e, d
        return best


def _dist_point_segment(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))
