"""Tiempo de cálculo por plancha: automático (según copias, rotaciones y finura) o fijo.

Fórmula del modo automático (medida el 15/10/2026 con las juntas reales, 4
núcleos; ver docs/medicion_motor.md). Es PROVISIONAL: pocos puntos y un solo
tipo de pieza (marcos casi rectangulares).

  tiempo = base(copias) × factor(rotaciones) × finura, entre MIN_TIME y MAX_TIME

- base: 1,25 s por copia que queda por colocar, entre 10 y 120 s
  (16 copias → 20 s; 48 → 60 s; 96 → 120 s). Con 48 copias, el largo mejoraba
  ≈ 0,7 % cada vez que se doblaba el tiempo hasta 120 s, y nada después.
- factor: nº de orientaciones / 4, entre 1 y 3 (90° → ×1; 45° → ×2; 15° o libre
  → ×3): con más orientaciones el motor necesita más tiempo para el mismo largo.
  Media ponderada por copias si las piezas tienen rotaciones distintas.
- finura: Rápido ×0,25 · Normal ×1 · Fino ×2.
- MAX_TIME = 180 s por plancha (Mikel: prima tener un resultado rápido; para
  tiradas grandes, modo fijo). No entra la complejidad de las piezas (no medida).
"""
from __future__ import annotations

from collections.abc import Iterable

FINENESS = {"rapido": 0.25, "normal": 1.0, "fino": 2.0}
FINENESS_LABELS = {"rapido": "Rápido", "normal": "Normal", "fino": "Fino"}
SECONDS_PER_COPY = 1.25
BASE_MIN, BASE_MAX = 10.0, 120.0
MIN_TIME, MAX_TIME = 5, 180


def rotation_factor(angles: list[float] | None) -> float:
    """Factor de tiempo por las orientaciones permitidas (None = rotación libre)."""
    if angles is None:
        return 3.0
    return min(3.0, max(1.0, len(set(angles)) / 4))


def auto_time(copies: int, factor: float = 1.0, fineness: str = "normal") -> int:
    base = min(BASE_MAX, max(BASE_MIN, SECONDS_PER_COPY * copies))
    t = base * factor * FINENESS.get(fineness, 1.0)
    return int(round(min(MAX_TIME, max(MIN_TIME, t))))


def sheet_time(time_limit: int | None, fineness: str, items: Iterable[tuple[int, list[float] | None]]) -> int:
    """Segundos para una plancha. `items` = (copias, ángulos permitidos) de lo que queda
    por colocar. `time_limit` fijo (int) manda sobre el automático (None)."""
    if time_limit is not None:
        return int(time_limit)
    items = [(n, a) for n, a in items if n > 0]
    copies = sum(n for n, _ in items)
    factor = sum(n * rotation_factor(a) for n, a in items) / copies if copies else 1.0
    return auto_time(copies, factor, fineness)


def describe(time_limit: int | None, fineness: str) -> str:
    """«Automático · Normal» o «Fijo · 30 s»."""
    if time_limit is not None:
        return f"Fijo · {int(time_limit)} s"
    return f"Automático · {FINENESS_LABELS.get(fineness, fineness)}"
