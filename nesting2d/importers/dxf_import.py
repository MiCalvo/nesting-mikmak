"""Importador DXF (ezdxf).

AÚN NO PROBADO CON DXF REALES DE UN CAD (solo con DXF generados por esta app).
Comprobar con archivos reales: unidades ($INSUNITS), arcos, splines, bloques.

Lee LINE, ARC, CIRCLE, ELLIPSE, LWPOLYLINE, POLYLINE y SPLINE (también dentro
de bloques INSERT), los discretiza y reconstruye las piezas con
`contours.build_parts`. Ignora textos, cotas y sombreados.
"""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf import path as ezpath
from ezdxf import units

from ..geometry import Part
from .contours import ImportOptions, build_parts
from .pdf_import import ImportResult

GEOM_TYPES = {"LINE", "ARC", "CIRCLE", "ELLIPSE", "LWPOLYLINE", "POLYLINE", "SPLINE"}


def _entities(layout):
    for e in layout:
        t = e.dxftype()
        if t in GEOM_TYPES:
            yield e
        elif t == "INSERT":
            yield from (v for v in e.virtual_entities() if v.dxftype() in GEOM_TYPES)


def import_dxf(file: str | Path, opts: ImportOptions | None = None,
               layers: list[str] | None = None) -> ImportResult:
    opts = opts or ImportOptions()
    file = Path(file)
    res = ImportResult()
    doc = ezdxf.readfile(file)
    src = doc.units
    if src == units.InsertUnits.Unitless:
        res.warnings.append(f"{file.name}: el DXF no declara unidades; se asumen mm.")
        factor = 1.0
    else:
        factor = units.conversion_factor(src, units.MM)

    polylines = []
    for e in _entities(doc.modelspace()):
        if layers and e.dxf.layer not in layers:
            continue
        try:
            p = ezpath.make_path(e)
        except (TypeError, ValueError):
            continue
        pts = [(v.x * factor, v.y * factor) for v in p.flattening(opts.max_segment / 10)]
        if len(pts) >= 2:
            polylines.append(pts)

    polys = build_parts(polylines, opts)
    for k, poly in enumerate(polys, start=1):
        name = file.stem if len(polys) == 1 else f"{file.stem}_{k}"
        res.parts.append(Part(name=name, shape=poly, source=str(file)))
    if not polys:
        res.warnings.append(f"{file.name}: no se encontró ningún contorno cerrado.")
    return res
