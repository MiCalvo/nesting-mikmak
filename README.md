# nesting-mikmak

Aplicación de escritorio de **nesting 2D**: importar siluetas, escalarlas y colocarlas de la forma más eficiente posible dentro de una plancha.

> Estado: **fase de diseño y definición de alcance**. Todavía no hay código.

## Primer caso de uso

Cortar planchas de **junta de mica** (formato estándar 1000 × 1200 mm). El corte lo hace un proveedor externo, que fijará la separación mínima necesaria entre piezas.

Más adelante: fresadora CNC (router) y corte láser.

## Alcance previsto

### Entrada
- Importar siluetas desde **PDF**, **DXF** y **DWG**.
- Pestaña de elementos importados donde seleccionar cada pieza y ajustar su escala:
  - cambiándola a mano, o
  - poniendo una cota sobre la pieza y definiendo su dimensión real.
  (Los PDF actuales están a escala 1:1, pero no se puede dar por hecho).

### Parámetros por proyecto
- Tamaño de la plancha.
- Separación entre piezas.
- Distancia al borde.
- Rotaciones permitidas.
- Espejo: opción configurable según el caso (en principio el material no tiene veta).

### Nesting
- Colocación automática optimizada.
- Pensado para tiradas pequeñas.
- No es requisito que el motor coloque piezas dentro de los huecos de otras.
- Tras el cálculo, edición manual: seleccionar piezas y moverlas con el ratón o introduciendo valores.

### Salida
1. **DXF** (primera versión).
2. **PDF** de plano.
3. **G-code** con herramienta de fresado (más adelante).

## Plataforma

- Windows.
- Python.
- Uso propio; posible ampliación futura a otro usuario.
