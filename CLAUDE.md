# Nesting 2D — guía para Claude Code

App de escritorio (Windows) para colocar piezas 2D en planchas usando el mínimo
material. Uso propio de Mikel (ingeniero mecánico); quizá más adelante su hermano.
Primer uso real: 16 juntas de mica (RIGCCP0016–0020) en planchas de 1200 × 1000 mm.

La especificación completa está en `docs/especificacion_v1.md`. Léela antes de
cambiar comportamiento o alcance.

## Cómo trabajar con Mikel
- Responde en español.
- Precisión antes que rapidez: si algo no está claro, pregunta en vez de suponer.
  No inventes funciones de librerías; si dudas de una API, compruébala (código,
  docstring, documentación) antes de usarla.
- Las decisiones de diseño ya cerradas están en la especificación; no las
  cambies sin preguntar.

## Estado actual
Fase 1 (núcleo sin interfaz) HECHA y probada: `python -m pytest` → 16 pruebas en verde.
**Siguiente: fase 2, interfaz básica con PySide6** (ver "Plan por fases").

## Estructura
```
nesting2d/
  geometry.py            Part (pieza: forma original + escala, cantidad, rotaciones, espejo)
  importers/contours.py  trazos sueltos -> piezas con huecos (unión de extremos + regla par-impar)
  importers/pdf_import.py  PDF vectorial (pdfplumber)
  importers/dxf_import.py  DXF (ezdxf) — SIN PROBAR con DXF reales de CAD
  engine/params.py       NestParams (parámetros de proyecto)
  engine/part_in_part.py relleno voraz de huecos antes del motor
  engine/nester.py       capa sobre spyrrow: márgenes, lado de compactación, varias planchas
  validate.py            solapes, separación, margen (lo usará la edición manual)
  exporters/dxf_export.py  DXF por plancha: capas CORTE, PLANCHA, ETIQUETAS (off por defecto)
  exporters/preview.py   PNG de comprobación (matplotlib, solo desarrollo)
  project.py             guardar/abrir proyecto .json (geometría en WKT)
  cli.py                 línea de comandos: `piezas` y `nest`
tests/                   pruebas con las juntas reales de datos_prueba/
datos_prueba/            5 PDFs de juntas (A4, 1:1) + un plano A0 con varias vistas
```

## Hechos comprobados (no los "corrijas" sin volver a medir)
- Unidades: mm en todo el código. PDF: 1 pt = 25,4/72 mm.
- **pdfplumber da las coordenadas de los trazados con Y hacia abajo** (origen
  arriba). `pdf_import` invierte Y con la altura de página. Hay una prueba
  (`test_pdf_y_axis_is_not_flipped`) que lo vigila: sin ella las piezas salen espejadas.
- La unión de extremos (tolerancia 0,01 mm) es necesaria: sin ella, en las
  juntas quedaban círculos sin cerrar.
- Los PDF de NX (cgm2pdf) dibujan el texto como trazos: en planos con varias
  vistas salen contornos falsos (marco, letras O/D). Por eso habrá selección
  manual de contornos (fase 5).
- spyrrow 0.9.0 (MIT, sobre sparrow MIT y jagua-rs MPL-2.0), según su documentación:
  - resuelve "strip packing": alto fijo, minimiza el largo;
  - pieza colocada = girar `rotation` grados alrededor de (0,0) y luego trasladar `translation`;
  - `allowed_orientations`: lista de grados, o None = libre;
  - `min_items_separation` funciona (medido: 3,002 mm con 3 pedidos);
  - NO admite huecos (por eso `part_in_part.py`), ni espejo, ni piezas fijas;
  - hay ruedas para Windows de Python 3.11 a 3.14.
- Importar un DXF de plancha SIN filtrar capas mete el borde de la plancha como
  pieza (regla par-impar). Al reimportar DXF propios, usar `layers=["CORTE"]`.

## Decisiones cerradas (de la especificación)
- Escala 1:1 por defecto; corrección manual o acotando dos puntos/arista
  (escala = real / medida, siempre uniforme; "aplicar a todo el archivo").
- Parámetros por proyecto: plancha (1200×1000), nº de planchas (ilimitado),
  separación y margen (5 mm PROVISIONALES, pendiente del proveedor), rotaciones
  (cada 90°; también 45°, 15°, libre), pieza dentro de pieza (activado), lado de
  compactación (izquierda), tiempo (30 s por plancha), semilla, material/espesor.
  Por pieza: cantidad, escala, rotaciones restringidas, espejo (manual).
- Perfiles de material reutilizables (plancha + separación + margen).
- Edición manual tras el nesting: seleccionar, arrastrar, flechas (1 mm / 10 mm
  con Mayús), panel X/Y/ángulo absoluto o relativo, girar, validación en vivo en
  rojo, métricas, deshacer/rehacer, volver al resultado del motor.
- Salidas: DXF por plancha + PDF de taller + proyecto .json.
- Fuera de alcance v1: G-code/CAM, DWG nativo, PDF escaneado, vinilo de rollo.
  v2: fijar piezas y recalcular, pieza en pieza recursiva/global, espejo
  automático, modo rellenar, retales.

## Plan por fases
1. ~~Núcleo~~ (hecho).
2. **Interfaz básica (PySide6)**: proyecto, importar, pestaña Piezas (escala,
   acotar, cantidad), parámetros, calcular (en un hilo aparte; spyrrow libera el
   GIL y tiene `ProgressQueue`) y ver el resultado.
3. Edición manual con validación en vivo (`validate.check`) y deshacer.
4. PDF de taller, varias planchas en la interfaz, perfiles de material, guardar/abrir.
5. Importador DXF probado con archivos reales, selección manual de contornos,
   ejecutable de Windows (PyInstaller u otro; comprobar que incluye spyrrow).

## Pendientes abiertos
- Separación y margen reales: los dirá el proveedor de la mica.
- Formato de DXF que acepta su máquina (capas, unidades, arcos vs polilíneas).
- Reparto en varias planchas: versión sencilla (las piezas que no caben pasan a
  la siguiente). Mejorable.
- Licencias si algún día se distribuye: MPL-2.0 (jagua-rs), LGPL (PySide6).
  No usar PyMuPDF (AGPL).

## Comandos
```
python -m pytest
python -m nesting2d piezas "datos_prueba/RIGCCP*.pdf"
python -m nesting2d nest "datos_prueba/RIGCCP*.pdf" --cantidad RIGCCP0020=4 RIGCCP0019=4 RIGCCP0018=4 RIGCCP0016=2 RIGCCP0017=2 --salida salida
```
