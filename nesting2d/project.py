"""Archivo de proyecto (.json): piezas, parámetros y resultado.

La geometría se guarda en WKT (texto estándar de shapely), así el archivo se
puede reabrir sin los PDF/DXF originales.
"""
from __future__ import annotations

import json
from pathlib import Path

from shapely import wkt

from .engine.nester import Layout, Placement
from .engine.params import NestParams
from .geometry import Part

VERSION = 1


def save(path: str | Path, parts: list[Part], params: NestParams, layout: Layout | None = None) -> Path:
    data = {
        "version": VERSION,
        "params": params.to_dict(),
        "parts": [{
            "name": p.name, "source": p.source, "page": p.page, "scale": p.scale,
            "quantity": p.quantity, "rotations": p.rotations, "mirror": p.mirror,
            "shape": p.shape.wkt,
        } for p in parts],
        "layout": None if layout is None else {
            "sheets": layout.sheets,
            "unplaced": layout.unplaced,
            "warnings": layout.warnings,
            "placements": [{
                "part": q.part, "sheet": q.sheet, "angle": q.angle, "host": q.host,
                "polygon": q.polygon.wkt,
            } for q in layout.placements],
        },
    }
    path = Path(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load(path: str | Path) -> tuple[list[Part], NestParams, Layout | None]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    params = NestParams.from_dict(data["params"])
    parts = [Part(name=d["name"], shape=wkt.loads(d["shape"]), source=d.get("source", ""),
                  page=d.get("page"), scale=d.get("scale", 1.0), quantity=d.get("quantity", 1),
                  rotations=d.get("rotations"), mirror=d.get("mirror", False))
             for d in data["parts"]]
    layout = None
    if data.get("layout"):
        L = data["layout"]
        layout = Layout(params=params, sheets=L["sheets"], unplaced=L.get("unplaced", {}),
                        warnings=L.get("warnings", []),
                        placements=[Placement(q["part"], q["sheet"], q["angle"],
                                              wkt.loads(q["polygon"]), q.get("host"))
                                    for q in L["placements"]])
    return parts, params, layout
