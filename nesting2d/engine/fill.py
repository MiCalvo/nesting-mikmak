"""Modo «rellenar la plancha»: cuántos juegos caben en UNA plancha.

Las cantidades de las piezas se leen como PROPORCIÓN (2, 1, 1 = juegos de 2 de A,
1 de B y 1 de C). Después de los juegos completos, el hueco que quede se puede
rellenar con piezas sueltas de una referencia elegida (`params.fill_with`).
Decidido por Mikel el 15/10/2026.

spyrrow solo resuelve «strip packing» con cantidades fijas: no tiene un modo
«mete el máximo». Por eso se busca el número por tanteo:

1. Estimación inicial por el rectángulo envolvente de cada pieza.
2. Intentos cortos (PROBE_TIME s) con k juegos en una plancha: si caben todas,
   se sube; si no, se baja (primero a saltos, luego por mitades).
3. Lo mismo con las piezas de relleno, con los juegos ya fijados.
4. Colocación final con el perfil de cálculo del proyecto (si da más tiempo que
   los intentos) para dejarla apretada; si el cálculo final no consigue meterlas
   todas, se usa la colocación del intento que sí lo consiguió.

El resultado es «caben AL MENOS N»: que el motor no meta N+1 en el tiempo dado
no demuestra que sea imposible.

Medido con las juntas (1200 × 1000, separación y margen 5, intentos de 10 s):
solo RIGCCP0019 → 79; RIGCCP0019:0018:0016 = 2:1:1 → 21 juegos.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from ..geometry import Part
from .nester import Layout, nest
from .params import NestParams
from .timing import sheet_time

PROBE_TIME = 10          # s por intento
MAX_PROBES = 24          # tope de intentos por búsqueda (juegos, y luego relleno)

# on_probe(juegos, sueltas, ¿caben?, ¿es la colocación final?) tras cada cálculo
ProbeCallback = Callable[[int, int, bool, bool], None]


def _maximize(test, start: int, cap: int, should_stop) -> tuple[int, object]:
    """Mayor n en [0, cap] con test(n) cierto, suponiendo que si n cabe, n−1 también.
    test(n) -> (ok, dato). Devuelve (n, dato de ese n) — dato None si n = 0."""
    if cap <= 0:
        return 0, None
    lo, lo_data, hi = 0, None, cap + 1         # lo: cabe seguro; hi: no cabe seguro
    n = min(cap, max(1, start))
    for _ in range(MAX_PROBES):
        if should_stop is not None and should_stop():
            break
        ok, data = test(n)
        if ok:
            lo, lo_data = n, data
        else:
            hi = n
        if hi - lo <= 1:
            break
        if hi == cap + 1:                       # aún no ha fallado ninguno: subir a saltos
            n = min(cap, max(lo + 1, math.ceil(lo * 1.15)))
        elif lo == 0:                           # aún no ha cabido ninguno: bajar a saltos
            n = max(1, min(hi - 1, math.floor(hi * 0.8)))
        else:
            n = (lo + hi) // 2
    return lo, lo_data


def fill_sheet(parts: list[Part], params: NestParams,
               on_sheet=None, should_stop: Callable[[], bool] | None = None,
               on_probe: ProbeCallback | None = None) -> Layout:
    by_name = {p.name: p for p in parts}
    ratio = {p.name: int(p.quantity) for p in parts if p.quantity > 0}
    filler = params.fill_with if params.fill_with in by_name else None
    W, H, m = params.sheet_width, params.sheet_height, params.margin
    usable = max(0.0, (W - 2 * m) * (H - 2 * m))
    probe_time = PROBE_TIME if params.time_limit is None else min(PROBE_TIME, int(params.time_limit))
    run_params = replace(params, max_sheets=1, mode="cantidades")
    tries = {"n": 0}

    def attempt(k: int, j: int, seconds: int, final: bool = False):
        order = []
        for name, p in by_name.items():
            q = ratio.get(name, 0) * k + (j if name == filler else 0)
            if q > 0:
                order.append(replace(p, quantity=q))
        L = nest(order, replace(run_params, time_limit=seconds), on_sheet=on_sheet)
        ok = not L.unplaced and L.sheets <= 1
        tries["n"] += 1
        if on_probe is not None:
            on_probe(k, j, ok, final)
        return ok, L

    def area(name):          # material (sin huecos): cota superior segura
        return by_name[name].geometry().area

    def env(name):           # rectángulo envolvente: estimación de partida
        return by_name[name].geometry().envelope.area

    # --- 1) juegos completos -----------------------------------------------------
    k, L = 0, None
    if ratio:
        set_area = sum(r * area(n) for n, r in ratio.items())
        set_env = sum(r * env(n) for n, r in ratio.items())
        k, L = _maximize(lambda n: attempt(n, 0, probe_time), int(usable / set_env),
                         int(usable / set_area), should_stop)
    # --- 2) relleno con piezas sueltas ----------------------------------------------
    j = 0
    if filler is not None:
        used = sum(r * area(n) for n, r in ratio.items()) * k
        used_env = sum(r * env(n) for n, r in ratio.items()) * k
        j, Lj = _maximize(lambda n: attempt(k, n, probe_time), int((usable - used_env) / env(filler)),
                          int((usable - used) / area(filler)), should_stop)
        if j:
            L = Lj
    # --- 3) colocación final con el perfil de cálculo ------------------------------------
    stopped = should_stop is not None and should_stop()
    if L is not None and not stopped:
        items = [(ratio.get(n, 0) * k + (j if n == filler else 0),
                  p.rotations if p.rotations is not None else params.angles()) for n, p in by_name.items()]
        final_time = sheet_time(params.time_limit, params.fineness, items)
        if final_time > probe_time:
            ok, Lf = attempt(k, j, final_time, final=True)
            if ok:
                L = Lf
    if L is None:
        L = Layout(params=params)
    L.params = params
    L.unplaced = {}
    L.warnings = [w for w in L.warnings if not w.startswith("Piezas sin colocar")]
    if stopped:
        L.warnings.append("Cálculo detenido por el usuario: el resultado es el mejor encontrado hasta entonces")
    if k == 0 and j == 0:
        L.warnings.append("No cabe ni un juego completo en la plancha")
    L.fill = {"sets": k, "ratio": ratio, "filler": filler, "extra": j, "tries": tries["n"]}
    return L


def describe_fill(fill: dict) -> str:
    """«21 juegos (42 × A, 21 × B, 21 × C) + 3 × A de relleno»."""
    k, ratio = fill.get("sets", 0), fill.get("ratio", {})
    parts = ", ".join(f"{r * k} × {n}" for n, r in ratio.items() if r * k)
    text = f"{k} juego{'s' if k != 1 else ''}" + (f" ({parts})" if parts else "")
    if fill.get("extra"):
        text += f" + {fill['extra']} × {fill['filler']} de relleno"
    return text
