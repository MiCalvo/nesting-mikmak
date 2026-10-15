# Nesting 2D

Coloca piezas 2D (importadas de PDF vectorial o DXF) en planchas usando el
mínimo material y exporta un DXF por plancha.

Estado: **fases 1 a 5 hechas**. Falta probar el importador DXF con archivos reales del CAD. Especificación: `docs/especificacion_v1.md`. Guía para Claude Code: `CLAUDE.md`.

## Instalación en Windows

Necesitas Python 3.11, 3.12, 3.13 o 3.14 (64 bits). En una terminal, dentro de esta carpeta:

```
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -e .[dev,gui]
python -m pytest
```

Si `py` no existe, usa la ruta de tu `python.exe`. Las pruebas tardan alrededor
de 1 minuto (el motor calcula de verdad) y deben salir 27 en verde.

## Ejecutable de Windows

Sin instalar Python: en GitHub, pestaña **Actions** → la última ejecución de
«Windows» en verde → **Artifacts** → `Nesting2D-windows` (hay que haber iniciado
sesión en GitHub). Es un único .zip: clic derecho → «Extraer todo…» en una
carpeta tuya (por ejemplo Documentos; en `C:\` o `Program Files` Windows pide
permisos de administrador) y abre `Nesting2D\Nesting2D.exe` (no lo saques de su
carpeta: necesita `_internal`). No hace falta instalar nada: los ajustes y perfiles
se guardan en tu carpeta de usuario (AppData). Como el .exe no está firmado,
Windows puede avisar («Windows protegió su PC»): «Más información» → «Ejecutar de
todas formas».
`nesting2d-cli.exe autoprueba` comprueba que todo funciona.

Para construirlo tú: `packaging\construir_windows.bat` (deja el resultado en
`dist\Nesting2D\`).

## Interfaz gráfica

```
python -m nesting2d gui
```

(o `nesting2d-gui`, que abre la ventana sin consola).

La ventana sigue los pasos del trabajo. A la izquierda, **1 Piezas · 2 Material
y parámetros · 3 Resultado · 4 Exportar**, cada uno con su estado (✓ hecho,
! con avisos) y una línea que dice qué falta («Importa los planos», «Sin
calcular», «Desactualizado: vuelve a calcular»…); debajo, el botón **Calcular
nesting** (F5), siempre a mano, con el progreso. Se puede ir a cualquier paso
(clic o Ctrl+1…4); abajo, «Anterior» y «Siguiente». El panel de mensajes está
oculto y se abre solo cuando hay un aviso (o desde Ver › Mensajes).

1. **Paso 1 · Piezas → «Importar planos…»** (Ctrl+I), o arrastra los archivos a la ventana. Cada archivo da una o varias piezas. Un DXF
   con varias capas pregunta cuáles importar. Si un archivo tiene muchos
   contornos (un plano con vistas, cotas y cajetín), la app pregunta si
   importarlos con cantidad 0 o **seleccionar los contornos a mano**
   (también: Archivo → Importar seleccionando contornos, Ctrl+Mayús+I). En ese
   diálogo, **lo azul es la pieza**: una ventana añade lo que encierra (con sus
   huecos), un clic cambia una zona de hueco a material o al revés, y
   Mayús+clic hace ese cambio en todas las zonas iguales (por ejemplo, todos
   los taladros).
   En planos con cotas y ejes, elige **Seleccionar por: Aristas**: clic en una
   arista elige su contorno continuo (o el círculo), Ctrl+clic una sola arista,
   Mayús+clic en un círculo todos los del mismo Ø, y **Taladros…** añade los
   círculos de dentro del contorno por diámetros. Al pasar el ratón se ve si es
   recta, arco o círculo y su Ø. Las cotas y ejes no cuentan si no los eliges;
   en rojo, los extremos que no cierran.
   **Imágenes** (capturas de pantalla y escaneos: PNG, JPG, BMP, TIFF): se abre
   ese mismo diálogo con el tipo de imagen (dibujo de líneas o silueta), el
   umbral de blanco y negro y la **escala**, que es obligatoria: sale sola de
   los ppp de un escaneo, o se mide en la imagen una distancia conocida
   («Medir en la imagen…»). La precisión depende de la resolución (≈ ±1 píxel).
2. **Paso 1 · Piezas**: al elegir una pieza se ve ampliada y, en **Propiedades
   de la pieza**, su nombre, medidas, origen, escala, cantidad, rotaciones y
   espejo (también se cambian con doble clic en la tabla). Para corregir la
   escala con una medida conocida, pulsa **Acotar: Dos puntos** (engancha a
   centros de círculo, vértices y aristas) o **Arista recta**, y escribe la
   medida real; puedes aplicarla a todas las piezas del mismo archivo. Con
   varias filas elegidas, «Cantidad · Aplicar a la selección».
3. **Paso 2 · Material y parámetros**: plancha, separación, margen, rotaciones,
   pieza dentro de pieza, lado de compactación, **perfil de cálculo** y semilla.
   El perfil por defecto es «Automático · Normal»: el tiempo por plancha crece
   con el nº de copias y con las rotaciones permitidas (45° ×2; 15° o libre ×3),
   hasta 180 s; con el pedido de 16 juntas, ≈ 20 s. «Rápido» para tantear,
   «Fino» para tiradas grandes, o «Fijo» con los segundos que quieras. Debajo se
   ve el tiempo estimado. (Medición en `docs/medicion_motor.md`.)
4. **Calcular nesting** (F5, en la barra lateral). Se calcula en segundo plano;
   debajo del botón se ven la plancha, la fase y el mejor largo encontrado. El
   botón pasa a **Detener**, que para al acabar la plancha en curso (el motor no
   se puede cortar a mitad).
5. **Paso 3 · Resultado**: arriba, los indicadores (planchas, piezas colocadas,
   aprovechamiento y retal libre de la plancha que se ve) y la validación (✓ o
   el nº de problemas, que salen en la tarjeta «Problemas»; en rojo las piezas
   que incumplan separación o margen). Edición manual:
   - clic selecciona, Ctrl+clic añade o quita; arrastrar en vacío hace una
     ventana (de izquierda a derecha, piezas enteras dentro; de derecha a
     izquierda, piezas que toca);
   - arrastrar mueve (con «Enganche», se pega a los márgenes y a la separación
     de las vecinas); flechas mueven 1 mm (con Mayús, 10; el paso se cambia);
   - R / Mayús+R giran con el paso del proyecto; el panel X, Y, ángulo coloca
     por coordenadas (absoluto) o desplaza (relativo);
   - Ctrl+Z / Ctrl+Y deshacen y rehacen; «Volver al resultado del motor».
   - «A la plancha»: pasa la selección a otra plancha o a una nueva;
     «Eliminar planchas vacías».
6. **Paso 4 · Exportar**: primero, las comprobaciones «Antes de cortar»
   (resultado al día, sin problemas de validación, todas las piezas colocadas,
   giros permitidos). **Exportar DXF…** (Ctrl+E): `plancha_1.dxf`,
   `plancha_2.dxf`… en la carpeta que elijas; la casilla «Arcos y círculos» (la
   misma que Archivo → «DXF con arcos y círculos») los escribe con arcos reales
   (desviación ≤ 0,05 mm) en vez de segmentos; por defecto, segmentos.
   **Exportar PDF de taller…** (Ctrl+P): resumen con la tabla de piezas y una
   página por plancha a escala, con cada pieza numerada.
   **Guardar** (Ctrl+S) crea el proyecto `.json` (con el resultado del motor y
   tus ediciones). Archivo → Abrir reciente; también puedes arrastrar PDF, DXF o
   proyectos a la ventana.

**Rellenar la plancha** (paso 2 → «Qué calcular»): en vez de colocar las
cantidades pedidas, busca cuántos **juegos** caben en una plancha. La columna
«Cantidad» pasa a ser «Proporción» (2, 1, 1 = juegos de 2 de la primera y 1 de
cada otra; 0 = fuera) y el hueco que quede se rellena con piezas sueltas de la
referencia que elijas. Hace varios intentos de 10 s y la colocación final con
el perfil de cálculo (normalmente 1–3 minutos). El resultado es «caben al menos
N juegos»: con más tiempo quizá entre alguna más.

**Perfiles de material** (paso 2): plantillas con plancha,
separación, margen, material y espesor. «Guardar como perfil…» guarda los
valores actuales; al crear un proyecto nuevo se elige perfil.

Si cambias piezas o parámetros después de calcular, el resultado se marca como
obsoleto y no se guarda en el proyecto hasta que vuelvas a calcular.

## Línea de comandos

Listar las piezas de unos PDF con sus medidas:

```
python -m nesting2d piezas "datos_prueba\RIGCCP*.pdf"
```

Calcular el nesting del primer proyecto (16 juntas):

```
python -m nesting2d nest "datos_prueba\RIGCCP*.pdf" --cantidad RIGCCP0020=4 RIGCCP0019=4 RIGCCP0018=4 RIGCCP0016=2 RIGCCP0017=2 --plancha 1200x1000 --separacion 5 --margen 5 --salida salida
```

Rellenar una plancha (las cantidades se leen como proporción):

```
python -m nesting2d nest datos_prueba\RIGCCP0019.pdf datos_prueba\RIGCCP0018.pdf datos_prueba\RIGCCP0016.pdf --cantidad RIGCCP0019=2 RIGCCP0018=1 RIGCCP0016=1 --rellenar --relleno RIGCCP0016 --salida salida
```

Tiempo de cálculo: automático por defecto (`--finura rapido|normal|fino`), o
fijo con `--tiempo SEGUNDOS` por plancha.

En `salida\` quedan `plancha_1.dxf` (para el proveedor), `plancha_1.png`
(para comprobarlo a ojo) y `proyecto.json`.

Opciones útiles: `--rotacion 45` o `--rotacion libre`, `--lado abajo`,
`--sin-pieza-en-pieza`, `--max-planchas 2`, `--semilla 1` (repite el mismo
resultado), `--etiquetas` (nombres de pieza en una capa aparte del DXF),
`--tolerancia 0.01` (unión de trazos al importar).

La separación y el margen de 5 mm son provisionales hasta confirmarlos con el
proveedor que corta la mica.
