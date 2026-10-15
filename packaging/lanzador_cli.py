"""Punto de entrada de nesting2d-cli.exe (línea de comandos, con consola).

  nesting2d-cli.exe autoprueba
  nesting2d-cli.exe piezas plano.pdf
  nesting2d-cli.exe nest *.pdf --cantidad A=2 --salida salida
"""
import sys

from nesting2d.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
