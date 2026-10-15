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
Fases 1 a 5 HECHAS y probadas por Mikel en Windows ("parece que funciona bien").
Fase 6 (imágenes: capturas y escaneos con OpenCV) HECHA, sin probar aún por Mikel.
Fase 7 (selección por aristas, círculos/arcos, taladros, DXF con arcos) HECHA, sin probar aún por Mikel.
Fase 8 (rediseño de la interfaz: pasos en barra lateral, aspecto profesional) HECHA, sin probar aún por Mikel.
Fase 9 (perfiles de cálculo: tiempo automático Rápido/Normal/Fino o fijo) HECHA, sin probar aún por Mikel.
Fase 10 (modo rellenar la plancha: juegos en proporción + relleno) HECHA, sin probar aún por Mikel.
`python -m pytest` → todas en verde (las de interfaz, sin pantalla; se saltan si
no está PySide6). Pendiente: DXF reales de su CAD.

## Estructura
```
nesting2d/
  geometry.py            Part (pieza: forma original + escala, cantidad, rotaciones, espejo)
  importers/contours.py  trazos sueltos -> piezas con huecos (unión de extremos + regla par-impar)
  importers/pdf_import.py  PDF vectorial (pdfplumber)
  importers/image_import.py  imágenes (Pillow + OpenCV): modos líneas/silueta/silueta clara,
                         umbral Otsu, caras en píxeles con Y hacia arriba
  importers/strokes.py   aristas: recta/arco/círculo/polilínea, cadenas por extremos, círculos
                         completos (también arcos que suman 360°), piezas con solo lo elegido
  importers/dxf_import.py  DXF (ezdxf): bloques anidados/MINSERT, capa 0 heredada, capas
                         — probado con DXF sintéticos; FALTAN DXF reales del CAD
  engine/params.py       NestParams (parámetros de proyecto); time_limit None = automático
  engine/timing.py       tiempo por plancha: automático (copias × rotaciones × finura) o fijo
  engine/fill.py         modo rellenar: máximo de juegos (proporción) en UNA plancha por tanteo
                         (intentos de 10 s, a saltos y por mitades) + sueltas de una referencia
  engine/part_in_part.py relleno voraz de huecos antes del motor
  engine/nester.py       capa sobre spyrrow: márgenes, lado de compactación, varias planchas
  validate.py            solapes, separación, margen (lo usará la edición manual)
  exporters/dxf_export.py  DXF por plancha: capas CORTE, PLANCHA, ETIQUETAS (off por defecto);
                         opción arcs=True (menú Archivo, `nest --arcos`)
  exporters/arcs.py      ajuste de arcos/círculos a anillos (≤ 0,05 mm) -> CIRCLE / LWPOLYLINE bulge
  exporters/preview.py   PNG de comprobación (matplotlib, solo desarrollo)
  exporters/shop_pdf.py  PDF de taller con QPdfWriter (resumen + una página por plancha a
                         escala normalizada, piezas numeradas por posición, retal libre)
  profiles.py            perfiles de material (plancha, separación, margen, material, espesor)
  project.py             guardar/abrir proyecto .json (geometría en WKT); v2 guarda también
                         el resultado del motor para "volver" a él
  editing.py             edición manual sin Qt: mover, girar, enganche, cambiar de plancha,
                         avisos de giro no permitido (devuelve cambios; la GUI los deshace)
  cli.py                 línea de comandos: `gui`, `autoprueba`, `piezas` y `nest`
  selftest.py            autoprueba sin archivos externos (motor, DXF, PDF, Qt)
  gui/app.py             arranque (QApplication + gc_guard + style + MainWindow)
  gui/style.py           aspecto: Fusion + paleta clara + QSS; Card, Kpi, Badge, button(kind=…)
  gui/steps.py           StepButton: paso de la barra lateral (número/✓/!, título, estado)
  gui/main_window.py     ventana: barra lateral de pasos + cabecera + páginas (QStackedWidget
                         `tabs`) + pie Anterior/Siguiente; menús, importar/calcular en hilos,
                         guardar/abrir, exportar; `_refresh_steps` pone el estado de cada paso
  gui/export_panel.py    paso 4: comprobaciones «Antes de cortar» y botones DXF/PDF/guardar
  gui/parts_model.py     tabla de piezas (modelo + editores de escala/cantidad/rotaciones)
  gui/parts_tab.py       paso 1: tabla (estado vacío), vista previa, tarjeta de propiedades
                         (edita por `model.setData`) + diálogo de escala por cota
  gui/part_view.py       vista ampliada de una pieza y herramienta de acotar
  gui/snapping.py        enganche a centros/vértices/aristas (sin Qt, probado aparte)
  gui/params_panel.py    paso 2: parámetros, perfiles (perfiles.json en AppData) y ajustes
                         de importación (QSettings)
  gui/result_view.py     paso 3 y editor: indicadores, insignia de validación, tarjetas; selección (clic/ventana CAD), arrastre
                         con enganche, flechas, panel X/Y/ángulo, QUndoStack, validación en vivo
  gui/workers.py         QThreads de importación y de nesting (trabajan sobre copias)
  gui/gc_guard.py        recolección de basura solo en el hilo principal (ver abajo)
  gui/contour_dialog.py  selección manual de contornos ("lo azul es la pieza") por zonas o por
                         aristas (cadena, Ctrl, Mayús = mismo Ø, Taladros…), y capas DXF
  gui/image_dialog.py    el mismo diálogo para imágenes: tipo, umbral, escala (ppp o medir)
tools/medir_motor.py     medición del motor (tiempo, semillas, rotaciones, copias)
packaging/               PyInstaller: nesting2d.spec, lanzadores, construir_windows.bat
.github/workflows/windows.yml  pruebas + ejecutable + autoprueba en Windows en cada push
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
  Y al terminar, `gc_guard.shutdown(app)` (lo hacen app.main y el fixture de las
  pruebas): con el GC desactivado, los ciclos con objetos de Qt se destruían al
  salir de Python, ya sin QApplication → segmentation fault (código 139) DESPUÉS
  de pasar todas las pruebas. Comprobar siempre el código de salida de pytest, no
  solo "N passed".
- Interfaz: Y hacia arriba en los datos; las escenas de Qt dibujan en (x, −y).
- Aspecto (`gui/style.py`): estilo Fusion + paleta + QSS. NO estilar con QSS los
  campos numéricos ni las listas desplegables: con borde por QSS, Qt deja de
  dibujar sus flechas con el estilo base. La QApplication de las pruebas llama
  también a `style.apply` (como la app real). `self.tabs` es un QStackedWidget
  con las 4 páginas en el orden de los pasos (las pruebas usan `setCurrentWidget`).
- `Layout.stats()["free"]` = retal desde un margen más allá de la última pieza
  hasta el borde de la plancha, a todo su ancho. `nester.free_rect` da esa misma
  zona como rectángulo (la usan la vista y el PDF; hay prueba que lo vigila).
- PDF de taller: librería elegida = QPdfWriter (viene con PySide6; sin dependencia
  nueva). Necesita una QGuiApplication: `shop_pdf` la crea si no existe.
  **En Windows, la plataforma Qt "offscreen" no tiene fuentes**: el PDF sale sin
  texto (comprobado en Actions: plataforma "windows" → 157 fuentes y texto bien;
  "offscreen" → 0 fuentes). Por eso conftest.py solo fuerza offscreen fuera de
  Windows y `shop_pdf` lanza un error si Qt no encuentra fuentes. Al extraer
  texto con pdfplumber, los ":" salen como un carácter raro (mapeo de la fuente);
  en las pruebas no se comparan textos con ":".
- Pruebas de interfaz: `QStandardPaths.setTestModeEnabled(True)` para no tocar
  los perfiles ni los ajustes reales.
- Selección manual de contornos: la regla par-impar NO sirve sola en planos con
  líneas que no son cortes (escalones, chaflanes, taladros dibujados con dos
  circunferencias). Por eso el diálogo es "lo azul es la pieza": la ventana
  propone material/hueco por par-impar entre lo que encierra, el clic corrige una
  zona y Mayús+clic todas las zonas iguales. Visto con el plano RIG23P0054.
- `build_parts` = `closed_faces` + `parts_from_faces`; el diálogo usa las caras.
- DXF: los bloques anidados se perdían (0 piezas) hasta la fase 5; hay prueba.
- Imágenes (OpenCV 5.0.0 instalado; API igual que 4.x en lo que usamos, comprobado):
  - se leen con Pillow (ppp y transparencia; evita cv2.imread con rutas no ASCII);
  - ppp < 150 = de pantalla, no se usan como escala; la escala es obligatoria;
  - modo líneas: caras = zonas claras cerradas (las que tocan el borde de la imagen
    son el fondo y se descartan), ampliadas 0,5 px + medio trazo (grosor estimado
    con la transformada de distancia) hasta el eje de la línea; siluetas: +0,5 px
    las componentes, −0,5 px los huecos;
  - precisión medida con imágenes sintéticas a 300 ppp: ±0,1 mm; con el PDF de la
    RIGCCP0016 pasado a imagen de 200 ppp: 123,98 × 72,67 mm y 11 huecos (vectorial:
    124,0 × 72,7);
  - Otsu se adapta a líneas grises suavizadas (167–219); un umbral fijo de 128 las
    pierde. En imágenes de dos tonos puros Otsu da 0, y da igual.
- Aristas (fase 7), medido con los datos de prueba:
  - un polígono regular tiene todos sus vértices sobre su circunferencia
    circunscrita (un rectángulo pasaba por círculo): un trazo solo es círculo/arco
    si además ningún segmento abarca más de 25° (las Bézier de los PDF salen en
    ≥ 4 segmentos por cuarto: ≤ 22,5°). Comprobar puntos medios NO sirve;
  - NumPy 2.5: `np.cross` con vectores 2D da error; se calcula a mano;
  - RIGCCP0019 por aristas (1 cadena + 15 círculos) = misma pieza que por zonas;
  - plano A0 pág. 2: 3.789 trazos clasificados en < 1 s; el anillo de Ø340 con
    el agujero de Ø220 y 15 taladros sale con 1 clic + «Taladros…»;
  - empates al pinchar (recta que toca un círculo): se prefiere círculo/arco.
- Motor medido (15/10/2026, `docs/medicion_motor.md`, 4 núcleos, juntas reales):
  pedido real de 16 copias = 189 mm SIEMPRE (tope geométrico, ya a los 5 s, con
  cualquier rotación); 48 copias: −0,7 % de largo por cada vez que se dobla el
  tiempo hasta 120 s, nada de 120 a 240; más orientaciones necesitan más tiempo
  (45° ≈ ×2, 15°/libre ≈ ×3) y con estas piezas 90° gana a igual tiempo; varios
  intentos cortos rinden MENOS que uno largo. `StripPackingConfig`: si se dan
  `exploration_time` y `compression_time`, hay que pasar `total_computation_time=None`
  (su valor por defecto es 600 y da error).
- Arcos para el DXF: empezar el recorrido del anillo al principio del segmento
  más largo (si no, un arco queda partido al cerrar) y parar los tramos rectos
  donde empieza un arco (si no, se comen su primer punto). Con eso las esquinas
  de R salen de 90° exactos (rectángulo redondeado: área exacta).
- Ejecutable: PyInstaller en modo carpeta (dist/Nesting2D: Nesting2D.exe ventana +
  nesting2d-cli.exe consola). Construido y probado en Linux (≈300 MB; la
  autoprueba pasa con spyrrow empaquetado). En Windows lo construye Actions.

## Decisiones cerradas (de la especificación)
- Escala 1:1 por defecto; corrección manual o acotando dos puntos/arista
  (escala = real / medida, siempre uniforme; "aplicar a todo el archivo").
- Parámetros por proyecto: plancha (1200×1000), nº de planchas (ilimitado),
  separación y margen (5 mm PROVISIONALES, pendiente del proveedor), rotaciones
  (cada 90°; también 45°, 15°, libre), pieza dentro de pieza (activado), lado de
  compactación (izquierda), perfil de cálculo (Automático · Normal; también Rápido,
  Fino o Fijo en s — decidido por Mikel el 15/10/2026: prima un resultado rápido;
  máximo 180 s/plancha en automático; las rotaciones, parámetro aparte), semilla,
  material/espesor.
  Por pieza: cantidad, escala, rotaciones restringidas, espejo (manual).
- Perfiles de material reutilizables (plancha + separación + margen).
- Edición manual tras el nesting: seleccionar, arrastrar, flechas (1 mm / 10 mm
  con Mayús), panel X/Y/ángulo absoluto o relativo, girar, validación en vivo en
  rojo, métricas, deshacer/rehacer, volver al resultado del motor.
- Salidas: DXF por plancha + PDF de taller + proyecto .json.
- Fuera de alcance v1: G-code/CAM, DWG nativo, PDF escaneado, vinilo de rollo.
  v2: fijar piezas y recalcular, pieza en pieza recursiva/global, espejo
  automático, retales. (El modo rellenar se adelantó: ver fase 10.)
- Modo rellenar (Mikel, 15/10/2026): la cantidad se lee como PROPORCIÓN, juegos
  completos en UNA plancha y el hueco con sueltas de UNA referencia elegida;
  intentos de 10 s y colocación final con el perfil de cálculo; «caben al menos N».

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
5. ~~Ampliaciones~~ (hechas, salvo DXF reales): importador DXF reforzado (bloques
   anidados, MINSERT, capa 0, aviso de pulgadas, elegir capas); selección manual
   de contornos; ejecutable de Windows con PyInstaller y autoprueba.
6. ~~Imágenes~~ (hecha, 15/10/2026, a petición de Mikel): capturas de pantalla y
   escaneos con OpenCV; fotos con perspectiva, por ahora no.
7. ~~Aristas~~ (hecha, 15/10/2026, a petición de Mikel): selección por aristas y
   reconocimiento de círculos/arcos; DXF con arcos como opción. Mikel NO eligió el
   filtro por grosor/tipo de línea (comprobado viable; posible mejora).
8. ~~Rediseño de la interfaz~~ (hecho, 15/10/2026, a petición de Mikel: «fea y poco
   clara»): barra lateral con los pasos y su estado, «Calcular nesting» siempre
   visible, tarjeta de propiedades, indicadores y validación en el resultado,
   página Exportar con comprobaciones; mensajes ocultos salvo avisos. Sin tocar la
   lógica de nesting.
9. ~~Perfiles de cálculo~~ (hecho, 15/10/2026, a petición de Mikel): medición del motor
   (`docs/medicion_motor.md`) y tiempo automático Rápido/Normal/Fino o fijo.
10. ~~Modo rellenar la plancha~~ (hecho, 15/10/2026, a petición de Mikel; era v2):
   «Qué calcular» en el paso 2, columna Proporción, relleno con una referencia,
   resumen en el resultado y en el PDF, `nest --rellenar --relleno`.

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
python -m nesting2d autoprueba
pyinstaller --noconfirm packaging/nesting2d.spec   (o packaging\construir_windows.bat)
python -m pytest                   (interfaz: offscreen en Linux; plataforma normal en Windows)
python -m nesting2d piezas "datos_prueba/RIGCCP*.pdf"
python -m nesting2d nest "datos_prueba/RIGCCP*.pdf" --cantidad RIGCCP0020=4 RIGCCP0019=4 RIGCCP0018=4 RIGCCP0016=2 RIGCCP0017=2 --salida salida
```
