import os
import sys
from pathlib import Path

import pytest

# Pruebas de interfaz sin pantalla. En Linux, con la plataforma "offscreen". En
# Windows NO: ahí "offscreen" no encuentra ninguna fuente y el PDF de taller sale
# sin texto (comprobado en GitHub Actions); la plataforma normal sí funciona.
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
