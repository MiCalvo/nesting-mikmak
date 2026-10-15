"""Importación de imágenes (capturas y escaneos) con imágenes sintéticas."""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from PIL import Image  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from nesting2d.importers.image_import import (RasterImage, image_faces, is_image,  # noqa: E402
                                              load_image, otsu_threshold)

DPI = 300
S = 25.4 / DPI          # mm por píxel


def drawing(lw=2, filled=False, invert=False):
    """Placa de 100 × 60 mm con un taladro de Ø20 mm, a 300 ppp.
    Como dibujo de líneas (trazo de `lw`) o como silueta rellena."""
    img = np.full((1000, 1400), 255, np.uint8)
    x0, y0 = 200, 200
    w, h = 100 / S, 60 / S
    cx, cy, r = x0 + w / 2, y0 + h / 2, 10 / S
    f = 16    # coordenadas con 4 bits de fracción (shift=4)
    rect = np.array([[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]) * f
    if filled:
        cv2.fillPoly(img, [np.round(rect).astype(np.int32)], 0, cv2.LINE_8, shift=4)
        cv2.circle(img, (round(cx * f), round(cy * f)), round(r * f), 255, -1, cv2.LINE_8, shift=4)
    else:
        cv2.polylines(img, [np.round(rect).astype(np.int32)], True, 0, lw, cv2.LINE_8, shift=4)
        cv2.circle(img, (round(cx * f), round(cy * f)), round(r * f), 0, lw, cv2.LINE_8, shift=4)
    return 255 - img if invert else img


def plate_from_faces(faces):
    """Lo que haría el usuario con una ventana alrededor: par-impar entre las caras."""
    from shapely.geometry import Polygon
    shells = [Polygon(f.exterior) for f in faces]
    material = [f for i, f in enumerate(faces)
                if sum(1 for j, s in enumerate(shells) if j != i and s.contains(f.representative_point())) % 2 == 0]
    return unary_union(material)


@pytest.mark.parametrize("lw", [1, 2, 3])
def test_line_drawing_dimensions(lw):
    faces, t, width = image_faces(RasterImage(drawing(lw), DPI), "lineas")
    plate = plate_from_faces(faces)
    minx, miny, maxx, maxy = plate.bounds
    # ±1 px aprox. (0,085 mm a 300 ppp)
    assert (maxx - minx) * S == pytest.approx(100, abs=0.15)
    assert (maxy - miny) * S == pytest.approx(60, abs=0.15)
    assert len(plate.interiors) == 1
    hb = plate.interiors[0].bounds
    assert (hb[2] - hb[0]) * S == pytest.approx(20, abs=0.2)


@pytest.mark.parametrize("mode,invert", [("silueta", False), ("silueta_clara", True)])
def test_silhouette_dimensions(mode, invert):
    faces, _, _ = image_faces(RasterImage(drawing(filled=True, invert=invert), DPI), mode)
    plate = plate_from_faces(faces)
    minx, miny, maxx, maxy = plate.bounds
    assert (maxx - minx) * S == pytest.approx(100, abs=0.15)
    assert (maxy - miny) * S == pytest.approx(60, abs=0.15)
    assert len(plate.interiors) == 1


def test_background_is_not_a_face_and_y_points_up():
    faces, _, _ = image_faces(RasterImage(drawing(), DPI), "lineas")
    assert len(faces) == 2                      # interior de la placa y disco del taladro
    # la placa está arriba en la imagen (filas 200..909 de 1000) -> abajo con Y hacia arriba
    assert max(f.bounds[3] for f in faces) < 1000 - 200 + 5


def test_load_image_reads_dpi_transparency_and_unicode_path(tmp_path):
    img = drawing()
    rgba = np.dstack([img, img, img, np.where(img < 128, 255, 0).astype(np.uint8)])   # fondo transparente
    path = tmp_path / "junta_ñ_pequeña.png"
    Image.fromarray(rgba, "RGBA").save(path, dpi=(DPI, DPI))
    r = load_image(path)
    assert r.dpi == pytest.approx(DPI, abs=0.5)
    assert r.mm_per_px_from_dpi() == pytest.approx(S, rel=1e-3)
    assert r.gray[5, 5] == 255                  # lo transparente queda blanco
    assert is_image(path) and not is_image(tmp_path / "a.pdf")


def test_screen_dpi_is_not_used_as_scale(tmp_path):
    path = tmp_path / "captura.png"
    Image.fromarray(drawing()).save(path, dpi=(96, 96))
    assert load_image(path).mm_per_px_from_dpi() is None


def test_otsu_on_grey_scan():
    noisy = drawing().astype(np.int16)
    noisy = np.clip(np.where(noisy > 128, 235, 40) + np.random.default_rng(0).integers(-15, 15, noisy.shape),
                    0, 255).astype(np.uint8)
    t = otsu_threshold(noisy)
    # tinta 25..54, papel 220..249: el umbral tiene que separarlas (Otsu se arrima a la
    # clase pequeña, la tinta, cuando hay mucho más papel)
    assert noisy[noisy < 128].max() <= t < noisy[noisy >= 128].min()
    faces, _, _ = image_faces(RasterImage(noisy, DPI), "lineas")
    plate = plate_from_faces(faces)
    assert (plate.bounds[2] - plate.bounds[0]) * S == pytest.approx(100, abs=0.2)
