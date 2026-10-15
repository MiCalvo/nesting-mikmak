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

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)
from shapely import STRtree
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from ..geometry import Part
from ..importers.contours import ImportOptions, closed_faces
from .qt_util import polygon_path


def _pen(color, width=0.0, style=Qt.PenStyle.SolidLine) -> QPen:
    p = QPen(QColor(color), width, style)
    p.setCosmetic(True)
    return p


FILL_SELECTED = QColor(0, 90, 220, 110)
FILL_USED = QColor(60, 160, 90, 90)


class FacesWorker(QThread):
    """Lee el archivo y calcula las caras cerradas de cada página (o del DXF)."""
    done = Signal(object, object)    # {página: [caras]}, [avisos]
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
        self.done.emit(faces, warnings)


class FacesView(QGraphicsView):
    clicked = Signal(float, float, bool)                  # punto en mm, ¿Mayús?
    band = Signal(float, float, float, float, bool, bool)  # x0, y0, x1, y1, ventana, quitar

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("white"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._press = None
        self._end = None
        self._pan = None

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
        if self._press is not None:
            self._end = self._mm(e.position().toPoint())
            self.viewport().update()

    def mouseReleaseEvent(self, e):
        if self._pan is not None:
            self._pan = None
            return
        if self._press is None:
            return
        (x0, y0), (x1, y1) = self._press, self._mm(e.position().toPoint())
        self._press = self._end = None
        self.viewport().update()
        tol = 3 / (abs(self.transform().m11()) or 1)       # 3 píxeles
        if abs(x1 - x0) < tol and abs(y1 - y0) < tol:
            self.clicked.emit(x0, y0, bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        else:
            remove = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.band.emit(x0, y0, x1, y1, x1 >= x0, remove)

    def drawForeground(self, painter, rect):
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

    def __init__(self, file: str, opts: ImportOptions, layers: list[str] | None = None, parent=None):
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

        self.page_combo = QComboBox()
        self.page_combo.currentIndexChanged.connect(self._page_changed)
        self.info = QLabel("Leyendo el archivo…")
        self.view = FacesView()
        self.view.clicked.connect(self._clicked)
        self.view.band.connect(self._band)
        fit = QPushButton("Ajustar")
        fit.clicked.connect(self.view.fit)
        top = QHBoxLayout()
        top.addWidget(QLabel("Página:"))
        top.addWidget(self.page_combo)
        top.addWidget(self.info, 1)
        top.addWidget(fit)

        self.b_create = QPushButton("Crear pieza con la selección")
        self.b_create.setDefault(True)
        self.b_create.clicked.connect(self.create_part)
        b_clear = QPushButton("Quitar selección")
        b_clear.clicked.connect(lambda: self._set_selection(set()))
        self.list = QListWidget()
        self.list.itemChanged.connect(self._renamed)
        b_del = QPushButton("Deshacer pieza")
        b_del.clicked.connect(self._delete_part)
        help_ = QLabel("Lo AZUL es la pieza.\n"
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
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addWidget(self.buttons)
        self._update_buttons()

        self.worker = FacesWorker(file, opts, layers, self)
        self.worker.done.connect(self._loaded)
        self.worker.failed.connect(lambda tb: (self.info.setText("Error al leer el archivo."),
                                              QMessageBox.warning(self, "Error", tb)))
        self.worker.start()

    def done(self, r):
        if self.worker.isRunning():
            self.worker.wait()
        super().done(r)

    # --- carga -----------------------------------------------------------------
    def _loaded(self, faces, warnings):
        self.faces = faces
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

    def _clicked(self, x, y, same_shape: bool = False):
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

    def _twins(self, i: int, tol: float = 0.05) -> set[int]:
        """Caras con la misma forma y tamaño que la i (área, medidas y nº de huecos), en
        cualquier posición; admite giros de 90° (ancho y alto intercambiados)."""
        faces = self.faces[self.page]
        f = faces[i]
        w, h = f.bounds[2] - f.bounds[0], f.bounds[3] - f.bounds[1]
        out = set()
        for j, g in enumerate(faces):
            gw, gh = g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1]
            dims = (abs(gw - w) <= tol and abs(gh - h) <= tol) or (abs(gw - h) <= tol and abs(gh - w) <= tol)
            if dims and abs(g.area - f.area) <= max(tol, 0.002 * f.area) and len(g.interiors) == len(f.interiors):
                out.add(j)
        return out

    def _band(self, x0, y0, x1, y1, window, remove):
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
            self.parts.append(Part(name=name, shape=poly, source=str(self.file), page=self.page,
                                   extra={"faces": sorted(self.selected), "group": group}))
            item = QListWidgetItem(f"{name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(Qt.ItemDataRole.UserRole, len(self.parts) - 1)
            self.list.addItem(item)
        for i in self.selected:
            self.used[self.page][i] = self.parts[-1].name
        self.selected = set()
        self._repaint()

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
        return [replace(p, extra={k: v for k, v in p.extra.items() if k not in ("faces", "group")})
                for p in self.parts if p is not None]

    def _update_buttons(self):
        self.b_create.setEnabled(bool(self.selected))
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
