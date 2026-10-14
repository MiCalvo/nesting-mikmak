"""Línea de comandos (fase 1, antes de la interfaz).

Ejemplos (desde la carpeta del proyecto):

  python -m nesting2d piezas datos_prueba/RIGCCP*.pdf

  python -m nesting2d nest datos_prueba/RIGCCP*.pdf ^
      --cantidad RIGCCP0020=4 RIGCCP0019=4 RIGCCP0018=4 RIGCCP0016=2 RIGCCP0017=2 ^
      --plancha 1200x1000 --separacion 5 --margen 5 --tiempo 30 --salida salida

(en PowerShell el salto de línea es ` en lugar de ^; en Windows los comodines
como RIGCCP*.pdf los expande la propia app)
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

from .engine.nester import nest
from .engine.params import SIDES, NestParams
from .exporters.dxf_export import export_sheet
from .geometry import Part
from .importers.contours import ImportOptions
from .importers.dxf_import import import_dxf
from .importers.pdf_import import import_pdf
from .validate import check_layout
from . import project


def _expand(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pat in patterns:
        hits = sorted(glob.glob(pat)) or [pat]
        files.extend(Path(h) for h in hits)
    return files


def load_parts(patterns: list[str], opts: ImportOptions) -> list[Part]:
    parts: list[Part] = []
    for f in _expand(patterns):
        ext = f.suffix.lower()
        if ext == ".pdf":
            res = import_pdf(f, opts)
        elif ext == ".dxf":
            res = import_dxf(f, opts)
        elif ext == ".dwg":
            print(f"AVISO {f.name}: DWG no se lee directamente. Conviértelo a DXF "
                  "(ODA File Converter o LibreDWG).", file=sys.stderr)
            continue
        else:
            print(f"AVISO {f.name}: formato no soportado.", file=sys.stderr)
            continue
        for w in res.warnings:
            print(f"AVISO {w}", file=sys.stderr)
        parts.extend(res.parts)
    return parts


def _sheet(s: str) -> tuple[float, float]:
    w, h = s.lower().replace("×", "x").split("x")
    return float(w), float(h)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nesting2d", description="Nesting 2D: importar, colocar y exportar.")
    ap.add_argument("--tolerancia", type=float, default=0.01, help="tolerancia de unión de trazos, mm")
    ap.add_argument("--area-minima", type=float, default=1.0, help="área mínima de pieza, mm²")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("piezas", help="importa y lista las piezas con sus medidas")
    a.add_argument("archivos", nargs="+")

    b = sub.add_parser("nest", help="calcula el nesting y exporta DXF + PNG + proyecto")
    b.add_argument("archivos", nargs="+")
    b.add_argument("--cantidad", nargs="*", default=[], metavar="NOMBRE=N")
    b.add_argument("--plancha", type=_sheet, default=(1200.0, 1000.0), metavar="ANCHOxALTO")
    b.add_argument("--max-planchas", type=int, default=None)
    b.add_argument("--separacion", type=float, default=5.0)
    b.add_argument("--margen", type=float, default=5.0)
    b.add_argument("--rotacion", default="90", help="paso en grados, o 'libre'")
    b.add_argument("--lado", choices=list(SIDES), default="izquierda")
    b.add_argument("--sin-pieza-en-pieza", action="store_true")
    b.add_argument("--tiempo", type=int, default=30, help="segundos de cálculo por plancha")
    b.add_argument("--semilla", type=int, default=None)
    b.add_argument("--etiquetas", action="store_true", help="añade la capa ETIQUETAS al DXF")
    b.add_argument("--salida", default="salida")

    args = ap.parse_args(argv)
    opts = ImportOptions(join_tolerance=args.tolerancia, min_area=args.area_minima)
    parts = load_parts(args.archivos, opts)
    if not parts:
        print("No se importó ninguna pieza.", file=sys.stderr)
        return 1

    if args.cmd == "piezas":
        for p in parts:
            w, h = p.size
            print(f"{p.name:40s} {w:9.2f} x {h:9.2f} mm  huecos {len(p.geometry().interiors):3d}  "
                  f"área {p.area:10.1f} mm²")
        return 0

    qty = {}
    for item in args.cantidad:
        name, _, n = item.partition("=")
        qty[name] = int(n)
    unknown = set(qty) - {p.name for p in parts}
    if unknown:
        print(f"Cantidades para piezas que no existen: {sorted(unknown)}", file=sys.stderr)
        return 1
    for p in parts:
        p.quantity = qty.get(p.name, 1)

    params = NestParams(
        sheet_width=args.plancha[0], sheet_height=args.plancha[1], max_sheets=args.max_planchas,
        separation=args.separacion, margin=args.margen,
        rotation_step=None if args.rotacion == "libre" else float(args.rotacion),
        part_in_part=not args.sin_pieza_en_pieza, compact_side=args.lado,
        time_limit=args.tiempo, seed=args.semilla)
    total = sum(p.quantity for p in parts)
    print(f"Calculando {total} piezas, hasta {args.tiempo} s por plancha…")
    layout = nest(parts, params)

    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)
    issues = check_layout(layout)
    for s in range(layout.sheets):
        st = layout.stats(s)
        dxf = export_sheet(layout, s, out / f"plancha_{s + 1}.dxf", labels=args.etiquetas)
        try:
            from .exporters.preview import sheet_png
            sheet_png(layout, s, out / f"plancha_{s + 1}.png")
        except ImportError:
            pass
        print(f"Plancha {s + 1}: {len(layout.on_sheet(s))} piezas, largo ocupado {st['used_length']:.1f} mm, "
              f"zona libre {st['free'][0]:.0f} x {st['free'][1]:.0f} mm, "
              f"aprovechamiento {100 * st['utilization']:.1f} % -> {dxf}")
    project.save(out / "proyecto.json", parts, params, layout)
    for w in layout.warnings:
        print(f"AVISO {w}", file=sys.stderr)
    if issues:
        print(f"ERROR de validación: {len(issues)} problemas", file=sys.stderr)
        for i in issues[:10]:
            print(f"  {i}", file=sys.stderr)
        return 2
    print("Validación: sin solapes, separación y margen respetados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
