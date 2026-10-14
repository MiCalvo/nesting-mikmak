"""Pestaña Piezas: tabla de piezas importadas + vista ampliada con acotar."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QSpinBox, QSplitter, QTableView, QVBoxLayout, QWidget)

from ..geometry import scale_from_measure
from .part_view import MODE_EDGE, MODE_POINTS, PartView
from .parts_model import (COL_FILE, COL_HOLES, COL_MIRROR, COL_NAME, COL_PREVIEW, COL_QTY, COL_ROT,
                          COL_SCALE, COL_SIZE, PartsDelegate, PartsModel)
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
    hint = Signal(str)
    message = Signal(str)

    def __init__(self, model: PartsModel, parent=None):
        super().__init__(parent)
        self.model = model

        self.table = QTableView()
        self.table.setModel(model)
        self.table.setItemDelegate(PartsDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.setIconSize(QSize(40, 40))
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.verticalHeader().hide()
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        widths = {COL_PREVIEW: 52, COL_FILE: 140, COL_SIZE: 115, COL_HOLES: 62, COL_SCALE: 80,
                  COL_QTY: 72, COL_ROT: 130, COL_MIRROR: 58}
        for col, width in widths.items():
            self.table.setColumnWidth(col, width)

        b_import = QPushButton("Importar PDF/DXF…")
        b_import.clicked.connect(self.import_requested)
        self.b_delete = QPushButton("Eliminar")
        self.b_delete.clicked.connect(self.delete_selected)
        self.qty = QSpinBox()
        self.qty.setRange(0, 100000)
        self.qty.setValue(1)
        self.b_qty = QPushButton("Poner cantidad a la selección")
        self.b_qty.clicked.connect(lambda: self.model.set_quantity(self.selected_rows(), self.qty.value()))
        row = QHBoxLayout()
        row.addWidget(b_import)
        row.addWidget(self.b_delete)
        row.addStretch(1)
        row.addWidget(self.qty)
        row.addWidget(self.b_qty)
        self.totals = QLabel()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addLayout(row)
        ll.addWidget(self.table, 1)
        ll.addWidget(self.totals)

        # --- vista ampliada + acotar --------------------------------------------
        self.view = PartView()
        self.view.measured.connect(self._on_measured)
        self.view.hint.connect(self.hint)
        self.b_points = QPushButton("Acotar: dos puntos")
        self.b_edge = QPushButton("Acotar: arista recta")
        self.b_reset = QPushButton("Escala 1:1")
        self.b_points.clicked.connect(lambda: self._start_measure(MODE_POINTS))
        self.b_edge.clicked.connect(lambda: self._start_measure(MODE_EDGE))
        self.b_reset.clicked.connect(lambda: self.model.set_scale(self.selected_rows(), 1.0))
        tools = QHBoxLayout()
        tools.addWidget(self.b_points)
        tools.addWidget(self.b_edge)
        tools.addStretch(1)
        tools.addWidget(self.b_reset)
        self.info = QLabel("Selecciona una pieza para verla ampliada.")
        self.info.setWordWrap(True)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addLayout(tools)
        rl.addWidget(self.view, 1)
        rl.addWidget(self.info)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
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
        copies = sum(p.quantity for p in parts)
        self.totals.setText(f"{len(parts)} piezas distintas · {copies} copias a cortar")
        rows = self.selected_rows()
        one = len(rows) == 1
        self.b_points.setEnabled(one)
        self.b_edge.setEnabled(one)
        self.b_reset.setEnabled(bool(rows))
        self.b_delete.setEnabled(bool(rows))
        self.b_qty.setEnabled(bool(rows))
        if one:
            p = self.model.part(rows[0])
            w, h = p.size
            src = Path(p.source).name if p.source else "—"
            page = f", pág. {p.page}" if p.page else ""
            self.info.setText(f"<b>{p.name}</b> · {fmt(w)} × {fmt(h)} mm · escala {fmt(p.scale, 4)} · "
                              f"{len(p.shape.interiors)} huecos · área {fmt(p.area, 0)} mm²<br>"
                              f"Origen: {src}{page}. Rueda del ratón para ampliar.")
        elif rows:
            self.info.setText(f"{len(rows)} piezas seleccionadas.")
        else:
            self.info.setText("Selecciona una pieza para verla ampliada." if parts else
                              "No hay piezas. Pulsa «Importar PDF/DXF…» (Ctrl+I).")

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
