import os

import pytest

pytest.importorskip("PySide6")


def test_autoprueba(tmp_path):
    from nesting2d.selftest import run
    informe = tmp_path / "informe.txt"
    assert run(informe) == 0
    assert "AUTOPRUEBA CORRECTA" in informe.read_text(encoding="utf-8")
