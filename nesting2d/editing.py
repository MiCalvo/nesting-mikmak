"""Edición manual de un resultado de nesting (sin Qt, para poder probarlo).

Todas las funciones devuelven los cambios como {índice: Placement nueva} en vez
de modificar el Layout; quien llama los aplica con `apply` y así puede
deshacerlos (la interfaz guarda el antes y el después).

Pieza dentro de pieza: al mover o girar un contenedor se mueven con él las
piezas que lleva dentro (`with_inners`). Si se mueve sola una pieza interior,
deja de estar ligada a su contenedor (host = None).
"""
from __future__ import annotations

from dataclasses import replace

from shapely.affinity import rotate, translate

from .engine.nester import Layout, Placement
from .engine.params import NestParams
from .geometry import Part

ANGLE_TOL = 1e-6

Changes = dict[int, Placement]


def with_inners(layout: Layout, indices) -> list[int]:
    """Los índices dados más las piezas que van dentro de alguno de ellos."""
    sel = set(indices)
    extra = {i for i, q in enumerate(layout.placements) if q.host in sel}
    return sorted(sel | extra)


def bounds(layout: Layout, indices) -> tuple[float, float, float, float]:
    """Rectángulo envolvente (minx, miny, maxx, maxy) de las piezas dadas."""
    bs = [layout.placements[i].polygon.bounds for i in indices]
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def _detach(layout: Layout, moved: set[int], i: int) -> int | None:
    """Host que conserva la pieza i tras mover el conjunto `moved`."""
    h = layout.placements[i].host
    return h if h is not None and h in moved else None


def moved(layout: Layout, indices, dx: float, dy: float) -> Changes:
    sel = set(indices)
    return {i: replace(layout.placements[i], polygon=translate(layout.placements[i].polygon, dx, dy),
                       host=_detach(layout, sel, i))
            for i in sel}


def rotated(layout: Layout, indices, angle: float, center: tuple[float, float] | None = None) -> Changes:
    """Gira las piezas `angle` grados (positivo = antihorario) alrededor de `center`
    (por defecto, el centro del rectángulo que las envuelve)."""
    sel = set(indices)
    if center is None:
        x0, y0, x1, y1 = bounds(layout, sel)
        center = ((x0 + x1) / 2, (y0 + y1) / 2)
    out = {}
    for i in sel:
        q = layout.placements[i]
        out[i] = replace(q, polygon=rotate(q.polygon, angle, origin=center),
                         angle=round((q.angle + angle) % 360, 9), host=_detach(layout, sel, i))
    return out


def to_sheet(layout: Layout, indices, sheet: int) -> Changes:
    """Pasa las piezas a otra plancha, en la misma posición. Si se sacan de su
    contenedor (que se queda), dejan de estar ligadas a él."""
    sel = set(indices)
    return {i: replace(layout.placements[i], sheet=sheet, host=_detach(layout, sel, i)) for i in sel}


def apply(layout: Layout, changes: Changes) -> None:
    for i, q in changes.items():
        layout.placements[i] = q


def snapshot(layout: Layout, indices) -> Changes:
    return {i: layout.placements[i] for i in indices}


def snap_delta(layout: Layout, indices, dx: float, dy: float, tol: float) -> tuple[float, float]:
    """Corrige un desplazamiento para enganchar el rectángulo envolvente de la
    selección a los bordes útiles de la plancha (margen) o a la separación
    mínima de las piezas vecinas, si queda a menos de `tol` mm.

    Se trabaja con rectángulos envolventes: si dos rectángulos quedan separados
    por la separación mínima, las piezas también (pueden quedar más lejos si sus
    formas no llenan el rectángulo).
    """
    sel = set(indices)
    p = layout.params
    s = layout.placements[next(iter(sel))].sheet
    x0, y0, x1, y1 = bounds(layout, sel)
    x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
    m, sep = p.margin, p.separation

    # candidatos: (posición objetivo del borde, borde de la selección que se engancha)
    cand_x = [(m, x0), (p.sheet_width - m, x1)]
    cand_y = [(m, y0), (p.sheet_height - m, y1)]
    for i, q in enumerate(layout.placements):
        if i in sel or q.sheet != s:
            continue
        a0, b0, a1, b1 = q.polygon.bounds
        if b0 - sep < y1 and b1 + sep > y0:      # vecina a la izquierda o a la derecha
            cand_x += [(a1 + sep, x0), (a0 - sep, x1)]
        if a0 - sep < x1 and a1 + sep > x0:      # vecina arriba o abajo
            cand_y += [(b1 + sep, y0), (b0 - sep, y1)]

    def best(cands):
        hits = [(abs(t - e), t - e) for t, e in cands if abs(t - e) <= tol]
        return min(hits)[1] if hits else 0.0

    return dx + best(cand_x), dy + best(cand_y)


def allowed_angles(part: Part, params: NestParams) -> list[float] | None:
    return part.rotations if part.rotations is not None else params.angles()


def rotation_warnings(layout: Layout, parts: list[Part], params: NestParams) -> list[tuple[int, str]]:
    """Piezas giradas a mano a un ángulo que no está entre sus rotaciones permitidas."""
    by_name = {p.name: p for p in parts}
    out = []
    for i, q in enumerate(layout.placements):
        part = by_name.get(q.part)
        if part is None:
            continue
        angs = allowed_angles(part, params)
        if angs is None:
            continue
        if not any(abs(((q.angle - a) + 180) % 360 - 180) <= ANGLE_TOL for a in angs):
            allowed = ", ".join(f"{a:g}°" for a in angs)
            out.append((i, f"{q.part} (plancha {q.sheet + 1}) girada {q.angle:g}°, fuera de sus "
                           f"rotaciones permitidas ({allowed})"))
    return out


def transformed(layout: Layout, indices, angle: float = 0.0, dx: float = 0.0, dy: float = 0.0,
                target: tuple[float, float] | None = None) -> Changes:
    """Gira (alrededor del centro de la selección) y después desplaza. Con `target`,
    el desplazamiento lleva la esquina inferior izquierda del rectángulo envolvente
    (ya girado) a ese punto; si no, se desplaza (dx, dy)."""
    tmp = Layout(layout.params, list(layout.placements), layout.sheets)
    changes: Changes = {}
    if angle:
        changes = rotated(tmp, indices, angle)
        apply(tmp, changes)
    if target is not None:
        x0, y0, _, _ = bounds(tmp, indices)
        dx, dy = target[0] - x0, target[1] - y0
    if dx or dy:
        changes.update(moved(tmp, indices, dx, dy))
    return changes


def compact_sheets(layout: Layout) -> tuple[Changes, int]:
    """Quita las planchas vacías renumerando las demás. Devuelve (cambios, nº de planchas)."""
    used = sorted({q.sheet for q in layout.placements})
    remap = {old: new for new, old in enumerate(used)}
    changes = {i: replace(q, sheet=remap[q.sheet]) for i, q in enumerate(layout.placements)
               if remap[q.sheet] != q.sheet}
    return changes, len(used)
