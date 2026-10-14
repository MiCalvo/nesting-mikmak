"""Exportación DXF de una plancha (ezdxf).

Capas:
- CORTE: contornos exteriores y huecos de las piezas, polilíneas cerradas en mm.
- PLANCHA: borde de la plancha (opcional).
- ETIQUETAS: nombre de cada pieza (desactivada por defecto para que el texto no
  acabe cortado).

PENDIENTE (ver especificación): ajustar capas, unidades y formato de curvas
(arcos o polilíneas) a lo que pida el proveedor. Ahora las curvas salen como
polilíneas de segmentos de ≤ 0,5 mm.
"""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf import units

from ..engine.nester import Layout

LAYER_CUT, LAYER_SHEET, LAYER_LABELS = "CORTE", "PLANCHA", "ETIQUETAS"


def export_sheet(layout: Layout, sheet: int, path: str | Path,
                 sheet_border: bool = True, labels: bool = False) -> Path:
    path = Path(path)
    doc = ezdxf.new("R2010", setup=False)
    doc.units = units.MM
    doc.header["$MEASUREMENT"] = 1  # métrico
    doc.layers.add(LAYER_CUT, color=7)
    msp = doc.modelspace()

    for pl in layout.on_sheet(sheet):
        for ring in [pl.polygon.exterior, *pl.polygon.interiors]:
            pts = list(ring.coords)[:-1]
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": LAYER_CUT})

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
