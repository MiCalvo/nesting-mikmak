"""Importación de imágenes (capturas de pantalla y escaneos) vectorizando con OpenCV.

Alcance acordado con Mikel (15/10/2026): capturas de pantalla y escaneos.
Las fotos con perspectiva (que exigirían corregirla) quedan fuera por ahora.

Pasos:
1. Leer con Pillow (lee los ppp de los escaneos; y así no dependemos de
   cv2.imread con rutas no ASCII en Windows). Se respeta la orientación EXIF y
   la transparencia se pone sobre blanco.
2. Pasar a blanco y negro con un umbral (automático por Otsu o el que elija el
   usuario).
3. Sacar las zonas cerradas como "caras", igual que en PDF/DXF, para el diálogo
   de selección de contornos:
   - "lineas" (captura de un plano): los trazos oscuros son BORDES. Las caras
     son las zonas claras cerradas, ampliadas hasta el centro del trazo.
   - "silueta" (pieza oscura sobre fondo claro) y "silueta_clara" (al revés):
     las caras son las zonas de cada color; el borde es el de los píxeles.

Las caras salen en PÍXELES con la Y hacia arriba; la escala (mm por píxel) la
aplica quien crea las piezas. La precisión está limitada por la resolución:
del orden de ±1 píxel.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
MODES = ("lineas", "silueta", "silueta_clara")
MIN_DPI_FOR_SCALE = 150   # por debajo, los ppp suelen ser los de la pantalla, no una escala real


@dataclass
class RasterImage:
    gray: np.ndarray          # (alto, ancho) uint8, 0 = negro
    dpi: float | None         # ppp del archivo, si los declara

    @property
    def height(self) -> int:
        return self.gray.shape[0]

    @property
    def width(self) -> int:
        return self.gray.shape[1]

    def mm_per_px_from_dpi(self) -> float | None:
        """Escala a partir de los ppp, solo si parecen de un escáner (≥ 150 ppp)."""
        if self.dpi and self.dpi >= MIN_DPI_FOR_SCALE:
            return 25.4 / self.dpi
        return None


def is_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def load_image(path: str | Path) -> RasterImage:
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        dpi = im.info.get("dpi")
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            im = Image.alpha_composite(white, rgba)
        gray = np.array(im.convert("L"), dtype=np.uint8)
    d = None
    if dpi:
        try:
            d = round(float(dpi[0]), 2)
        except (TypeError, ValueError, IndexError):
            d = None
        if d is not None and d <= 1:
            d = None
    return RasterImage(gray, d)


def otsu_threshold(gray: np.ndarray) -> int:
    import cv2
    t, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return int(t)


def dark_mask(gray: np.ndarray, threshold: int) -> np.ndarray:
    """255 donde el píxel es oscuro (≤ umbral), 0 donde es claro."""
    return np.where(gray <= threshold, 255, 0).astype(np.uint8)


def stroke_width(dark: np.ndarray) -> float:
    """Grosor típico de los trazos oscuros, en píxeles (mediana sobre sus ejes)."""
    import cv2
    if not dark.any():
        return 1.0
    dist = cv2.distanceTransform(dark, cv2.DIST_L2, 3)
    ridge = dist[(dist > 0) & (dist >= cv2.dilate(dist, np.ones((3, 3), np.uint8)))]
    if ridge.size == 0:
        return 1.0
    # distancia en el eje d ⇒ grosor ≈ 2d − 0,5 (error de ±0,5 px entre pares e impares)
    return max(1.0, 2 * float(np.median(ridge)) - 0.5)


def _contour_polygon(c: np.ndarray, height: int, eps: float) -> Polygon | None:
    import cv2
    if eps > 0:
        c = cv2.approxPolyDP(c, eps, True)
    pts = c.reshape(-1, 2).astype(float)
    if len(pts) < 3:
        return None
    pts[:, 1] = height - pts[:, 1]            # Y hacia arriba
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if isinstance(poly, Polygon) and not poly.is_empty else None


def _regions(mask: np.ndarray, height: int, eps: float, skip_border: bool) -> list[tuple[Polygon, bool]]:
    """Cada componente de `mask` (255) como polígono con sus huecos, y también
    cada hueco como región (con las componentes que tenga dentro como huecos).

    Con `skip_border`, se descartan las componentes que tocan el borde de la
    imagen (en el modo líneas, el fondo exterior no es una zona cerrada).

    Devuelve (región, ¿es componente?): las componentes pasan por el centro de
    sus propios píxeles de borde; los huecos, por el de los píxeles de la
    componente que los rodea (medio píxel por fuera del hueco)."""
    import cv2
    contours, hier = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []
    hier = hier[0]
    h_img, w_img = mask.shape
    polys = [_contour_polygon(c, height, eps) for c in contours]

    def depth(i):
        d = 0
        while hier[i][3] != -1:
            i = hier[i][3]
            d += 1
        return d

    def children(i):
        out, j = [], hier[i][2]
        while j != -1:
            out.append(j)
            j = hier[j][0]
        return out

    regions = []
    for i, c in enumerate(contours):
        if polys[i] is None:
            continue
        is_component = depth(i) % 2 == 0
        if skip_border and is_component:
            x, y, w, h = cv2.boundingRect(c)
            if x <= 0 or y <= 0 or x + w >= w_img or y + h >= h_img:
                continue
        if skip_border and not is_component:
            continue        # en el modo líneas solo interesan las zonas claras
        holes = [polys[j] for j in children(i) if polys[j] is not None]
        region = polys[i]
        for hole in holes:
            region = region.difference(hole)
        if isinstance(region, Polygon) and not region.is_empty:
            regions.append((region, is_component))
        elif hasattr(region, "geoms"):
            regions.extend((g, is_component) for g in region.geoms if isinstance(g, Polygon) and not g.is_empty)
    return regions


def image_faces(img: RasterImage, mode: str = "lineas", threshold: int | None = None,
                min_area_px: float = 9.0, eps_px: float = 0.4) -> tuple[list[Polygon], int, float]:
    """Caras cerradas de la imagen, en píxeles (Y hacia arriba).

    Devuelve (caras, umbral usado, grosor de trazo estimado en píxeles)."""
    if mode not in MODES:
        raise ValueError(f"modo debe ser uno de {MODES}")
    t = otsu_threshold(img.gray) if threshold is None else int(threshold)
    dark = dark_mask(img.gray, t)
    H = img.height
    width = 0.0
    if mode == "lineas":
        width = stroke_width(dark)
        light = 255 - dark
        # los contornos pasan por el centro de los píxeles del borde: medio píxel
        # hasta el borde del trazo y medio trazo más hasta su eje
        grow = 0.5 + width / 2
        faces = [f.buffer(grow, join_style="mitre", mitre_limit=2.0)
                 for f, _ in _regions(light, H, eps_px, skip_border=True)]
    else:
        mask = dark if mode == "silueta" else 255 - dark
        faces = [f.buffer(0.5 if comp else -0.5, join_style="mitre", mitre_limit=2.0)
                 for f, comp in _regions(mask, H, eps_px, skip_border=False)]
    faces = [f for f in faces if isinstance(f, Polygon) and f.area >= min_area_px]
    return faces, t, width
