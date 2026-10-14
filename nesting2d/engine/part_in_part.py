"""Pieza dentro de pieza: preproceso voraz antes del motor.

spyrrow solo ve el contorno exterior de cada pieza, así que no aprovecha los
huecos. Aquí se rellenan los huecos de las piezas grandes con piezas pequeñas
del mismo pedido; cada contenedor y su contenido viajan al motor como un único
bloque con el contorno exterior del contenedor.

Limitaciones conocidas (ver especificación):
- Voraz: rellena hueco a hueco, sin búsqueda global.
- No recursivo: no mete piezas dentro de piezas que ya están dentro de otra.
- Busca posiciones en una rejilla de `step` mm; con muchas piezas o huecos
  grandes puede ir lento.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import shapely
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

from ..geometry import normalize

FALLBACK_ANGLES = [0.0, 90.0, 180.0, 270.0]  # para piezas con rotación libre


@dataclass
class Inner:
    part: str
    polygon: Polygon   # en coordenadas de la geometría normalizada del contenedor
    angle: float       # giro aplicado a la pieza interior respecto a su geometría original


@dataclass
class Block:
    host: str
    host_geom: Polygon
    inners: list[Inner] = field(default_factory=list)


@dataclass
class PipItem:
    name: str
    geom: Polygon               # normalizada
    quantity: int
    angles: list[float] | None  # None = libre


def _try_fit(container: Polygon, piece: Polygon, angles, others: list[Polygon], sep: float, step: float):
    """Primera posición abajo-izquierda donde `piece` cabe en `container` y queda
    a ≥ sep de `others`. Devuelve (ángulo, polígono colocado) o None."""
    cminx, cminy, cmaxx, cmaxy = container.bounds
    shapely.prepare(container)
    for ang in angles:
        g = normalize(rotate(piece, ang, origin=(0, 0)))
        gw, gh = g.bounds[2], g.bounds[3]
        if gw > cmaxx - cminx or gh > cmaxy - cminy:
            continue
        y = cminy
        while y + gh <= cmaxy + 1e-9:
            x = cminx
            while x + gw <= cmaxx + 1e-9:
                t = translate(g, x, y)
                if container.contains(t) and all(t.distance(o) >= sep - 1e-9 for o in others):
                    return ang, t
                x += step
            y += step
    return None


def fill_holes(items: list[PipItem], sep: float, step: float = 0.5):
    """Devuelve (bloques, cantidades restantes por pieza)."""
    remaining = {it.name: it.quantity for it in items}
    blocks: list[Block] = []

    hosts = sorted((it for it in items if it.geom.interiors),
                   key=lambda it: -Polygon(it.geom.exterior).area)
    for host in hosts:
        containers = []
        for ring in host.geom.interiors:
            c = Polygon(ring).buffer(-sep)
            if not c.is_empty and c.area > 0:
                containers.extend([c] if isinstance(c, Polygon) else list(c.geoms))
        if not containers:
            continue
        while remaining[host.name] > 0:
            inners: list[Inner] = []
            for cont in containers:
                placed_here: list[Polygon] = []
                for cand in sorted(items, key=lambda it: -it.geom.area):
                    if cand.name == host.name:
                        continue
                    # una pieza no puede ir dentro de otra y a la vez contener otras en este bloque
                    while remaining[cand.name] > 0 and cand.geom.area <= cont.area:
                        angs = cand.angles if cand.angles is not None else FALLBACK_ANGLES
                        r = _try_fit(cont, cand.geom, angs, placed_here, sep, step)
                        if r is None:
                            break
                        ang, poly = r
                        placed_here.append(poly)
                        inners.append(Inner(cand.name, poly, ang))
                        remaining[cand.name] -= 1
            if not inners:
                break  # si no cabe nada en este contenedor, tampoco en sus copias
            blocks.append(Block(host.name, host.geom, inners))
            remaining[host.name] -= 1
    return blocks, remaining
