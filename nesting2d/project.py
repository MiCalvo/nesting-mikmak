"""Archivo de proyecto (.json): piezas, parámetros y resultado.

La geometría se guarda en WKT (texto estándar de shapely), así el archivo se
puede reabrir sin los PDF/DXF originales.

Versión 2: además del resultado (con las ediciones manuales) guarda el
resultado tal como lo dio el motor, para poder volver a él. Los archivos de la
versión 1 se siguen leyendo (sin resultado del motor aparte).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from shapely import wkt

from .engine.nester import Layout, Placement
from .engine.params import NestParams
from .geometry import Part

VERSION = 2


@dataclass
class ProjectData:
    parts: list[Part]
    params: NestParams
    layout: Layout | None          # resultado actual, con las ediciones manuales
    engine_layout: Layout | None   # resultado tal como salió del motor


def _layout_to_dict(layout: Layout) -> dict:
    return {
        "sheets": layout.sheets,
        "unplaced": layout.unplaced,
        "warnings": layout.warnings,
        "placements": [{
            "part": q.part, "sheet": q.sheet, "angle": q.angle, "host": q.host,
            "polygon": q.polygon.wkt,
        } for q in layout.placements],
    }


def _layout_from_dict(L: dict, params: NestParams) -> Layout:
    return Layout(params=params, sheets=L["sheets"], unplaced=L.get("unplaced", {}),
                  warnings=L.get("warnings", []),
                  placements=[Placement(q["part"], q["sheet"], q["angle"],
                                        wkt.loads(q["polygon"]), q.get("host"))
                              for q in L["placements"]])


def save(path: str | Path, parts: list[Part], params: NestParams, layout: Layout | None = None,
         engine_layout: Layout | None = None) -> Path:
    data = {
        "version": VERSION,
        "params": params.to_dict(),
        "parts": [{
            "name": p.name, "source": p.source, "page": p.page, "scale": p.scale,
            "quantity": p.quantity, "rotations": p.rotations, "mirror": p.mirror,
            "shape": p.shape.wkt,
        } for p in parts],
        "layout": None if layout is None else _layout_to_dict(layout),
        "engine_layout": None if layout is None or engine_layout is None else _layout_to_dict(engine_layout),
    }
    path = Path(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_project(path: str | Path) -> ProjectData:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version", 1) > VERSION:
        raise ValueError(f"el proyecto es de una versión más nueva de la app ({data['version']})")
    params = NestParams.from_dict(data["params"])
    parts = [Part(name=d["name"], shape=wkt.loads(d["shape"]), source=d.get("source", ""),
                  page=d.get("page"), scale=d.get("scale", 1.0), quantity=d.get("quantity", 1),
                  rotations=d.get("rotations"), mirror=d.get("mirror", False))
             for d in data["parts"]]
    layout = _layout_from_dict(data["layout"], params) if data.get("layout") else None
    engine = _layout_from_dict(data["engine_layout"], params) if data.get("engine_layout") else None
    return ProjectData(parts, params, layout, engine)


def load(path: str | Path) -> tuple[list[Part], NestParams, Layout | None]:
    d = load_project(path)
    return d.parts, d.params, d.layout
