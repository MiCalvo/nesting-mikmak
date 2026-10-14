"""Pruebas de la interfaz (fase 2), sin pantalla (QT_QPA_PLATFORM=offscreen).

Se saltan si PySide6 no está instalado (pip install -e .[gui]).
"""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QPoint, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from shapely.geometry import box  # noqa: E402

from nesting2d import project  # noqa: E402
from nesting2d.engine.nester import nest  # noqa: E402
from nesting2d.engine.params import NestParams  # noqa: E402
from nesting2d.geometry import Part  # noqa: E402

from .conftest import DATA, QTY  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from nesting2d.gui import gc_guard
    app = QApplication.instance() or QApplication([])
    gc_guard.install(app)   # como en la app real: sin esto, el GC en otro hilo tumba Qt
    app.setOrganizationName("nesting2d-pruebas")
    app.setApplicationName("pruebas")
    yield app
    QSettings().clear()


def wait_until(app, cond, timeout=60):
    t0 = time.time()
    while not cond():
        assert time.time() - t0 < timeout, "tiempo de espera agotado"
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        time.sleep(0.01)


@pytest.fixture
def window(qapp):
    from nesting2d.gui.main_window import MainWindow
    w = MainWindow()
    w._warn = w.log   # sin pantalla nadie cerraría los avisos modales
    w.resize(1200, 800)
    w.show()
    yield w
    w.modified = False
    w.close()


def import_gaskets(app, w):
    w.import_files([str(DATA / f"{n}.pdf") for n in QTY])
    wait_until(app, lambda: w.import_worker is None)
    for i, p in enumerate(w.model.parts):
        w.model.set_quantity([i], QTY[p.name])


# --- motor: progreso y parada -------------------------------------------------------
def test_nest_reports_progress_and_can_stop(gaskets):
    calls = []
    layout = nest(gaskets, NestParams(time_limit=2, seed=1, part_in_part=False),
                  on_sheet=lambda s, drain: calls.append((s, drain)))
    assert [s for s, _ in calls] == [0]
    assert layout.sheets == 1
    stopped = nest(gaskets, NestParams(time_limit=2, seed=1), should_stop=lambda: True)
    assert stopped.sheets == 0
    assert sum(stopped.unplaced.values()) == 16
    assert "Cálculo detenido por el usuario" in stopped.warnings


# --- enganche para acotar -------------------------------------------------------------
def test_snapping_on_real_gasket():
    from nesting2d.gui.snapping import SnapTargets
    from nesting2d.importers.pdf_import import import_pdf
    g = import_pdf(DATA / "RIGCCP0016.pdf").parts[0].geometry()
    t = SnapTargets(g)
    assert len(t.circles) == 10            # 4 × Ø7 y 6 × Ø10 (el hueco central no es círculo)
    cx, cy, r = t.circles[0]
    s = t.snap(cx + 0.3, cy + 0.3, radius=1.0)
    assert s.kind == "centro" and s.point == pytest.approx((cx, cy))


def test_rounded_frame_is_not_a_circle():
    """La RIGCCP0020 (marco) tiene todos sus vértices en las esquinas: no es un círculo."""
    from nesting2d.gui.snapping import SnapTargets
    from nesting2d.importers.pdf_import import import_pdf
    t = SnapTargets(import_pdf(DATA / "RIGCCP0020.pdf").parts[0].geometry())
    assert t.circles == []


def test_straight_edges_and_snap_priority():
    from nesting2d.gui.snapping import SnapTargets
    t = SnapTargets(box(0, 0, 100, 40))
    assert sorted(round(e.length, 6) for e in t.edges) == [40, 40, 100, 100]
    assert t.edge_at(50, 1, radius=2).length == pytest.approx(100)
    assert t.snap(99.5, 39.5, radius=1).kind == "vertice"
    s = t.snap(50, 0.4, radius=1)
    assert s.kind == "arista" and s.point == pytest.approx((50, 0))
    assert t.snap(50, 20, radius=1) is None


# --- tabla de piezas --------------------------------------------------------------------
def test_parts_model_edits(qapp):
    from nesting2d.gui.parts_model import COL_MIRROR, COL_NAME, COL_QTY, COL_ROT, COL_SCALE, COL_SIZE, PartsModel
    m = PartsModel()
    edits = []
    m.edited.connect(lambda: edits.append(1))
    m.add_parts([Part("A", box(0, 0, 100, 50)), Part("A", box(0, 0, 10, 10))])
    assert [p.name for p in m.parts] == ["A", "A_2"]      # nombres únicos
    assert m.setData(m.index(0, COL_SCALE), 2.0)
    assert m.parts[0].size == pytest.approx((200, 100))
    assert "200" in m.data(m.index(0, COL_SIZE))
    assert m.setData(m.index(0, COL_QTY), 7) and m.parts[0].quantity == 7
    assert m.setData(m.index(0, COL_ROT), [0.0, 180.0]) and m.parts[0].rotations == [0.0, 180.0]
    assert m.data(m.index(0, COL_ROT)) == "0° y 180°"
    assert m.setData(m.index(0, COL_MIRROR), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert m.parts[0].mirror
    assert not m.setData(m.index(1, COL_NAME), "A")           # repetido: rechazado
    assert m.setData(m.index(1, COL_NAME), "B") and m.parts[1].name == "B"
    m.remove_rows([0])
    assert [p.name for p in m.parts] == ["B"]
    assert edits


# --- ventana: importar, acotar, calcular, guardar, exportar --------------------------------
def test_measure_two_points_sets_scale(qapp, window, monkeypatch):
    """Acotar con dos clics los extremos de una arista de 100 mm y decir que mide 50."""
    from nesting2d.gui import parts_tab
    w = window
    w.model.add_parts([Part("caja", box(0, 0, 100, 40), source="a.pdf"),
                       Part("otra", box(0, 0, 10, 10), source="a.pdf")])
    w.parts_tab.select_row(0)
    qapp.processEvents()
    view = w.parts_tab.view

    def click(x, y):
        pos = view.mapFromScene(x, -y)
        for kind in (QMouseEvent.Type.MouseMove, QMouseEvent.Type.MouseButtonPress):
            ev = QMouseEvent(kind, QPoint(pos).toPointF(), QPoint(pos).toPointF(), Qt.MouseButton.LeftButton,
                             Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            (view.mouseMoveEvent if kind == QMouseEvent.Type.MouseMove else view.mousePressEvent)(ev)

    seen = {}

    def fake_exec(dlg):
        seen["measured"] = dlg.measured
        dlg.real.setValue(50.0)
        dlg.apply_all.setChecked(True)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(parts_tab.ScaleDialog, "exec", fake_exec)

    w.parts_tab.b_points.click()
    click(0.3, 0.2)        # cerca de la esquina (0, 0): engancha al vértice
    click(99.8, 0.3)       # cerca de (100, 0)
    assert seen["measured"] == pytest.approx(100.0)
    assert [p.scale for p in w.model.parts] == pytest.approx([0.5, 0.5])   # aplicado a todo el archivo
    assert w.model.parts[0].size == pytest.approx((50, 20))


def test_full_flow(qapp, window, tmp_path):
    w = window
    import_gaskets(qapp, w)
    assert [p.name for p in w.model.parts] == list(QTY)
    w.params_panel.time_limit.setValue(2)
    w.params_panel.fix_seed.setChecked(True)
    w.params_panel.seed.setValue(1)
    w.params_panel.part_in_part.setChecked(False)
    w.start_nest()
    wait_until(qapp, lambda: w.nest_worker is None, timeout=120)
    L = w.layout_
    assert L is not None and L.sheets == 1 and len(L.placements) == 16
    assert w.result_panel.issues == []
    assert not w.result_stale

    # guardar y volver a abrir
    f = tmp_path / "p.json"
    assert w._save_to(f)
    parts, params, lay = project.load(f)
    assert params.time_limit == 2 and params.seed == 1 and not params.part_in_part
    assert len(lay.placements) == 16

    # un cambio deja el resultado obsoleto, y ya no se guarda
    w.model.set_quantity([0], 3)
    assert w.result_stale
    assert w._save_to(f)
    assert project.load(f)[2] is None

    w.modified = False
    assert w.open_project(tmp_path / "p.json")
    assert w.layout_ is None and w.model.parts[0].quantity == 3


def test_export_dxf(qapp, window, tmp_path, monkeypatch, gaskets):
    from PySide6.QtWidgets import QFileDialog

    from nesting2d.importers.dxf_import import import_dxf
    w = window
    layout = nest(gaskets, NestParams(sheet_width=400, sheet_height=300, time_limit=2, seed=1, part_in_part=False))
    assert layout.sheets >= 2
    w.model.set_parts(gaskets)
    w._set_layout(layout, [])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    w.export_dxf()
    files = sorted(tmp_path.glob("plancha_*.dxf"))
    assert len(files) == layout.sheets
    n = sum(len(import_dxf(f, layers=["CORTE"]).parts) for f in files)
    assert n == 16


def test_result_free_rect():
    from nesting2d.gui.result_view import free_rect
    from nesting2d.engine.nester import Layout, Placement
    for side, expect in [("izquierda", (65, 0, 1200, 1000)), ("abajo", (0, 65, 1200, 1000))]:
        L = Layout(NestParams(compact_side=side), [Placement("a", 0, 0, box(5, 5, 60, 60))], sheets=1)
        assert free_rect(L, 0) == pytest.approx(expect)
        st = L.stats(0)
        fw, fh = st["free"]
        x0, y0, x1, y1 = free_rect(L, 0)
        assert (x1 - x0, y1 - y0) == pytest.approx((fw, fh))   # misma zona que Layout.stats


def test_stop_after_current_sheet(qapp, window):
    w = window
    import_gaskets(qapp, w)
    w.params_panel.width.setValue(400)
    w.params_panel.height.setValue(300)
    w.params_panel.time_limit.setValue(2)
    w.params_panel.part_in_part.setChecked(False)
    w.start_nest()
    w.stop_nest()          # se pide antes de que acabe la primera plancha
    wait_until(qapp, lambda: w.nest_worker is None, timeout=120)
    L = w.layout_
    assert L.sheets <= 1
    assert sum(L.unplaced.values()) + len(L.placements) == 16
    assert "Cálculo detenido por el usuario" in L.warnings or L.sheets == 1 and not L.unplaced


def test_import_multiview_drawing_with_quantity_zero(qapp, window, monkeypatch):
    w = window
    monkeypatch.setattr(w, "_ask_multi_qty", lambda name, n: 0)
    w.import_files([str(DATA / "RIG23P0054_plano_varias_vistas.pdf")])
    wait_until(qapp, lambda: w.import_worker is None, timeout=120)
    parts = w.model.parts
    assert len(parts) > 10
    assert all(p.quantity == 0 for p in parts)
    assert len({p.name for p in parts}) == len(parts)
