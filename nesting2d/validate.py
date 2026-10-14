"""Validación de una colocación: solapes, separación mínima y margen.

La usa el motor en las pruebas y la usará la edición manual (fase 3) para poner
en rojo las piezas que incumplen las reglas.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely import STRtree
from shapely.geometry import box

from .engine.nester import Layout, Placement
from .engine.params import NestParams

TOL = 1e-3  # mm de holgura numérica


@dataclass
class Issue:
    kind: str            # "solape" | "separacion" | "margen"
    items: tuple[int, ...]  # índices de las Placement implicadas
    value: float         # área de solape (mm²), distancia (mm) o distancia fuera (mm)

    def __str__(self) -> str:
        unit = "mm²" if self.kind == "solape" else "mm"
        return f"{self.kind}: piezas {self.items} ({self.value:.3f} {unit})"


def check(placements: list[Placement], params: NestParams, sheet: int | None = None) -> list[Issue]:
    idx = [i for i, p in enumerate(placements) if sheet is None or p.sheet == sheet]
    issues: list[Issue] = []
    m = params.margin
    inner_area = box(m, m, params.sheet_width - m, params.sheet_height - m)

    for i in idx:
        g = placements[i].polygon
        if not inner_area.buffer(TOL).contains(g):
            out = g.difference(inner_area)
            issues.append(Issue("margen", (i,), out.area))

    by_sheet: dict[int, list[int]] = {}
    for i in idx:
        by_sheet.setdefault(placements[i].sheet, []).append(i)
    for ids in by_sheet.values():
        geoms = [placements[i].polygon for i in ids]
        tree = STRtree(geoms)
        for a_pos, a in enumerate(ids):
            ga = geoms[a_pos]
            for b_pos in tree.query(ga.buffer(params.separation)):
                b = ids[b_pos]
                if b <= a:
                    continue
                gb = geoms[b_pos]
                inter = ga.intersection(gb).area
                if inter > TOL:
                    issues.append(Issue("solape", (a, b), inter))
                    continue
                d = ga.distance(gb)
                if d < params.separation - TOL:
                    issues.append(Issue("separacion", (a, b), d))
    return issues


def check_layout(layout: Layout) -> list[Issue]:
    return check(layout.placements, layout.params)
