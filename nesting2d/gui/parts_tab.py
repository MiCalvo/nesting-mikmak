"""Paso 1 · Piezas: tabla de piezas importadas, vista ampliada con acotar y
propiedades de la pieza elegida.

Todo lo que se cambia aquí pasa por el modelo (`PartsModel.setData` y compañía),
igual que si se editara en la tabla; la vista no guarda datos propios.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QSpinBox, QSplitter, QStackedWidget, QTableView, QVBoxLayout,
                               QWidget)

from ..geometry import scale_from_measure
from .part_view import MODE_EDGE, MODE_POINTS, PartView
from . import style
from .parts_model import (COL_FILE, COL_HOLES, COL_MIRROR, COL_NAME, COL_PREVIEW, COL_QTY, COL_ROT,
                          COL_SCALE, COL_SIZE, ROTATION_CHOICES, PartsDelegate, PartsModel, rotation_label)
from .qt_util import fmt


class ScaleDialog(QDialog):
    """Pide la medida real de una cota y calcula la escala nueva (siempre uniforme)."""

    def __init__(self, measured: float, current_scale: float, file_name: str, n_in_file: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Acotar: escala por medida real")
        self.measured = measured
        self.current = current_scale
        self.real = QDoubleSpinBox()
        self.real.setDecimals(4)
        self.real.setRange(0.0001, 1e6)
        self.real.setSuffix(" mm")
        self.real.setValue(measured)
        self.result_label = QLabel()
        self.apply_all = QCheckBox(f"Aplicar a todas las piezas de {file_name} ({n_in_file})")
        self.apply_all.setEnabled(n_in_file > 1)
        f = QFormLayout()
        f.addRow("Medida en la pieza:", QLabel(f"{fmt(measured, 4)} mm (con la escala actual {fmt(current_scale, 4)})"))
        f.addRow("Medida real:", self.real)
        f.addRow("Escala nueva:", self.result_label)
        f.addRow(self.apply_all)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(buttons)
        self.real.valueChanged.connect(self._update)
        self._update()
        self.real.selectAll()

    def new_scale(self) -> float:
        # la medida se tomó con la escala actual aplicada
        return self.current * scale_from_measure(self.measured, self.real.value())

    def _update(self, *_):
        self.result_label.setText(fmt(self.new_scale(), 4))


class PartsTab(QWidget):
    import_requested = Signal()
    import_manual_requested = Signal()
    hint = Signal(str)
    message = Signal(str)

    def __init__(self, model: PartsModel, parent=None):
        super().__init__(parent)
        self.model = model
        self._syncing = False

        # --- tabla -------------------------------------------------------------
        self.table = QTableView()
        self.table.setModel(model)
        self.table.setItemDelegate(PartsDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.setIconSize(QSize(38, 38))
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.verticalHeader().hide()
        self.table.setColumnHidden(COL_FILE, True)     # el archivo se ve en Propiedades y en la ayuda
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        hh.setHighlightSections(False)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        widths = {COL_PREVIEW: 50, COL_SIZE: 108, COL_HOLES: 68, COL_SCALE: 70,
                  COL_QTY: 80, COL_ROT: 118, COL_MIRROR: 60}
        for col, width in widths.items():
            self.table.setColumnWidth(col, width)

        # --- estado vacío ------------------------------------------------------------
        empty = QFrame()
        empty.setObjectName("dropZone")
        el = QVBoxLayout(empty)
        el.setContentsMargins(30, 30, 30, 30)
        el.addStretch(1)
        for text, name in [("Empieza importando tus planos", "emptyTitle"),
                           ("Arrastra aquí los archivos o pulsa «Importar planos».\n"
                            "PDF vectorial, DXF, capturas de pantalla y escaneos.", "muted")]:
            lab = style.label(text, name, wrap=True)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.addWidget(lab)
        eb = QHBoxLayout()
        eb.addStretch(1)
        eb.addWidget(style.button("Importar planos…", "primary", self.import_requested.emit))
        eb.addWidget(style.button("Elegir contornos a mano…", "", self.import_manual_requested.emit,
                                  "Para planos con varias vistas, cotas o cajetín"))
        eb.addStretch(1)
        el.addSpacing(10)
        el.addLayout(eb)
        tips = style.label("Consejo: en planos con varias vistas, cotas o cajetín usa «Elegir contornos a mano» "
                           "y marca solo lo que forma la pieza.", "muted", wrap=True)
        tips.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addSpacing(16)
        el.addWidget(tips)
        el.addStretch(2)
        self.stack = QStackedWidget()
        self.stack.addWidget(empty)
        self.stack.addWidget(self.table)

        # --- tarjeta de la lista ------------------------------------------------------
        self.b_delete = style.button("Eliminar", "danger", self.delete_selected,
                                     "Quita las piezas seleccionadas (Supr)")
        self.qty = QSpinBox()
        self.qty.setRange(0, 100000)
        self.qty.setValue(1)
        self.b_qty = style.button("Aplicar a la selección", "",
                                  lambda: self.model.set_quantity(self.selected_rows(), self.qty.value()))
        list_card = style.Card("Piezas importadas")
        list_card.header.addWidget(style.button("Importar planos…", "primary", self.import_requested.emit,
                                                "PDF, DXF o imagen (Ctrl+I)"))
        list_card.header.addWidget(style.button("Elegir contornos…", "", self.import_manual_requested.emit,
                                                "Importar eligiendo a mano qué contornos forman la pieza "
                                                "(Ctrl+Mayús+I)"))
        list_card.body.addWidget(self.stack, 1)
        foot = QHBoxLayout()
        self.totals = style.label("", "muted")
        foot.addWidget(self.totals, 1)
        foot.addWidget(QLabel("Cantidad:"))
        foot.addWidget(self.qty)
        foot.addWidget(self.b_qty)
        foot.addSpacing(8)
        foot.addWidget(self.b_delete)
        list_card.body.addLayout(foot)

        # --- vista ampliada + acotar -------------------------------------------------
        self.view = PartView()
        self.view.setMinimumHeight(220)
        self.view.measured.connect(self._on_measured)
        self.view.hint.connect(self.hint)
        self.b_points = style.button("Dos puntos", "", lambda: self._start_measure(MODE_POINTS),
                                     "Mide entre dos puntos (engancha a centros, vértices y aristas) "
                                     "y corrige la escala con la medida real")
        self.b_edge = style.button("Arista recta", "", lambda: self._start_measure(MODE_EDGE),
                                   "Mide una arista recta y corrige la escala con la medida real")
        self.b_reset = style.button("1:1", "", lambda: self.model.set_scale(self.selected_rows(), 1.0),
                                    "Vuelve a escala 1:1 las piezas seleccionadas")
        self.info = style.label("Selecciona una pieza para verla ampliada.", "muted", wrap=True)
        view_card = style.Card("Vista previa")
        view_card.body.addWidget(self.view, 1)
        view_card.body.addWidget(self.info)

        # --- propiedades de la pieza ----------------------------------------------------
        self.p_title = style.label("", "muted", wrap=True)
        self.p_name = QLineEdit()
        self.p_name.editingFinished.connect(self._name_edited)
        self.p_size = QLabel()
        self.p_src = QLabel()
        self.p_src.setWordWrap(True)
        self.p_scale = QDoubleSpinBox()
        self.p_scale.setDecimals(4)
        self.p_scale.setRange(0.0001, 1000.0)
        self.p_scale.setSingleStep(0.01)
        self.p_scale.setKeyboardTracking(False)
        self.p_scale.valueChanged.connect(lambda v: self._set_field(COL_SCALE, v))
        self.p_qty = QSpinBox()
        self.p_qty.setRange(0, 100000)
        self.p_qty.setKeyboardTracking(False)
        self.p_qty.valueChanged.connect(lambda v: self._set_field(COL_QTY, v))
        self.p_rot = QComboBox()
        for text, angs in ROTATION_CHOICES:
            self.p_rot.addItem(text, angs)
        self.p_rot.activated.connect(lambda i: self._set_field(COL_ROT, self.p_rot.itemData(i)))
        self.p_mirror = QCheckBox("Cortar la pieza espejada")
        self.p_mirror.toggled.connect(self._mirror_toggled)
        scale_row = QHBoxLayout()
        scale_row.addWidget(self.p_scale, 1)
        scale_row.addWidget(self.b_reset)
        measure_row = QHBoxLayout()
        measure_row.addWidget(self.b_points)
        measure_row.addWidget(self.b_edge)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form.setHorizontalSpacing(12)
        self.form.addRow("Nombre", self.p_name)
        self.form.addRow("Medidas", self.p_size)
        self.form.addRow("Origen", self.p_src)
        self.form.addRow("Escala", scale_row)
        self.form.addRow("Acotar", measure_row)
        self.form.addRow("Cantidad", self.p_qty)
        self.form.addRow("Rotaciones", self.p_rot)
        self.form.addRow("", self.p_mirror)
        self.props = QWidget()
        self.props.setLayout(self.form)
        props_card = style.Card("Propiedades de la pieza")
        props_card.body.addWidget(self.p_title)
        props_card.body.addWidget(self.props)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)
        rl.addWidget(view_card, 1)
        rl.addWidget(props_card)

        split = QSplitter()
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)
        split.addWidget(list_card)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([780, 380])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.addWidget(split)

        act_del = QAction("Eliminar piezas", self)
        act_del.setShortcut(QKeySequence.StandardKey.Delete)
        act_del.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        act_del.triggered.connect(self.delete_selected)
        self.table.addAction(act_del)

        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        model.dataChanged.connect(self._data_changed)
        model.modelReset.connect(self._refresh)
        model.rowsInserted.connect(self._refresh)
        model.rowsRemoved.connect(self._refresh)
        self._refresh()

    # --- selección --------------------------------------------------------------
    def selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()})

    def current_row(self) -> int | None:
        rows = self.selected_rows()
        return rows[0] if len(rows) == 1 else None

    def select_row(self, row: int) -> None:
        self.table.selectionModel().select(
            self.model.index(row, 0),
            QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)

    def _selection_changed(self, *_):
        r = self.current_row()
        self.view.set_part(self.model.part(r) if r is not None else None)
        self._refresh()

    def _data_changed(self, top_left, bottom_right, *_):
        r = self.current_row()
        if r is not None and top_left.row() <= r <= bottom_right.row():
            self.view.set_part(self.model.part(r))  # la escala o el espejo pueden haber cambiado
        self._refresh()

    def _refresh(self, *_):
        parts = self.model.parts
        self.stack.setCurrentIndex(1 if parts else 0)
        copies = sum(p.quantity for p in parts)
        zero = sum(1 for p in parts if p.quantity == 0)
        text = f"{len(parts)} piezas distintas · {copies} copias a cortar"
        if zero:
            text += f" · {zero} con cantidad 0 (no se calculan)"
        self.totals.setText(text if parts else "")
        rows = self.selected_rows()
        one = len(rows) == 1
        self.b_points.setEnabled(one)
        self.b_edge.setEnabled(one)
        self.b_reset.setEnabled(bool(rows))
        self.b_delete.setEnabled(bool(rows))
        self.b_qty.setEnabled(bool(rows))
        self.qty.setEnabled(bool(rows))
        self.props.setEnabled(one)
        self._fill_props(self.model.part(rows[0]) if one else None)
        if one:
            self.info.setText("Rueda del ratón para ampliar. Acota sobre la vista para corregir la escala.")
            self.p_title.hide()
        elif rows:
            self.info.setText(f"{len(rows)} piezas seleccionadas.")
            self.p_title.setText(f"{len(rows)} piezas seleccionadas. Elige una sola para ver y cambiar sus "
                                 "propiedades; la cantidad se puede poner a todas desde la lista.")
            self.p_title.show()
        else:
            self.info.setText("Selecciona una pieza para verla ampliada." if parts else
                              "No hay piezas. Pulsa «Importar planos…» (Ctrl+I).")
            self.p_title.setText("Selecciona una pieza de la lista." if parts else
                                 "Aquí verás las medidas, la escala y la cantidad de la pieza elegida.")
            self.p_title.show()

    def _fill_props(self, p) -> None:
        self._syncing = True
        try:
            if p is None:
                self.p_name.clear()
                self.p_size.setText("—")
                self.p_src.setText("—")
                self.p_scale.setValue(1.0)
                self.p_qty.setValue(0)
                self.p_rot.setCurrentIndex(0)
                self.p_mirror.setChecked(False)
                return
            w, h = p.size
            if not self.p_name.hasFocus():
                self.p_name.setText(p.name)
            holes = len(p.shape.interiors)
            self.p_size.setText(f"{fmt(w)} × {fmt(h)} mm · {holes} hueco{'s' if holes != 1 else ''} · "
                                f"{fmt(p.area, 0)} mm²")
            src = Path(p.source).name if p.source else "—"
            self.p_src.setText(src + (f", pág. {p.page}" if p.page else ""))
            self.p_src.setToolTip(p.source or "")
            self.p_scale.setValue(p.scale)
            self.p_qty.setValue(p.quantity)
            label = rotation_label(p.rotations)
            i = self.p_rot.findText(label)
            if i < 0:   # rotaciones personalizadas (p. ej. de un proyecto guardado)
                self.p_rot.addItem(label, p.rotations)
                i = self.p_rot.count() - 1
            self.p_rot.setCurrentIndex(i)
            self.p_mirror.setChecked(p.mirror)
        finally:
            self._syncing = False

    def _set_field(self, col: int, value) -> None:
        r = self.current_row()
        if self._syncing or r is None:
            return
        self.model.setData(self.model.index(r, col), value)

    def _name_edited(self):
        r = self.current_row()
        if self._syncing or r is None or self.p_name.text().strip() == self.model.part(r).name:
            return
        if not self.model.setData(self.model.index(r, COL_NAME), self.p_name.text()):
            self.p_name.setText(self.model.part(r).name)

    def _mirror_toggled(self, on: bool):
        r = self.current_row()
        if self._syncing or r is None:
            return
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        self.model.setData(self.model.index(r, COL_MIRROR), state, Qt.ItemDataRole.CheckStateRole)

    # --- acciones ------------------------------------------------------------------
    def delete_selected(self):
        rows = self.selected_rows()
        if rows:
            self.model.remove_rows(rows)

    def _start_measure(self, mode: str):
        self.view.setFocus()
        self.view.set_mode(mode)

    def _on_measured(self, dist: float):
        r = self.current_row()
        if r is None:
            return
        p = self.model.part(r)
        same_file = self.model.rows_from_source(p.source) if p.source else [r]
        dlg = ScaleDialog(dist, p.scale, Path(p.source).name if p.source else p.name, len(same_file), self)
        self.hint.emit("")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        scale = dlg.new_scale()
        rows = same_file if dlg.apply_all.isChecked() else [r]
        self.model.set_scale(rows, scale)
        self.message.emit(f"Escala {fmt(scale, 4)} aplicada a {len(rows)} pieza(s) "
                          f"(medida {fmt(dist, 3)} mm → real {fmt(dlg.real.value(), 3)} mm).")
