"""Medición del motor: calidad del nesting según tiempo, semilla, rotaciones, nº de copias
y reparto exploración/compactación, con las juntas reales de datos_prueba/.

  python tools/medir_motor.py resultados.jsonl [tanda1|tanda2|todo]

Escribe una línea JSON por cálculo; si se corta, al relanzarlo sigue donde iba.
Los cálculos van uno detrás de otro (en paralelo se falsearían los tiempos).
Resultados del 15/10/2026 y conclusiones: docs/medicion_motor.md.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import spyrrow  # noqa: E402

from nesting2d.engine.nester import nest  # noqa: E402
from nesting2d.engine.params import NestParams  # noqa: E402
from nesting2d.importers.pdf_import import import_pdf  # noqa: E402

DATA = ROOT / "datos_prueba"
QTY = {"RIGCCP0020": 4, "RIGCCP0019": 4, "RIGCCP0018": 4, "RIGCCP0016": 2, "RIGCCP0017": 2}
BASE = {n: import_pdf(DATA / f"{n}.pdf").parts[0] for n in QTY}
OUT = Path(sys.argv[1])
ORIG_CFG = spyrrow.StripPackingConfig


def parts(mult):
    import copy
    out = []
    for n, q in QTY.items():
        p = copy.deepcopy(BASE[n])
        p.quantity = q * mult
        out.append(p)
    return out


def run(exp, mult, T, seed, rot, split=None):
    if split is not None:
        def cfg(**kw):
            total = kw.pop("total_computation_time")
            e = max(1, round(total * split))
            return ORIG_CFG(total_computation_time=None, exploration_time=e, compression_time=max(1, total - e), **kw)
        spyrrow.StripPackingConfig = cfg
    try:
        params = NestParams(time_limit=T, seed=seed, rotation_step=rot)
        t0 = time.monotonic()
        L = nest(parts(mult), params)
        dt = time.monotonic() - t0
    finally:
        spyrrow.StripPackingConfig = ORIG_CFG
    H = params.sheet_height - 2 * params.margin
    used = [L.stats(s)["used_length"] for s in range(L.sheets)]
    area = sum(q.polygon.area for q in L.placements)
    rec = dict(exp=exp, copies=16 * mult, T=T, seed=seed, rot=rot, split=split, sheets=L.sheets,
               used=used, total_used=sum(used), density=area / (sum(used) * H) if used else 0,
               placed=len(L.placements), unplaced=sum(L.unplaced.values()), wall=dt)
    with OUT.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(rec, flush=True)


WHICH = sys.argv[2] if len(sys.argv) > 2 else "todo"
PLAN = []
if WHICH in ("tanda1", "todo"):   # 16 juntas (pedido real), 48 y 96 copias
    for T in (5, 15, 30, 60, 120):
        for s in (1, 2, 3, 4):
            PLAN.append(("tiempo_rot90", 1, T, s, 90.0, None))
    for rot, name in ((45.0, "rot45"), (15.0, "rot15")):
        for T in (15, 30, 60, 120):
            for s in (1, 2, 3):
                PLAN.append((name, 1, T, s, rot, None))
    for T in (30, 120):
        for s in (1, 2, 3):
            PLAN.append(("rotlibre", 1, T, s, None, None))
    for split in (0.5, 0.95):
        for s in (1, 2, 3):
            PLAN.append(("reparto", 1, 60, s, 90.0, split))
    for T in (15, 30, 60, 120):
        for s in (1, 2, 3):
            PLAN.append(("copias48", 3, T, s, 90.0, None))
    for T in (30, 60, 120):
        for s in (1, 2):
            PLAN.append(("copias96", 6, T, s, 90.0, None))
if WHICH in ("tanda2", "todo"):   # rotaciones con 48 copias, y 240 s
    for rot, name in ((45.0, "c48_rot45"), (15.0, "c48_rot15"), (None, "c48_rotlibre")):
        for T in (30, 60, 120):
            for sd in (1, 2):
                PLAN.append((name, 3, T, sd, rot, None))
    for sd in (1, 2):
        PLAN.append(("copias48", 3, 240, sd, 90.0, None))

done = set()
if OUT.exists():
    for line in OUT.read_text().splitlines():
        r = json.loads(line)
        done.add((r["exp"], r["copies"] // 16, r["T"], r["seed"], r["rot"], r["split"]))
print(f"{len(PLAN)} cálculos, ya hechos {len(done)}; estimado "
      f"{sum(p[2] for p in PLAN if p not in done) / 60:.0f} min (sin contar planchas extra)", flush=True)
for p in PLAN:
    if p not in done:
        run(*p)
print("FIN", flush=True)
