"""Autoprueba: comprueba que todas las piezas de la app funcionan juntas.

Pensada sobre todo para el ejecutable de Windows (PyInstaller): confirma que el
paquete incluye y carga el motor compilado (spyrrow), shapely, ezdxf,
pdfplumber y Qt. No necesita archivos externos: genera sus propias piezas.

  Nesting2D.exe autoprueba --informe informe.txt
  python -m nesting2d autoprueba
"""
from __future__ import annotations

import tempfile
import time
import traceback
from pathlib import Path


def run(report: str | Path | None = None) -> int:
    lines: list[str] = []

    def log(msg: str):
        lines.append(msg)
        try:
            print(msg)
        except UnicodeEncodeError:   # consola de Windows sin UTF-8
            print(msg.encode("ascii", "replace").decode("ascii"))

    ok = True
    t0 = time.time()
    try:
        import platform
        import sys

        log(f"Python {sys.version.split()[0]} en {platform.platform()}"
            + (" (ejecutable empaquetado)" if getattr(sys, "frozen", False) else ""))
        import ezdxf
        import pdfplumber
        import shapely
        import spyrrow  # noqa: F401  (motor compilado)
        from importlib.metadata import PackageNotFoundError, version

        def ver(pkg):
            try:
                return version(pkg)
            except PackageNotFoundError:   # en el ejecutable puede faltar la metadata
                return "?"
        log(f"spyrrow {ver('spyrrow')} · shapely {shapely.__version__} · ezdxf {ezdxf.__version__} · "
            f"pdfplumber {ver('pdfplumber')}")

        from shapely.geometry import box

        from .engine.nester import nest
        from .engine.params import NestParams
        from .exporters.dxf_export import export_sheet
        from .geometry import Part
        from .importers.dxf_import import import_dxf
        from .importers.pdf_import import import_pdf
        from .validate import check_layout

        parts = [Part("marco", box(0, 0, 100, 80).difference(box(15, 15, 85, 65)), quantity=2),
                 Part("taco", box(0, 0, 30, 20), quantity=3)]
        layout = nest(parts, NestParams(sheet_width=400, sheet_height=300, time_limit=2, seed=1))
        issues = check_layout(layout)
        log(f"Nesting: {len(layout.placements)} piezas en {layout.sheets} plancha(s), "
            f"{sum(1 for q in layout.placements if q.host is not None)} dentro de huecos, "
            f"{len(issues)} problemas de validación")
        ok &= len(layout.placements) == 5 and not issues

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dxf = export_sheet(layout, 0, tmp / "p1.dxf")
            back = import_dxf(dxf, layers=["CORTE"])
            log(f"DXF: exportado y reimportado, {len(back.parts)} piezas")
            ok &= len(back.parts) == len(layout.on_sheet(0))

            from .exporters.shop_pdf import export_shop_pdf
            pdf = export_shop_pdf(layout, parts, tmp / "taller.pdf", title="Autoprueba")
            with pdfplumber.open(pdf) as doc:
                pages = len(doc.pages)
            log(f"PDF de taller (Qt): {pages} páginas")
            ok &= pages == 1 + layout.sheets
            res = import_pdf(pdf, pages=[2])
            log(f"PDF: reimportado con pdfplumber, {len(res.parts)} contornos")
            ok &= len(res.parts) > 0

        from PySide6 import __version__ as pyside_version
        log(f"PySide6 {pyside_version}")
    except Exception:
        ok = False
        log(traceback.format_exc())

    log(f"{'AUTOPRUEBA CORRECTA' if ok else 'AUTOPRUEBA FALLIDA'} ({time.time() - t0:.1f} s)")
    if report:
        Path(report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1
