"""Selección de contornos sobre una imagen (captura de pantalla o escaneo).

Es el mismo diálogo de contornos ("lo azul es la pieza") con controles extra:
- Tipo de imagen: dibujo de líneas (captura de un plano), silueta oscura o silueta clara.
- Umbral de blanco y negro (automático o a mano); se recalculan las zonas.
- Escala, OBLIGATORIA antes de crear piezas (una imagen no tiene milímetros):
  de los ppp del archivo si es un escaneo (≥ 150 ppp), o midiendo en la imagen
  una distancia conocida.
- La imagen se ve debajo de las zonas.

Las zonas se calculan en píxeles; al crear la pieza se pasa a mm con la escala.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QInputDialog, QLabel,
                               QMessageBox, QPushButton, QSlider, QVBoxLayout)
from shapely.affinity import scale as _scale
from shapely.geometry import Polygon

from ..importers.contours import ImportOptions
from ..importers.image_import import RasterImage, image_faces, load_image, otsu_threshold
from .contour_dialog import ContourDialog
from .qt_util import fmt

MODE_LABELS = [("Dibujo de líneas (captura de un plano)", "lineas"),
               ("Silueta oscura sobre fondo claro", "silueta"),
               ("Silueta clara sobre fondo oscuro", "silueta_clara")]


def guess_mode(img: RasterImage, threshold: int) -> str:
    """Poca tinta = dibujo de líneas; mucha = silueta."""
    dark = float((img.gray <= threshold).mean())
    if dark < 0.25:
        return "lineas"
    return "silueta" if dark < 0.75 else "silueta_clara"


class ImageContourDialog(ContourDialog):
    # en píxeles: las zonas iguales difieren en ±1 píxel por el redondeo
    twin_tol = 1.5
    twin_area_rel = 0.03

    def __init__(self, file: str, opts: ImportOptions, parent=None):
        super().__init__(file, opts, None, parent, load=False)
        self.setWindowTitle(f"Seleccionar contornos en imagen — {self.stem}")
        self.img = load_image(file)
        self._pixmap_item = None
        auto = otsu_threshold(self.img.gray)

        self.mode = QComboBox()
        for text, m in MODE_LABELS:
            self.mode.addItem(text, m)
        self.mode.setCurrentIndex([m for _, m in MODE_LABELS].index(guess_mode(self.img, auto)))
        self.threshold = QSlider(Qt.Orientation.Horizontal)
        self.threshold.setRange(1, 254)
        self.threshold.setValue(max(1, min(254, auto)))
        self.threshold.setMinimumWidth(160)
        self.threshold_label = QLabel()
        self.threshold_label.setMinimumWidth(28)
        b_auto = QPushButton("Auto")
        b_auto.setToolTip("Umbral automático (método de Otsu)")
        b_auto.clicked.connect(lambda: self.threshold.setValue(max(1, min(254, otsu_threshold(self.img.gray)))))
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setDecimals(5)
        self.scale_spin.setRange(0.0, 100.0)
        self.scale_spin.setSingleStep(0.001)
        self.scale_spin.setSpecialValueText("sin escala")
        self.scale_spin.setSuffix(" mm/px")
        self.scale_spin.setKeyboardTracking(False)
        b_measure = QPushButton("Medir en la imagen…")
        b_measure.setToolTip("Dos clics sobre una distancia conocida y escribe cuánto mide de verdad.")
        b_measure.clicked.connect(self._start_measure)
        self.show_image = QCheckBox("Ver imagen")
        self.show_image.setChecked(True)
        self.show_image.toggled.connect(lambda on: self._pixmap_item and self._pixmap_item.setVisible(on))
        self.scale_info = QLabel()
        self.scale_info.setStyleSheet("color: #8a6d00;")

        # dos filas: en una sola no caben y el deslizador se queda sin ancho
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        row1.addWidget(QLabel("Tipo:"))
        row1.addWidget(self.mode)
        row1.addSpacing(16)
        row1.addWidget(QLabel("Umbral:"))
        row1.addWidget(self.threshold, 1)
        row1.addWidget(self.threshold_label)
        row1.addWidget(b_auto)
        row1.addSpacing(16)
        row1.addWidget(self.show_image)
        row2.addWidget(QLabel("Escala:"))
        row2.addWidget(self.scale_spin)
        row2.addWidget(b_measure)
        row2.addSpacing(10)
        row2.addWidget(self.scale_info, 1)
        rows = QVBoxLayout()
        rows.setContentsMargins(0, 0, 0, 0)
        rows.addLayout(row1)
        rows.addLayout(row2)
        self.extra_bar.addLayout(rows, 1)

        self._scale_source = ""
        self._programmatic = False
        from_dpi = self.img.mm_per_px_from_dpi()
        if from_dpi:
            self._set_scale(from_dpi, f"de los {fmt(self.img.dpi, 0)} ppp del archivo")
        self._update_scale_info()

        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.setInterval(250)
        self._recalc_timer.timeout.connect(self.recompute)
        self.mode.currentIndexChanged.connect(lambda *_: self.recompute())
        self.threshold.valueChanged.connect(lambda *_: self._recalc_timer.start())
        self.scale_spin.valueChanged.connect(self._scale_changed)
        self.view.measured.connect(self._measured)
        self.recompute()

    # --- zonas ---------------------------------------------------------------
    def recompute(self):
        from PySide6.QtWidgets import QApplication
        self.threshold_label.setText(str(self.threshold.value()))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            faces, _, width = image_faces(self.img, self.mode.currentData(), self.threshold.value())
        finally:
            QApplication.restoreOverrideCursor()
        # las zonas cambian: las marcas de "ya usada" dejan de valer (las piezas creadas se quedan)
        self.used = {}
        self.faces = {1: faces} if faces else {}
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        if faces:
            self.page_combo.addItem(f"imagen ({len(faces)} zonas)", 1)
        self.page_combo.blockSignals(False)
        self._page_changed()
        if not faces:
            self.info.setText("No sale ninguna zona cerrada: prueba otro tipo de imagen o mueve el umbral.")

    def _page_changed(self, *_):
        if not self.faces:
            self.view.scene().clear()
            self._pixmap_item = None
            self._add_pixmap()
            return
        super()._page_changed()
        self._add_pixmap()

    def _add_pixmap(self):
        g = self.img.gray
        h, w = g.shape
        qimg = QImage(g.data, w, h, g.strides[0], QImage.Format.Format_Grayscale8).copy()
        item = self.view.scene().addPixmap(QPixmap.fromImage(qimg))
        item.setPos(0, -h)                 # las zonas están en (x, −y) con y hacia arriba
        item.setOpacity(0.45)
        item.setZValue(-1)
        item.setVisible(self.show_image.isChecked())
        self._pixmap_item = item
        sc = self.view.scene()
        pad = 0.02 * max(w, h)
        sc.setSceneRect(-pad, -h - pad, w + 2 * pad, h + 2 * pad)
        self.view.fit()

    # --- escala ---------------------------------------------------------------
    def mm_per_px(self) -> float:
        return self.scale_spin.value()

    def _ready_to_create(self) -> bool:
        return self.mm_per_px() > 0

    def _finalize_poly(self, poly: Polygon) -> Polygon:
        s = self.mm_per_px()
        return _scale(poly, s, s, origin=(0, 0))

    def _start_measure(self):
        self.view.start_measure()
        self.info.setText("Medir: haz clic en los dos extremos de una distancia conocida (rueda para ampliar).")

    def _measured(self, px: float):
        real, ok = QInputDialog.getDouble(self, "Escala", f"Distancia medida: {fmt(px, 1)} píxeles.\n"
                                          "¿Cuánto mide de verdad (mm)?", 10.0, 0.001, 1e6, 3)
        if ok and real > 0:
            self.set_scale_from_measure(px, real)

    def set_scale_from_measure(self, px: float, real_mm: float):
        self._set_scale(real_mm / px, f"medida: {fmt(px, 1)} px = {fmt(real_mm, 3)} mm")

    def _set_scale(self, value: float, source: str):
        self._programmatic = True
        try:
            self._scale_source = source
            self.scale_spin.setValue(value)
        finally:
            self._programmatic = False
        self._update_scale_info()
        self._update_buttons()

    def _scale_changed(self, *_):
        if not self._programmatic:
            self._scale_source = "escrita a mano"
        self._update_scale_info()
        self._update_buttons()

    def _update_scale_info(self):
        s = self.mm_per_px()
        if s <= 0:
            self.scale_info.setText("Sin escala: mide una distancia conocida antes de crear piezas.")
        else:
            self.scale_info.setText(f"1 px = {fmt(s, 4)} mm ({self._scale_source}). "
                                    f"Precisión ≈ ±{fmt(s, 2)} mm.")

    def accept(self):
        if any(p is not None for p in self.parts) and self.mm_per_px() <= 0:
            QMessageBox.warning(self, "Escala", "Falta la escala.")
            return
        super().accept()
