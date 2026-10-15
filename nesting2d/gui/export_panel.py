"""Paso 4 · Exportar: comprobaciones antes de cortar y botones de salida.

No exporta nada por sí misma: emite señales y la ventana principal hace el
trabajo (los mismos `export_dxf` / `export_pdf` / guardar de los menús). Las
opciones del DXF son las mismas acciones del menú Archivo, sincronizadas.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import style

ICONS = {"ok": ("✓", style.OK, style.OK_SOFT), "warn": ("!", style.WARN, style.WARN_SOFT),
         "bad": ("✕", style.BAD, style.BAD_SOFT), "todo": ("–", style.MUTED, "#eef1f5")}


class CheckRow(QWidget):
    """Una comprobación: icono de estado + texto + detalle."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.icon = QLabel()
        self.icon.setFixedSize(24, 24)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = style.label(title)
        self.detail = style.label("", "muted", wrap=True)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(self.title)
        text.addWidget(self.detail)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(text, 1)
        self.state = "todo"
        self.set("todo", "")

    def set(self, state: str, detail: str) -> None:
        self.state = state
        mark, fg, bg = ICONS[state]
        self.icon.setText(mark)
        self.icon.setStyleSheet(f"background: {bg}; color: {fg}; border-radius: 12px; font-weight: 700;")
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))


class ExportPanel(QWidget):
    export_dxf_requested = Signal()
    export_pdf_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()

    def __init__(self, a_labels: QAction, a_arcs: QAction, parent=None):
        super().__init__(parent)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(12)

        # --- comprobaciones ---------------------------------------------------------
        checks = style.Card("Antes de cortar", "Lo que conviene revisar antes de mandar los archivos a la máquina.")
        self.c_result = CheckRow("Hay un resultado calculado y al día")
        self.c_valid = CheckRow("Sin solapes; separación y margen respetados")
        self.c_placed = CheckRow("Todas las piezas colocadas")
        self.c_rot = CheckRow("Giros dentro de los permitidos para cada pieza")
        for c in (self.c_result, self.c_valid, self.c_placed, self.c_rot):
            checks.body.addWidget(c)
        self.verdict = style.Badge()
        checks.header.addWidget(self.verdict)
        col.addWidget(checks)

        # --- salidas -----------------------------------------------------------------
        grid = QGridLayout()
        grid.setSpacing(12)
        dxf = style.Card("DXF por plancha", "Un archivo por plancha (plancha_1.dxf, plancha_2.dxf…), en mm. "
                                            "Capas CORTE (contornos) y PLANCHA (borde).")
        self.labels = QCheckBox("Incluir nombres de las piezas (capa ETIQUETAS, apagada)")
        self.arcs = QCheckBox("Arcos y círculos en vez de segmentos (desviación ≤ 0,05 mm)")
        self.arcs.setToolTip(a_arcs.statusTip())
        _sync(self.labels, a_labels)
        _sync(self.arcs, a_arcs)
        self.b_dxf = style.button("Exportar DXF…", "primary", self.export_dxf_requested.emit)
        dxf.body.addWidget(self.labels)
        dxf.body.addWidget(self.arcs)
        dxf.body.addStretch(1)
        dxf.body.addWidget(self.b_dxf, 0, Qt.AlignmentFlag.AlignLeft)

        pdf = style.Card("PDF de taller", "Resumen con las cantidades y una página por plancha, a escala, "
                                          "con las piezas numeradas y el retal libre.")
        self.b_pdf = style.button("Exportar PDF de taller…", "primary", self.export_pdf_requested.emit)
        pdf.body.addStretch(1)
        pdf.body.addWidget(self.b_pdf, 0, Qt.AlignmentFlag.AlignLeft)

        proj = style.Card("Proyecto", "Guarda piezas, parámetros y el resultado (también el del motor, para "
                                      "poder volver a él) en un archivo .json.")
        self.project_label = style.label("", "muted", wrap=True)
        row = QHBoxLayout()
        row.addWidget(style.button("Guardar", "", self.save_requested.emit))
        row.addWidget(style.button("Guardar como…", "", self.save_as_requested.emit))
        row.addStretch(1)
        proj.body.addWidget(self.project_label)
        proj.body.addStretch(1)
        proj.body.addLayout(row)

        grid.addWidget(dxf, 0, 0)
        grid.addWidget(pdf, 0, 1)
        grid.addWidget(proj, 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        col.addLayout(grid)
        self.last = style.label("", "muted", wrap=True)
        col.addWidget(self.last)
        col.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(style.page_scroll(content))

    def update_checks(self, has_result: bool, stale: bool, issues: int, unplaced: int, rot_warnings: int,
                      project_name: str) -> None:
        if not has_result:
            self.c_result.set("bad", "Calcula el nesting (F5) para poder exportar.")
            for c in (self.c_valid, self.c_placed, self.c_rot):
                c.set("todo", "")
        else:
            self.c_result.set("warn" if stale else "ok",
                              "Has cambiado piezas o parámetros después de calcular: vuelve a calcular."
                              if stale else "")
            self.c_valid.set("bad" if issues else "ok",
                             f"{issues} problema(s): revísalos en el paso 3 (piezas con borde rojo)." if issues else "")
            self.c_placed.set("bad" if unplaced else "ok",
                              f"Faltan {unplaced} pieza(s): no caben en las planchas disponibles." if unplaced else "")
            self.c_rot.set("warn" if rot_warnings else "ok",
                           f"{rot_warnings} pieza(s) giradas a mano fuera de sus rotaciones." if rot_warnings else "")
        states = [c.state for c in (self.c_result, self.c_valid, self.c_placed, self.c_rot)]
        if not has_result:
            self.verdict.set("Sin resultado", "neutral")
        elif "bad" in states:
            self.verdict.set("Revisar antes de exportar", "bad")
        elif "warn" in states:
            self.verdict.set("Con avisos", "warn")
        else:
            self.verdict.set("Listo para exportar", "ok")
        self.b_dxf.setEnabled(has_result)
        self.b_pdf.setEnabled(has_result)
        self.project_label.setText(f"Archivo: {project_name}" if project_name else "Proyecto sin guardar.")


def _sync(box: QCheckBox, action: QAction) -> None:
    """Casilla y acción del menú siempre iguales, se cambie donde se cambie."""
    box.setChecked(action.isChecked())
    box.toggled.connect(action.setChecked)
    action.toggled.connect(box.setChecked)
