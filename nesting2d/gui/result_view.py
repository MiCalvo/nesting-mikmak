"""Paso 3 · Resultado: dibujo de cada plancha, indicadores, validación y edición manual.

Edición manual (fase 3, ver especificación «Edición manual»):
- Seleccionar: clic; Ctrl+clic añade o quita; arrastrar en vacío hace una
  ventana (de izquierda a derecha: piezas enteras dentro; de derecha a
  izquierda: piezas que toca, como en CAD).
- Mover: arrastrar con el ratón (enganche opcional a márgenes y a la separación
  de las vecinas), flechas (paso configurable; ×10 con Mayús) o panel numérico.
- Girar: R / Mayús+R con el paso del proyecto, o un ángulo escrito.
- Validación en vivo (en rojo), métricas en vivo, deshacer/rehacer y volver al
  resultado del motor.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QTransform, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
                               QGraphicsItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView, QHBoxLayout, QHeaderView, QLabel,
                               QListWidget, QListWidgetItem, QRadioButton, QSplitter, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from shapely.affinity import translate
from shapely.geometry import Polygon, box
from shapely.ops import polylabel

from .. import editing
from ..engine.nester import Layout, free_rect  # noqa: F401  (free_rect: la usan las pruebas)
from ..validate import Issue, check, check_layout
from . import style
from .qt_util import fmt, part_color, polygon_path

SHEET_FILL = style.SHEET
FREE_FILL = QColor(46, 160, 67, 34)
SNAP_PX = 8


def issue_text(layout: Layout, iss: Issue, separation: float) -> str:
    names = [layout.placements[i].part for i in iss.items]
    s = layout.placements[iss.items[0]].sheet + 1
    if iss.kind == "solape":
        return f"Pl. {s} · solape: {names[0]} y {names[1]} ({fmt(iss.value, 1)} mm²)"
    if iss.kind == "separacion":
        return f"Pl. {s} · separación: {names[0]} y {names[1]} a {fmt(iss.value, 2)} mm (mín. {fmt(separation, 2)})"
    return f"Pl. {s} · margen: {names[0]} se sale ({fmt(iss.value, 1)} mm² fuera)"


def _centered_text(text: str, x: float, y: float, color: QColor, point_size: float | None = None):
    """Texto de tamaño fijo en pantalla, centrado en el punto de escena (x, y)."""
    t = QGraphicsSimpleTextItem(text)
    t.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    t.setBrush(color)
    if point_size:
        f = t.font()
        f.setPointSizeF(point_size)
        t.setFont(f)
    br = t.boundingRect()
    # la transformación propia sí se aplica (solo se ignoran las heredadas de la vista)
    t.setTransform(QTransform.fromTranslate(-br.width() / 2, -br.height() / 2))
    t.setPos(x, y)
    t.setZValue(3)
    t.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    return t


def _pen(color, width=0.0, style=Qt.PenStyle.SolidLine) -> QPen:
    pen = QPen(QColor(color), width, style)
    pen.setCosmetic(True)
    return pen


PEN_NORMAL = _pen("#3b4452", 0.8)
PEN_BAD = _pen(style.BAD, 2.5)
PEN_SELECTED = _pen(style.ACCENT, 2.5)


class SheetView(QGraphicsView):
    """Vista de una plancha con selección y arrastre.

    No modifica el resultado: emite señales y el panel decide (así todo pasa por
    deshacer/rehacer). Los nombres solo se muestran si caben dentro de su pieza
    al zoom actual.
    """

    selection_changed = Signal()
    drag_moved = Signal(float, float)       # desplazamiento provisional en mm
    drag_finished = Signal(float, float)    # desplazamiento final en mm
    key_move = Signal(float, float)         # en pasos (±1); el panel aplica el paso en mm
    key_rotate = Signal(int)                # +1 antihorario, −1 horario

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(style.CANVAS)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.labels: list[tuple[QGraphicsSimpleTextItem, Polygon, tuple[float, float]]] = []
        self.piece_items: dict[int, object] = {}    # índice de Placement -> QGraphicsPathItem
        self.label_of: dict[int, QGraphicsSimpleTextItem] = {}
        self.selection: set[int] = set()
        self.bad: set[int] = set()
        self.drag_set_fn = lambda sel: sel            # el panel añade las piezas interiores
        self.snap_fn = None                           # (dx, dy, tol_mm) -> (dx, dy)
        self.auto_fit = True
        self._press = None        # punto de escena (mm) donde se pulsó
        self._mode = ""           # "", "drag", "band", "pan"
        self._band_end = None
        self._drag_set: list[int] = []
        self._pan_last = None

    # --- zoom ---------------------------------------------------------------
    def fit(self):
        self.auto_fit = True
        if not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.update_labels()

    def zoom(self, k: float):
        self.auto_fit = False
        self.scale(k, k)
        self.update_labels()

    def px_to_mm(self, px: float) -> float:
        return px / (abs(self.transform().m11()) or 1.0)

    def update_labels(self):
        k = abs(self.transform().m11()) or 1.0   # píxeles por mm
        for t, poly, (x, y) in self.labels:
            br = t.boundingRect()
            w, h = br.width() / k, br.height() / k
            t.setVisible(poly.contains(box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.auto_fit:
            self.fit()

    def wheelEvent(self, e):
        self.zoom(1.25 if e.angleDelta().y() > 0 else 0.8)

    # --- aspecto de las piezas ------------------------------------------------
    def refresh_pens(self):
        for i, it in self.piece_items.items():
            base = it.data(1)
            sel = i in self.selection
            it.setPen(PEN_BAD if i in self.bad else PEN_SELECTED if sel else PEN_NORMAL)
            it.setBrush(QBrush(base.lighter(125) if sel else base))

    def set_selection(self, sel: set[int]):
        self.selection = set(sel) & set(self.piece_items)
        self.refresh_pens()
        self.selection_changed.emit()

    # --- ratón -------------------------------------------------------------------
    def _mm(self, pos) -> tuple[float, float]:
        p = self.mapToScene(pos)
        return p.x(), -p.y()

    def _item_at(self, pos) -> int | None:
        for it in self.items_at(pos):
            return it
        return None

    def items_at(self, pos):
        for it in self.items(pos):
            i = it.data(0)
            if i is not None:
                yield i

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mode, self._pan_last = "pan", e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        self.setFocus()
        pos = e.position().toPoint()
        self._press = self._mm(pos)
        i = self._item_at(pos)
        ctrl = bool(e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        if i is None:
            if not ctrl:
                self.set_selection(set())
            self._mode, self._band_end = "band", self._press
            return
        if ctrl:
            self.set_selection(self.selection ^ {i})
            self._mode = ""
            return
        if i not in self.selection:
            self.set_selection({i})
        self._mode = "drag"
        self._drag_set = self.drag_set_fn(self.selection)

    def _drag_delta(self, pos) -> tuple[float, float]:
        x, y = self._mm(pos)
        dx, dy = x - self._press[0], y - self._press[1]
        if self.snap_fn is not None:
            dx, dy = self.snap_fn(dx, dy, self.px_to_mm(SNAP_PX))
        return dx, dy

    def mouseMoveEvent(self, e):
        if self._mode == "pan":
            d = e.position() - self._pan_last
            self._pan_last = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if self._mode == "drag":
            dx, dy = self._drag_delta(e.position().toPoint())
            for i in self._drag_set:
                self.piece_items[i].setPos(dx, -dy)
                if i in self.label_of:
                    self.label_of[i].setVisible(False)
            self.drag_moved.emit(dx, dy)
            return
        if self._mode == "band":
            self._band_end = self._mm(e.position().toPoint())
            self.viewport().update()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        mode, self._mode = self._mode, ""
        if mode == "pan":
            self.unsetCursor()
            return
        if mode == "drag":
            dx, dy = self._drag_delta(e.position().toPoint())
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                for i in self._drag_set:
                    self.piece_items[i].setPos(0, 0)
                self.update_labels()
                return
            self.drag_finished.emit(dx, dy)
            return
        if mode == "band":
            (x0, y0), (x1, y1) = self._press, self._band_end
            self.viewport().update()
            if abs(x1 - x0) < 1e-6 and abs(y1 - y0) < 1e-6:
                return
            rect = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            window = x1 >= x0   # izquierda→derecha: ventana; derecha→izquierda: captura
            hit = {i for i, it in self.piece_items.items()
                   if (rect.contains(it.data(2)) if window else rect.intersects(it.data(2)))}
            add = bool(e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            self.set_selection(self.selection | hit if add else hit)
            return
        super().mouseReleaseEvent(e)

    def drawForeground(self, painter: QPainter, rect):
        super().drawForeground(painter, rect)
        if self._mode != "band" or self._band_end is None:
            return
        (x0, y0), (x1, y1) = self._press, self._band_end
        window = x1 >= x0
        painter.setPen(_pen(style.ACCENT if window else style.OK, 1,
                            Qt.PenStyle.SolidLine if window else Qt.PenStyle.DashLine))
        painter.setBrush(QColor(31, 111, 235, 28) if window else QColor(26, 127, 55, 28))
        painter.drawRect(QRectF(QPointF(min(x0, x1), -max(y0, y1)), QPointF(max(x0, x1), -min(y0, y1))))

    # --- teclado -------------------------------------------------------------------
    def keyPressEvent(self, e):
        k = e.key()
        moves = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                 Qt.Key.Key_Up: (0, 1), Qt.Key.Key_Down: (0, -1)}
        if k in moves and self.selection:
            mult = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            dx, dy = moves[k]
            self.key_move.emit(dx * mult, dy * mult)
            return
        if k == Qt.Key.Key_R and self.selection:
            self.key_rotate.emit(-1 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)
            return
        if k == Qt.Key.Key_Escape:
            self.set_selection(set())
            return
        if k == Qt.Key.Key_A and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_selection(set(self.piece_items))
            return
        super().keyPressEvent(e)


class EditCommand(QUndoCommand):
    """Cambio de una o varias piezas (y, si hace falta, del nº de planchas)."""

    def __init__(self, panel: "ResultPanel", text: str, before, after, sheets_before: int, sheets_after: int):
        super().__init__(text)
        self.panel = panel
        self.before, self.after = before, after
        self.sheets_before, self.sheets_after = sheets_before, sheets_after

    def redo(self):
        self.panel._apply(self.after, self.sheets_after)

    def undo(self):
        self.panel._apply(self.before, self.sheets_before)


class ResultPanel(QWidget):
    edited = Signal()                 # el resultado ha cambiado por edición manual (o deshacer/rehacer)
    calculate_requested = Signal()    # botón «Calcular» del estado vacío

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout_: Layout | None = None
        self.engine: Layout | None = None      # copia del resultado tal como salió del motor
        self.parts_fn = lambda: []             # piezas actuales (para avisos de rotación)
        self.issues: list[Issue] = []
        self.rot_warnings: list[tuple[int, str]] = []
        self._colors: dict[str, QColor] = {}
        self._labels_cache: dict[int, tuple[Polygon, tuple[float, float]]] = {}
        self.undo = QUndoStack(self)

        self.stale = style.label("El resultado no corresponde a los datos actuales: has cambiado piezas o "
                                 "parámetros después de calcular. Vuelve a calcular (F5).", "banner", wrap=True)
        self.stale.hide()

        # --- barra de la vista ---------------------------------------------------
        self.sheet_combo = QComboBox()
        self.sheet_combo.setMinimumContentsLength(18)
        self.sheet_combo.currentIndexChanged.connect(self._sheet_changed)
        self.b_prev = style.button("◀", "", lambda: self.show_sheet(self.current_sheet() - 1), "Plancha anterior")
        self.b_next = style.button("▶", "", lambda: self.show_sheet(self.current_sheet() + 1), "Plancha siguiente")
        for b in (self.b_prev, self.b_next):
            b.setFixedWidth(34)
        self.labels = QCheckBox("Nombres")
        self.labels.setChecked(True)
        self.labels.toggled.connect(self._draw)
        self.show_free = QCheckBox("Retal libre")
        self.show_free.setChecked(True)
        self.show_free.toggled.connect(self._draw)
        self.snap = QCheckBox("Enganche")
        self.snap.setChecked(True)
        self.snap.setToolTip("Al arrastrar, engancha el rectángulo de la selección a los márgenes de la "
                             "plancha y a la separación mínima de las piezas vecinas.")
        self.view = SheetView()
        fit = style.button("Ajustar", "", self.view.fit, "Ver la plancha entera")
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("Plancha"))
        bar.addWidget(self.b_prev)
        bar.addWidget(self.sheet_combo)
        bar.addWidget(self.b_next)
        bar.addSpacing(16)
        bar.addWidget(self.labels)
        bar.addWidget(self.show_free)
        bar.addWidget(self.snap)
        bar.addStretch(1)
        bar.addWidget(fit)

        # --- indicadores ---------------------------------------------------------------
        self.k_sheets = style.Kpi("Planchas")
        self.k_parts = style.Kpi("Piezas colocadas")
        self.k_util = style.Kpi("Aprovechamiento")
        self.k_free = style.Kpi("Retal libre (mm)")
        self.badge = style.Badge()
        kpis = QHBoxLayout()
        kpis.setSpacing(10)
        for k in (self.k_sheets, self.k_parts, self.k_util, self.k_free):
            kpis.addWidget(k, 1)
        badge_box = QVBoxLayout()
        badge_box.addStretch(1)
        badge_box.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignRight)
        badge_box.addStretch(1)
        kpis.addLayout(badge_box)

        # --- lienzo (o estado vacío) -------------------------------------------------------
        canvas = QFrame()
        canvas.setObjectName("card")
        cl = QVBoxLayout(canvas)
        cl.setContentsMargins(1, 1, 1, 1)
        cl.addWidget(self.view)
        empty = QFrame()
        empty.setObjectName("dropZone")
        el = QVBoxLayout(empty)
        el.addStretch(1)
        for text, name in [("Todavía no hay resultado", "emptyTitle"),
                           ("Importa las piezas (paso 1), revisa el material (paso 2) y pulsa «Calcular nesting».",
                            "muted")]:
            lab = style.label(text, name, wrap=True)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.addWidget(lab)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(style.button("Calcular nesting (F5)", "primary", self.calculate_requested.emit))
        row.addStretch(1)
        el.addSpacing(10)
        el.addLayout(row)
        el.addStretch(2)
        self.canvas_stack = QStackedWidget()
        self.canvas_stack.addWidget(empty)
        self.canvas_stack.addWidget(canvas)

        # --- panel lateral --------------------------------------------------------------------
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 4, 0)
        sl.setSpacing(10)
        self.problems = QListWidget()
        self.problems.setToolTip("Clic en un problema para seleccionar las piezas implicadas.")
        self.problems.itemClicked.connect(self._problem_clicked)
        self.problems.setMaximumHeight(140)
        self.problems_card = style.Card("Problemas")
        self.problems_card.body.addWidget(self.problems)
        sl.addWidget(self.problems_card)          # arriba: es lo primero que hay que ver
        sl.addWidget(self._make_edit_box())
        self.summary = style.label("Todavía no hay resultado. Importa piezas y pulsa «Calcular» (F5).", wrap=True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Pieza", "Uds."])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setMinimumHeight(150)
        self.count_card = style.Card("En esta plancha")
        self.count_card.body.addWidget(self.table)
        self.count_card.body.addWidget(self.summary)
        sl.addWidget(self.count_card, 1)
        help_card = style.Card("Atajos")
        help_card.body.addWidget(style.label(
            "Clic selecciona · Ctrl+clic añade · arrastrar en vacío: ventana (→ dentro, ← tocando) · "
            "flechas mueven (Mayús ×10) · R / Mayús+R giran · botón central desplaza · rueda amplía.",
            "muted", wrap=True))
        sl.addWidget(help_card)
        scroll = style.page_scroll(side)
        scroll.setMinimumWidth(330)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)
        self.top = QWidget()
        tl = QVBoxLayout(self.top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(10)
        tl.addLayout(kpis)
        tl.addLayout(bar)
        ll.addWidget(self.top)
        ll.addWidget(self.canvas_stack, 1)

        self.split = QSplitter()
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(12)
        self.split.addWidget(left)
        self.split.addWidget(scroll)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        self.split.setSizes([1000, 350])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        lay.addWidget(self.stale)
        lay.addWidget(self.split, 1)

        self.view.drag_set_fn = self._drag_set
        self.view.snap_fn = self._snap
        self.view.selection_changed.connect(self._selection_changed)
        self.view.drag_moved.connect(self._drag_moved)
        self.view.drag_finished.connect(self._drag_finished)
        self.view.key_move.connect(self._key_move)
        self.view.key_rotate.connect(self._key_rotate)
        self._live = QTimer(self)
        self._live.setSingleShot(True)
        self._live.setInterval(40)
        self._live.timeout.connect(self._live_validate)
        self._pending_drag = (0.0, 0.0)
        self._show_empty()
        self._update_edit_box()

    def _show_empty(self):
        has = self.layout_ is not None and self.layout_.sheets > 0
        self.canvas_stack.setCurrentIndex(1 if has else 0)
        self.top.setVisible(has)
        self.split.widget(1).setVisible(has)

    # --- panel de edición ----------------------------------------------------------
    def _make_edit_box(self) -> QWidget:
        box_ = QWidget()
        v = QVBoxLayout(box_)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        g = style.Card("Selección")
        self.sel_info = style.label("", "muted", wrap=True)
        self.ex = self._spin(-1e5, 1e5, 2, " mm")
        self.ey = self._spin(-1e5, 1e5, 2, " mm")
        self.ea = self._spin(-3600, 3600, 3, " °")
        self.mode_abs = QRadioButton("Absoluto")
        self.mode_rel = QRadioButton("Relativo")
        self.mode_abs.setChecked(True)
        grp = QButtonGroup(g)
        grp.addButton(self.mode_abs)
        grp.addButton(self.mode_rel)
        self.mode_abs.toggled.connect(lambda *_: self._update_edit_box())
        self.apply_btn = style.button("Aplicar", "primary", self._apply_fields)
        for w in (self.ex, self.ey, self.ea):
            w.lineEdit().returnPressed.connect(self._apply_fields)
        self.rot_ccw = style.button("Girar +", "", lambda: self._key_rotate(1))
        self.rot_cw = style.button("Girar −", "", lambda: self._key_rotate(-1))
        self.step = self._spin(0.01, 1000, 2, " mm")
        self.step.setValue(1.0)
        self.step.setToolTip("Lo que se mueve la selección con cada pulsación de flecha (×10 con Mayús)")
        self.b_undo = style.button("Deshacer", "", self.undo.undo)
        self.b_redo = style.button("Rehacer", "", self.undo.redo)
        self.undo.canUndoChanged.connect(self.b_undo.setEnabled)
        self.undo.canRedoChanged.connect(self.b_redo.setEnabled)
        self.b_undo.setEnabled(False)
        self.b_redo.setEnabled(False)
        self.b_engine = style.button("Volver al resultado del motor", "flat", self.revert_to_engine,
                                     "Deshace todas las ediciones manuales (se puede deshacer)")
        self.target_sheet = QComboBox()
        self.b_to_sheet = style.button("Mover", "", self._move_to_sheet,
                                       "Pasa la selección (con las piezas que lleve dentro) a otra plancha, "
                                       "en la misma posición.")
        self.b_compact = style.button("Eliminar planchas vacías", "flat", self.remove_empty_sheets)

        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        modes = QHBoxLayout()
        modes.addWidget(self.mode_abs)
        modes.addWidget(self.mode_rel)
        modes.addStretch(1)
        f.addRow("", modes)
        f.addRow("X", self.ex)
        f.addRow("Y", self.ey)
        f.addRow("Ángulo", self.ea)
        rot = QHBoxLayout()
        rot.addWidget(self.rot_ccw)
        rot.addWidget(self.rot_cw)
        rot.addStretch(1)
        rot.addWidget(self.apply_btn)
        g.body.addWidget(self.sel_info)
        g.body.addLayout(f)
        g.body.addLayout(rot)
        g.body.addWidget(style.label("X, Y: esquina inferior izquierda del rectángulo que envuelve la selección.",
                                     "muted", wrap=True))
        sf = QFormLayout()
        sf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        sf.addRow("Paso de flechas", self.step)
        g.body.addLayout(sf)
        v.addWidget(g)

        sh = style.Card("Planchas")
        mv = QHBoxLayout()
        mv.addWidget(QLabel("Pasar a"))
        mv.addWidget(self.target_sheet, 1)
        mv.addWidget(self.b_to_sheet)
        sh.body.addLayout(mv)
        sh.body.addWidget(self.b_compact, 0, Qt.AlignmentFlag.AlignLeft)
        v.addWidget(sh)

        hist = style.Card("Historial")
        ur = QHBoxLayout()
        ur.addWidget(self.b_undo)
        ur.addWidget(self.b_redo)
        ur.addStretch(1)
        hist.body.addLayout(ur)
        hist.body.addWidget(self.b_engine, 0, Qt.AlignmentFlag.AlignLeft)
        v.addWidget(hist)
        return box_

    @staticmethod
    def _spin(lo, hi, dec, suffix) -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(dec)
        w.setSuffix(suffix)
        w.setKeyboardTracking(False)
        return w

    def rotation_step(self) -> float:
        if self.layout_ is None or self.layout_.params.rotation_step is None:
            return 90.0
        return self.layout_.params.rotation_step

    def _update_edit_box(self):
        sel = sorted(self.view.selection)
        has = bool(sel) and self.layout_ is not None
        for w in (self.ex, self.ey, self.apply_btn, self.rot_ccw, self.rot_cw, self.target_sheet, self.b_to_sheet):
            w.setEnabled(has)
        L = self.layout_
        self.target_sheet.clear()
        if L is not None:
            for t in range(L.sheets):
                if t != self.current_sheet():
                    self.target_sheet.addItem(f"Plancha {t + 1}", t)
            self.target_sheet.addItem("Plancha nueva", L.sheets)
        self.b_compact.setEnabled(L is not None and len({q.sheet for q in L.placements}) < L.sheets)
        step = self.rotation_step()
        self.rot_ccw.setText(f"Girar +{step:g}°")
        self.rot_cw.setText(f"Girar −{step:g}°")
        self.b_engine.setEnabled(self.engine is not None and self.layout_ is not None
                                 and len(self.engine.placements) == len(self.layout_.placements))
        if not has:
            self.sel_info.setText("Nada seleccionado." if self.layout_ else "")
            self.ea.setEnabled(False)
            return
        L = self.layout_
        names = Counter(L.placements[i].part for i in sel)
        self.sel_info.setText(f"{len(sel)} seleccionada(s): " + ", ".join(
            f"{n} × {k}" if n > 1 else k for k, n in sorted(names.items())))
        absolute = self.mode_abs.isChecked()
        single = len(sel) == 1
        self.ea.setEnabled(not absolute or single)
        for w in (self.ex, self.ey, self.ea):
            w.blockSignals(True)
        if absolute:
            x0, y0, _, _ = editing.bounds(L, editing.with_inners(L, sel))
            self.ex.setValue(x0)
            self.ey.setValue(y0)
            self.ea.setValue(L.placements[sel[0]].angle if single else 0.0)
        else:
            self.ex.setValue(0.0)
            self.ey.setValue(0.0)
            self.ea.setValue(0.0)
        for w in (self.ex, self.ey, self.ea):
            w.blockSignals(False)

    def _apply_fields(self):
        L = self.layout_
        sel = sorted(self.view.selection)
        if L is None or not sel:
            return
        idx = editing.with_inners(L, sel)
        if self.mode_abs.isChecked():
            angle = (self.ea.value() - L.placements[sel[0]].angle) if len(sel) == 1 else 0.0
            ch = editing.transformed(L, idx, angle=angle, target=(self.ex.value(), self.ey.value()))
            text = "Colocar por coordenadas"
        else:
            ch = editing.transformed(L, idx, angle=self.ea.value(), dx=self.ex.value(), dy=self.ey.value())
            text = "Mover/girar relativo"
        self.commit(text, ch)

    # --- edición con deshacer ---------------------------------------------------------
    def commit(self, text: str, changes, sheets_after: int | None = None) -> None:
        L = self.layout_
        if L is None or not changes:
            return
        before = editing.snapshot(L, changes)
        self.undo.push(EditCommand(self, text, before, changes, L.sheets,
                                   L.sheets if sheets_after is None else sheets_after))

    def _apply(self, changes, sheets: int):
        """Lo llaman los comandos de deshacer/rehacer."""
        L = self.layout_
        editing.apply(L, changes)
        L.sheets = sheets
        self._fill_sheet_combo(min(self.current_sheet(), sheets - 1))
        self._revalidate()
        self._draw()
        self.edited.emit()

    def _drag_set(self, sel):
        return editing.with_inners(self.layout_, sel) if self.layout_ else []

    def _snap(self, dx, dy, tol):
        if not self.snap.isChecked() or not self.view.selection:
            return dx, dy
        return editing.snap_delta(self.layout_, self._drag_set(self.view.selection), dx, dy, tol)

    def _drag_moved(self, dx, dy):
        self._pending_drag = (dx, dy)
        if not self._live.isActive():
            self._live.start()

    def _live_validate(self):
        """Validación en vivo mientras se arrastra (sobre una copia provisional)."""
        L = self.layout_
        if L is None or self.view._mode != "drag":
            return
        dx, dy = self._pending_drag
        moving = set(self.view._drag_set)
        tmp = [replace(q, polygon=translate(q.polygon, dx, dy)) if i in moving else q
               for i, q in enumerate(L.placements)]
        issues = check(tmp, L.params, sheet=self.current_sheet())
        self.view.bad = {i for iss in issues for i in iss.items}
        self.view.refresh_pens()

    def _drag_finished(self, dx, dy):
        self._live.stop()
        self.commit("Mover", editing.moved(self.layout_, self.view._drag_set, dx, dy))

    def _key_move(self, sx, sy):
        if self.layout_ is None or not self.view.selection:
            return
        st = self.step.value()
        self.commit("Mover con flechas", editing.moved(self.layout_, self._drag_set(self.view.selection),
                                                       sx * st, sy * st))

    def _key_rotate(self, sign: int):
        if self.layout_ is None or not self.view.selection:
            return
        self.commit("Girar", editing.rotated(self.layout_, self._drag_set(self.view.selection),
                                             sign * self.rotation_step()))

    def _move_to_sheet(self):
        L = self.layout_
        target = self.target_sheet.currentData()
        if L is None or not self.view.selection or target is None:
            return
        idx = self._drag_set(self.view.selection)
        self.commit(f"Pasar a la plancha {target + 1}", editing.to_sheet(L, idx, target),
                    sheets_after=max(L.sheets, target + 1))

    def remove_empty_sheets(self):
        L = self.layout_
        if L is None:
            return
        changes, n = editing.compact_sheets(L)
        if n != L.sheets:
            self.commit("Eliminar planchas vacías", changes, sheets_after=n)

    def revert_to_engine(self):
        L, E = self.layout_, self.engine
        if L is None or E is None or len(E.placements) != len(L.placements):
            return
        changes = {i: q for i, q in enumerate(E.placements) if L.placements[i] is not q}
        if changes or L.sheets != E.sheets:
            self.commit("Volver al resultado del motor", changes, sheets_after=E.sheets)

    # --- API ------------------------------------------------------------------
    def set_layout(self, layout: Layout | None, issues: list[Issue] | None = None,
                   engine: Layout | None = None) -> None:
        self.layout_ = layout
        self.undo.clear()
        self._labels_cache.clear()
        if layout is not None and engine is None:
            engine = Layout(layout.params, list(layout.placements), layout.sheets,
                            dict(layout.unplaced), list(layout.warnings))
        self.engine = engine
        self.stale.hide()
        names = sorted({q.part for q in layout.placements}) if layout else []
        self._colors = {n: part_color(i) for i, n in enumerate(names)}
        self.view.selection = set()
        self._fill_sheet_combo(0)
        if issues is None and layout is not None:
            self._revalidate()
        else:
            self.issues = issues or []
            self._revalidate(rotation_only=True)
        self._show_empty()
        self._draw()
        self.view.fit()

    def refresh_warnings(self) -> None:
        """Recalcula los avisos de giro (cambian si se tocan las rotaciones de una pieza)."""
        if self.layout_ is not None:
            self._revalidate(rotation_only=True)
            self._update_summary()

    def set_stale(self, stale: bool) -> None:
        self.stale.setVisible(stale and self.layout_ is not None)

    def current_sheet(self) -> int:
        return max(0, self.sheet_combo.currentIndex())

    def show_sheet(self, sheet: int) -> None:
        if 0 <= sheet < self.sheet_combo.count():
            self.sheet_combo.setCurrentIndex(sheet)

    def _fill_sheet_combo(self, current: int):
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        L = self.layout_
        if L:
            n = Counter(q.sheet for q in L.placements)
            for s in range(L.sheets):
                self.sheet_combo.addItem(f"{s + 1} de {L.sheets} ({n.get(s, 0)} piezas)", s)
            self.sheet_combo.setCurrentIndex(max(0, min(current, L.sheets - 1)))
        self.sheet_combo.blockSignals(False)

    def _sheet_changed(self, *_):
        self.view.selection = set()
        self._draw()
        self.view.fit()

    def _selection_changed(self):
        self._update_edit_box()

    def _revalidate(self, rotation_only: bool = False):
        L = self.layout_
        if L is None:
            self.issues, self.rot_warnings = [], []
            return
        if not rotation_only:
            self.issues = check_layout(L)
        self.rot_warnings = editing.rotation_warnings(L, self.parts_fn(), L.params)

    def _problem_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not idx or self.layout_ is None:
            return
        self.show_sheet(self.layout_.placements[idx[0]].sheet)
        self.view.set_selection(set(idx))

    # --- dibujo ---------------------------------------------------------------
    def _label_point(self, i: int, poly: Polygon):
        hit = self._labels_cache.get(i)
        if hit is None or hit[0] is not poly:
            # el texto puede pisar huecos, pero no salirse del contorno exterior; se
            # coloca en el polo de inaccesibilidad (punto más alejado del borde)
            shell = Polygon(poly.exterior)
            c = polylabel(shell, 0.5)
            hit = (poly, (shell, (c.x, c.y)))
            self._labels_cache[i] = hit
        return hit[1]

    def _draw(self, *_):
        sc = self.view.scene()
        sc.clear()
        self.view.labels = []
        self.view.piece_items = {}
        self.view.label_of = {}
        L = self.layout_
        if L is None or L.sheets == 0:
            sc.setSceneRect(QRectF())
            self._update_summary()
            self._update_edit_box()
            return
        s = self.current_sheet()
        p = L.params
        W, H, m = p.sheet_width, p.sheet_height, p.margin
        off = 0.006 * max(W, H)     # sombra suave bajo la plancha
        sc.addRect(QRectF(off, -H + off, W, H), QPen(Qt.PenStyle.NoPen), QBrush(QColor(20, 30, 45, 40)))
        sc.addRect(QRectF(0, -H, W, H), _pen(style.SHEET_EDGE, 1.2), QBrush(SHEET_FILL))
        if m > 0:
            sc.addRect(QRectF(m, -(H - m), W - 2 * m, H - 2 * m), _pen("#9aa4b2", 1, Qt.PenStyle.DashLine))
        if self.show_free.isChecked():
            fr = free_rect(L, s)
            if fr:
                x0, y0, x1, y1 = fr
                sc.addRect(QRectF(x0, -y1, x1 - x0, y1 - y0), _pen("#2ea043", 1, Qt.PenStyle.DashLine),
                           QBrush(FREE_FILL))
                sc.addItem(_centered_text(f"Retal libre {fmt(x1 - x0, 0)} × {fmt(y1 - y0, 0)} mm",
                                          (x0 + x1) / 2, -(y0 + y1) / 2, QColor(style.OK), 9))

        self.view.bad = {i for iss in self.issues for i in iss.items if L.placements[i].sheet == s}
        for i, q in enumerate(L.placements):
            if q.sheet != s:
                continue
            color = self._colors.get(q.part, QColor("gray"))
            item = sc.addPath(polygon_path(q.polygon), PEN_NORMAL, QBrush(color))
            item.setData(0, i)
            item.setData(1, color)
            item.setData(2, q.polygon)
            item.setZValue(1 if q.host is not None else 0)   # las interiores, encima para poder pincharlas
            where = f"dentro de {L.placements[q.host].part}" if q.host is not None else ""
            item.setToolTip(f"{q.part}\ngiro {q.angle:g}° {where}".strip())
            self.view.piece_items[i] = item
            if self.labels.isChecked():
                shell, (x, y) = self._label_point(i, q.polygon)
                t = _centered_text(q.part, x, -y, QColor("#1f2933"), 7.5)
                sc.addItem(t)
                self.view.labels.append((t, shell, (x, y)))
                self.view.label_of[i] = t
        self.view.selection &= set(self.view.piece_items)
        self.view.refresh_pens()
        pad = 0.03 * max(W, H)
        sc.setSceneRect(QRectF(-pad, -H - pad, W + 2 * pad, H + 2 * pad))
        self.view.update_labels()
        self._update_summary()
        self._update_edit_box()

    def _update_summary(self):
        L = self.layout_
        self.table.setRowCount(0)
        self.problems.clear()
        self.b_prev.setEnabled(L is not None and self.current_sheet() > 0)
        self.b_next.setEnabled(L is not None and self.current_sheet() < L.sheets - 1)
        if L is None:
            self.summary.setText("Todavía no hay resultado. Importa piezas y pulsa «Calcular» (F5).")
            self.problems_card.hide()
            return
        placed = len(L.placements)
        missing = sum(L.unplaced.values())
        self.k_sheets.set(str(L.sheets))
        self.k_parts.set(f"{placed} / {placed + missing}", style.BAD if missing else None)
        lines = []
        if L.sheets:
            s = self.current_sheet()
            st = L.stats(s)
            fw, fh = st["free"]
            self.k_util.set(f"{fmt(100 * st['utilization'])} %")
            self.k_free.set(f"{fmt(fw, 0)} × {fmt(fh, 0)}")
            for k in (self.k_util, self.k_free):
                k.setToolTip(f"De la plancha {s + 1} (la que se está viendo)")
            lines.append(f"{len(L.on_sheet(s))} piezas · largo ocupado {fmt(st['used_length'])} mm")
            counts = Counter(q.part for q in L.on_sheet(s))
            self.table.setRowCount(len(counts))
            for r, (name, n) in enumerate(sorted(counts.items())):
                it = QTableWidgetItem(f"  {name}")
                it.setIcon(_swatch(self._colors.get(name, QColor("white"))))
                self.table.setItem(r, 0, it)
                num = QTableWidgetItem(str(n))
                num.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, 1, num)
            self.count_card.title.setText(f"En la plancha {s + 1}")
        if L.sheets > 1:
            per = []
            for t in range(L.sheets):
                stt = L.stats(t)
                per.append(f"Pl. {t + 1}: {len(L.on_sheet(t))} piezas · {fmt(100 * stt['utilization'])} %")
            lines.append("<span style='color:%s'>%s</span>" % (style.MUTED, "<br>".join(per)))
        if L.unplaced:
            left = ", ".join(f"{n} × {k}" for k, n in sorted(L.unplaced.items()))
            lines.append(f"<span style='color:{style.BAD}'><b>Sin colocar:</b> {left}</span>")
        self.summary.setText("<br>".join(lines))
        if self.issues:
            n = len(self.issues)
            self.badge.set(f"✕  {n} problema{'s' if n != 1 else ''}", "bad")
        elif self.rot_warnings:
            n = len(self.rot_warnings)
            self.badge.set(f"!  {n} giro{'s' if n != 1 else ''} no permitido{'s' if n != 1 else ''}", "warn")
        else:
            self.badge.set("✓  Validación correcta", "ok")
        self.badge.setToolTip("Se comprueba en vivo: solapes, separación mínima entre piezas y margen al borde."
                              + ("" if self.issues or self.rot_warnings else "\nTodo correcto."))
        for iss in self.issues:
            it = QListWidgetItem(issue_text(L, iss, L.params.separation))
            it.setForeground(QColor(style.BAD))
            it.setData(Qt.ItemDataRole.UserRole, list(iss.items))
            self.problems.addItem(it)
        for i, text in self.rot_warnings:
            it = QListWidgetItem(text)
            it.setForeground(QColor(style.WARN))
            it.setData(Qt.ItemDataRole.UserRole, [i])
            self.problems.addItem(it)
        self.problems.setVisible(self.problems.count() > 0)
        self.problems_card.setVisible(self.problems.count() > 0)
        self.problems_card.title.setText(f"Problemas ({self.problems.count()})")


def _swatch(color: QColor):
    """Cuadradito del color de la pieza (para la tabla de recuentos)."""
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap(14, 14)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(_pen("#3b4452", 1))
    p.setBrush(color)
    p.drawRoundedRect(QRectF(1, 1, 12, 12), 3, 3)
    p.end()
    return QIcon(pm)
