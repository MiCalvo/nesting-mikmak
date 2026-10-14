"""Importador de PDF vectorial (pdfplumber, licencia MIT).

Lee líneas, rectángulos y curvas Bézier de cada página, los pasa a mm con el
eje Y hacia arriba y reconstruye las piezas con `contours.build_parts`.

Ojo: pdfplumber da las coordenadas de los trazados con el origen ARRIBA (Y hacia
abajo). Se invierte Y con la altura de página; si no, las piezas saldrían
espejadas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from ..geometry import Part
from .contours import ImportOptions, build_parts

PT_TO_MM = 25.4 / 72.0


@dataclass
class ImportResult:
    parts: list[Part] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _bezier(p0, p1, p2, p3, max_seg: float):
    """Discretiza una Bézier cúbica (en mm) con segmentos de como mucho `max_seg`."""
    ctrl_len = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
    n = max(4, math.ceil(ctrl_len / max_seg))
    pts = []
    for k in range(1, n + 1):
        t = k / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def _path_to_polylines(path, page_h: float, max_seg: float):
    """Convierte la lista de operaciones de pdfplumber ('m','l','c','h') en polilíneas en mm."""
    def mm(p):
        return (p[0] * PT_TO_MM, (page_h - p[1]) * PT_TO_MM)

    polylines, cur, start = [], [], None
    for op in path:
        kind = op[0]
        if kind == "m":
            if len(cur) >= 2:
                polylines.append(cur)
            cur = [mm(op[1])]
            start = cur[0]
        elif kind == "l":
            cur.append(mm(op[1]))
        elif kind == "c" and cur:
            cur.extend(_bezier(cur[-1], mm(op[1]), mm(op[2]), mm(op[3]), max_seg))
        elif kind == "h" and cur and start is not None:
            cur.append(start)
    if len(cur) >= 2:
        polylines.append(cur)
    return polylines


def page_polylines(page, opts: ImportOptions):
    out = []
    for obj in page.lines + page.rects + page.curves:
        path = obj.get("path")
        if path:
            out.extend(_path_to_polylines(path, page.height, opts.max_segment))
    return out


def import_pdf(file: str | Path, opts: ImportOptions | None = None, pages: list[int] | None = None) -> ImportResult:
    """Importa todas las piezas de un PDF vectorial.

    Nombre de cada pieza: el nombre del archivo si sale una sola pieza en todo
    el PDF; si no, `<archivo>_p<página>_<n>`.

    Un plano con varias vistas, cotas y texto dibujado como trazos (típico de
    NX) genera muchas "piezas" falsas (letras O, D…). Eso se resolverá en la
    interfaz con selección manual de contornos (fase 5); aquí se devuelve todo.
    """
    opts = opts or ImportOptions()
    file = Path(file)
    res = ImportResult()
    found: list[tuple[int, object]] = []
    with pdfplumber.open(file) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            if pages and i not in pages:
                continue
            pls = page_polylines(page, opts)
            if not pls:
                kind = "imágenes" if page.images else "ningún trazo"
                res.warnings.append(
                    f"{file.name} pág. {i}: sin trazos vectoriales ({kind}); "
                    "¿PDF escaneado? No se importa nada de esta página.")
                continue
            for poly in build_parts(pls, opts):
                found.append((i, poly))

    single = len(found) == 1
    counter: dict[int, int] = {}
    for page_no, poly in found:
        counter[page_no] = counter.get(page_no, 0) + 1
        name = file.stem if single else f"{file.stem}_p{page_no}_{counter[page_no]}"
        res.parts.append(Part(name=name, shape=poly, source=str(file), page=page_no))
    if not found and not res.warnings:
        res.warnings.append(f"{file.name}: no se encontró ningún contorno cerrado.")
    return res
