"""Ajuste de arcos a contornos discretizados, para exportar DXF con arcos reales.

Las piezas se guardan como polígonos (las curvas, en segmentos de ≤ 0,5 mm).
Para el DXF "con arcos" cada anillo se convierte en:
- un CÍRCULO si el anillo entero es una circunferencia, o
- una polilínea con abombamiento ("bulge", la forma estándar de arcos en
  LWPOLYLINE): tramos rectos y tramos de arco, sin desviarse del anillo
  original más de `tol` mm.

Opción de la exportación (Mikel, 15/10/2026); por defecto se sigue exportando
en segmentos hasta saber qué acepta la máquina del proveedor.
"""
from __future__ import annotations

import math

import numpy as np

DEFAULT_TOL = 0.05     # mm: desviación máxima respecto al contorno original
MIN_ARC_POINTS = 4     # un arco tiene que cubrir al menos 3 segmentos
MAX_RADIUS = 1e4       # por encima, se trata como recta


def _circumcenter(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy


def _arc_ok(P: np.ndarray, i: int, j: int, tol: float):
    """¿Los puntos i..j caben en un arco (círculo por i, medio y j) con desviación ≤ tol,
    girando siempre en el mismo sentido? Devuelve (centro, radio, sentido) o None."""
    m = (i + j) // 2
    c = _circumcenter(P[i], P[m], P[j])
    if c is None:
        return None
    r = math.dist(c, P[i])
    if r > MAX_RADIUS:
        return None
    seg = P[i:j + 1]
    if np.abs(np.hypot(seg[:, 0] - c[0], seg[:, 1] - c[1]) - r).max() > tol:
        return None
    # mismo sentido de giro en todos los vértices y en el centro de cada segmento
    d = np.diff(seg, axis=0)
    turn = d[:-1, 0] * d[1:, 1] - d[:-1, 1] * d[1:, 0]
    if not (np.all(turn > 0) or np.all(turn < 0)):
        return None
    mids = (seg[:-1] + seg[1:]) / 2
    if np.abs(np.hypot(mids[:, 0] - c[0], mids[:, 1] - c[1]) - r).max() > tol:
        return None
    return c, r, 1 if turn[0] > 0 else -1


def _bulge(a, b, c, ccw: int) -> float:
    """Abombamiento del arco de a a b con centro c: tan(ángulo / 4), positivo si es antihorario."""
    a0 = math.atan2(a[1] - c[1], a[0] - c[0])
    a1 = math.atan2(b[1] - c[1], b[0] - c[0])
    if ccw > 0:
        theta = (a1 - a0) % (2 * math.pi)
    else:
        theta = -((a0 - a1) % (2 * math.pi))
    return math.tan(theta / 4)


def ring_circle(coords, tol: float = DEFAULT_TOL):
    """(centro, radio) si el anillo entero es una circunferencia; si no, None."""
    P = np.asarray(coords, dtype=float)
    if np.allclose(P[0], P[-1]):
        P = P[:-1]
    if len(P) < 8:
        return None
    x, y = P[:, 0], P[:, 1]
    A = np.c_[x, y, np.ones_like(x)]
    a, b, c = np.linalg.lstsq(A, -(x * x + y * y), rcond=None)[0]
    cx, cy = -a / 2, -b / 2
    r2 = cx * cx + cy * cy - c
    if r2 <= 0:
        return None
    r = math.sqrt(r2)
    if np.abs(np.hypot(x - cx, y - cy) - r).max() > tol:
        return None
    # que los segmentos tampoco se aparten (anillo con pocos puntos)
    Q = np.vstack([P, P[:1]])
    mids = (Q[:-1] + Q[1:]) / 2
    if np.abs(np.hypot(mids[:, 0] - cx, mids[:, 1] - cy) - r).max() > tol:
        return None
    return (float(cx), float(cy)), r


def ring_to_bulges(coords, tol: float = DEFAULT_TOL) -> list[tuple[float, float, float]]:
    """Anillo cerrado -> vértices (x, y, bulge) de una LWPOLYLINE cerrada."""
    P = np.asarray(coords, dtype=float)
    if np.allclose(P[0], P[-1]):
        P = P[:-1]
    n = len(P)
    if n < 3:
        return [(float(x), float(y), 0.0) for x, y in P]
    # Empezar donde seguro que no hay un arco a medias (si no, al cerrar el anillo el
    # arco queda partido): al principio del segmento más largo si es claramente una
    # recta (las curvas vienen en segmentos cortos); si no, en la esquina más marcada.
    nxt = np.roll(P, -1, axis=0)
    seg_len = np.hypot(*(nxt - P).T)
    if seg_len.max() > 3 * np.median(seg_len):
        start = int(seg_len.argmax())
    else:
        prev = np.roll(P, 1, axis=0)
        v1, v2 = P - prev, nxt - P
        ang = np.abs(np.arctan2(v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0], (v1 * v2).sum(axis=1)))
        start = int(ang.argmax())
    P = np.vstack([np.roll(P, -start, axis=0), np.roll(P, -start, axis=0)[:1]])   # cerrado
    out: list[tuple[float, float, float]] = []
    i, last = 0, len(P) - 1
    while i < last:
        best = None
        j = i + MIN_ARC_POINTS - 1
        while j <= last:
            fit = _arc_ok(P, i, j, tol)
            if fit is None:
                break
            best = (j, fit)
            j += 1
        if best is not None:
            j, (c, r, sense) = best
            out.append((float(P[i][0]), float(P[i][1]), _bulge(P[i], P[j], c, sense)))
            i = j
            continue
        # tramo recto: juntar los puntos alineados dentro de la tolerancia
        j = i + 1
        while j + 1 <= last:
            # parar donde empieza un arco: si no, la recta se come su primer punto
            if j + MIN_ARC_POINTS - 1 <= last and _arc_ok(P, j, j + MIN_ARC_POINTS - 1, tol) is not None:
                break
            a, b = P[i], P[j + 1]
            d = math.dist(a, b)
            seg = P[i:j + 2]
            dev = np.abs((b[0] - a[0]) * (seg[:, 1] - a[1]) - (b[1] - a[1]) * (seg[:, 0] - a[0])) / d if d else np.inf
            if np.max(dev) > tol:
                break
            j += 1
        out.append((float(P[i][0]), float(P[i][1]), 0.0))
        i = j
    return out


def bulges_to_points(verts, max_seg: float = 0.2) -> list[tuple[float, float]]:
    """Vuelve a discretizar una polilínea con abombamientos (para comprobar el ajuste)."""
    pts = []
    n = len(verts)
    for k in range(n):
        x0, y0, bulge = verts[k]
        x1, y1, _ = verts[(k + 1) % n]
        pts.append((x0, y0))
        if abs(bulge) < 1e-12:
            continue
        theta = 4 * math.atan(bulge)
        chord = math.hypot(x1 - x0, y1 - y0)
        r = chord / (2 * math.sin(abs(theta) / 2))
        # centro: a la izquierda de la cuerda si el arco es antihorario
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        h = r * math.cos(abs(theta) / 2)
        ux, uy = (x1 - x0) / chord, (y1 - y0) / chord
        sign = 1 if theta > 0 else -1
        if abs(theta) > math.pi:
            h = -h
        cx, cy = mx - sign * uy * h, my + sign * ux * h
        a0 = math.atan2(y0 - cy, x0 - cx)
        steps = max(2, int(abs(theta) * r / max_seg))
        for s in range(1, steps):
            a = a0 + theta * s / steps
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts
