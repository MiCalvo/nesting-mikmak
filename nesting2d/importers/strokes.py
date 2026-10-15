"""Trazos (aristas) de un plano: clasificación, cadenas y círculos (sin Qt).

Para la selección de contornos "por aristas": la pieza se define eligiendo
aristas en vez de zonas, así las cotas, ejes y referencias que crucen la pieza
no la parten (solo cuentan las aristas elegidas).

- Un trazo es una polilínea del archivo (un subtrazado de PDF o una entidad
  DXF), en mm.
- Se clasifica como recta, arco, círculo o polilínea (mezcla). Los círculos y
  arcos llevan centro y radio ajustados por mínimos cuadrados.
- Cadena: trazos unidos por sus EXTREMOS (no por cruces) a través de nudos con
  exactamente dos extremos; se corta en las bifurcaciones. Un eje que cruza un
  círculo no lo parte, porque el cruce no es un extremo.
- Círculos completos: trazos cerrados que son círculos, o grupos de arcos con el
  mismo centro y radio que suman 360° (NX parte los círculos grandes en arcos).

Medido con los PDF de Mikel (15/10/2026): los taladros de las juntas ajustan a
una circunferencia con residuo < 0,001 mm; en el plano A0, los círculos grandes
vienen partidos en arcos.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon

from .contours import ImportOptions, closed_faces, parts_from_faces, snap_endpoints

KINDS = ("recta", "arco", "circulo", "polilinea")
MAX_SEGMENT_SPAN = 25.0   # grados que puede abarcar un segmento de una curva discretizada


def circle_tol(r: float) -> float:
    """Desviación admitida para tomar un trazo por circunferencia (mm)."""
    return max(0.01, 0.001 * r)


def fit_circle(pts: np.ndarray) -> tuple[float, float, float, float]:
    """Circunferencia por mínimos cuadrados (método de Kåsa): (cx, cy, r, residuo máx)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.c_[x, y, np.ones_like(x)]
    b = -(x * x + y * y)
    a, bb, c = np.linalg.lstsq(A, b, rcond=None)[0]
    cx, cy = -a / 2, -bb / 2
    r2 = cx * cx + cy * cy - c
    if r2 <= 0:
        return cx, cy, 0.0, math.inf
    r = math.sqrt(r2)
    return float(cx), float(cy), r, float(np.abs(np.hypot(x - cx, y - cy) - r).max())


@dataclass
class Stroke:
    pts: np.ndarray                    # (n, 2) en mm
    kind: str = "polilinea"
    center: tuple[float, float] | None = None
    radius: float | None = None
    sweep: float = 0.0                 # grados recorridos (arcos y círculos)
    length: float = 0.0
    closed: bool = False

    @property
    def diameter(self) -> float | None:
        return None if self.radius is None else 2 * self.radius

    def describe(self) -> str:
        if self.kind == "circulo":
            return f"círculo Ø{self.diameter:.2f} mm".replace(".", ",")
        if self.kind == "arco":
            return f"arco R{self.radius:.2f} mm, {self.sweep:.0f}°".replace(".", ",")
        if self.kind == "recta":
            return f"recta de {self.length:.2f} mm".replace(".", ",")
        return f"trazo de {self.length:.2f} mm".replace(".", ",")


def classify(pts, join_tol: float = 0.01) -> Stroke:
    P = np.asarray(pts, dtype=float)
    s = Stroke(P)
    if len(P) < 2:
        return s
    seg = np.hypot(*np.diff(P, axis=0).T)
    s.length = float(seg.sum())
    s.closed = len(P) > 3 and math.dist(P[0], P[-1]) <= join_tol
    if not s.closed:
        a, b = P[0], P[-1]
        d = math.dist(a, b)
        if d > 0:
            # distancia de cada punto a la recta a-b
            ux, uy = b - a
            dev = np.abs(ux * (P[:, 1] - a[1]) - uy * (P[:, 0] - a[0])) / d   # np.cross 2D ya no vale en NumPy 2
            if dev.max() <= 0.01:
                s.kind = "recta"
                return s
    if len(P) >= 5:
        cx, cy, r, res = fit_circle(P)
        # Los vértices de cualquier polígono regular (un rectángulo, un hexágono) están
        # sobre su circunferencia circunscrita: lo que distingue una curva discretizada
        # es que cada segmento abarca un ángulo pequeño (las Bézier de los PDF salen
        # en ≥ 4 segmentos por cuarto de círculo: ≤ 22,5°).
        max_span = math.degrees(2 * math.asin(min(1.0, float(seg.max()) / (2 * r)))) if r > 0 else 180.0
        if r > 0 and res <= circle_tol(r) and max_span <= MAX_SEGMENT_SPAN and r < 1e5:
            ang = np.unwrap(np.arctan2(P[:, 1] - cy, P[:, 0] - cx))
            sweep = abs(math.degrees(ang[-1] - ang[0]))
            s.center, s.radius = (cx, cy), r
            if s.closed and sweep >= 350:
                s.kind, s.sweep = "circulo", 360.0
            elif not s.closed and sweep >= 3:
                s.kind, s.sweep = "arco", sweep
    return s


@dataclass
class Circle:
    """Círculo completo: un trazo cerrado o varios arcos que suman 360°."""
    center: tuple[float, float]
    radius: float
    strokes: list[int] = field(default_factory=list)

    @property
    def diameter(self) -> float:
        return 2 * self.radius


class StrokeSet:
    """Trazos de una página con su grafo de extremos."""

    def __init__(self, polylines: list, opts: ImportOptions | None = None):
        self.opts = opts or ImportOptions()
        snapped = [pl for pl in snap_endpoints(polylines, self.opts.join_tolerance) if len(pl) >= 2]
        self.strokes = [classify(pl, self.opts.join_tolerance) for pl in snapped]
        self.strokes = [s for s in self.strokes if s.length > 0]
        self.lines = [LineString(s.pts) for s in self.strokes]
        self.tree = STRtree(self.lines) if self.lines else None
        # nudos: extremos (ya unidos por snap_endpoints) -> trazos que llegan
        self.ends: list[tuple[tuple, tuple]] = []
        self.node_strokes: dict[tuple, list[int]] = {}
        for i, s in enumerate(self.strokes):
            a, b = tuple(s.pts[0]), tuple(s.pts[-1])
            self.ends.append((a, b))
            self.node_strokes.setdefault(a, []).append(i)
            self.node_strokes.setdefault(b, []).append(i)   # cerrado: dos veces el mismo nudo
        self.circles = self._find_circles()

    def __len__(self):
        return len(self.strokes)

    # --- búsqueda -----------------------------------------------------------------
    def nearest(self, x: float, y: float, tol: float) -> int | None:
        if self.tree is None:
            return None
        p = Point(x, y)
        cands = [(self.lines[j].distance(p), int(j)) for j in self.tree.query(p.buffer(tol))]
        cands = [(d, j) for d, j in cands if d <= tol]
        if not cands:
            return None
        # empate (aristas que se tocan en el punto, p. ej. una recta que llega a un
        # círculo): preferir las de un círculo o arco y, después, la más larga
        dmin = min(d for d, _ in cands)
        close = [j for d, j in cands if d <= dmin + 0.25 * tol]
        return min(close, key=lambda j: (self.strokes[j].kind not in ("circulo", "arco"), -self.strokes[j].length))

    def in_rect(self, x0, y0, x1, y1, window: bool) -> list[int]:
        """Trazos enteros dentro (ventana) o que tocan (captura) el rectángulo."""
        if self.tree is None:
            return []
        from shapely.geometry import box
        r = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        cands = [int(i) for i in self.tree.query(r)]
        return [i for i in cands if (r.contains(self.lines[i]) if window else r.intersects(self.lines[i]))]

    # --- cadenas ---------------------------------------------------------------------
    def chain(self, i: int) -> list[int]:
        """Trazos unidos a i por extremos, a través de nudos con exactamente dos extremos."""
        out = {i}
        for start_node in self.ends[i]:
            node, prev = start_node, i
            while len(self.node_strokes.get(node, [])) == 2:
                a, b = self.node_strokes[node]
                nxt = b if a == prev else a
                if nxt in out:      # se ha cerrado el contorno (o es un trazo cerrado)
                    break
                out.add(nxt)
                e0, e1 = self.ends[nxt]
                node, prev = (e1 if e0 == node else e0), nxt
        return sorted(out)

    def open_ends(self, idx) -> list[tuple[float, float]]:
        """Extremos que solo toca un trazo de la selección: huecos que impiden cerrar."""
        count: dict[tuple, int] = {}
        for i in idx:
            for n in self.ends[i]:
                count[n] = count.get(n, 0) + 1
        return [n for n, c in count.items() if c % 2 == 1]

    # --- círculos ---------------------------------------------------------------------
    def _find_circles(self) -> list[Circle]:
        out: list[Circle] = []
        arcs: list[int] = []
        for i, s in enumerate(self.strokes):
            if s.kind == "circulo":
                out.append(Circle(s.center, s.radius, [i]))
            elif s.kind == "arco":
                arcs.append(i)
        # agrupar arcos con el mismo centro y radio; completos si suman ~360°
        used = set()
        for k, i in enumerate(arcs):
            if i in used:
                continue
            si = self.strokes[i]
            tol = circle_tol(si.radius) * 5
            group = [i]
            for j in arcs[k + 1:]:
                sj = self.strokes[j]
                if j in used:
                    continue
                if (abs(sj.radius - si.radius) <= tol and math.dist(sj.center, si.center) <= tol):
                    group.append(j)
            total = sum(self.strokes[j].sweep for j in group)
            if 355 <= total <= 365:
                used.update(group)
                r = float(np.mean([self.strokes[j].radius for j in group]))
                cx = float(np.mean([self.strokes[j].center[0] for j in group]))
                cy = float(np.mean([self.strokes[j].center[1] for j in group]))
                out.append(Circle((cx, cy), r, group))
        return out

    def circle_of_stroke(self, i: int) -> Circle | None:
        for c in self.circles:
            if i in c.strokes:
                return c
        return None

    def same_diameter(self, i: int) -> list[Circle]:
        """Círculos completos con el mismo Ø que el del trazo i (si i es parte de uno)."""
        c = self.circle_of_stroke(i)
        if c is None:
            return []
        tol = max(0.02, 0.002 * c.radius)
        return [o for o in self.circles if abs(o.radius - c.radius) <= tol]

    def circles_inside(self, outer: Polygon) -> list[Circle]:
        """Círculos completos enteramente dentro del contorno dado (candidatos a taladros)."""
        out = []
        for c in self.circles:
            disk = Point(c.center).buffer(c.radius, 32)
            if outer.contains(disk) and not disk.buffer(-1e-6).contains(Polygon(outer.exterior).boundary):
                out.append(c)
        return out

    # --- piezas ------------------------------------------------------------------------
    def parts_from(self, idx) -> list[Polygon]:
        """Piezas que forman SOLO los trazos dados (regla par-impar entre ellos)."""
        pls = [self.strokes[i].pts.tolist() for i in idx]
        return parts_from_faces(closed_faces(pls, self.opts))

    def outer_of(self, idx) -> Polygon | None:
        """Mayor contorno cerrado que forman los trazos dados (sin huecos)."""
        faces = closed_faces([self.strokes[i].pts.tolist() for i in idx], self.opts)
        if not faces:
            return None
        from shapely.ops import unary_union
        merged = unary_union([Polygon(f.exterior) for f in faces])
        geoms = getattr(merged, "geoms", [merged])
        return max((Polygon(g.exterior) for g in geoms if isinstance(g, Polygon)), key=lambda g: g.area, default=None)
