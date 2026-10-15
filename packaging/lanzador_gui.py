"""Punto de entrada de Nesting2D.exe (ventana, sin consola).

  Nesting2D.exe                 abre la app
  Nesting2D.exe proyecto.json   abre la app con ese proyecto
"""
import sys

from nesting2d.gui.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
