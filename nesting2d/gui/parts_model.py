"""Modelo de la tabla de la pestaña Piezas (una fila por pieza importada)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox, QStyledItemDelegate

from ..geometry import Part
from .qt_util import fmt, shape_icon

COL_PREVIEW, COL_NAME, COL_FILE, COL_SIZE, COL_HOLES, COL_SCALE, COL_QTY, COL_ROT, COL_MIRROR = range(9)
HEADERS = ["Vista", "Nombre", "Archivo", "Medidas (mm)", "Huecos", "Escala", "Cantidad", "Rotaciones", "Espejo"]


def _steps(step: float) -> list[float]:
    return [float(i * step) for i in range(int(round(360 / step)))]


# (texto, ángulos). None = las rotaciones del proyecto.
ROTATION_CHOICES: list[tuple[str, list[float] | None]] = [
    ("Las del proyecto", None),
    ("Solo 0°", [0.0]),
    ("0° y 180°", [0.0, 180.0]),
    ("Cada 90°", _steps(90)),
    ("Cada 45°", _steps(45)),
    ("Cada 15°", _steps(15)),
]


def rotation_label(rotations: list[float] | None) -> str:
    for text, angs in ROTATION_CHOICES:
        if angs == rotations or (angs is not None and rotations is not None
                                 and sorted(angs) == sorted(float(a) for a in rotations)):
            return text
    return "Personalizadas: " + ", ".join(f"{a:g}°" for a in rotations)


def _checked(value) -> bool:
    return int(getattr(value, "value", value)) == Qt.CheckState.Checked.value


class PartsModel(QAbstractTableModel):
    """Lista de piezas. Emite `edited` cada vez que cambia algo que afecta al nesting
    y `message` con avisos para el usuario (p. ej. un nombre repetido)."""

    edited = Signal()
    message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parts: list[Part] = []
        # id(pieza) -> (pieza, espejo, icono); se guarda la pieza para no confundir
        # una pieza borrada con otra nueva que reutilice el mismo id()
        self._icons: dict[int, tuple[Part, bool, object]] = {}

    # --- API ------------------------------------------------------------------
    def set_parts(self, parts: list[Part]) -> None:
        self.beginResetModel()
        self.parts = list(parts)
        self._icons.clear()
        self.endResetModel()

    def add_parts(self, parts: list[Part]) -> list[Part]:
        """Añade piezas; si un nombre ya existe le pone un sufijo _2, _3…"""
        if not parts:
            return []
        taken = {p.name for p in self.parts}
        for p in parts:
            base, k = p.name, 2
            while p.name in taken:
                p.name = f"{base}_{k}"
                k += 1
            taken.add(p.name)
        first = len(self.parts)
        self.beginInsertRows(QModelIndex(), first, first + len(parts) - 1)
        self.parts.extend(parts)
        self.endInsertRows()
        self.edited.emit()
        return parts

    def remove_rows(self, rows: list[int]) -> None:
        for r in sorted(set(rows), reverse=True):
            self.beginRemoveRows(QModelIndex(), r, r)
            del self.parts[r]
            self.endRemoveRows()
        if rows:
            self.edited.emit()

    def part(self, row: int) -> Part:
        return self.parts[row]

    def set_scale(self, rows: list[int], scale: float) -> None:
        for r in rows:
            self.parts[r].scale = scale
            self._row_changed(r)
        self.edited.emit()

    def set_quantity(self, rows: list[int], qty: int) -> None:
        for r in rows:
            self.parts[r].quantity = qty
            self._row_changed(r)
        self.edited.emit()

    def rows_from_source(self, source: str) -> list[int]:
        return [i for i, p in enumerate(self.parts) if p.source == source]

    def _row_changed(self, r: int) -> None:
        self.dataChanged.emit(self.index(r, 0), self.index(r, len(HEADERS) - 1))

    # --- Qt -------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.parts)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def flags(self, index):
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        c = index.column()
        if c in (COL_NAME, COL_SCALE, COL_QTY, COL_ROT):
            f |= Qt.ItemFlag.ItemIsEditable
        elif c == COL_MIRROR:
            f |= Qt.ItemFlag.ItemIsUserCheckable
        return f

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        p = self.parts[index.row()]
        c = index.column()
        R = Qt.ItemDataRole
        if role == R.DecorationRole and c == COL_PREVIEW:
            hit = self._icons.get(id(p))
            if hit is None or hit[0] is not p or hit[1] != p.mirror:
                hit = (p, p.mirror, shape_icon(p.geometry()))
                self._icons[id(p)] = hit
            return hit[2]
        if role == R.CheckStateRole and c == COL_MIRROR:
            return Qt.CheckState.Checked if p.mirror else Qt.CheckState.Unchecked
        if role == R.TextAlignmentRole and c in (COL_SIZE, COL_HOLES, COL_SCALE, COL_QTY):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == R.ToolTipRole and c == COL_FILE:
            page = f" (pág. {p.page})" if p.page else ""
            return p.source + page
        if role == R.DisplayRole:
            if c == COL_NAME:
                return p.name
            if c == COL_FILE:
                return Path(p.source).name if p.source else ""
            if c == COL_SIZE:
                # escala uniforme y positiva: medidas = medidas originales × escala
                minx, miny, maxx, maxy = p.shape.bounds
                return f"{fmt((maxx - minx) * p.scale)} × {fmt((maxy - miny) * p.scale)}"
            if c == COL_HOLES:
                return len(p.shape.interiors)
            if c == COL_SCALE:
                return fmt(p.scale, 4)
            if c == COL_QTY:
                return p.quantity
            if c == COL_ROT:
                return rotation_label(p.rotations)
        if role == R.EditRole:
            if c == COL_NAME:
                return p.name
            if c == COL_SCALE:
                return p.scale
            if c == COL_QTY:
                return p.quantity
            if c == COL_ROT:
                return p.rotations
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
        p = self.parts[index.row()]
        c = index.column()
        if role == Qt.ItemDataRole.CheckStateRole and c == COL_MIRROR:
            p.mirror = _checked(value)
        elif role == Qt.ItemDataRole.EditRole and c == COL_NAME:
            name = str(value).strip()
            if not name:
                return False
            if name != p.name and any(q.name == name for q in self.parts):
                self.message.emit(f"Ya hay una pieza llamada «{name}»; los nombres no se pueden repetir.")
                return False
            p.name = name
        elif role == Qt.ItemDataRole.EditRole and c == COL_SCALE:
            v = float(value)
            if v <= 0:
                return False
            p.scale = v
        elif role == Qt.ItemDataRole.EditRole and c == COL_QTY:
            p.quantity = max(0, int(value))
        elif role == Qt.ItemDataRole.EditRole and c == COL_ROT:
            p.rotations = None if value is None else [float(a) for a in value]
        else:
            return False
        self._row_changed(index.row())
        self.edited.emit()
        return True


class PartsDelegate(QStyledItemDelegate):
    """Editores de la tabla: escala con 4 decimales, cantidad entera, rotaciones en lista."""

    def createEditor(self, parent, option, index):
        c = index.column()
        if c == COL_SCALE:
            e = QDoubleSpinBox(parent)
            e.setDecimals(4)
            e.setRange(0.0001, 1000.0)
            e.setSingleStep(0.01)
            return e
        if c == COL_QTY:
            e = QSpinBox(parent)
            e.setRange(0, 100000)
            return e
        if c == COL_ROT:
            e = QComboBox(parent)
            for text, angs in ROTATION_CHOICES:
                e.addItem(text, angs)
            return e
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        c = index.column()
        v = index.model().data(index, Qt.ItemDataRole.EditRole)
        if c in (COL_SCALE, COL_QTY):
            editor.setValue(v)
        elif c == COL_ROT:
            label = rotation_label(v)
            i = editor.findText(label)
            if i < 0:  # rotaciones personalizadas (p. ej. de un proyecto guardado)
                editor.addItem(label, v)
                i = editor.count() - 1
            editor.setCurrentIndex(i)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        c = index.column()
        if c in (COL_SCALE, COL_QTY):
            editor.interpretText()
            model.setData(index, editor.value())
        elif c == COL_ROT:
            model.setData(index, editor.currentData())
        else:
            super().setModelData(editor, model, index)
