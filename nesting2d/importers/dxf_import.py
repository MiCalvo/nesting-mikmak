"""Importador DXF (ezdxf).

Probado con DXF SINTÉTICOS (generados con ezdxf imitando lo que exporta un CAD:
arcos, polilíneas con bulge, splines, elipses, bloques escalados/girados y
anidados, MINSERT, pulgadas, capas). FALTA probarlo con DXF reales del CAD.

Lee LINE, ARC, CIRCLE, ELLIPSE, LWPOLYLINE, POLYLINE y SPLINE, también dentro de
bloques (INSERT, anidados y MINSERT), los discretiza y reconstruye las piezas con
`contours.build_parts`. Ignora textos, cotas y sombreados.

Capas: como en CAD, una entidad de la capa "0" dentro de un bloque toma la capa
del INSERT que la coloca. Con `layers` se importan solo esas capas.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import ezdxf
from ezdxf import path as ezpath
from ezdxf import units

from ..geometry import Part
from .contours import ImportOptions, build_parts
from .pdf_import import ImportResult

GEOM_TYPES = {"LINE", "ARC", "CIRCLE", "ELLIPSE", "LWPOLYLINE", "POLYLINE", "SPLINE"}
MAX_BLOCK_DEPTH = 32   # protección contra bloques que se referencian a sí mismos


def _entities(entities, parent_layer: str | None = None, depth: int = 0):
    """(entidad, capa efectiva) de todas las entidades geométricas, entrando en bloques."""
    for e in entities:
        t = e.dxftype()
        layer = e.dxf.get("layer", "0")
        if parent_layer is not None and layer == "0":
            layer = parent_layer
        if t in GEOM_TYPES:
            yield e, layer
        elif t == "INSERT" and depth < MAX_BLOCK_DEPTH:
            inserts = e.multi_insert() if e.mcount > 1 else [e]
            for ins in inserts:
                try:
                    content = list(ins.virtual_entities())
                except Exception:   # bloque inexistente o transformación no soportada
                    continue
                yield from _entities(content, layer, depth + 1)


def _read(file: Path):
    doc = ezdxf.readfile(file)
    warnings = []
    src = doc.units
    if src == units.InsertUnits.Unitless:
        imperial = doc.header.get("$MEASUREMENT", 1) == 0
        warnings.append(f"{file.name}: el DXF no declara unidades; se asumen mm."
                        + (" OJO: el archivo dice ser de sistema imperial; si las medidas salen "
                           "25,4 veces pequeñas, está en pulgadas (corrige la escala a 25,4)." if imperial else ""))
        factor = 1.0
    else:
        factor = units.conversion_factor(src, units.MM)
    return doc, factor, warnings


def dxf_layers(file: str | Path) -> Counter:
    """Capas efectivas con geometría y cuántas entidades tiene cada una."""
    doc, _, _ = _read(Path(file))
    return Counter(layer for _, layer in _entities(doc.modelspace()))


def dxf_polylines(file: str | Path, opts: ImportOptions | None = None,
                  layers: list[str] | None = None) -> tuple[list, list[str]]:
    """Trazos del DXF en mm (polilíneas) y avisos."""
    opts = opts or ImportOptions()
    file = Path(file)
    doc, factor, warnings = _read(file)
    polylines = []
    for e, layer in _entities(doc.modelspace()):
        if layers is not None and layer not in layers:
            continue
        try:
            p = ezpath.make_path(e)
        except (TypeError, ValueError):
            continue
        pts = [(v.x * factor, v.y * factor) for v in p.flattening(opts.max_segment / 10)]
        if len(pts) >= 2:
            polylines.append(pts)
    return polylines, warnings


def import_dxf(file: str | Path, opts: ImportOptions | None = None,
               layers: list[str] | None = None) -> ImportResult:
    opts = opts or ImportOptions()
    file = Path(file)
    res = ImportResult()
    polylines, res.warnings = dxf_polylines(file, opts, layers)
    polys = build_parts(polylines, opts)
    for k, poly in enumerate(polys, start=1):
        name = file.stem if len(polys) == 1 else f"{file.stem}_{k}"
        res.parts.append(Part(name=name, shape=poly, source=str(file)))
    if not polys:
        res.warnings.append(f"{file.name}: no se encontró ningún contorno cerrado.")
    return res
