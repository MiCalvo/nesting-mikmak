"""Selección manual de contornos (planos con varias vistas, cotas o cajetín).

La app muestra la hoja con todas las caras cerradas (regiones mínimas que
encierran los trazos). Lo que se ve en AZUL es exactamente el material de la
pieza que se va a crear:
- arrastrar: ventana que AÑADE las caras de dentro (izquierda→derecha: enteras
  dentro; derecha→izquierda: las que toca), ya resueltas con la regla
  par-impar entre ellas (los huecos quedan en blanco; el marco o el cajetín, al
  quedar fuera de la ventana, no cuentan); con Ctrl, la ventana QUITA;
- clic: cambia la cara más interior bajo el cursor de hueco a material o al
  revés. Sirve para los planos con líneas que no son cortes (escalones,
  chaflanes): la regla par-impar las tomaría por huecos;
- «Crear pieza con la selección»: une las caras azules; lo que quede sin
  seleccionar dentro es hueco.

También está aquí el diálogo para elegir capas de un DXF.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)
from shapely import STRtree
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from ..geometry import Part
from ..importers.contours import ImportOptions, closed_faces
from ..importers.strokes import StrokeSet
from .qt_util import fmt, polygon_path


def _pen(color, width=0.0, style=Qt.PenStyle.SolidLine) -> QPen:
    p = QPen(QColor(color), width, style)
    p.setCosmetic(True)
    return p


EDGE_HELP = ("Lo AZUL es la pieza que forman las aristas elegidas (en azul fuerte).\n"
             "Clic: elige o quita el contorno continuo (cadena) o el círculo bajo el cursor.\n"
             "Ctrl+clic: una sola arista. Mayús+clic en un círculo: todos los del mismo Ø.\n"
             "Arrastrar: añade aristas (→ enteras dentro; ← las que toca). Ctrl+arrastrar: quita.\n"
             "«Taladros…»: añade los círculos de dentro del contorno, por diámetros.\n"
             "Las cotas, ejes y referencias no cuentan si no las eliges. En rojo, extremos sin cerrar.\n"
             "Al pasar el ratón: tipo de arista y Ø. Rueda: zoom; botón central: desplazar.")
FILL_SELECTED = QColor(0, 90, 220, 110)
FILL_USED = QColor(60, 160, 90, 90)


class FacesWorker(QThread):
    """Lee el archivo y calcula las caras cerradas de cada página (o del DXF)."""
    done = Signal(object, object, object)    # {página: [caras]}, [avisos], {página: [trazos]}
    failed = Signal(str)

    def __init__(self, file: str, opts: ImportOptions, layers: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.file, self.opts, self.layers = file, opts, layers

    def run(self):
        import traceback
        try:
            path = Path(self.file)
            if path.suffix.lower() == ".dxf":
                from ..importers.dxf_import import dxf_polylines
                pls, warnings = dxf_polylines(path, self.opts, self.layers)
                pages = {1: pls} if pls else {}
            else:
                from ..importers.pdf_import import pdf_page_polylines
                pages, warnings = pdf_page_polylines(path, self.opts)
            faces = {pg: closed_faces(pls, self.opts) for pg, pls in pages.items()}
        except Exception:
            self.failed.emit(traceback.format_exc())
            return
        self.done.emit(faces, warnings, pages)


class FacesView(QGraphicsView):
    clicked = Signal(float, float, bool, bool)            # punto en mm, ¿Mayús?, ¿Ctrl?
    hovered = Signal(float, float)                        # ratón encima (sin pulsar)
    band = Signal(float, float, float, float, bool, bool)  # x0, y0, x1, y1, ventana, quitar
    measured = Signal(float)                              # distancia entre dos clics (modo medir)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("white"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self._press = None
        self._end = None
        self._pan = None
        self.measuring = False      # modo medir: dos clics -> `measured`
        self._measure_pts: list[tuple[float, float]] = []
        self._cursor = None

    def start_measure(self):
        self.measuring = True
        self._measure_pts = []
        self.setCursor(Qt.CursorShape.CrossCursor)

    def stop_measure(self):
        self.measuring = False
        self._measure_pts = []
        self.unsetCursor()
        self.viewport().update()

    def fit(self):
        if not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, e):
        k = 1.25 if e.angleDelta().y() > 0 else 0.8
        self.scale(k, k)

    def _mm(self, pos):
        p = self.mapToScene(pos)
        return p.x(), -p.y()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._pan = e.position()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = self._end = self._mm(e.position().toPoint())

    def mouseMoveEvent(self, e):
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if self.measuring:
            self._cursor = self._mm(e.position().toPoint())
            self.viewport().update()
            return
        if self._press is not None:
            self._end = self._mm(e.position().toPoint())
            self.viewport().update()
            return
        self.hovered.emit(*self._mm(e.position().toPoint()))

    def mouseReleaseEvent(self, e):
        if self._pan is not None:
            self._pan = None
            return
        if self._press is None:
            return
        if self.measuring:
            self._press = self._end = None
            self._measure_pts.append(self._mm(e.position().toPoint()))
            if len(self._measure_pts) == 2:
                (ax, ay), (bx, by) = self._measure_pts
                self.stop_measure()
                d = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
                if d > 0:
                    self.measured.emit(d)
            self.viewport().update()
            return
        (x0, y0), (x1, y1) = self._press, self._mm(e.position().toPoint())
        self._press = self._end = None
        self.viewport().update()
        tol = 3 / (abs(self.transform().m11()) or 1)       # 3 píxeles
        if abs(x1 - x0) < tol and abs(y1 - y0) < tol:
            mods = e.modifiers()
            self.clicked.emit(x0, y0, bool(mods & Qt.KeyboardModifier.ShiftModifier),
                              bool(mods & Qt.KeyboardModifier.ControlModifier))
        else:
            remove = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.band.emit(x0, y0, x1, y1, x1 >= x0, remove)

    def drawForeground(self, painter, rect):
        if self.measuring and self._measure_pts:
            a = self._measure_pts[0]
            b = self._cursor or a
            painter.setPen(_pen("#d00000", 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(a[0], -a[1]), QPointF(b[0], -b[1]))
            return
        if self._press is None or self._end is None:
            return
        (x0, y0), (x1, y1) = self._press, self._end
        window = x1 >= x0
        painter.setPen(_pen("#0050d0" if window else "#208020", 1,
                            Qt.PenStyle.SolidLine if window else Qt.PenStyle.DashLine))
        painter.setBrush(QColor(0, 80, 208, 25) if window else QColor(32, 128, 32, 25))
        painter.drawRect(QRectF(QPointF(min(x0, x1), -max(y0, y1)), QPointF(max(x0, x1), -min(y0, y1))))


class ContourDialog(QDialog):
    """Devuelve en `parts` las piezas creadas a mano."""

    # tolerancias de "zonas iguales" (Mayús+clic): en mm para PDF/DXF; las imágenes las cambian
    twin_tol = 0.05
    twin_area_rel = 0.002

    def __init__(self, file: str, opts: ImportOptions, layers: list[str] | None = None, parent=None,
                 load: bool = True):
        super().__init__(parent)
        self.setWindowTitle(f"Seleccionar contornos — {Path(file).name}")
        self.resize(1250, 820)
        self.file = file
        self.stem = Path(file).stem
        self.faces: dict[int, list[Polygon]] = {}
        self.page = None
        self.selected: set[int] = set()
        self.used: dict[int, dict[int, str]] = {}      # página -> {cara: nombre de pieza}
        self.parts: list[Part] = []
        self._items: dict[int, object] = {}
        self._tree = None

        # modo "aristas": la pieza se define eligiendo aristas (cotas y ejes no cuentan)
        self.edge_mode = False
        self._polylines: dict[int, list] = {}
        self._strokes: dict[int, StrokeSet] = {}
        self.sel_edges: set[int] = set()
        self.used_edges: dict[int, dict[int, str]] = {}
        self._hover_text = ""
        self.opts = opts

        self.by_label = QLabel("Seleccionar por:")
        self.by_combo = QComboBox()
        self.by_combo.addItem("Zonas", False)
        self.by_combo.addItem("Aristas", True)
        self.by_combo.setToolTip("Zonas: regiones cerradas. Aristas: eliges líneas, arcos y círculos; las "
                                 "cotas, ejes y referencias que crucen la pieza no la parten.")
        self.by_combo.currentIndexChanged.connect(self._mode_changed)
        self.page_combo = QComboBox()
        self.page_combo.currentIndexChanged.connect(self._page_changed)
        self.info = QLabel("Leyendo el archivo…")
        self.view = FacesView()
        self.view.clicked.connect(self._clicked)
        self.view.band.connect(self._band)
        self.view.hovered.connect(self._hovered)
        fit = QPushButton("Ajustar")
        fit.clicked.connect(self.view.fit)
        top = QHBoxLayout()
        top.addWidget(self.by_label)
        top.addWidget(self.by_combo)
        top.addSpacing(10)
        top.addWidget(QLabel("Página:"))
        top.addWidget(self.page_combo)
        top.addWidget(self.info, 1)
        top.addWidget(fit)

        self.b_create = QPushButton("Crear pieza con la selección")
        self.b_create.setDefault(True)
        self.b_create.clicked.connect(self.create_part)
        b_clear = QPushButton("Quitar selección")
        b_clear.clicked.connect(self._clear_selection)
        self.b_holes = QPushButton("Taladros…")
        self.b_holes.setToolTip("Añade los círculos que hay dentro del contorno elegido, por diámetros.")
        self.b_holes.clicked.connect(self.add_holes)
        self.b_holes.hide()
        self.list = QListWidget()
        self.list.itemChanged.connect(self._renamed)
        b_del = QPushButton("Deshacer pieza")
        b_del.clicked.connect(self._delete_part)
        self.help = help_ = QLabel("Lo AZUL es la pieza.\n"
                       "Arrastrar: añade lo de dentro de la ventana, con sus huecos (→ enteros dentro; "
                       "← los que toca). Ctrl+arrastrar: quita.\n"
                       "Clic: cambia una zona de hueco a material o al revés (útil si una línea que no es "
                       "de corte, como un escalón, ha dejado en blanco parte de la pieza).\n"
                       "Mayús+clic: el mismo cambio en todas las zonas iguales (p. ej. todos los taladros).\n"
                       "Rueda: zoom; botón central: desplazar.")
        help_.setWordWrap(True)
        help_.setStyleSheet("color: gray;")
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.b_create)
        sl.addWidget(b_clear)
        sl.addWidget(self.b_holes)
        sl.addWidget(QLabel("Piezas creadas (doble clic para renombrar):"))
        sl.addWidget(self.list, 1)
        sl.addWidget(b_del)
        sl.addWidget(help_)

        split = QSplitter()
        split.addWidget(self.view)
        split.addWidget(side)
        split.setStretchFactor(0, 1)
        split.setSizes([950, 300])
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.extra_bar = QHBoxLayout()      # controles propios de cada tipo de archivo
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(self.extra_bar)
        lay.addWidget(split, 1)
        lay.addWidget(self.buttons)
        self._update_buttons()

        self.worker = None
        if load:
            self.worker = FacesWorker(file, opts, layers, self)
            self.worker.done.connect(self._loaded)
            self.worker.failed.connect(lambda tb: (self.info.setText("Error al leer el archivo."),
                                                  QMessageBox.warning(self, "Error", tb)))
            self.worker.start()

    def done(self, r):
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait()
        super().done(r)

    # --- ganchos para otros tipos de archivo (imágenes) ------------------------------
    def _ready_to_create(self) -> bool:
        return True

    def _finalize_poly(self, poly: Polygon) -> Polygon:
        """Pasa una pieza de las unidades de las caras a mm (en PDF/DXF ya son mm)."""
        return poly

    # --- carga -----------------------------------------------------------------
    def _loaded(self, faces, warnings, polylines=None):
        self.faces = faces
        self._polylines = polylines or {}
        self.page_combo.blockSignals(True)
        for pg in sorted(faces):
            self.page_combo.addItem(f"{pg} ({len(faces[pg])} contornos)", pg)
        self.page_combo.blockSignals(False)
        if warnings:
            self.info.setText(" · ".join(warnings))
        if not faces:
            self.info.setText("No hay contornos cerrados en el archivo.")
            return
        self._page_changed()

    def _page_changed(self, *_):
        if self.edge_mode:
            self.page = self.page_combo.currentData()
            self._draw_edges()
            return
        self.page = self.page_combo.currentData()
        self.selected = set()
        faces = self.faces.get(self.page, [])
        self._tree = STRtree(faces) if faces else None
        self.used.setdefault(self.page, {})
        sc = self.view.scene()
        sc.clear()
        self._items = {}
        for i, f in enumerate(faces):
            it = sc.addPath(polygon_path(Polygon(f.exterior)), _pen("#303030", 0.6), QBrush(Qt.BrushStyle.NoBrush))
            self._items[i] = it
        if faces:
            minx = min(f.bounds[0] for f in faces)
            miny = min(f.bounds[1] for f in faces)
            maxx = max(f.bounds[2] for f in faces)
            maxy = max(f.bounds[3] for f in faces)
            pad = 0.02 * max(maxx - minx, maxy - miny)
            sc.setSceneRect(QRectF(minx - pad, -maxy - pad, maxx - minx + 2 * pad, maxy - miny + 2 * pad))
        self._repaint()
        self.view.fit()

    # --- selección ---------------------------------------------------------------
    def _repaint(self):
        if self.edge_mode:
            self._repaint_edges()
            return
        used = self.used.get(self.page, {})
        faces = self.faces.get(self.page, [])
        for i, it in self._items.items():
            if i in self.selected:
                it.setBrush(QBrush(FILL_SELECTED))
                it.setPath(polygon_path(faces[i]))
            elif i in used:
                it.setBrush(QBrush(FILL_USED))
                it.setPath(polygon_path(faces[i]))
            else:
                it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                it.setPath(polygon_path(Polygon(faces[i].exterior)))
        n = len(faces)
        self.info.setText(f"{n} contornos · {len(self.selected)} seleccionados · {len(used)} ya usados en piezas")
        self._update_buttons()

    def _set_selection(self, sel: set[int]):
        self.selected = {i for i in sel if i not in self.used.get(self.page, {})}
        self._repaint()

    def _clicked(self, x, y, same_shape: bool = False, ctrl: bool = False):
        if self.edge_mode:
            self._edge_click(x, y, same_shape, ctrl)
            return
        if self._tree is None:
            return
        faces = self.faces[self.page]
        pt = Point(x, y)
        hits = [int(i) for i in self._tree.query(pt, predicate="intersects")]
        # contiene el punto: la de menor contorno exterior (la más interior)
        inside = [i for i in hits if Polygon(faces[i].exterior).contains(pt)]
        cands = inside or [int(i) for i in self._tree.query(pt.buffer(3 / (abs(self.view.transform().m11()) or 1)))]
        if not cands:
            return
        i = min(cands, key=lambda j: Polygon(faces[j].exterior).area)
        if not same_shape:
            self._set_selection(self.selected ^ {i})
            return
        # Mayús+clic: el mismo cambio en todas las caras iguales (p. ej. todos los taladros)
        twins = self._twins(i)
        if i in self.selected:
            self._set_selection(self.selected - twins)
        else:
            self._set_selection(self.selected | twins)

    def _twins(self, i: int, tol: float | None = None) -> set[int]:
        """Caras con la misma forma y tamaño que la i (área, medidas y nº de huecos), en
        cualquier posición; admite giros de 90° (ancho y alto intercambiados)."""
        tol = self.twin_tol if tol is None else tol
        faces = self.faces[self.page]
        f = faces[i]
        w, h = f.bounds[2] - f.bounds[0], f.bounds[3] - f.bounds[1]
        out = set()
        for j, g in enumerate(faces):
            gw, gh = g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1]
            dims = (abs(gw - w) <= tol and abs(gh - h) <= tol) or (abs(gw - h) <= tol and abs(gh - w) <= tol)
            if dims and abs(g.area - f.area) <= max(tol, self.twin_area_rel * f.area) and len(g.interiors) == len(f.interiors):
                out.add(j)
        return out

    def _band(self, x0, y0, x1, y1, window, remove):
        if self.edge_mode:
            ss = self._strokeset()
            if ss is not None:
                hit = set(ss.in_rect(x0, y0, x1, y1, window))
                self._set_edge_selection(self.sel_edges - hit if remove else self.sel_edges | hit)
            return
        if self._tree is None:
            return
        faces = self.faces[self.page]
        r = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        cand = [int(i) for i in self._tree.query(r)]
        hit = [i for i in cand if (r.contains(faces[i]) if window else r.intersects(faces[i]))]
        if remove:
            self._set_selection(self.selected - set(hit))
        else:
            self._set_selection(self.selected | self._material(hit))

    def _material(self, idx: list[int]) -> set[int]:
        """Regla par-impar SOLO entre las caras dadas: las de profundidad par son material."""
        faces = self.faces[self.page]
        shells = [Polygon(faces[i].exterior) for i in idx]
        tree = STRtree(shells) if shells else None
        out = set()
        for k, i in enumerate(idx):
            pt = faces[i].representative_point()
            depth = sum(1 for j in tree.query(pt, predicate="within") if j != k)
            if depth % 2 == 0:
                out.add(i)
        return out

    # --- piezas --------------------------------------------------------------------
    def _next_name(self) -> str:
        multi = len(self.faces) > 1
        k = len(self.parts) + 1
        base = f"{self.stem}_p{self.page}" if multi else self.stem
        taken = {p.name for p in self.parts if p is not None}
        while f"{base}_{k}" in taken:
            k += 1
        return f"{base}_{k}"

    def create_part(self):
        if not self._ready_to_create():
            return
        if self.edge_mode:
            self._create_from_edges()
            return
        if not self.selected:
            return
        faces = self.faces[self.page]
        merged = unary_union([faces[i] for i in sorted(self.selected)])
        polys = sorted((g for g in getattr(merged, "geoms", [merged]) if isinstance(g, Polygon) and not g.is_empty),
                       key=lambda g: -g.area)
        if not polys:
            return
        if len(polys) > 1:
            choice = self._confirm_many(len(polys))
            if choice is None:
                return
            if choice == "largest":
                polys = polys[:1]
        group = len(self.parts)   # las piezas de una misma selección se deshacen juntas
        for poly in polys:
            name = self._next_name()
            self.parts.append(Part(name=name, shape=self._finalize_poly(poly), source=str(self.file), page=self.page,
                                   extra={"faces": sorted(self.selected), "group": group}))
            item = QListWidgetItem(f"{name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(Qt.ItemDataRole.UserRole, len(self.parts) - 1)
            self.list.addItem(item)
        for i in self.selected:
            self.used[self.page][i] = self.parts[-1].name
        self.selected = set()
        self._repaint()

    # --- modo aristas ------------------------------------------------------------------
    HELP_ZONES = None   # se rellena con el texto inicial de la ayuda

    def _mode_changed(self, *_):
        self.edge_mode = bool(self.by_combo.currentData())
        self.selected = set()
        self.sel_edges = set()
        self.b_holes.setVisible(self.edge_mode)
        if self.HELP_ZONES is None:
            type(self).HELP_ZONES = self.help.text()
        self.help.setText(EDGE_HELP if self.edge_mode else self.HELP_ZONES)
        self._page_changed()

    def _strokeset(self) -> StrokeSet | None:
        if self.page is None or self.page not in self._polylines:
            return None
        if self.page not in self._strokes:
            self._strokes[self.page] = StrokeSet(self._polylines[self.page], self.opts)
        return self._strokes[self.page]

    def _draw_edges(self):
        sc = self.view.scene()
        sc.clear()
        self._items = {}
        self._preview = None
        self._open_marks = []
        ss = self._strokeset()
        self.used_edges.setdefault(self.page, {})
        if ss is None:
            self.info.setText("Este archivo no tiene aristas que elegir.")
            return
        for i, st in enumerate(ss.strokes):
            path = QPainterPath()
            pts = st.pts
            path.moveTo(pts[0][0], -pts[0][1])
            for x, y in pts[1:]:
                path.lineTo(x, -y)
            it = sc.addPath(path, _pen("#707070", 0.8))
            it.setZValue(1)
            self._items[i] = it
        allpts = np.vstack([st.pts for st in ss.strokes])
        minx, miny = allpts.min(axis=0)
        maxx, maxy = allpts.max(axis=0)
        pad = 0.02 * max(maxx - minx, maxy - miny, 1)
        sc.setSceneRect(QRectF(minx - pad, -maxy - pad, maxx - minx + 2 * pad, maxy - miny + 2 * pad))
        self._repaint_edges()
        self.view.fit()

    def _repaint_edges(self):
        ss = self._strokeset()
        if ss is None:
            return
        used = self.used_edges.get(self.page, {})
        for i, it in self._items.items():
            if i in self.sel_edges:
                it.setPen(_pen("#0050d0", 2.5))
            elif i in used:
                it.setPen(_pen("#2a8a4a", 2))
            else:
                it.setPen(_pen("#707070", 0.8))
        sc = self.view.scene()
        if getattr(self, "_preview", None) is not None:
            sc.removeItem(self._preview)
            self._preview = None
        for m in getattr(self, "_open_marks", []):
            sc.removeItem(m)
        self._open_marks = []
        piece = ""
        if self.sel_edges:
            polys = ss.parts_from(sorted(self.sel_edges))
            if polys:
                path = QPainterPath()
                path.setFillRule(Qt.FillRule.OddEvenFill)
                for p in polys:
                    path.addPath(polygon_path(p))
                self._preview = sc.addPath(path, _pen("#0050d0", 0), QBrush(FILL_SELECTED))
                self._preview.setZValue(0)
                b = polys[0].bounds
                piece = (f" · pieza {fmt(b[2] - b[0])} × {fmt(b[3] - b[1])} con {len(polys[0].interiors)} huecos"
                         + (f" (+{len(polys) - 1} sueltas)" if len(polys) > 1 else ""))
            ends = ss.open_ends(sorted(self.sel_edges))
            r = 4 / (abs(self.view.transform().m11()) or 1)
            for x, y in ends[:200]:
                m = sc.addEllipse(QRectF(x - r, -y - r, 2 * r, 2 * r), _pen("#d00000", 1.5))
                m.setZValue(3)
                self._open_marks.append(m)
            if ends and not polys:
                piece = f" · NO CIERRA: {len(ends)} extremos sueltos (en rojo)"
        self.info.setText(f"{len(ss)} aristas · {len(self.sel_edges)} elegidas · {len(used)} ya usadas{piece}"
                          + (f" · {self._hover_text}" if self._hover_text else ""))
        self._update_buttons()

    def _set_edge_selection(self, sel: set[int]):
        used = self.used_edges.get(self.page, {})
        self.sel_edges = {i for i in sel if i not in used}
        self._repaint_edges()

    def _clear_selection(self):
        if self.edge_mode:
            self._set_edge_selection(set())
        else:
            self._set_selection(set())

    def _hover_tol(self) -> float:
        return 5 / (abs(self.view.transform().m11()) or 1)

    def _hovered(self, x, y):
        if not self.edge_mode:
            return
        ss = self._strokeset()
        i = ss.nearest(x, y, self._hover_tol()) if ss else None
        text = ""
        if i is not None:
            st = ss.strokes[i]
            circle = ss.circle_of_stroke(i)
            text = (f"círculo Ø{fmt(circle.diameter, 2)} mm" if circle and st.kind != "circulo" else st.describe())
        if text != self._hover_text:
            self._hover_text = text
            self._repaint_edges()

    def _edge_click(self, x, y, shift: bool, ctrl: bool):
        ss = self._strokeset()
        if ss is None:
            return
        i = ss.nearest(x, y, self._hover_tol())
        if i is None:
            return
        if shift and ss.circle_of_stroke(i) is not None:
            group = {k for c in ss.same_diameter(i) for k in c.strokes}
        elif ctrl:
            group = {i}
        else:
            group = set(ss.chain(i))
            circle = ss.circle_of_stroke(i)
            if circle is not None:
                group |= set(circle.strokes)
        if i in self.sel_edges:
            self._set_edge_selection(self.sel_edges - group)
        else:
            self._set_edge_selection(self.sel_edges | group)

    def add_holes(self):
        ss = self._strokeset()
        if ss is None or not self.sel_edges:
            QMessageBox.information(self, "Taladros", "Elige primero el contorno exterior de la pieza.")
            return
        outer = ss.outer_of(sorted(self.sel_edges))
        if outer is None:
            QMessageBox.information(self, "Taladros", "Las aristas elegidas todavía no cierran un contorno.")
            return
        cands = [c for c in ss.circles_inside(outer) if not set(c.strokes) <= self.sel_edges]
        if not cands:
            QMessageBox.information(self, "Taladros", "No hay más círculos completos dentro del contorno.")
            return
        groups: list[list] = []
        for c in sorted(cands, key=lambda c: c.radius):
            if groups and abs(groups[-1][0].radius - c.radius) <= max(0.02, 0.002 * c.radius):
                groups[-1].append(c)
            else:
                groups.append([c])
        chosen = self._choose_holes(groups)
        if chosen is None:
            return
        add = {k for g in chosen for c in g for k in c.strokes}
        self._set_edge_selection(self.sel_edges | add)

    def _choose_holes(self, groups):
        """Diálogo con una casilla por diámetro (todas marcadas). None = cancelar."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Taladros dentro del contorno")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Círculos completos dentro del contorno elegido:"))
        checks = []
        for g in groups:
            c = QCheckBox(f"Ø{fmt(g[0].diameter, 2)} mm  × {len(g)}")
            c.setChecked(True)
            lay.addWidget(c)
            checks.append(c)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return [g for g, c in zip(groups, checks) if c.isChecked()]

    def _create_from_edges(self):
        ss = self._strokeset()
        if ss is None or not self.sel_edges:
            return
        polys = ss.parts_from(sorted(self.sel_edges))
        if not polys:
            n = len(ss.open_ends(sorted(self.sel_edges)))
            QMessageBox.information(self, "Seleccionar aristas",
                                    f"Las aristas elegidas no cierran ningún contorno: hay {n} extremos sueltos "
                                    "(en rojo). Añade el tramo que falta (Ctrl+clic elige una sola arista).")
            return
        if len(polys) > 1:
            choice = self._confirm_many(len(polys))
            if choice is None:
                return
            if choice == "largest":
                polys = polys[:1]
        group = len(self.parts)
        for poly in polys:
            name = self._next_name()
            self.parts.append(Part(name=name, shape=self._finalize_poly(poly), source=str(self.file), page=self.page,
                                   extra={"edges": sorted(self.sel_edges), "group": group}))
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(Qt.ItemDataRole.UserRole, len(self.parts) - 1)
            self.list.addItem(item)
        used = self.used_edges.setdefault(self.page, {})
        for i in self.sel_edges:
            used[i] = self.parts[-1].name
        self.sel_edges = set()
        self._repaint_edges()

    def _confirm_many(self, n: int) -> str | None:
        """"all", "largest" o None (cancelar)."""
        box_ = QMessageBox(self)
        box_.setWindowTitle("Seleccionar contornos")
        box_.setIcon(QMessageBox.Icon.Question)
        box_.setText(f"La selección forma {n} piezas separadas.")
        box_.setInformativeText("Suele pasar si la ventana ha cogido letras, flechas o símbolos sueltos "
                                "alrededor de la vista.")
        b_large = box_.addButton("Solo la mayor", QMessageBox.ButtonRole.AcceptRole)
        b_all = box_.addButton(f"Crear las {n}", QMessageBox.ButtonRole.AcceptRole)
        box_.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box_.setDefaultButton(b_large)
        box_.exec()
        if box_.clickedButton() is b_large:
            return "largest"
        if box_.clickedButton() is b_all:
            return "all"
        return None

    def _renamed(self, item: QListWidgetItem):
        k = item.data(Qt.ItemDataRole.UserRole)
        name = item.text().strip()
        if k is None or not name:
            return
        if any(p is not None and p.name == name for j, p in enumerate(self.parts) if j != k):
            QMessageBox.warning(self, "Nombre repetido", f"Ya hay una pieza llamada «{name}».")
            self.list.blockSignals(True)
            item.setText(self.parts[k].name)
            self.list.blockSignals(False)
            return
        self.parts[k].name = name

    def _delete_part(self):
        item = self.list.currentItem()
        if item is None:
            return
        p = self.parts[item.data(Qt.ItemDataRole.UserRole)]
        used = self.used.get(p.page, {})
        for i in p.extra.get("faces", []):
            used.pop(i, None)
        used_e = self.used_edges.get(p.page, {})
        for i in p.extra.get("edges", []):
            used_e.pop(i, None)
        group = p.extra.get("group")
        for row in reversed(range(self.list.count())):
            j = self.list.item(row).data(Qt.ItemDataRole.UserRole)
            q = self.parts[j]
            if q is not None and q.extra.get("group") == group:
                self.parts[j] = None
                self.list.takeItem(row)
        self._repaint()

    def result_parts(self) -> list[Part]:
        """Copias de las piezas creadas, sin los datos internos del diálogo."""
        return [replace(p, extra={k: v for k, v in p.extra.items() if k not in ("faces", "edges", "group")})
                for p in self.parts if p is not None]

    def _update_buttons(self):
        has = bool(self.sel_edges) if self.edge_mode else bool(self.selected)
        self.b_create.setEnabled(has and self._ready_to_create())
        n = len([p for p in self.parts if p is not None])
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(f"Importar {n} pieza(s)")
        ok.setEnabled(n > 0)


class LayerDialog(QDialog):
    """Elegir qué capas de un DXF importar."""

    def __init__(self, file_name: str, layers: dict[str, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Capas de {file_name}")
        default = {"CORTE"} if "CORTE" in layers else set(layers)
        self.checks: dict[str, QCheckBox] = {}
        inner = QWidget()
        v = QVBoxLayout(inner)
        for name, n in sorted(layers.items()):
            c = QCheckBox(f"{name}  ({n} entidades)")
            c.setChecked(name in default)
            self.checks[name] = c
            v.addWidget(c)
        v.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        note = QLabel("Desmarca las capas que no sean de corte (marco, cotas, ejes…). Un marco "
                      "alrededor de las piezas las convertiría en huecos.")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addWidget(scroll, 1)
        lay.addWidget(buttons)

    def layers(self) -> list[str]:
        return [n for n, c in self.checks.items() if c.isChecked()]
