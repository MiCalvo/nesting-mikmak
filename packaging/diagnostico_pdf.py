"""Diagnóstico temporal: ¿el PDF de taller lleva texto en Windows? (según plataforma Qt)."""
import os
import sys

import pdfplumber
from shapely.geometry import box

from nesting2d.engine.nester import nest
from nesting2d.engine.params import NestParams
from nesting2d.exporters.shop_pdf import export_shop_pdf
from nesting2d.geometry import Part

out = sys.argv[1]
parts = [Part("PIEZA_A", box(0, 0, 100, 50), quantity=2)]
layout = nest(parts, NestParams(sheet_width=400, sheet_height=300, time_limit=1, seed=1))
export_shop_pdf(layout, parts, out, title="Diagnostico")
from PySide6.QtGui import QFontDatabase, QGuiApplication  # noqa: E402
print("plataforma Qt:", QGuiApplication.platformName(), "| QT_QPA_PLATFORM =", os.environ.get("QT_QPA_PLATFORM"))
print("familias de fuentes:", len(QFontDatabase.families()), QFontDatabase.families()[:5])
with pdfplumber.open(out) as pdf:
    p = pdf.pages[0]
    print("letras:", len(p.chars), "| curvas:", len(p.curves), "| rectángulos:", len(p.rects),
          "| texto:", repr((p.extract_text() or "")[:120]))
