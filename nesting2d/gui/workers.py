"""Hilos de trabajo para que la ventana no se congele.

- ImportWorker: importar PDF/DXF (un plano A0 tarda unos segundos).
- NestWorker: calcular el nesting. spyrrow libera el bloqueo de Python mientras
  calcula, así que la interfaz sigue respondiendo y puede leer el progreso.

Los hilos trabajan sobre COPIAS de las piezas: el usuario puede seguir tocando la
tabla mientras se calcula sin cambiar lo que está calculando el motor.
"""
from __future__ import annotations

import threading
import traceback
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..engine.fill import fill_sheet
from ..engine.nester import nest
from ..engine.params import NestParams
from ..geometry import Part
from ..importers.contours import ImportOptions
from ..importers.dxf_import import import_dxf
from ..importers.pdf_import import import_pdf
from ..validate import check_layout


def copy_part(p: Part) -> Part:
    # los polígonos de shapely son inmutables; basta con copiar lo mutable
    return replace(p, rotations=None if p.rotations is None else list(p.rotations), extra=dict(p.extra))


class ImportWorker(QThread):
    # [(archivo, [piezas])], [avisos]
    done = Signal(object, object)
    failed = Signal(str)

    def __init__(self, files: list[str], opts: ImportOptions, parent=None,
                 layers: dict[str, list[str]] | None = None):
        super().__init__(parent)
        self.files = files
        self.opts = opts
        self.layers = layers or {}     # archivo DXF -> capas a importar (si no está: todas)

    def run(self):
        results, warnings = [], []
        try:
            for f in self.files:
                path = Path(f)
                ext = path.suffix.lower()
                if ext == ".pdf":
                    res = import_pdf(path, self.opts)
                elif ext == ".dxf":
                    res = import_dxf(path, self.opts, layers=self.layers.get(f))
                    warnings.append(f"{path.name}: el importador DXF aún no se ha probado con DXF "
                                    "reales de CAD; revisa medidas y contornos.")
                elif ext == ".dwg":
                    warnings.append(f"{path.name}: los DWG no se leen directamente. Conviértelo antes a DXF "
                                    "con ODA File Converter o LibreDWG.")
                    continue
                else:
                    warnings.append(f"{path.name}: formato no soportado (solo PDF y DXF).")
                    continue
                warnings.extend(res.warnings)
                results.append((str(path), res.parts))
        except Exception:
            self.failed.emit(traceback.format_exc())
            return
        self.done.emit(results, warnings)


class NestWorker(QThread):
    sheet_started = Signal(int, object)    # nº de plancha, función drain() de progreso
    probe = Signal(int, int, bool, bool)   # rellenar: juegos, sueltas, ¿caben?, ¿colocación final?
    done = Signal(object, object)          # Layout, problemas de validación
    failed = Signal(str)

    def __init__(self, parts: list[Part], params: NestParams, parent=None):
        super().__init__(parent)
        self.parts = [copy_part(p) for p in parts]
        self.params = replace(params)
        self._stop = threading.Event()

    def request_stop(self):
        """spyrrow no se puede interrumpir: para al acabar la plancha en curso."""
        self._stop.set()

    def run(self):
        try:
            on_sheet = lambda s, drain: self.sheet_started.emit(s, drain)  # noqa: E731
            if self.params.mode == "rellenar":
                layout = fill_sheet(self.parts, self.params, on_sheet=on_sheet, should_stop=self._stop.is_set,
                                    on_probe=lambda k, j, ok, final: self.probe.emit(k, j, ok, final))
            else:
                layout = nest(self.parts, self.params, on_sheet=on_sheet, should_stop=self._stop.is_set)
            issues = check_layout(layout)
        except Exception:
            self.failed.emit(traceback.format_exc())
            return
        self.done.emit(layout, issues)
