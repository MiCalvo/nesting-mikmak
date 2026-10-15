"""Línea de comandos.

Ejemplos (desde la carpeta del proyecto):

  python -m nesting2d gui                      (interfaz gráfica)

  python -m nesting2d piezas datos_prueba/RIGCCP*.pdf

  python -m nesting2d nest datos_prueba/RIGCCP*.pdf ^
      --cantidad RIGCCP0020=4 RIGCCP0019=4 RIGCCP0018=4 RIGCCP0016=2 RIGCCP0017=2 ^
      --plancha 1200x1000 --separacion 5 --margen 5 --finura normal --salida salida

Tiempo de cálculo: automático según copias y rotaciones (--finura rapido, normal
o fino; normal por defecto), o fijo con --tiempo SEGUNDOS.

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
from .engine.timing import FINENESS, describe, sheet_time
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
        elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"):
            print(f"AVISO {f.name}: las imágenes necesitan elegir contornos y escala; "
                  "impórtalas desde la interfaz (python -m nesting2d gui).", file=sys.stderr)
            continue
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

    g = sub.add_parser("gui", help="abre la interfaz gráfica")
    g.add_argument("proyecto", nargs="?", help="proyecto .json para abrir al arrancar")

    t = sub.add_parser("autoprueba", help="comprueba que motor, importadores, exportadores y Qt funcionan")
    t.add_argument("--informe", help="guarda también el resultado en este archivo de texto")

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
    b.add_argument("--tiempo", type=int, default=None,
                   help="segundos FIJOS de cálculo por plancha (si no se pone: automático)")
    b.add_argument("--finura", choices=list(FINENESS), default="normal",
                   help="modo automático: rapido, normal (por defecto) o fino")
    b.add_argument("--semilla", type=int, default=None)
    b.add_argument("--rellenar", action="store_true",
                   help="máximo de juegos en UNA plancha; --cantidad se lee como proporción")
    b.add_argument("--relleno", default=None, metavar="NOMBRE",
                   help="con --rellenar: referencia para el hueco que dejen los juegos completos")
    b.add_argument("--etiquetas", action="store_true", help="añade la capa ETIQUETAS al DXF")
    b.add_argument("--pdf-taller", action="store_true", help="genera también el PDF de taller (necesita PySide6)")
    b.add_argument("--arcos", action="store_true", help="DXF con arcos y círculos en vez de segmentos")
    b.add_argument("--material", default="", help="informativo, sale en el PDF de taller")
    b.add_argument("--espesor", default="", help="informativo, sale en el PDF de taller")
    b.add_argument("--salida", default="salida")

    args = ap.parse_args(argv)
    if args.cmd == "autoprueba":
        from .selftest import run
        return run(args.informe)
    if args.cmd == "gui":
        try:
            from .gui.app import main as gui_main
        except ImportError as e:
            print(f"No se puede abrir la interfaz ({e}). Instala PySide6: pip install -e .[gui]", file=sys.stderr)
            return 1
        return gui_main([sys.argv[0]] + ([args.proyecto] if args.proyecto else []))

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
        time_limit=args.tiempo, fineness=args.finura, seed=args.semilla,
        material=args.material, thickness=args.espesor,
        mode="rellenar" if args.rellenar else "cantidades", fill_with=args.relleno)
    if args.relleno and args.relleno not in {p.name for p in parts}:
        print(f"--relleno: no hay ninguna pieza llamada {args.relleno}", file=sys.stderr)
        return 1
    total = sum(p.quantity for p in parts)
    if args.rellenar:
        from .engine.fill import describe_fill, fill_sheet
        print("Rellenar: buscando cuántos juegos caben en una plancha…")
        layout = fill_sheet(parts, params, on_probe=lambda k, j, ok, final: print(
            f"  {'final' if final else 'intento'}: {k} juegos + {j} sueltas -> {'caben' if ok else 'no caben'}"))
        print(f"Caben al menos {describe_fill(layout.fill)}")
    else:
        est = sheet_time(params.time_limit, params.fineness,
                         [(p.quantity, p.rotations if p.rotations is not None else params.angles()) for p in parts])
        print(f"Calculando {total} piezas, tiempo {describe(params.time_limit, params.fineness)}: "
              f"~{est} s la primera plancha…")
        layout = nest(parts, params)

    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)
    issues = check_layout(layout)
    for s in range(layout.sheets):
        st = layout.stats(s)
        dxf = export_sheet(layout, s, out / f"plancha_{s + 1}.dxf", labels=args.etiquetas, arcs=args.arcos)
        try:
            from .exporters.preview import sheet_png
            sheet_png(layout, s, out / f"plancha_{s + 1}.png")
        except ImportError:
            pass
        print(f"Plancha {s + 1}: {len(layout.on_sheet(s))} piezas, largo ocupado {st['used_length']:.1f} mm, "
              f"zona libre {st['free'][0]:.0f} x {st['free'][1]:.0f} mm, "
              f"aprovechamiento {100 * st['utilization']:.1f} % -> {dxf}")
    project.save(out / "proyecto.json", parts, params, layout)
    if args.pdf_taller:
        try:
            from .exporters.shop_pdf import export_shop_pdf
        except ImportError:
            print("AVISO: el PDF de taller necesita PySide6 (pip install -e .[gui]).", file=sys.stderr)
        else:
            pdf = export_shop_pdf(layout, parts, out / "taller.pdf", title=out.name, issues_count=len(issues))
            print(f"PDF de taller: {pdf}")
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
