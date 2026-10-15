"""Pruebas de la interfaz (la plataforma Qt la decide conftest.py).

Se saltan si PySide6 no está instalado (pip install -e .[gui]).
"""
import os
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QPoint, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from shapely.geometry import Polygon, box  # noqa: E402

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
    from PySide6.QtCore import QStandardPaths
    QStandardPaths.setTestModeEnabled(True)   # perfiles y ajustes en una carpeta de pruebas
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


# --- fase 3: edición manual del resultado ---------------------------------------------
def _boxes_layout():
    from nesting2d.engine.nester import Layout, Placement
    params = NestParams(sheet_width=300, sheet_height=200, separation=5, margin=5)
    return Layout(params, [Placement("a", 0, 0.0, box(10, 10, 50, 40)),
                           Placement("b", 0, 0.0, box(100, 10, 140, 40))], sheets=1)


def _mouse(view, kind, x, y, mods=Qt.KeyboardModifier.NoModifier, button=Qt.MouseButton.LeftButton):
    from PySide6.QtCore import QPointF
    p = QPointF(view.mapFromScene(x, -y))
    ev = QMouseEvent(kind, p, p, button, button, mods)
    {QMouseEvent.Type.MouseButtonPress: view.mousePressEvent,
     QMouseEvent.Type.MouseMove: view.mouseMoveEvent,
     QMouseEvent.Type.MouseButtonRelease: view.mouseReleaseEvent}[kind](ev)


def _key(view, key, mods=Qt.KeyboardModifier.NoModifier):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods))


def test_manual_editing(qapp, window, tmp_path):
    P = QMouseEvent.Type
    w = window
    w.model.set_parts([Part("a", box(0, 0, 40, 30)), Part("b", box(0, 0, 40, 30))])
    w._set_layout(_boxes_layout(), None)
    w.tabs.setCurrentWidget(w.result_panel)
    qapp.processEvents()
    rp, view = w.result_panel, w.result_panel.view
    L = w.layout_
    rp.snap.setChecked(False)
    tol = view.px_to_mm(1.5)     # el arrastre va en píxeles enteros

    # clic selecciona; arrastrar mueve
    _mouse(view, P.MouseButtonPress, 30, 25)
    assert view.selection == {0}
    _mouse(view, P.MouseMove, 50, 25)
    _mouse(view, P.MouseButtonRelease, 50, 25)
    assert L.placements[0].polygon.bounds[0] == pytest.approx(30, abs=tol)
    x_after_drag = L.placements[0].polygon.bounds[0]

    # flechas: 1 mm, y 10 mm con Mayús
    _key(view, Qt.Key.Key_Right)
    _key(view, Qt.Key.Key_Up, Qt.KeyboardModifier.ShiftModifier)
    b = L.placements[0].polygon.bounds
    assert b[0] == pytest.approx(x_after_drag + 1) and b[1] == pytest.approx(20)

    # girar con R (paso del proyecto, 90°)
    _key(view, Qt.Key.Key_R)
    assert L.placements[0].angle == 90

    # deshacer todo y rehacer uno
    for _ in range(4):
        rp.undo.undo()
    assert L.placements[0].polygon.bounds == pytest.approx((10, 10, 50, 40))
    rp.undo.redo()
    assert L.placements[0].polygon.bounds[0] == pytest.approx(x_after_drag)

    # panel numérico absoluto: esquina inferior izquierda a (200, 100)
    rp.ex.setValue(200)
    rp.ey.setValue(100)
    rp._apply_fields()
    assert L.placements[0].polygon.bounds[:2] == pytest.approx((200, 100))
    # relativo: +20 en X
    rp.mode_rel.setChecked(True)
    rp.ex.setValue(20)
    rp._apply_fields()
    assert L.placements[0].polygon.bounds[0] == pytest.approx(220)
    rp.mode_abs.setChecked(True)

    # validación en vivo: encima de b -> en rojo
    view.set_selection({0})
    rp.ex.setValue(110)
    rp.ey.setValue(15)
    rp._apply_fields()
    assert any(i.kind == "solape" for i in rp.issues)
    assert 0 in view.bad and rp.problems.count() >= 1

    # volver al resultado del motor
    rp.revert_to_engine()
    assert L.placements[0].polygon.bounds == pytest.approx((10, 10, 50, 40))
    assert rp.issues == []

    # ventana de selección (izquierda -> derecha): solo piezas enteras dentro
    _mouse(view, P.MouseButtonPress, 5, 5)
    _mouse(view, P.MouseMove, 60, 45)
    _mouse(view, P.MouseButtonRelease, 60, 45)
    assert view.selection == {0}
    # de derecha a izquierda: las que toca
    _mouse(view, P.MouseButtonPress, 120, 45)
    _mouse(view, P.MouseMove, 40, 30)
    _mouse(view, P.MouseButtonRelease, 40, 30)
    assert view.selection == {0, 1}

    # guardar con ediciones y resultado del motor, y volver a abrir
    rp.undo.undo()   # deshace "volver al motor": queda la pieza encima de b
    f = tmp_path / "e.json"
    assert w._save_to(f)
    w.modified = False
    assert w.open_project(f)
    assert w.layout_.placements[0].polygon.bounds[:2] == pytest.approx((110, 15))
    w.result_panel.revert_to_engine()
    assert w.layout_.placements[0].polygon.bounds == pytest.approx((10, 10, 50, 40))


def test_drag_snaps_to_neighbour_separation(qapp, window):
    P = QMouseEvent.Type
    w = window
    w._set_layout(_boxes_layout(), None)
    w.tabs.setCurrentWidget(w.result_panel)
    qapp.processEvents()
    view, L = w.result_panel.view, w.layout_
    assert w.result_panel.snap.isChecked()
    # b (100..140) arrastrada hacia a (10..50) hasta casi tocar la separación de 5 mm
    _mouse(view, P.MouseButtonPress, 120, 25)
    _mouse(view, P.MouseMove, 120 - 44, 25)
    _mouse(view, P.MouseButtonRelease, 120 - 44, 25)
    assert L.placements[1].polygon.bounds[0] == pytest.approx(55)    # 50 + 5
    assert w.result_panel.issues == []


# --- fase 4: varias planchas, PDF de taller, perfiles, recientes -------------------------
def test_move_to_new_sheet_and_remove_empty(qapp, window):
    w = window
    w._set_layout(_boxes_layout(), None)
    rp, L = w.result_panel, w.layout_
    rp.view.set_selection({1})
    rp.target_sheet.setCurrentIndex(rp.target_sheet.findData(1))    # "Plancha nueva"
    rp._move_to_sheet()
    assert L.sheets == 2 and [q.sheet for q in L.placements] == [0, 1]
    assert "1 piezas" in rp.sheet_combo.itemText(1)
    # vaciar la plancha 1 y eliminarla
    rp.view.set_selection({0})
    rp.target_sheet.setCurrentIndex(rp.target_sheet.findData(1))
    rp._move_to_sheet()
    assert [q.sheet for q in L.placements] == [1, 1]
    assert rp.b_compact.isEnabled()
    rp.remove_empty_sheets()
    assert L.sheets == 1 and [q.sheet for q in L.placements] == [0, 0]
    rp.undo.undo()
    assert L.sheets == 2 and [q.sheet for q in L.placements] == [1, 1]


def test_shop_pdf(qapp, gaskets, tmp_path):
    import pdfplumber

    from nesting2d.exporters.shop_pdf import choose_scale, export_shop_pdf
    assert choose_scale(1200, 1000, 190, 150) == 10
    assert choose_scale(600, 400, 190, 150) == 5
    layout = nest(gaskets, NestParams(sheet_width=400, sheet_height=300, time_limit=2, seed=1,
                                      part_in_part=False, material="Mica", thickness="1,5 mm"))
    f = export_shop_pdf(layout, gaskets, tmp_path / "t.pdf", title="Prueba")
    with pdfplumber.open(f) as pdf:
        assert len(pdf.pages) == 1 + layout.sheets
        first = pdf.pages[0].extract_text()
        for n in QTY:
            assert n in first
        assert "Mica" in first and "1,5 mm" in first
        assert "Plancha 2 de" in pdf.pages[2].extract_text()


def test_export_pdf_from_window(qapp, window, tmp_path, monkeypatch, gaskets):
    from PySide6.QtWidgets import QFileDialog
    w = window
    layout = nest(gaskets, NestParams(time_limit=2, seed=1, part_in_part=False))
    w.model.set_parts(gaskets)
    w._set_layout(layout, [])
    target = tmp_path / "salida.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    w.export_pdf()
    assert target.exists() and target.stat().st_size > 1000


def test_profiles_roundtrip_and_new_project(qapp, window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QInputDialog

    from nesting2d.gui import params_panel
    from nesting2d.profiles import Profile, load_profiles, save_profiles
    path = tmp_path / "perfiles.json"
    monkeypatch.setattr(params_panel, "profiles_path", lambda: path)
    assert load_profiles(path)[0].name.startswith("Mica 1200")      # de serie si no hay archivo
    save_profiles(path, [Profile("Vinilo 610", 610, 2000, 2, 3, "Vinilo")])
    pp = window.params_panel
    pp.reload_profiles()
    assert pp.profile_combo.currentText() == "Vinilo 610"
    pp.apply_selected_profile()
    p = pp.params()
    assert (p.sheet_width, p.sheet_height, p.separation, p.margin, p.material) == (610, 2000, 2, 3, "Vinilo")
    # guardar el proyecto actual como perfil nuevo
    pp.width.setValue(1500)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Mica grande", True))
    pp.save_as_profile()
    assert [x.name for x in load_profiles(path)] == ["Vinilo 610", "Mica grande"]
    # proyecto nuevo con perfil
    window.modified = False
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("Mica grande", True))
    window.new_project()
    assert window.params_panel.params().sheet_width == 1500


def test_recent_files(qapp, window, tmp_path):
    w = window
    f = tmp_path / "r.json"
    assert w._save_to(f)
    assert w._recent()[0] == str(f.resolve())


# --- fase 5: selección manual de contornos y capas DXF --------------------------------
def _framed_dxf(path):
    import ezdxf
    doc = ezdxf.new("R2010")
    doc.units = 4  # mm
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (400, 0), (400, 300), (0, 300)], close=True, dxfattribs={"layer": "MARCO"})
    msp.add_lwpolyline([(50, 50), (150, 50), (150, 110), (50, 110)], close=True, dxfattribs={"layer": "CORTE"})
    msp.add_circle((100, 80), 10, dxfattribs={"layer": "CORTE"})
    msp.add_lwpolyline([(200, 50), (260, 50), (260, 90), (200, 90)], close=True, dxfattribs={"layer": "CORTE"})
    doc.saveas(path)
    return path


def test_contour_dialog_builds_parts_ignoring_frame(qapp, tmp_path):
    from nesting2d.gui.contour_dialog import ContourDialog
    from nesting2d.importers.contours import ImportOptions
    f = _framed_dxf(tmp_path / "plano.dxf")
    dlg = ContourDialog(str(f), ImportOptions())
    wait_until(qapp, lambda: dlg.faces)
    assert len(dlg.faces[1]) == 4               # marco, placa, taladro, placa pequeña
    # ventana alrededor de la primera placa: entran placa y taladro, pero el taladro
    # queda como hueco (par-impar entre lo de dentro de la ventana)
    dlg._band(40, 40, 160, 120, True, False)
    assert len(dlg.selected) == 1
    dlg.create_part()
    # clic dentro de la placa pequeña, y luego otra vez para quitarla y volver a ponerla
    dlg._clicked(230, 70)
    dlg._clicked(230, 70)
    assert dlg.selected == set()
    dlg._clicked(230, 70)
    dlg.create_part()
    parts = dlg.result_parts()
    assert [p.size for p in parts] == [pytest.approx((100, 60)), pytest.approx((60, 40))]
    assert len(parts[0].shape.interiors) == 1    # el taladro es hueco; el marco no cuenta
    # deshacer la segunda pieza libera sus contornos
    dlg.list.setCurrentRow(1)
    dlg._delete_part()
    assert len(dlg.result_parts()) == 1
    dlg.reject()


def test_contour_dialog_click_selects_innermost(qapp, tmp_path):
    from nesting2d.gui.contour_dialog import ContourDialog
    from nesting2d.importers.contours import ImportOptions
    f = _framed_dxf(tmp_path / "plano.dxf")
    dlg = ContourDialog(str(f), ImportOptions())
    wait_until(qapp, lambda: dlg.faces)
    faces = dlg.faces[1]
    dlg._clicked(100, 80)                        # dentro del taladro
    (i,) = dlg.selected
    assert faces[i].area == pytest.approx(3.1416 * 100, rel=0.01)
    # placa + taladro marcados a mano como material: el taladro deja de ser hueco
    dlg._clicked(60, 60)
    dlg.create_part()
    (p,) = dlg.result_parts()
    assert p.size == pytest.approx((100, 60)) and len(p.shape.interiors) == 0
    dlg.reject()


def test_contour_dialog_several_pieces_keep_largest(qapp, tmp_path):
    from nesting2d.gui.contour_dialog import ContourDialog
    from nesting2d.importers.contours import ImportOptions
    f = _framed_dxf(tmp_path / "plano.dxf")
    dlg = ContourDialog(str(f), ImportOptions())
    wait_until(qapp, lambda: dlg.faces)
    dlg._confirm_many = lambda n: "largest"
    dlg._band(40, 40, 270, 120, True, False)     # las dos placas
    dlg.create_part()
    (p,) = dlg.result_parts()
    assert p.size == pytest.approx((100, 60))
    dlg.reject()


def test_dxf_import_asks_layers_and_defaults_to_corte(qapp, window, monkeypatch, tmp_path):
    from nesting2d.gui.contour_dialog import LayerDialog
    w = window
    f = _framed_dxf(tmp_path / "plano.dxf")
    seen = {}

    def fake_exec(dlg):
        seen["layers"] = dlg.layers()
        return LayerDialog.DialogCode.Accepted
    monkeypatch.setattr(LayerDialog, "exec", fake_exec)
    monkeypatch.setattr(w, "_ask_multi_qty", lambda name, n: 1)
    w.import_files([str(f)])
    wait_until(qapp, lambda: w.import_worker is None)
    assert seen["layers"] == ["CORTE"]
    assert sorted(p.size for p in w.model.parts) == [pytest.approx((60, 40)), pytest.approx((100, 60))]


def test_contour_dialog_shift_click_fixes_all_counterbores(qapp, tmp_path):
    """Taladros dibujados con dos circunferencias (avellanado): la ventana deja un
    islote dentro de cada uno. Para cortar el taladro pasante, las coronas son
    material y los islotes hueco: dos Mayús+clic los arreglan todos."""
    import ezdxf

    from nesting2d.gui.contour_dialog import ContourDialog
    from nesting2d.importers.contours import ImportOptions
    doc = ezdxf.new("R2010")
    doc.units = 4
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (120, 0), (120, 40), (0, 40)], close=True)
    for x in (20, 60, 100):
        msp.add_circle((x, 20), 8)     # avellanado
        msp.add_circle((x, 20), 4)     # taladro pasante
    doc.saveas(tmp_path / "av.dxf")
    dlg = ContourDialog(str(tmp_path / "av.dxf"), ImportOptions())
    wait_until(qapp, lambda: dlg.faces)
    dlg._band(-5, -5, 125, 45, True, False)
    assert len(dlg.selected) == 4                 # placa + 3 islotes
    dlg._clicked(26, 20, True)                    # Mayús+clic en una corona: las 3 pasan a material
    assert len(dlg.selected) == 7
    dlg._clicked(20, 20, True)                    # Mayús+clic en un islote: los 3 quedan como hueco
    assert len(dlg.selected) == 4
    dlg.create_part()
    (p,) = dlg.result_parts()
    assert len(p.shape.interiors) == 3
    assert all(abs(Polygon(r).area - 3.1416 * 16) < 1 for r in p.shape.interiors)   # huecos de Ø8
    dlg.reject()


# --- imágenes (capturas y escaneos) ---------------------------------------------------
def _png(tmp_path, name="captura.png", dpi=None):
    pytest.importorskip("cv2")
    from PIL import Image

    from tests.test_image import drawing
    path = tmp_path / name
    Image.fromarray(drawing()).save(path, **({"dpi": (dpi, dpi)} if dpi else {}))
    return path


def test_image_dialog_scan_with_dpi(qapp, tmp_path):
    from nesting2d.gui.image_dialog import ImageContourDialog
    from nesting2d.importers.contours import ImportOptions
    dlg = ImageContourDialog(str(_png(tmp_path, "escaneo.png", 300)), ImportOptions())
    assert dlg.mode.currentData() == "lineas"
    assert dlg.mm_per_px() == pytest.approx(25.4 / 300, rel=1e-3)
    assert len(dlg.faces[1]) == 2
    dlg._band(0, 0, 1400, 1000, True, False)    # ventana a toda la imagen (píxeles)
    dlg.create_part()
    (p,) = dlg.result_parts()
    assert p.size == pytest.approx((100, 60), abs=0.15)
    assert len(p.shape.interiors) == 1
    dlg.reject()


def test_image_dialog_screenshot_needs_scale(qapp, tmp_path):
    from nesting2d.gui.image_dialog import ImageContourDialog
    from nesting2d.importers.contours import ImportOptions
    dlg = ImageContourDialog(str(_png(tmp_path)), ImportOptions())
    assert dlg.mm_per_px() == 0
    dlg._band(0, 0, 1400, 1000, True, False)
    assert not dlg.b_create.isEnabled()          # sin escala no se crean piezas
    dlg.create_part()
    assert dlg.result_parts() == []
    # medir el lado largo de la placa: 100 mm son 1181,1 px a 300 ppp
    dlg.set_scale_from_measure(100 / (25.4 / 300), 100.0)
    assert "medida" in dlg.scale_info.text()
    assert dlg.b_create.isEnabled()
    dlg.create_part()
    (p,) = dlg.result_parts()
    assert p.size == pytest.approx((100, 60), abs=0.15)
    # cambiar el umbral recalcula las zonas pero conserva las piezas creadas
    dlg.threshold.setValue(100)
    dlg.recompute()
    assert len(dlg.result_parts()) == 1
    dlg.scale_spin.setValue(0.1)
    assert "a mano" in dlg.scale_info.text()
    dlg.reject()


def test_window_imports_image_through_dialog(qapp, window, monkeypatch, tmp_path):
    from nesting2d.gui.image_dialog import ImageContourDialog
    w = window

    def fake_exec(dlg):
        dlg._band(0, 0, 1400, 1000, True, False)
        dlg.create_part()
        return ImageContourDialog.DialogCode.Accepted
    monkeypatch.setattr(ImageContourDialog, "exec", fake_exec)
    w.import_files([str(_png(tmp_path, "plano.png", 300))])
    assert w.import_worker is None               # las imágenes no pasan por el hilo de importación
    (p,) = w.model.parts
    assert p.name == "plano_1" and p.quantity == 1
    assert p.size == pytest.approx((100, 60), abs=0.15)


# --- selección por aristas ---------------------------------------------------------------
def _plate_with_dims_dxf(path):
    """Placa 100×60 con taladro Ø20, un eje que cruza el taladro y una 'cota' que cruza la placa."""
    import ezdxf
    doc = ezdxf.new("R2010")
    doc.units = 4
    m = doc.modelspace()
    m.add_lwpolyline([(0, 0), (100, 0), (100, 60), (0, 60)], close=True)
    m.add_circle((50, 30), 10)
    m.add_line((30, 30), (70, 30))
    m.add_line((-10, 45), (110, 45))
    doc.saveas(path)
    return path


def test_edges_mode_chain_plus_holes(qapp, tmp_path, monkeypatch):
    from nesting2d.gui.contour_dialog import ContourDialog
    from nesting2d.importers.contours import ImportOptions
    dlg = ContourDialog(str(_plate_with_dims_dxf(tmp_path / "p.dxf")), ImportOptions())
    wait_until(qapp, lambda: dlg.faces)
    # por zonas, la "cota" parte la placa en dos zonas de material
    assert len(dlg.faces[1]) > 3
    dlg.by_combo.setCurrentIndex(dlg.by_combo.findData(True))
    assert dlg.edge_mode and dlg.b_holes.isVisible() is not None
    qapp.processEvents()
    dlg._hovered(60, 30.2)                       # sobre el taladro
    assert "Ø20" in dlg._hover_text
    dlg._clicked(100, 20)                        # clic en el lado derecho de la placa: cadena = contorno
    assert len(dlg.sel_edges) == 1
    monkeypatch.setattr(dlg, "_choose_holes", lambda groups: groups)
    dlg.add_holes()
    assert len(dlg.sel_edges) == 2               # contorno + taladro; ni el eje ni la cota
    dlg.create_part()
    (p,) = dlg.result_parts()
    assert p.size == pytest.approx((100, 60))
    assert len(p.shape.interiors) == 1
    assert p.area == pytest.approx(6000 - 3.14159 * 100, rel=1e-3)
    dlg.reject()


def test_edges_mode_open_selection_is_reported(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from nesting2d.gui.contour_dialog import ContourDialog
    from nesting2d.importers.contours import ImportOptions
    dlg = ContourDialog(str(_plate_with_dims_dxf(tmp_path / "p.dxf")), ImportOptions())
    wait_until(qapp, lambda: dlg.faces)
    dlg.by_combo.setCurrentIndex(dlg.by_combo.findData(True))
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    dlg._clicked(50, 45, False, True)            # Ctrl+clic: solo la línea de la "cota"
    assert len(dlg.sel_edges) == 1
    assert "NO CIERRA" in dlg.info.text()
    dlg.create_part()
    assert dlg.result_parts() == [] and "no cierran" in shown[0]
    dlg.reject()


def test_edges_mode_shift_click_same_diameter_on_real_gasket(qapp):
    from nesting2d.gui.contour_dialog import ContourDialog
    from nesting2d.importers.contours import ImportOptions
    dlg = ContourDialog(str(DATA / "RIGCCP0019.pdf"), ImportOptions())
    wait_until(qapp, lambda: dlg.faces)
    dlg.by_combo.setCurrentIndex(dlg.by_combo.findData(True))
    ss = dlg._strokeset()
    c = ss.circles[0]
    x, y = c.center[0] + c.radius, c.center[1]
    dlg._clicked(x, y, True, False)              # Mayús+clic en un taladro de Ø4,49
    assert len(dlg.sel_edges) == 15
    dlg.reject()
