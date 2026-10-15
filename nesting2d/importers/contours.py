"""Reconstrucción de piezas a partir de trazos sueltos (común a PDF y DXF).

Entrada: polilíneas en mm (listas de puntos). Salida: polígonos con huecos.

Pasos:
1. Unir extremos cercanos (tolerancia de unión): los CAD exportan trazos cuyos
   extremos no coinciden exactamente. Sin este paso, en las pruebas con las
   juntas RIGCCP quedaban círculos sin cerrar.
2. Nodar todos los trazos y formar las caras cerradas (polygonize). Los trazos
   abiertos (cruces de centro, cotas) no forman caras y desaparecen solos.
3. Regla par-impar: una cara es material si está contenida en un número PAR de
   contornos de otras caras. Así se distinguen pieza (0), hueco (1), pieza
   dentro de un hueco (2), etc.
4. Unir las caras de material que comparten borde (una línea que cruce la
   pieza la parte en varias caras) y separar en piezas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely import STRtree
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union


@dataclass
class ImportOptions:
    join_tolerance: float = 0.01   # mm: extremos más cercanos que esto se unen
    min_area: float = 1.0          # mm²: piezas más pequeñas se descartan
    max_segment: float = 0.5       # mm: longitud máx. de segmento al discretizar curvas


def snap_endpoints(polylines: list[list[tuple[float, float]]], tol: float) -> list[list[tuple[float, float]]]:
    """Une los extremos de las polilíneas que están a menos de `tol` entre sí.

    Usa una rejilla de celdas de tamaño `tol` y busca en las 9 celdas vecinas,
    así no depende de dónde caiga el redondeo (que fallaría con dos puntos a
    ambos lados de un borde de celda).
    """
    if tol <= 0:
        return polylines
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def rep(p: tuple[float, float]) -> tuple[float, float]:
        cx, cy = math.floor(p[0] / tol), math.floor(p[1] / tol)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in grid.get((cx + dx, cy + dy), ()):
                    if math.dist(p, q) <= tol:
                        return q
        grid.setdefault((cx, cy), []).append(p)
        return p

    out = []
    for pl in polylines:
        if len(pl) < 2:
            continue
        pl = list(pl)
        pl[0] = rep(pl[0])
        pl[-1] = rep(pl[-1])
        out.append(pl)
    return out


def closed_faces(polylines: list[list[tuple[float, float]]], opts: ImportOptions) -> list[Polygon]:
    """Pasos 1 y 2: une extremos, noda los trazos y devuelve las caras cerradas
    mínimas (cada región que encierran los trazos). Los trazos abiertos no forman caras."""
    polylines = snap_endpoints(polylines, opts.join_tolerance)
    lines = [LineString(pl) for pl in polylines if len(pl) >= 2]
    lines = [ln for ln in lines if ln.length > 0]
    if not lines:
        return []
    return [f for f in polygonize(unary_union(lines)) if f.area > 1e-9]


def parts_from_faces(faces: list[Polygon], min_area: float = 0.0) -> list[Polygon]:
    """Pasos 3 y 4: regla par-impar entre las caras dadas y unión de las de material.

    Sirve también para la selección manual de contornos: con solo las caras que
    elige el usuario, el marco o el cajetín no cuentan al decidir qué es hueco."""
    if not faces:
        return []
    shells = [Polygon(f.exterior) for f in faces]
    tree = STRtree(shells)
    material = []
    for i, f in enumerate(faces):
        pt = f.representative_point()
        depth = sum(1 for j in tree.query(pt, predicate="within") if j != i)
        if depth % 2 == 0:
            material.append(f)

    merged = unary_union(material)
    if isinstance(merged, Polygon):
        parts = [merged]
    elif isinstance(merged, MultiPolygon):
        parts = list(merged.geoms)
    else:
        parts = [g for g in getattr(merged, "geoms", []) if isinstance(g, Polygon)]

    parts = [p for p in parts if not p.is_empty and p.area >= min_area]
    parts.sort(key=lambda p: -p.area)
    return parts


def build_parts(polylines: list[list[tuple[float, float]]], opts: ImportOptions) -> list[Polygon]:
    """Convierte trazos sueltos en piezas (polígonos con huecos), de mayor a menor área."""
    return parts_from_faces(closed_faces(polylines, opts), opts.min_area)
