"""Nesting sobre planchas usando spyrrow (MIT) como motor.

spyrrow resuelve "strip packing": una tira de alto fijo y largo libre, que
minimiza el largo. Encima de él, esta capa añade:

- Márgenes al borde: la tira es la plancha menos 2 × margen.
- Lado de compactación: se resuelve en un "marco de tira" y luego se gira el
  resultado a la plancha (0° = izquierda, 90° = abajo, 180° = derecha,
  270° = arriba). Los ángulos permitidos se corrigen con ese giro para que las
  piezas con rotación restringida sigan respetándola en la plancha.
- Pieza dentro de pieza (preproceso, `part_in_part.py`).
- Varias planchas: si el largo resultante no cabe, las piezas que no caben
  pasan a la siguiente plancha y se recalculan. PRIMERA VERSIÓN: sencilla,
  puede dejar huecos aprovechables al final de cada plancha.

Convención de spyrrow (comprobada en su documentación): la pieza colocada =
girar la forma original `rotation` grados alrededor de (0, 0) y luego
trasladar `translation`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import spyrrow
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

from ..geometry import Part
from .params import NestParams
from .part_in_part import FALLBACK_ANGLES, Block, PipItem, fill_holes

EPS = 1e-6


@dataclass
class Placement:
    part: str          # nombre de la pieza
    sheet: int         # índice de plancha (0, 1, …)
    angle: float       # giro total aplicado a la geometría de la pieza, en grados
    polygon: Polygon   # geometría colocada, en coordenadas de plancha (mm)
    host: int | None = None  # índice de la Placement contenedora si va dentro de un hueco


@dataclass
class Layout:
    params: NestParams
    placements: list[Placement] = field(default_factory=list)
    sheets: int = 0
    unplaced: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def on_sheet(self, s: int) -> list[Placement]:
        return [p for p in self.placements if p.sheet == s]

    def stats(self, s: int) -> dict:
        """Largo ocupado en la dirección de compactación, zona libre y % de aprovechamiento.

        Zona libre = rectángulo desde el final de las piezas hasta el borde opuesto,
        dentro de los márgenes (largo total − largo ocupado − 2 × margen).
        """
        p = self.params
        W, H, m = p.sheet_width, p.sheet_height, p.margin
        pl = self.on_sheet(s)
        if not pl:
            return {"used_length": 0.0, "free": (W, H), "utilization": 0.0}
        minx = min(q.polygon.bounds[0] for q in pl)
        miny = min(q.polygon.bounds[1] for q in pl)
        maxx = max(q.polygon.bounds[2] for q in pl)
        maxy = max(q.polygon.bounds[3] for q in pl)
        side = p.compact_side
        if side == "izquierda":
            used, total, other = maxx - m, W, H
        elif side == "derecha":
            used, total, other = (W - m) - minx, W, H
        elif side == "abajo":
            used, total, other = maxy - m, H, W
        else:
            used, total, other = (H - m) - miny, H, W
        free_len = max(0.0, total - used - 2 * m)
        free = (free_len, other) if side in ("izquierda", "derecha") else (other, free_len)
        area = sum(q.polygon.area for q in pl)
        return {"used_length": used, "free": free, "utilization": area / (W * H)}


def _frame(params: NestParams):
    """Devuelve (giro R, alto de tira, largo disponible, desplazamiento tras girar)."""
    R = params.frame_rotation()
    We = params.sheet_width - 2 * params.margin
    He = params.sheet_height - 2 * params.margin
    if We <= 0 or He <= 0:
        raise ValueError("El margen es demasiado grande para la plancha")
    if R in (0, 180):
        strip_h, length = He, We
    else:
        strip_h, length = We, He
    offset = {0: (0.0, 0.0), 90: (We, 0.0), 180: (We, He), 270: (0.0, He)}[R]
    return R, strip_h, length, offset


def _to_sheet(g: Polygon, R: int, offset, margin: float) -> Polygon:
    g = rotate(g, R, origin=(0, 0))
    return translate(g, offset[0] + margin, offset[1] + margin)


def _fits_strip(g: Polygon, angles, strip_h: float, length: float) -> bool:
    for a in (angles if angles is not None else FALLBACK_ANGLES):
        minx, miny, maxx, maxy = rotate(g, a, origin=(0, 0)).bounds
        if maxx - minx <= length + EPS and maxy - miny <= strip_h + EPS:
            return True
    return False


def nest(parts: list[Part], params: NestParams) -> Layout:
    layout = Layout(params=params)
    R, strip_h, length, offset = _frame(params)
    default_angles = params.angles()

    # --- piezas a colocar ---------------------------------------------------
    items: list[PipItem] = []
    names = set()
    for p in parts:
        if p.quantity <= 0:
            continue
        if p.name in names:
            raise ValueError(f"Nombre de pieza repetido: {p.name}")
        names.add(p.name)
        angs = p.rotations if p.rotations is not None else default_angles
        g = p.geometry()
        if not _fits_strip(g, angs, strip_h, length):
            layout.unplaced[p.name] = p.quantity
            layout.warnings.append(f"{p.name} no cabe en la plancha con las rotaciones permitidas")
            continue
        items.append(PipItem(p.name, g, p.quantity, angs))
    geom_of = {it.name: it.geom for it in items}
    angles_of = {it.name: it.angles for it in items}

    # --- pieza dentro de pieza ---------------------------------------------
    blocks: list[Block] = []
    remaining = {it.name: it.quantity for it in items}
    if params.part_in_part:
        blocks, remaining = fill_holes(items, params.separation)

    # unidades que entran al motor: id -> (forma, demanda, ángulos, bloque|None)
    units: dict[str, list] = {}
    for i, b in enumerate(blocks):
        units[f"B:{i}"] = [b.host_geom, 1, angles_of[b.host], b]
    for name, q in remaining.items():
        if q > 0:
            units[f"P:{name}"] = [geom_of[name], q, angles_of[name], None]

    def shifted(angs):
        return None if angs is None else sorted({(a - R) % 360 for a in angs})

    # --- planchas -------------------------------------------------------------
    sheet = 0
    while any(u[1] > 0 for u in units.values()):
        if params.max_sheets is not None and sheet >= params.max_sheets:
            break
        sp_items = [spyrrow.Item(uid, list(u[0].exterior.coords)[:-1], demand=u[1],
                                 allowed_orientations=shifted(u[2]))
                    for uid, u in units.items() if u[1] > 0]
        inst = spyrrow.StripPackingInstance(f"plancha{sheet}", strip_height=strip_h, items=sp_items)
        cfg = spyrrow.StripPackingConfig(total_computation_time=int(params.time_limit),
                                         min_items_separation=params.separation or None,
                                         seed=params.seed, num_workers=params.workers)
        sol = inst.solve(cfg)

        accepted = 0
        for pi in sol.placed_items:
            u = units[pi.id]
            strip_poly = translate(rotate(u[0], pi.rotation, origin=(0, 0)), *pi.translation)
            if strip_poly.bounds[2] > length + EPS:
                continue  # no cabe en esta plancha: pasa a la siguiente
            u[1] -= 1
            accepted += 1
            final_angle = (pi.rotation + R) % 360
            block: Block | None = u[3]
            host_name = block.host if block else pi.id[2:]
            layout.placements.append(Placement(host_name, sheet, final_angle,
                                               _to_sheet(strip_poly, R, offset, params.margin)))
            if block:
                host_idx = len(layout.placements) - 1
                for inner in block.inners:
                    g = translate(rotate(inner.polygon, pi.rotation, origin=(0, 0)), *pi.translation)
                    layout.placements.append(Placement(
                        inner.part, sheet, (inner.angle + final_angle) % 360,
                        _to_sheet(g, R, offset, params.margin), host=host_idx))
        if accepted == 0:
            layout.warnings.append("El motor no pudo colocar ninguna pieza en una plancha nueva")
            break
        sheet += 1

    layout.sheets = sheet
    for uid, u in units.items():
        if u[1] > 0:
            names_left = [u[3].host] + [i.part for i in u[3].inners] if u[3] else [uid[2:]]
            for n in names_left:
                layout.unplaced[n] = layout.unplaced.get(n, 0) + u[1]
    if layout.unplaced:
        layout.warnings.append(f"Piezas sin colocar: {layout.unplaced}")
    return layout
