# Nesting 2D

Coloca piezas 2D (importadas de PDF vectorial o DXF) en planchas usando el
mínimo material y exporta un DXF por plancha.

Estado: **fase 1 (núcleo, por línea de comandos)**. La interfaz gráfica es la
fase 2. Especificación: `docs/especificacion_v1.md`. Guía para Claude Code: `CLAUDE.md`.

## Instalación en Windows

Necesitas Python 3.11, 3.12, 3.13 o 3.14 (64 bits). En una terminal, dentro de esta carpeta:

```
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
python -m pytest
```

Si `py` no existe, usa la ruta de tu `python.exe`. Las pruebas tardan unos 30 s
(el motor calcula de verdad) y deben salir 16 en verde.

## Uso

Listar las piezas de unos PDF con sus medidas:

```
python -m nesting2d piezas "datos_prueba\RIGCCP*.pdf"
```

Calcular el nesting del primer proyecto (16 juntas):

```
python -m nesting2d nest "datos_prueba\RIGCCP*.pdf" --cantidad RIGCCP0020=4 RIGCCP0019=4 RIGCCP0018=4 RIGCCP0016=2 RIGCCP0017=2 --plancha 1200x1000 --separacion 5 --margen 5 --tiempo 30 --salida salida
```

En `salida\` quedan `plancha_1.dxf` (para el proveedor), `plancha_1.png`
(para comprobarlo a ojo) y `proyecto.json`.

Opciones útiles: `--rotacion 45` o `--rotacion libre`, `--lado abajo`,
`--sin-pieza-en-pieza`, `--max-planchas 2`, `--semilla 1` (repite el mismo
resultado), `--etiquetas` (nombres de pieza en una capa aparte del DXF),
`--tolerancia 0.01` (unión de trazos al importar).

La separación y el margen de 5 mm son provisionales hasta confirmarlos con el
proveedor que corta la mica.
