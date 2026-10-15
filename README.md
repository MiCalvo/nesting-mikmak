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
sesión en GitHub). Es un único .zip: descomprímelo y abre `Nesting2D\Nesting2D.exe`
(no lo saques de su carpeta: necesita `_internal`).
`nesting2d-cli.exe autoprueba` comprueba que todo funciona.

Para construirlo tú: `packaging\construir_windows.bat` (deja el resultado en
`dist\Nesting2D\`).

## Interfaz gráfica

```
python -m nesting2d gui
```

(o `nesting2d-gui`, que abre la ventana sin consola). Flujo:

1. **Importar PDF/DXF…** (Ctrl+I). Cada archivo da una o varias piezas. Un DXF
   con varias capas pregunta cuáles importar. Si un archivo tiene muchos
   contornos (un plano con vistas, cotas y cajetín), la app pregunta si
   importarlos con cantidad 0 o **seleccionar los contornos a mano**
   (también: Archivo → Importar seleccionando contornos, Ctrl+Mayús+I). En ese
   diálogo, **lo azul es la pieza**: una ventana añade lo que encierra (con sus
   huecos), un clic cambia una zona de hueco a material o al revés, y
   Mayús+clic hace ese cambio en todas las zonas iguales (por ejemplo, todos
   los taladros).
2. **Pestaña Piezas**: doble clic para cambiar nombre, escala, cantidad o
   rotaciones; casilla de espejo. Para corregir la escala con una medida conocida,
   selecciona la pieza y pulsa **Acotar: dos puntos** (engancha a centros de
   círculo, vértices y aristas) o **Acotar: arista recta**, y escribe la medida
   real; puedes aplicarla a todas las piezas del mismo archivo.
3. **Pestaña Parámetros**: plancha, separación, margen, rotaciones, pieza dentro
   de pieza, lado de compactación, tiempo y semilla.
4. **Calcular** (F5). Se calcula en segundo plano; la barra de estado muestra la
   plancha, la fase y el mejor largo encontrado. **Detener** para al acabar la
   plancha en curso (el motor no se puede cortar a mitad).
5. **Pestaña Resultado**: cada plancha con el retal libre, métricas y validación
   (en rojo las piezas que incumplan separación o margen). Edición manual:
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
6. **Exportar DXF…** (Ctrl+E): `plancha_1.dxf`, `plancha_2.dxf`… en la carpeta
   que elijas. **Exportar PDF de taller…** (Ctrl+P): resumen con la tabla de
   piezas y una página por plancha a escala, con cada pieza numerada.
   **Guardar** (Ctrl+S) crea el proyecto `.json` (con el resultado del motor y
   tus ediciones). Archivo → Abrir reciente; también puedes arrastrar PDF, DXF o
   proyectos a la ventana.

**Perfiles de material** (pestaña Parámetros): plantillas con plancha,
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
