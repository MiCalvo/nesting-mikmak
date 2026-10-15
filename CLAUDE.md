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
Fases 1 (núcleo), 2 (interfaz básica, validada por Mikel), 3 (edición manual) y
4 (producción) HECHAS. `python -m pytest` → todas en verde (las de interfaz, sin
pantalla; se saltan si no está PySide6). Las fases 3 y 4 solo se han probado en
Linux sin pantalla y con capturas. **Siguiente: fase 5** (ver "Plan por fases").

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
  exporters/shop_pdf.py  PDF de taller con QPdfWriter (resumen + una página por plancha a
                         escala normalizada, piezas numeradas por posición, retal libre)
  profiles.py            perfiles de material (plancha, separación, margen, material, espesor)
  project.py             guardar/abrir proyecto .json (geometría en WKT); v2 guarda también
                         el resultado del motor para "volver" a él
  editing.py             edición manual sin Qt: mover, girar, enganche, cambiar de plancha,
                         avisos de giro no permitido (devuelve cambios; la GUI los deshace)
  cli.py                 línea de comandos: `gui`, `piezas` y `nest`
  gui/app.py             arranque (QApplication + gc_guard + MainWindow)
  gui/main_window.py     ventana: menús, importar/calcular en hilos, guardar/abrir, exportar DXF
  gui/parts_model.py     tabla de piezas (modelo + editores de escala/cantidad/rotaciones)
  gui/parts_tab.py       pestaña Piezas + diálogo de escala por cota
  gui/part_view.py       vista ampliada de una pieza y herramienta de acotar
  gui/snapping.py        enganche a centros/vértices/aristas (sin Qt, probado aparte)
  gui/params_panel.py    pestaña Parámetros, perfiles (perfiles.json en AppData) y ajustes
                         de importación (QSettings)
  gui/result_view.py     pestaña Resultado y editor: selección (clic/ventana CAD), arrastre
                         con enganche, flechas, panel X/Y/ángulo, QUndoStack, validación en vivo
  gui/workers.py         QThreads de importación y de nesting (trabajan sobre copias)
  gui/gc_guard.py        recolección de basura solo en el hilo principal (ver abajo)
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
- spyrrow 0.9.0, comprobado en su `__init__.pyi` y en pruebas:
  - `ProgressQueue().drain()` se puede llamar desde otro hilo mientras `solve()`
    calcula; `solve(cfg, progress=None)` también vale.
  - NO hay forma de interrumpir `solve()`: "Detener" para al acabar la plancha en curso.
  - `ReportType` no es hashable (no meterlo en un `set`); `==` e `in (tupla)` sí funcionan.
- **Recolector de basura y hilos (PySide6)**: el GC cíclico de Python puede saltar
  en un hilo de trabajo y destruir allí objetos de Qt de ventanas ya cerradas →
  segmentation fault (visto en las pruebas al importar el plano A0). Por eso
  `gui/gc_guard.install(app)` desactiva el GC automático y lo lanza con un QTimer
  en el hilo principal. Cualquier QApplication nueva (pruebas incluidas) debe llamarlo.
- Interfaz: Y hacia arriba en los datos; las escenas de Qt dibujan en (x, −y).
- `Layout.stats()["free"]` = retal desde un margen más allá de la última pieza
  hasta el borde de la plancha, a todo su ancho. `nester.free_rect` da esa misma
  zona como rectángulo (la usan la vista y el PDF; hay prueba que lo vigila).
- PDF de taller: librería elegida = QPdfWriter (viene con PySide6; sin dependencia
  nueva). Necesita una QGuiApplication: `shop_pdf` la crea si no existe. Al extraer
  texto con pdfplumber, los ":" salen como un carácter raro (mapeo de la fuente);
  en las pruebas no se comparan textos con ":".
- Pruebas de interfaz: `QStandardPaths.setTestModeEnabled(True)` para no tocar
  los perfiles ni los ajustes reales.

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
2. ~~Interfaz básica (PySide6)~~ (hecha): proyecto nuevo/abrir/guardar, importar
   en un hilo, pestaña Piezas (escala, acotar con enganche, cantidad, rotaciones,
   espejo), parámetros, calcular en un hilo con progreso y "Detener", ver el
   resultado (varias planchas, retal libre, validación estática en rojo) y
   exportar DXF. Planos con muchos contornos: se pregunta si importarlos con
   cantidad 0 (la selección manual de contornos sigue siendo fase 5).
3. ~~Edición manual~~ (hecha): selección por clic, Ctrl+clic y ventana (→ dentro,
   ← tocando); arrastrar con enganche por rectángulo envolvente (márgenes y
   separación de vecinas); flechas (paso configurable, ×10 con Mayús); R/Mayús+R;
   panel X/Y (esquina inferior izquierda del envolvente)/ángulo absoluto o
   relativo; validación en vivo en rojo + lista de problemas; aviso (naranja) de
   giro fuera de las rotaciones permitidas; deshacer/rehacer; volver al motor.
   Las piezas dentro de un hueco se mueven con su contenedor; movidas solas se desligan.
4. ~~Producción~~ (hecha): PDF de taller (también `nest --pdf-taller`); pasar piezas a
   otra plancha o a una nueva y eliminar planchas vacías (con deshacer); recuentos
   por plancha; perfiles de material (aplicar, guardar como, eliminar; se elige
   al crear proyecto nuevo); abrir reciente; arrastrar archivos a la ventana.
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
python -m nesting2d gui            (o `nesting2d-gui` tras `pip install -e .[gui]`)
python -m pytest                   (las de interfaz usan QT_QPA_PLATFORM=offscreen)
python -m nesting2d piezas "datos_prueba/RIGCCP*.pdf"
python -m nesting2d nest "datos_prueba/RIGCCP*.pdf" --cantidad RIGCCP0020=4 RIGCCP0019=4 RIGCCP0018=4 RIGCCP0016=2 RIGCCP0017=2 --salida salida
```
