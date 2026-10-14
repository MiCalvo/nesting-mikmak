# Nesting 2D — Especificación v1

14/10/2026 · Mikel. Copia en Markdown del documento de claude.ai, para que Claude
Code la tenga en el proyecto. Si cambia una, actualiza la otra.

## Objetivo

App de escritorio para Windows que importa siluetas de PDF vectorial o DXF, permite ajustar su escala y cantidad, y las coloca en planchas usando el mínimo material. Compacta las piezas contra un lado para que el sobrante quede como un retal rectangular aprovechable, y exporta el resultado en DXF y en PDF de taller.

- **Usuarios:** uso propio; más adelante, quizá también su hermano.
- **Primer uso:** 16 juntas de mica (RIGCCP0016–0020) en planchas de 1200 × 1000 mm.
- **Procesos:** el corte lo hace un proveedor externo. CNC router y láser quedan como usos futuros; el vinilo de rollo se descarta.

## Alcance

La v1 cubre el flujo completo, desde el PDF hasta el DXF de corte, con edición manual. Lo que exige programar algoritmos propios de nesting queda para la v2.

**v1**

- Importar PDF vectorial (también multipágina) y DXF.
- Reconstruir automáticamente contornos y huecos.
- Seleccionar a mano los contornos en planos con varias vistas.
- Pestaña Piezas: escala manual o por acotado, cantidad, y rotación y espejo por pieza.
- Parámetros por proyecto y perfiles de material reutilizables.
- Nesting con spyrrow en una o varias planchas.
- Pieza dentro de pieza, activable.
- Edición manual del resultado con validación en vivo.
- Exportar DXF de corte y PDF de taller; guardar y abrir proyectos.

**v2**

- Fijar piezas a mano y recalcular el resto a su alrededor.
- Pieza dentro de pieza mejorada: recursiva y con búsqueda global, no voraz.
- Espejo usado por el motor para encajar mejor.
- Modo rellenar: máximo de copias de una pieza en una plancha.
- Planchas de distinto tamaño e inventario de retales.

**Fuera de alcance**

- G-code o CAM para fresado; posible más adelante.
- Lectura nativa de DWG: se convierte antes a DXF con ODA File Converter o LibreDWG.
- PDF escaneado (imagen): exigiría vectorizar.
- Vinilo de rollo.

## Flujo de trabajo

1. **Crear el proyecto** y elegir un perfil de material, que trae la plancha, la separación y el margen.
2. **Importar** uno o varios PDF o DXF. La app reconstruye las piezas y muestra sus medidas.
3. **Seleccionar contornos a mano** solo en planos con varias vistas, cotas o cajetín.
4. **Revisar la pestaña Piezas**: escala (1:1 por defecto; acotar si hace falta), cantidad, rotaciones y espejo.
5. **Calcular el nesting.** Se ve la mejor solución encontrada dentro del tiempo configurado.
6. **Ajustar a mano** las piezas que se quiera, con validación en vivo.
7. **Exportar** el DXF de corte y el PDF de taller, y guardar el proyecto.

## Importación

El importador convierte los trazos sueltos de un PDF o DXF en piezas cerradas, con su contorno exterior y sus huecos, en milímetros reales.

**PDF vectorial**

- Lee líneas, rectángulos y curvas Bézier de cada página. Las coordenadas pasan de puntos a mm (1 pt = 25,4/72 mm), con Y hacia arriba, y las curvas se discretizan.
- Une los extremos con una **tolerancia** (0,01 mm por defecto). Sin ella quedaban círculos sin cerrar.
- Forma las caras cerradas, identifica el contorno exterior y los huecos (regla par-impar) y descarta los trazos abiertos (cruces de centro, líneas de cota).
- **Filtra contornos pequeños** por debajo de un área mínima configurable.
- Si la página no tiene trazos vectoriales (PDF escaneado), avisa en lugar de importar.

**Planos con varias vistas**

- En exportaciones de NX el texto viene dibujado como trazos, así que letras como O o D forman contornos cerrados falsos.
- En esos casos la app muestra la hoja y el usuario elige con ventana o clics qué contornos forman cada pieza.

**DXF**

- Se lee con ezdxf. **Aún no probado con archivos reales de CAD**; hay que comprobar unidades, arcos y polilíneas.

**DWG**

- No se lee directamente. La app avisa y sugiere convertir a DXF con ODA File Converter o LibreDWG.

## Pestaña Piezas

Cada elemento importado es una fila con escala 1:1 por defecto. La escala se corrige a mano o acotando una medida conocida.

| Columna | Contenido |
| --- | --- |
| Vista previa | Silueta de la pieza con sus huecos |
| Nombre | Por defecto, el del archivo (p. ej. RIGCCP0016) |
| Medidas | Ancho × alto en mm, recalculado en vivo |
| Escala | Editable; 1,000 por defecto |
| Cantidad | Copias a cortar |
| Rotaciones | Las del proyecto, o restringidas para esta pieza |
| Espejo | Sí/no; hereda el valor del proyecto |

**Acotar**

- Clic en dos puntos de la pieza, con enganche a vértices, centros de círculo y aristas, o selección de una arista recta.
- La app muestra la distancia medida, el usuario escribe la real y la escala se calcula sola: escala = real / medida.
- La escala es siempre uniforme, para no deformar la pieza.
- **Aplicar a todo el archivo**: propaga la escala a las demás piezas del mismo PDF o DXF.

## Parámetros

| Parámetro | Nivel | Por defecto |
| --- | --- | --- |
| Tamaño de plancha | Proyecto | 1200 × 1000 mm |
| Número de planchas disponibles | Proyecto | Ilimitado |
| Separación entre piezas | Proyecto | 5 mm (provisional, pendiente del proveedor) |
| Margen al borde | Proyecto | 5 mm (provisional) |
| Rotaciones permitidas | Proyecto y pieza | Cada 90°; opciones 45°, 15° o libre |
| Espejo permitido | Proyecto y pieza | No |
| Pieza dentro de pieza | Proyecto | Activado |
| Lado hacia el que compactar | Proyecto | Izquierda |
| Tiempo de cálculo | Proyecto | 30 s (por plancha) |
| Semilla (avanzado) | Proyecto | Aleatoria; fijarla repite el mismo resultado |
| Material y espesor | Proyecto | Vacío; solo informativo, sale en el PDF |
| Tolerancia de unión de trazos | Ajustes generales | 0,01 mm |
| Área mínima de contorno | Ajustes generales | 1 mm² provisional; ajustar en pruebas |

**Perfiles de material**: plantillas reutilizables con plancha, separación y margen (p. ej. "Mica 1200×1000 – proveedor X"). Al crear un proyecto se elige un perfil y sus valores se copian al proyecto, donde se pueden cambiar.

## Motor de nesting

spyrrow 0.9.0 (MIT), que envuelve para Python el algoritmo sparrow (Rust). Lo que spyrrow no hace va en una capa propia.

**Lo que aporta spyrrow** (comprobado en su documentación y en pruebas)

- Problema en tira: ancho fijo, largo mínimo. La plancha se modela como tira de alto = lado − 2 × margen.
- Separación mínima entre piezas (con 3 mm pedidos se midieron 3,002 mm).
- Rotaciones como lista de ángulos o libres.
- Tiempo de cálculo y semilla configurables.
- Libera el bloqueo de Python mientras calcula y ofrece una cola de progreso.

**Lo que no hace**: huecos (pieza en pieza), espejo, piezas fijas como obstáculos.

**Capa propia**

1. **Márgenes y lado de compactación**: se resuelve en un marco de tira y se gira a la plancha; las rotaciones restringidas se respetan.
2. **Pieza dentro de pieza** (preproceso voraz, rejilla de 0,5 mm). Cada contenedor y su contenido viajan al motor como un solo bloque.
3. **Varias planchas**: las piezas que no caben pasan a la siguiente plancha y se recalculan. Primera versión hecha (fase 1); mejorable.

El motor está encapsulado tras una interfaz propia para poder cambiarlo (Deepnest u otra librería).

## Edición manual

- **Seleccionar**: clic, o caja de selección para varias; se mueven juntas.
- **Arrastrar con el ratón**, con enganche opcional a bordes de plancha y a otras piezas, respetando la separación.
- **Teclado**: flechas con paso configurable (1 mm; 10 mm con Mayúsculas).
- **Panel numérico**: X, Y y ángulo, absoluto o relativo (+20 mm en X).
- **Girar** con el paso del proyecto o con un ángulo escrito.
- **Validación en vivo**: en rojo si hay solape, separación menor que la mínima o invasión del margen. Al exportar, aviso si queda alguna en rojo.
- **Métricas** en vivo: retal libre y % de aprovechamiento.
- **Deshacer/rehacer** y botón para volver al resultado del motor.

Fijar piezas y recalcular el resto queda para la v2.

## Salidas

**DXF de corte**, una plancha por archivo: capa CORTE (contornos y huecos en mm), capa PLANCHA (borde, opcional), capa ETIQUETAS (desactivada por defecto). Capas, unidades y formato de curvas a ajustar según el proveedor (pendiente).

**PDF de taller**: dibujo de cada plancha a escala con piezas numeradas; tabla de piezas (nombre, cantidad, plancha); material, espesor, separación, margen, % de aprovechamiento y retal libre.

**Archivo de proyecto** .json: geometría importada, escalas, parámetros, resultado del motor y ediciones manuales.

## Arquitectura y stack

Python 3.11–3.14 (ruedas de spyrrow para Windows disponibles), interfaz PySide6. Cuatro módulos coordinados por la interfaz:

- **Importación**: PDF con pdfplumber, DXF con ezdxf, contornos con shapely.
- **Proyecto**: piezas y escalas, parámetros, perfiles, archivo .json.
- **Nesting**: márgenes y planchas, pieza dentro de pieza, interfaz al motor → spyrrow (externo, intercambiable).
- **Exportación**: DXF con ezdxf; PDF de taller (librería por elegir).

| Librería | Uso | Licencia |
| --- | --- | --- |
| PySide6 | Interfaz | LGPL |
| pdfplumber 0.11 | Lectura de PDF | MIT (comprobado) |
| shapely 2.x | Geometría | BSD-3 (comprobado) |
| ezdxf | DXF | MIT (sin comprobar) |
| spyrrow 0.9.0 | Motor de nesting | MIT (comprobado) |
| sparrow / jagua-rs | Núcleo del motor | MIT / MPL-2.0 |

Ejecutable de Windows: PyInstaller u otro; por probar que incluya el módulo compilado de spyrrow.

## Validación hecha

| Junta | Tamaño (mm) | Huecos | Cantidad |
| --- | --- | --- | --- |
| RIGCCP0016 | 124,0 × 72,7 | 11 | 2 |
| RIGCCP0017 | 58,2 × 72,7 | 5 | 2 |
| RIGCCP0018 | 93,0 × 119,0 | 15 | 4 |
| RIGCCP0019 | 167,0 × 92,0 (forma de C) | 15 | 4 |
| RIGCCP0020 | 69,0 × 95,0 (marco fino) | 1 | 4 |

Nesting en plancha 1200 × 1000 mm, margen 5 mm, 30 s:

| Separación | Franja ocupada | Retal libre |
| --- | --- | --- |
| 2 mm | 171 mm | 1000 × 1019 mm |
| 3 mm | 175 mm | 1000 × 1015 mm |
| 5 mm | 194 mm | 1000 × 996 mm |

- Plano RIG23P0054 (A0, 4 hojas): vectorial y a escala real; diámetros 320, 252 y 220 mm exactos; texto como trazos.
- Pieza dentro de pieza: con 2 mm la 0017 entra en el hueco de 64 × 90 mm de la 0020; con ≥ 3 mm no cabe.

## Riesgos y puntos abiertos

- [ ] Separación y margen reales: preguntar al proveedor de la mica (provisional 5 mm).
- [ ] Formato de DXF que acepta su máquina: capas, unidades, arcos o polilíneas.
- [ ] Importador DXF: probar con archivos reales.
- [x] Reparto en varias planchas: primera versión hecha; mejorable.
- spyrrow está en 0.x: versión fijada y encapsulada.
- Licencias: sin problema para uso propio; si se distribuye, revisar MPL-2.0 y LGPL; evitar PyMuPDF (AGPL).
- Selección manual de contornos puede ser laboriosa en planos con muchas vistas.
- Rendimiento del relleno de huecos con muchas piezas o huecos complejos.

## Plan por fases

1. **Núcleo** (hecho): importador PDF, geometría, motor con márgenes, pieza en pieza y varias planchas, exportación DXF, proyecto .json, línea de comandos y pruebas.
2. **Interfaz básica**: proyecto, importar, pestaña Piezas (escala, acotar, cantidad), parámetros, calcular y ver el resultado.
3. **Edición manual**: mover, girar, validación en vivo, métricas y deshacer.
4. **Producción**: PDF de taller, varias planchas en la interfaz, perfiles de material, guardar y abrir proyectos.
5. **Ampliaciones**: importador DXF con archivos reales, selección manual de contornos, ejecutable de Windows.
