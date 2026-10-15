"""Exportación DXF de una plancha (ezdxf).

Capas:
- CORTE: contornos exteriores y huecos de las piezas, polilíneas cerradas en mm.
- PLANCHA: borde de la plancha (opcional).
- ETIQUETAS: nombre de cada pieza (desactivada por defecto para que el texto no
  acabe cortado).

Curvas: por defecto, polilíneas de segmentos de ≤ 0,5 mm (como siempre). Con
`arcs=True` se ajustan arcos y círculos (ver arcs.py): CIRCLE para los anillos
circulares y LWPOLYLINE con abombamiento (bulge) para el resto, sin desviarse
más de `arc_tol` mm. PENDIENTE: confirmar con el proveedor qué acepta su máquina.
"""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf import units

from ..engine.nester import Layout
from .arcs import DEFAULT_TOL, ring_circle, ring_to_bulges

LAYER_CUT, LAYER_SHEET, LAYER_LABELS = "CORTE", "PLANCHA", "ETIQUETAS"


def export_sheet(layout: Layout, sheet: int, path: str | Path,
                 sheet_border: bool = True, labels: bool = False,
                 arcs: bool = False, arc_tol: float = DEFAULT_TOL) -> Path:
    path = Path(path)
    doc = ezdxf.new("R2010", setup=False)
    doc.units = units.MM
    doc.header["$MEASUREMENT"] = 1  # métrico
    doc.layers.add(LAYER_CUT, color=7)
    msp = doc.modelspace()

    for pl in layout.on_sheet(sheet):
        for ring in [pl.polygon.exterior, *pl.polygon.interiors]:
            coords = list(ring.coords)
            if arcs:
                circle = ring_circle(coords, arc_tol)
                if circle is not None:
                    msp.add_circle(circle[0], circle[1], dxfattribs={"layer": LAYER_CUT})
                else:
                    msp.add_lwpolyline(ring_to_bulges(coords, arc_tol), format="xyb", close=True,
                                       dxfattribs={"layer": LAYER_CUT})
            else:
                msp.add_lwpolyline(coords[:-1], close=True, dxfattribs={"layer": LAYER_CUT})

    if sheet_border:
        doc.layers.add(LAYER_SHEET, color=8)
        W, H = layout.params.sheet_width, layout.params.sheet_height
        msp.add_lwpolyline([(0, 0), (W, 0), (W, H), (0, H)], close=True,
                           dxfattribs={"layer": LAYER_SHEET})
    if labels:
        doc.layers.add(LAYER_LABELS, color=3)
        for pl in layout.on_sheet(sheet):
            c = pl.polygon.representative_point()
            msp.add_text(pl.part, height=3.0, dxfattribs={"layer": LAYER_LABELS}).set_placement((c.x, c.y))

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    return path
