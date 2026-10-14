from pathlib import Path

import pytest

from nesting2d.importers.pdf_import import import_pdf

DATA = Path(__file__).resolve().parent.parent / "datos_prueba"

# Pedido real del primer proyecto (juntas de mica)
QTY = {"RIGCCP0020": 4, "RIGCCP0019": 4, "RIGCCP0018": 4, "RIGCCP0016": 2, "RIGCCP0017": 2}


@pytest.fixture
def gaskets():
    parts = []
    for name, q in QTY.items():
        p = import_pdf(DATA / f"{name}.pdf").parts[0]
        p.quantity = q
        parts.append(p)
    return parts
