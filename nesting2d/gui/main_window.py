"""Ventana principal (fase 2: interfaz básica).

Pestañas: Piezas · Parámetros · Resultado. Abajo, un panel de mensajes con los
avisos de importación y del motor.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QInputDialog, QLabel, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressBar, QTabWidget)

from .. import project
from ..engine.nester import Layout
from ..engine.params import NestParams
from ..exporters.dxf_export import export_sheet
from ..exporters.shop_pdf import export_shop_pdf
from ..validate import check_layout
from ..importers.image_import import is_image
from .contour_dialog import ContourDialog, LayerDialog
from .image_dialog import ImageContourDialog
from .params_panel import ParamsPanel
from .parts_model import PartsModel
from .parts_tab import PartsTab
from .qt_util import fmt
from .result_view import ResultPanel
from .workers import ImportWorker, NestWorker

APP_NAME = "Nesting 2D"
IMPORT_FILTER = ("Planos e imágenes (*.pdf *.dxf *.dwg *.png *.jpg *.jpeg *.bmp *.tif *.tiff);;"
                 "PDF (*.pdf);;DXF (*.dxf);;Imágenes (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;Todos (*)")
MAX_RECENT = 8
PHASES = {"exploring": "explorando", "compressing": "compactando", "final": "terminando"}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1300, 820)
        self.setAcceptDrops(True)
        self.project_path: Path | None = None
        self.modified = False
        self.layout_: Layout | None = None
        self.result_stale = False
        self.nest_worker: NestWorker | None = None
        self.import_worker: ImportWorker | None = None
        self._edited_while_running = False
        self._drain = None
        self._sheet = 0
        self._sheet_t0 = 0.0
        self._best: float | None = None
        self._phase = ""

        # --- contenido ----------------------------------------------------------
        self.model = PartsModel(self)
        self.parts_tab = PartsTab(self.model)
        self.params_panel = ParamsPanel()
        self.result_panel = ResultPanel()
        self.result_panel.parts_fn = lambda: self.model.parts
        self.tabs = QTabWidget()
        self.tabs.addTab(self.parts_tab, "Piezas")
        self.tabs.addTab(self.params_panel, "Parámetros")
        self.tabs.addTab(self.result_panel, "Resultado")
        self.setCentralWidget(self.tabs)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        dock = QDockWidget("Mensajes", self)
        dock.setObjectName("mensajes")
        dock.setWidget(self.log_view)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [120], Qt.Orientation.Vertical)

        self.status = QLabel()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.hide()
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(self.progress)

        self._make_actions(dock)

        # --- conexiones ---------------------------------------------------------
        self.model.edited.connect(self._on_parts_edited)
        self.model.message.connect(self._warn)
        self.parts_tab.import_requested.connect(self.import_files)
        self.parts_tab.hint.connect(self.status.setText)
        self.parts_tab.message.connect(self.log)
        self.params_panel.changed.connect(self._on_params_changed)
        self.result_panel.edited.connect(self._set_modified)

        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._poll_progress)

        self._update_title()
        self._update_actions()
        self.log("Listo. Importa piezas (Ctrl+I), revisa la pestaña Parámetros y pulsa Calcular (F5).")

    # --- acciones y menús -------------------------------------------------------
    def _act(self, text, slot, shortcut=None, tip=None) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        if tip:
            a.setStatusTip(tip)
        a.triggered.connect(slot)
        return a

    def _make_actions(self, dock):
        K = QKeySequence.StandardKey
        self.a_new = self._act("&Nuevo", self.new_project, K.New)
        self.a_open = self._act("&Abrir proyecto…", self.open_project_dialog, K.Open)
        self.a_save = self._act("&Guardar", self.save_project, K.Save)
        self.a_save_as = self._act("Guardar &como…", self.save_project_as, K.SaveAs)
        self.a_import = self._act("&Importar PDF/DXF/imagen…", self.import_files, "Ctrl+I")
        self.a_import_manual = self._act("Importar &seleccionando contornos…", self.import_manual, "Ctrl+Shift+I",
                                         "Para planos con varias vistas, cotas o cajetín")
        self.a_export = self._act("&Exportar DXF…", self.export_dxf, "Ctrl+E",
                                  "Un DXF por plancha (capas CORTE y PLANCHA)")
        self.a_pdf = self._act("Exportar &PDF de taller…", self.export_pdf, "Ctrl+P",
                               "Resumen + una página por plancha, a escala y con las piezas numeradas")
        self.a_labels = QAction("Incluir nombres en el DXF (capa ETIQUETAS)", self)
        self.a_labels.setCheckable(True)
        self.a_quit = self._act("&Salir", self.close, K.Quit)
        self.a_nest = self._act("&Calcular", self.start_nest, "F5", "Calcular el nesting")
        self.a_stop = self._act("&Detener", self.stop_nest, None,
                                "spyrrow no se puede interrumpir: para al acabar la plancha en curso")
        self.a_about = self._act("&Acerca de…", self.about)

        m = self.menuBar().addMenu("&Archivo")
        for a in (self.a_new, self.a_open):
            m.addAction(a)
        self.recent_menu = m.addMenu("Abrir &reciente")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        for a in (self.a_save, self.a_save_as, None, self.a_import, self.a_import_manual, None,
                  self.a_export, self.a_labels, self.a_pdf, None, self.a_quit):
            m.addSeparator() if a is None else m.addAction(a)
        m = self.menuBar().addMenu("&Editar")
        self.a_undo = self.result_panel.undo.createUndoAction(self, "&Deshacer")
        self.a_undo.setShortcut(K.Undo)
        self.a_redo = self.result_panel.undo.createRedoAction(self, "&Rehacer")
        self.a_redo.setShortcut(K.Redo)
        self.a_revert = self._act("&Volver al resultado del motor", self.result_panel.revert_to_engine)
        m.addAction(self.a_undo)
        m.addAction(self.a_redo)
        m.addSeparator()
        m.addAction(self.a_revert)
        m = self.menuBar().addMenu("&Nesting")
        m.addAction(self.a_nest)
        m.addAction(self.a_stop)
        m = self.menuBar().addMenu("&Ver")
        m.addAction(dock.toggleViewAction())
        m = self.menuBar().addMenu("Ay&uda")
        m.addAction(self.a_about)

        tb = self.addToolBar("Principal")
        tb.setObjectName("principal")
        tb.setMovable(False)
        for a in (self.a_new, self.a_open, self.a_save, None, self.a_import, None,
                  self.a_nest, self.a_stop, None, self.a_export, self.a_pdf):
            tb.addSeparator() if a is None else tb.addAction(a)

    def _update_actions(self):
        running = self.nest_worker is not None
        importing = self.import_worker is not None
        self.a_nest.setEnabled(not running)
        self.a_stop.setEnabled(running)
        self.a_import.setEnabled(not importing)
        self.a_import_manual.setEnabled(not importing)
        has_result = self.layout_ is not None and self.layout_.sheets > 0
        self.a_export.setEnabled(has_result)
        self.a_pdf.setEnabled(has_result)
        for a in (self.a_new, self.a_open):
            a.setEnabled(not running and not importing)

    # --- estado ------------------------------------------------------------------
    def log(self, text: str):
        self.log_view.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")

    def _warn(self, text: str):
        self.log("AVISO: " + text)
        QMessageBox.warning(self, APP_NAME, text)

    def _update_title(self):
        name = self.project_path.name if self.project_path else "Proyecto sin guardar"
        self.setWindowTitle(f"{name}{' *' if self.modified else ''} — {APP_NAME}")

    def _set_modified(self, on: bool = True):
        self.modified = on
        self._update_title()

    def _mark_stale(self):
        if self.nest_worker is not None:
            self._edited_while_running = True
        if self.layout_ is not None and not self.result_stale:
            self.result_stale = True
            self.result_panel.set_stale(True)

    def _on_parts_edited(self):
        self._set_modified()
        self._mark_stale()
        self.result_panel.refresh_warnings()   # las rotaciones permitidas pueden haber cambiado

    def _on_params_changed(self, affects_layout: bool):
        self._set_modified()
        if affects_layout:
            self._mark_stale()

    def _set_layout(self, layout: Layout | None, issues=None, stale=False, engine: Layout | None = None):
        self.layout_ = layout
        self.result_stale = stale
        self.result_panel.set_layout(layout, issues, engine)
        self.result_panel.set_stale(stale)
        self._update_actions()

    # --- proyecto ----------------------------------------------------------------
    def _confirm_discard(self) -> bool:
        if not self.modified:
            return True
        r = QMessageBox.question(
            self, APP_NAME, "Hay cambios sin guardar. ¿Guardarlos?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if r == QMessageBox.StandardButton.Save:
            return self.save_project()
        return r == QMessageBox.StandardButton.Discard

    def new_project(self):
        if not self._confirm_discard():
            return
        params = NestParams()
        profiles = self.params_panel.profiles
        if profiles:
            none = "Sin perfil (valores por defecto)"
            names = [p.name for p in profiles] + [none]
            name, ok = QInputDialog.getItem(self, "Proyecto nuevo", "Perfil de material:", names, 0, False)
            if not ok:
                return
            if name != none:
                params = profiles[names.index(name)].apply_to(params)
        self.model.set_parts([])
        self.params_panel.set_params(params)
        self._set_layout(None)
        self.project_path = None
        self._set_modified(False)
        self.log("Proyecto nuevo.")

    def open_project_dialog(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto", self._last_dir(), "Proyecto (*.json)")
        if path:
            self.open_project(path)

    def open_project(self, path: str | Path) -> bool:
        path = Path(path)
        try:
            data = project.load_project(path)
        except Exception as e:  # archivo dañado o de otra cosa
            self._warn(f"No se pudo abrir {path.name}: {e}")
            return False
        parts, params, layout = data.parts, data.params, data.layout
        self.model.set_parts(parts)
        self.params_panel.set_params(params)
        self._set_layout(layout, check_layout(layout) if layout else None, engine=data.engine_layout)
        self.project_path = path
        self._remember_dir(path)
        self._add_recent(path)
        self._set_modified(False)
        self.log(f"Abierto {path}: {len(parts)} piezas" + (f", resultado con {layout.sheets} planchas" if layout else ""))
        return True

    def save_project(self) -> bool:
        if self.project_path is None:
            return self.save_project_as()
        return self._save_to(self.project_path)

    def save_project_as(self) -> bool:
        start = str(self.project_path) if self.project_path else str(Path(self._last_dir()) / "proyecto.json")
        path, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto", start, "Proyecto (*.json)")
        if not path:
            return False
        path = Path(path)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        return self._save_to(path)

    def _save_to(self, path: Path) -> bool:
        layout = None if self.result_stale else self.layout_
        try:
            project.save(path, self.model.parts, self.params_panel.params(), layout,
                         engine_layout=self.result_panel.engine)
        except OSError as e:
            self._warn(f"No se pudo guardar {path}: {e}")
            return False
        self.project_path = path
        self._remember_dir(path)
        self._add_recent(path)
        self._set_modified(False)
        self.log(f"Guardado {path}")
        if self.result_stale and self.layout_ is not None:
            self.log("El resultado no se ha guardado porque no corresponde a los datos actuales; vuelve a calcular.")
        return True

    def _recent(self) -> list[str]:
        v = QSettings().value("recent", [])
        if isinstance(v, str):     # QSettings devuelve un str si solo hay uno
            v = [v]
        return [str(x) for x in (v or [])]

    def _add_recent(self, path: Path):
        p = str(Path(path).resolve())
        items = [p] + [x for x in self._recent() if x != p]
        QSettings().setValue("recent", items[:MAX_RECENT])

    def _fill_recent_menu(self):
        self.recent_menu.clear()
        items = self._recent()
        if not items:
            a = self.recent_menu.addAction("(ninguno)")
            a.setEnabled(False)
            return
        for p in items:
            a = self.recent_menu.addAction(p)
            a.triggered.connect(lambda _=False, p=p: self._open_recent(p))

    def _open_recent(self, p: str):
        if not Path(p).exists():
            self._warn(f"Ya no existe: {p}")
            QSettings().setValue("recent", [x for x in self._recent() if x != p])
            return
        if self._confirm_discard():
            self.open_project(p)

    # --- arrastrar y soltar archivos ----------------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        projects = [f for f in files if f.lower().endswith(".json")]
        drawings = [f for f in files if not f.lower().endswith(".json")]
        if projects:
            if self._confirm_discard():
                self.open_project(projects[0])
        elif drawings:
            self.import_files(drawings)

    def _last_dir(self) -> str:
        return str(QSettings().value("last_dir", str(Path.home())))

    def _remember_dir(self, path: Path):
        QSettings().setValue("last_dir", str(path.parent))

    # --- importar ------------------------------------------------------------------
    def import_files(self, files: list[str] | None = None):
        if self.import_worker is not None:
            return
        if not files:
            files, _ = QFileDialog.getOpenFileNames(
                self, "Importar piezas", self._last_dir(),
                IMPORT_FILTER)
        if not files:
            return
        self._remember_dir(Path(files[0]))
        # las imágenes necesitan elegir contornos y escala: siempre con el diálogo
        images = [f for f in files if is_image(f)]
        files = [f for f in files if not is_image(f)]
        for img in images:
            self.import_image(img)
        if not files:
            return
        layers = {}
        for f in files:
            if f.lower().endswith(".dxf"):
                chosen = self._ask_dxf_layers(f)
                if chosen is False:
                    return
                if chosen is not None:
                    layers[f] = chosen
        self._import_layers = layers
        self.import_worker = ImportWorker(list(files), self.params_panel.import_options(), self, layers=layers)
        self.import_worker.done.connect(self._import_done)
        self.import_worker.failed.connect(self._import_failed)
        self.import_worker.finished.connect(self._import_finished)
        self.status.setText(f"Importando {len(files)} archivo(s)…")
        self.progress.setRange(0, 0)
        self.progress.show()
        self._update_actions()
        self.import_worker.start()

    def _import_finished(self):
        self.import_worker.deleteLater()
        self.import_worker = None
        if self.nest_worker is None:
            self.progress.hide()
        self.status.setText("")
        self._update_actions()

    def _import_failed(self, tb: str):
        self.log(tb)
        self._warn("Error al importar. El detalle está en el panel de mensajes.")

    def _import_done(self, results, warnings):
        for w in warnings:
            self.log("AVISO: " + w)
        added = 0
        for file, parts in results:
            name = Path(file).name
            if not parts:
                continue
            qty = 1
            if len(parts) > 1:
                qty = self._ask_multi_qty(name, len(parts))
                if qty is None:
                    self.log(f"{name}: no se importa ({len(parts)} contornos).")
                    continue
                if qty == "manual":
                    dlg = ContourDialog(file, self.params_panel.import_options(),
                                        getattr(self, "_import_layers", {}).get(file), self)
                    if dlg.exec() == ContourDialog.DialogCode.Accepted:
                        manual = dlg.result_parts()
                        self._add_imported(name, manual, 1)
                        added += len(manual)
                    continue
            self._add_imported(name, parts, qty)
            added += len(parts)
        if warnings and not added:
            QMessageBox.information(self, APP_NAME, "\n".join(warnings))

    def _ask_dxf_layers(self, file: str):
        """Capas a importar de un DXF: lista, None (todas, o una sola capa) o False (cancelar)."""
        from ..importers.dxf_import import dxf_layers
        try:
            layers = dxf_layers(file)
        except Exception as e:   # archivo dañado: ya lo dirá el importador
            self.log(f"AVISO: no se pudieron leer las capas de {Path(file).name}: {e}")
            return None
        if len(layers) <= 1:
            return None
        dlg = LayerDialog(Path(file).name, dict(layers), self)
        if dlg.exec() != LayerDialog.DialogCode.Accepted:
            return False
        return dlg.layers()

    def import_manual(self, file: str | None = None):
        """Importar eligiendo a mano qué contornos forman cada pieza."""
        if not file:
            file, _ = QFileDialog.getOpenFileName(self, "Importar seleccionando contornos", self._last_dir(),
                                                  IMPORT_FILTER)
        if not file:
            return
        self._remember_dir(Path(file))
        if is_image(file):
            self.import_image(file)
            return
        layers = None
        if file.lower().endswith(".dxf"):
            layers = self._ask_dxf_layers(file)
            if layers is False:
                return
        dlg = ContourDialog(file, self.params_panel.import_options(), layers, self)
        if dlg.exec() != ContourDialog.DialogCode.Accepted:
            return
        self._add_imported(Path(file).name, dlg.result_parts(), 1)

    def import_image(self, file: str):
        """Captura de pantalla o escaneo: elegir tipo, umbral, escala y contornos."""
        try:
            dlg = ImageContourDialog(file, self.params_panel.import_options(), self)
        except Exception as e:   # imagen dañada o formato que Pillow no lee
            self._warn(f"No se pudo abrir la imagen {Path(file).name}: {e}")
            return
        if dlg.exec() != ImageContourDialog.DialogCode.Accepted:
            return
        parts = dlg.result_parts()
        self._add_imported(Path(file).name, parts, 1)
        if parts:
            self.log(f"{Path(file).name}: escala {fmt(dlg.mm_per_px(), 5)} mm/px "
                     f"(precisión ≈ ±{fmt(dlg.mm_per_px(), 2)} mm). Comprueba las medidas en la pestaña Piezas.")

    def _add_imported(self, name: str, parts, qty: int):
        if not parts:
            return
        original = [p.name for p in parts]
        for p in parts:
            p.quantity = qty
        self.model.add_parts(parts)
        for a, p in zip(original, parts):
            if a != p.name:
                self.log(f"{name}: ya había una pieza «{a}»; la nueva se llama «{p.name}».")
        self.log(f"{name}: {len(parts)} pieza(s) importadas con cantidad {qty}.")
        self.tabs.setCurrentWidget(self.parts_tab)
        self.parts_tab.select_row(next(i for i, q in enumerate(self.model.parts) if q is parts[0]))

    def _ask_multi_qty(self, name: str, n: int):
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"{name} tiene {n} contornos cerrados.")
        box.setInformativeText(
            "Si es un plano con varias vistas, cotas o cajetín, muchos serán contornos falsos (marco, "
            "letras…). La selección manual de contornos llegará más adelante; de momento puedes "
            "importarlos con cantidad 0 y poner cantidad solo a los buenos, o elegir a mano qué "
            "contornos forman cada pieza.")
        b0 = box.addButton("Cantidad 0 (elegir después)", QMessageBox.ButtonRole.AcceptRole)
        b1 = box.addButton("Cantidad 1 a todos", QMessageBox.ButtonRole.AcceptRole)
        bm = box.addButton("Seleccionar contornos a mano…", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("No importar", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b0)
        box.exec()
        if box.clickedButton() is b0:
            return 0
        if box.clickedButton() is b1:
            return 1
        if box.clickedButton() is bm:
            return "manual"
        return None

    # --- nesting -------------------------------------------------------------------
    def start_nest(self):
        if self.nest_worker is not None:
            return
        parts = [p for p in self.model.parts if p.quantity > 0]
        if not parts:
            self._warn("No hay piezas con cantidad mayor que 0.")
            return
        params = self.params_panel.params()
        if params.sheet_width <= 2 * params.margin or params.sheet_height <= 2 * params.margin:
            self._warn("El margen es demasiado grande para la plancha.")
            return
        total = sum(p.quantity for p in parts)
        self.log(f"Calculando {total} piezas, hasta {params.time_limit} s por plancha…")
        self._edited_while_running = False
        self._drain = None
        self._best = None
        self._phase = ""
        self.nest_worker = NestWorker(parts, params, self)
        self.nest_worker.sheet_started.connect(self._sheet_started)
        self.nest_worker.done.connect(self._nest_done)
        self.nest_worker.failed.connect(self._nest_failed)
        self.nest_worker.finished.connect(self._nest_finished)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText("Preparando (pieza dentro de pieza)…" if params.part_in_part else "Preparando…")
        self._update_actions()
        self.nest_worker.start()
        self.timer.start()

    def stop_nest(self):
        if self.nest_worker is not None:
            self.nest_worker.request_stop()
            self.a_stop.setEnabled(False)
            self.log("Se detendrá al acabar la plancha en curso (el motor no se puede interrumpir a mitad).")

    def _sheet_started(self, sheet: int, drain):
        self._sheet = sheet
        self._drain = drain
        self._sheet_t0 = time.monotonic()
        self._best = None
        self._phase = ""
        self.progress.setRange(0, int(self.nest_worker.params.time_limit) if self.nest_worker else 0)

    def _poll_progress(self):
        if self.nest_worker is None or self._drain is None:
            return
        for phase, width, feasible in self._drain():
            self._phase = PHASES.get(phase, phase)
            if feasible and (self._best is None or width < self._best):
                self._best = width
        elapsed = time.monotonic() - self._sheet_t0
        limit = self.nest_worker.params.time_limit
        self.progress.setValue(min(int(elapsed), limit))
        best = f" · mejor largo {fmt(self._best)} mm" if self._best is not None else ""
        phase = f" · {self._phase}" if self._phase else ""
        self.status.setText(f"Calculando plancha {self._sheet + 1}{phase}{best} · {int(elapsed)} / {limit} s")

    def _nest_done(self, layout: Layout, issues):
        stale = self._edited_while_running
        self._set_layout(layout, issues, stale=stale)
        self._set_modified()
        self.tabs.setCurrentWidget(self.result_panel)
        for w in layout.warnings:
            self.log("AVISO: " + w)
        for s in range(layout.sheets):
            st = layout.stats(s)
            self.log(f"Plancha {s + 1}: {len(layout.on_sheet(s))} piezas, largo ocupado {fmt(st['used_length'])} mm, "
                     f"retal libre {fmt(st['free'][0], 0)} × {fmt(st['free'][1], 0)} mm, "
                     f"aprovechamiento {fmt(100 * st['utilization'])} %")
        if issues:
            self.log(f"ERROR de validación: {len(issues)} problemas (piezas en rojo).")
        if layout.unplaced:
            self._warn("Hay piezas sin colocar: " + ", ".join(f"{n} × {k}" for k, n in sorted(layout.unplaced.items())))
        if stale:
            self.log("Has cambiado datos durante el cálculo: el resultado corresponde a los datos de antes.")

    def _nest_failed(self, tb: str):
        self.log(tb)
        self._warn("Error al calcular. El detalle está en el panel de mensajes.")

    def _nest_finished(self):
        self.timer.stop()
        self.nest_worker.deleteLater()
        self.nest_worker = None
        self._drain = None
        if self.import_worker is None:
            self.progress.hide()
        self.status.setText("")
        self._update_actions()

    # --- exportar ------------------------------------------------------------------
    def export_dxf(self):
        L = self.layout_
        if L is None or L.sheets == 0 or not self._export_problems():
            return
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para los DXF", self._last_dir())
        if not folder:
            return
        files = [Path(folder) / f"plancha_{s + 1}.dxf" for s in range(L.sheets)]
        existing = [f.name for f in files if f.exists()]
        if existing:
            r = QMessageBox.question(self, APP_NAME, "Ya existen y se sobrescribirán:\n" + "\n".join(existing)
                                     + "\n\n¿Continuar?")
            if r != QMessageBox.StandardButton.Yes:
                return
        try:
            for s, f in enumerate(files):
                export_sheet(L, s, f, labels=self.a_labels.isChecked())
        except OSError as e:
            self._warn(f"No se pudo escribir el DXF: {e}")
            return
        QSettings().setValue("last_dir", folder)
        for f in files:
            self.log(f"Exportado {f}")
        self.status.setText(f"{len(files)} DXF exportados en {folder}")

    def _export_problems(self) -> bool:
        """Avisa si se va a exportar algo dudoso. True = seguir."""
        L = self.layout_
        problems = []
        if self.result_stale:
            problems.append("el resultado no corresponde a los datos actuales")
        if self.result_panel.issues:
            problems.append(f"hay {len(self.result_panel.issues)} problemas de validación (piezas en rojo)")
        if self.result_panel.rot_warnings:
            problems.append(f"hay {len(self.result_panel.rot_warnings)} pieza(s) con giro no permitido")
        if L.unplaced:
            problems.append("hay piezas sin colocar")
        if not problems:
            return True
        r = QMessageBox.warning(self, APP_NAME, "Atención: " + "; ".join(problems) + ".\n\n¿Exportar igualmente?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No)
        return r == QMessageBox.StandardButton.Yes

    def export_pdf(self):
        L = self.layout_
        if L is None or L.sheets == 0 or not self._export_problems():
            return
        stem = self.project_path.stem if self.project_path else "taller"
        start = str(Path(self._last_dir()) / f"{stem}_taller.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "PDF de taller", start, "PDF (*.pdf)")
        if not path:
            return
        path = Path(path)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        title = self.project_path.stem if self.project_path else "Hoja de taller"
        try:
            export_shop_pdf(L, self.model.parts, path, title=title,
                            issues_count=len(self.result_panel.issues),
                            rotation_warnings=len(self.result_panel.rot_warnings))
        except OSError as e:
            self._warn(f"No se pudo escribir el PDF: {e}")
            return
        self._remember_dir(path)
        self.log(f"PDF de taller: {path}")
        self.status.setText(f"PDF de taller guardado en {path}")

    # --- otros -----------------------------------------------------------------------
    def about(self):
        QMessageBox.about(self, APP_NAME, (
            f"<b>{APP_NAME}</b><br><br>"
            "Motor de nesting: spyrrow 0.9.0 (MIT), sobre sparrow (MIT) y jagua-rs (MPL-2.0).<br>"
            "Interfaz: PySide6 / Qt (LGPL). PDF: pdfplumber (MIT). Geometría: shapely (BSD-3). DXF: ezdxf (MIT)."))

    def closeEvent(self, e):
        if self.nest_worker is not None:
            r = QMessageBox.question(
                self, APP_NAME, "El cálculo sigue en marcha. ¿Salir igualmente?\n\n"
                "Se esperará a que acabe la plancha en curso (el motor no se puede interrumpir).")
            if r != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        if not self._confirm_discard():
            e.ignore()
            return
        for w in (self.nest_worker, self.import_worker):
            if w is not None:
                if isinstance(w, NestWorker):
                    w.request_stop()
                self.status.setText("Esperando a que termine el cálculo en curso…")
                w.wait()
        e.accept()
