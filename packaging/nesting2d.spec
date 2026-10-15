# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: dos ejecutables en una misma carpeta, compartiendo librerías.
#   pyinstaller --noconfirm packaging/nesting2d.spec
# Resultado: dist/Nesting2D/Nesting2D.exe (ventana) y dist/Nesting2D/nesting2d-cli.exe (consola).
import os

from PyInstaller.utils.hooks import copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# metadata de los paquetes (la autoprueba muestra sus versiones)
datas = []
for dist in ("spyrrow", "pdfplumber", "pdfminer.six", "shapely", "ezdxf", "PySide6"):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

EXCLUDES = ["matplotlib", "tkinter", "IPython", "pytest", "PySide6.QtWebEngineCore",
            "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml"]


def analysis(script):
    return Analysis([os.path.join(SPECPATH, script)], pathex=[ROOT], datas=datas,
                    hiddenimports=["spyrrow"], excludes=EXCLUDES, noarchive=False)


a_gui = analysis("lanzador_gui.py")
a_cli = analysis("lanzador_cli.py")

exe_gui = EXE(PYZ(a_gui.pure), a_gui.scripts, [], exclude_binaries=True, name="Nesting2D",
              console=False, upx=False)
exe_cli = EXE(PYZ(a_cli.pure), a_cli.scripts, [], exclude_binaries=True, name="nesting2d-cli",
              console=True, upx=False)

coll = COLLECT(exe_gui, a_gui.binaries, a_gui.datas,
               exe_cli, a_cli.binaries, a_cli.datas,
               upx=False, name="Nesting2D")
