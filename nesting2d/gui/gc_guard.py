"""Recolección de basura de Python solo en el hilo de la interfaz.

Problema (visto en las pruebas): el recolector cíclico de Python se dispara en
el hilo que esté reservando memoria en ese momento. Si ese hilo es el de
importar o calcular y entre la basura hay objetos de Qt (una ventana o un
diálogo ya cerrados), Qt los destruye desde un hilo que no es el suyo y el
programa se cae (segmentation fault).

Solución: desactivar la recolección automática y lanzarla desde un QTimer del
hilo principal. La liberación por contador de referencias (la mayoría de los
objetos) no cambia; solo se mueve la de los ciclos.
"""
from __future__ import annotations

import gc

from PySide6.QtCore import QObject, QTimer

_guard: "_MainThreadGC | None" = None


class _MainThreadGC(QObject):
    def __init__(self, parent: QObject, interval_ms: int):
        super().__init__(parent)
        self.threshold = gc.get_threshold()
        gc.disable()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(interval_ms)

    def check(self):
        # mismas reglas que el recolector automático, por generaciones
        c0, c1, c2 = gc.get_count()
        if c0 > self.threshold[0]:
            gen = 0
            if c1 > self.threshold[1]:
                gen = 1
                if c2 > self.threshold[2]:
                    gen = 2
            gc.collect(gen)


def install(app: QObject, interval_ms: int = 500) -> None:
    """Llamar una vez, en el hilo principal, después de crear la QApplication."""
    global _guard
    if _guard is None:
        _guard = _MainThreadGC(app, interval_ms)
