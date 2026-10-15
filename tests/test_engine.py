from shapely.geometry import box

from nesting2d.engine.nester import nest
from nesting2d.engine.params import NestParams
from nesting2d.geometry import Part
from nesting2d.validate import check_layout

FAST = dict(time_limit=3, seed=1)


def test_project_fits_one_sheet_and_is_valid(gaskets):
    layout = nest(gaskets, NestParams(separation=5, margin=5, part_in_part=False, **FAST))
    assert layout.sheets == 1
    assert len(layout.placements) == 16
    assert layout.unplaced == {}
    assert check_layout(layout) == []
    # validado el 14/10/2026: ~170-195 mm de franja según separación y tiempo
    assert layout.stats(0)["used_length"] < 300


def test_restricted_rotation_respected_when_compacting_down(gaskets):
    for p in gaskets:
        p.rotations = [0.0]
    layout = nest(gaskets, NestParams(compact_side="abajo", part_in_part=False, **FAST))
    assert check_layout(layout) == []
    assert {round(q.angle) % 360 for q in layout.placements} == {0}


def test_several_sheets(gaskets):
    layout = nest(gaskets, NestParams(sheet_width=400, sheet_height=300, part_in_part=False, **FAST))
    assert layout.sheets >= 2
    assert layout.unplaced == {}
    assert len(layout.placements) == 16
    assert check_layout(layout) == []


def test_part_in_part_puts_0017_inside_0020_at_2mm(gaskets):
    layout = nest(gaskets, NestParams(separation=2, part_in_part=True, **FAST))
    assert check_layout(layout) == []
    inner = [q for q in layout.placements if q.host is not None]
    assert {q.part for q in inner} == {"RIGCCP0017"}
    assert all(layout.placements[q.host].part == "RIGCCP0020" for q in inner)
    assert len(layout.placements) == 16


def test_part_in_part_nothing_fits_at_3mm(gaskets):
    layout = nest(gaskets, NestParams(separation=3, part_in_part=True, **FAST))
    assert all(q.host is None for q in layout.placements)


def test_too_big_part_is_reported():
    big = Part("enorme", box(0, 0, 2000, 50), quantity=1)
    layout = nest([big], NestParams(**FAST))
    assert layout.unplaced == {"enorme": 1}
    assert layout.placements == []


def test_auto_time_formula():
    from nesting2d.engine.timing import MAX_TIME, auto_time, rotation_factor, sheet_time
    # base: 1,25 s por copia entre 10 y 120 s; finura ×0,25 / ×1 / ×2; entre 5 y MAX_TIME
    assert [auto_time(n) for n in (4, 16, 48, 96, 500)] == [10, 20, 60, 120, 120]
    assert [auto_time(48, 1, f) for f in ("rapido", "normal", "fino")] == [15, 60, 120]
    assert auto_time(16, 1, "rapido") == 5
    assert auto_time(96, 3, "fino") == MAX_TIME == 180
    # rotaciones: nº de orientaciones / 4, entre 1 y 3; libre = 3
    assert [rotation_factor(a) for a in ([0, 180], [0, 90, 180, 270], [i * 45 for i in range(8)],
                                         [i * 15 for i in range(24)], None)] == [1, 1, 2, 3, 3]
    # media ponderada por copias; el tiempo fijo manda
    assert sheet_time(None, "normal", [(24, [0, 90, 180, 270]), (24, None)]) == 120
    assert sheet_time(7, "fino", [(500, None)]) == 7


def test_nest_auto_time_per_sheet(gaskets):
    """Automático: el tiempo de cada plancha sale de lo que queda por colocar."""
    from nesting2d.engine.timing import auto_time
    for p in gaskets:
        p.quantity = 1
    calls = []
    layout = nest(gaskets, NestParams(fineness="rapido", seed=1, part_in_part=False),
                  on_sheet=lambda s, drain: calls.append(drain.time_limit))
    assert layout.sheet_times == calls == [auto_time(5, 1, "rapido")] == [5]


def test_fill_maximize_search():
    from nesting2d.engine.fill import _maximize
    for true_max, start, cap in [(79, 76, 165), (21, 23, 40), (1, 5, 9), (0, 3, 10), (10, 2, 10)]:
        seen = []

        def test(n):
            seen.append(n)
            return n <= true_max, n
        n, data = _maximize(test, start, cap, None)
        assert n == true_max and (data == n or n == 0)
        assert len(seen) <= 12


def test_fill_sheet_sets_and_filler(gaskets):
    """Rellenar: juegos completos en proporción y luego sueltas de la referencia elegida."""
    from collections import Counter

    from nesting2d.engine.fill import describe_fill, fill_sheet
    a, b = gaskets[1], gaskets[3]          # RIGCCP0019 (167 × 92) y RIGCCP0016 (124 × 73)
    a.quantity, b.quantity = 2, 1
    params = NestParams(sheet_width=500, sheet_height=400, time_limit=2, seed=1, part_in_part=False,
                        mode="rellenar", fill_with=b.name)
    probes = []
    L = fill_sheet([a, b], params, on_probe=lambda k, j, ok, final: probes.append((k, j, ok)))
    f = L.fill
    k, j = f["sets"], f["extra"]
    assert k >= 1 and L.sheets == 1 and L.unplaced == {}
    assert Counter(q.part for q in L.placements) == {a.name: 2 * k, b.name: k + j}
    assert check_layout(L) == []
    assert (k, 0, True) in probes and (k + 1, 0, False) in probes          # el siguiente juego no cabe
    assert describe_fill(f).startswith(f"{k} juego")
    assert L.params.mode == "rellenar"
