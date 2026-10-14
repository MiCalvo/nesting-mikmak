import pytest

from nesting2d.geometry import scale_from_measure
from nesting2d.importers.pdf_import import import_pdf

from .conftest import DATA

# Medidas comprobadas el 14/10/2026 (PDF A4 a escala 1:1 exportados desde NX)
EXPECTED = {
    "RIGCCP0016": (124.0, 72.7, 11),
    "RIGCCP0017": (58.2, 72.7, 5),
    "RIGCCP0018": (93.0, 119.0, 15),
    "RIGCCP0019": (167.0, 92.0, 15),
    "RIGCCP0020": (69.0, 95.0, 1),
}


@pytest.mark.parametrize("name", EXPECTED)
def test_gasket_dimensions_and_holes(name):
    res = import_pdf(DATA / f"{name}.pdf")
    assert res.warnings == []
    assert len(res.parts) == 1
    p = res.parts[0]
    w, h, holes = EXPECTED[name]
    assert p.name == name
    assert p.size == pytest.approx((w, h), abs=0.05)
    assert len(p.geometry().interiors) == holes
    assert p.geometry().is_valid


def test_pdf_y_axis_is_not_flipped(tmp_path):
    """pdfplumber da Y hacia abajo; el importador debe invertirla.
    Una L con su masa abajo a la izquierda tiene que seguir así."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(4, 4))
    fig.patch.set_visible(False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.patch.set_visible(False)
    L = [(10, 10), (90, 10), (90, 30), (30, 30), (30, 90), (10, 90), (10, 10)]
    ax.plot(*zip(*L), color="k", lw=0.5)
    f = tmp_path / "L.pdf"
    fig.savefig(f)
    plt.close(fig)

    p = import_pdf(f).parts[0]
    g = p.geometry()
    w, h = p.size
    assert g.centroid.x < w / 2 and g.centroid.y < h / 2


def test_multiview_drawing_imports_frame_and_letters_too():
    """Un plano con varias vistas genera también contornos falsos (marco, letras):
    por eso la interfaz tendrá selección manual de contornos."""
    res = import_pdf(DATA / "RIG23P0054_plano_varias_vistas.pdf", pages=[2])
    assert len(res.parts) > 10
    sizes = [p.size for p in res.parts]
    # los anillos de Ø220 y Ø253 de las vistas a escala 1:1 aparecen con su medida real
    assert any(abs(w - 221.0) < 0.05 and abs(h - 221.0) < 0.05 for w, h in sizes)


def test_scale_from_measure():
    assert scale_from_measure(50.0, 100.0) == pytest.approx(2.0)
    with pytest.raises(ValueError):
        scale_from_measure(0, 10)
