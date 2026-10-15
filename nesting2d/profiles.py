"""Perfiles de material reutilizables (ver especificación, «Parámetros»).

Un perfil guarda plancha, separación y margen (y, como información, material y
espesor). Al crear un proyecto se elige un perfil y sus valores se COPIAN al
proyecto, donde se pueden cambiar sin tocar el perfil.

Se guardan en un .json de la aplicación (la interfaz decide la ruta).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .engine.params import NestParams


@dataclass
class Profile:
    name: str
    sheet_width: float = 1200.0
    sheet_height: float = 1000.0
    separation: float = 5.0
    margin: float = 5.0
    material: str = ""
    thickness: str = ""

    def apply_to(self, params: NestParams) -> NestParams:
        """Copia del proyecto con los valores del perfil."""
        return replace(params, sheet_width=self.sheet_width, sheet_height=self.sheet_height,
                       separation=self.separation, margin=self.margin,
                       material=self.material, thickness=self.thickness)

    @classmethod
    def from_params(cls, name: str, params: NestParams) -> "Profile":
        return cls(name, params.sheet_width, params.sheet_height, params.separation, params.margin,
                   params.material, params.thickness)


def default_profiles() -> list[Profile]:
    return [Profile("Mica 1200 × 1000 (separación y margen provisionales)", material="Mica")]


def load_profiles(path: str | Path) -> list[Profile]:
    """Perfiles guardados; si el archivo no existe, los de serie."""
    path = Path(path)
    if not path.exists():
        return default_profiles()
    data = json.loads(path.read_text(encoding="utf-8"))
    fields = Profile.__dataclass_fields__
    return [Profile(**{k: v for k, v in d.items() if k in fields}) for d in data.get("profiles", [])]


def save_profiles(path: str | Path, profiles: list[Profile]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "profiles": [asdict(p) for p in profiles]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
