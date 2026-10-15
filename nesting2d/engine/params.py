"""Parámetros de un proyecto de nesting (ver especificación, sección Parámetros)."""
from __future__ import annotations

from dataclasses import asdict, dataclass

# Lado hacia el que se compactan las piezas -> giro del "marco de tira" (grados)
SIDES = {"izquierda": 0, "abajo": 90, "derecha": 180, "arriba": 270}


@dataclass
class NestParams:
    sheet_width: float = 1200.0       # mm, eje X de la plancha
    sheet_height: float = 1000.0      # mm, eje Y de la plancha
    max_sheets: int | None = None     # None = ilimitado
    separation: float = 5.0           # mm entre piezas (provisional hasta confirmar con el proveedor)
    margin: float = 5.0               # mm al borde de la plancha (provisional)
    rotation_step: float | None = 90.0  # grados; None = rotación libre
    part_in_part: bool = True
    compact_side: str = "izquierda"
    time_limit: int | None = None     # s de cálculo POR PLANCHA; None = automático (engine/timing.py)
    fineness: str = "normal"          # modo automático: "rapido", "normal" o "fino"
    mode: str = "cantidades"          # "cantidades" (las pedidas) o "rellenar" (máximo en UNA plancha)
    fill_with: str | None = None      # rellenar: referencia para el hueco que dejen los juegos
    seed: int | None = None           # fijarla repite el mismo resultado
    workers: int | None = None        # hilos del motor; None = todos los núcleos
    material: str = ""                # informativo (PDF de taller)
    thickness: str = ""               # informativo
    # Nota: el "espejo permitido para encajar" es v2 (spyrrow no lo soporta).
    # En v1 el espejo es una propiedad de cada pieza (Part.mirror), decidida a mano.

    def angles(self) -> list[float] | None:
        """Ángulos permitidos por defecto, o None si la rotación es libre."""
        if self.rotation_step is None:
            return None
        n = max(1, int(round(360.0 / self.rotation_step)))
        return [round(i * self.rotation_step, 6) % 360 for i in range(n)]

    def frame_rotation(self) -> int:
        try:
            return SIDES[self.compact_side]
        except KeyError:
            raise ValueError(f"compact_side debe ser uno de {list(SIDES)}") from None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "NestParams":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
