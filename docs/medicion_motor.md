# Medición del motor (15/10/2026)

Para decidir los perfiles de cálculo (Rápido / Normal / Fino / Automático) con
números medidos, no supuestos. Script: `tools/medir_motor.py`; datos en bruto:
`medicion_motor_datos.jsonl` (94 cálculos).

## Condiciones

- Juntas reales RIGCCP0016–0020 (`datos_prueba/`). Pedido real = 16 copias
  (4+4+4+2+2); además ×3 (48 copias) y ×6 (96 copias).
- Plancha 1200 × 1000, separación 5, margen 5, pieza dentro de pieza activada,
  compactación a la izquierda. spyrrow 0.9.0 con su reparto por defecto (80 %
  exploración, 20 % compactación) salvo donde se indica.
- Máquina: contenedor Linux con **4 núcleos**. En otro PC los segundos cambian;
  lo que vale es la tendencia.
- Medida: largo ocupado (mm; menos = mejor). De 2 a 4 semillas por caso, así que
  diferencias por debajo de ~0,5 % están dentro del ruido.
- Limitación: todas las piezas son marcos casi rectangulares. Con piezas
  irregulares (curvas, en L…) las rotaciones finas podrían ayudar más; no medido.

## Resultados

**Pedido real (16 copias):** 189,0 mm en todos los casos: con 5 s o 120 s, con
rotaciones cada 90°, 45°, 15° o libres, y con cualquier reparto. Es un tope
geométrico (dos columnas de 92 mm + 5 mm de separación). Pidiendo 120 s, el
motor se paró solo (`early_termination`) a los 64–82 s con 90° y 45°, a veces a
los ~80 s con 15°, y nunca con rotación libre; pero ya tenía el resultado a los 5 s.
La parada temprana, por tanto, no ahorra casi nada en pedidos fáciles.

**48 copias, rotaciones cada 90°:**

| Tiempo por plancha | Largo medio | Mín – máx |
| --- | --- | --- |
| 15 s | 506,5 | 501,9 – 513,6 |
| 30 s | 502,7 | 501,9 – 503,9 |
| 60 s | 499,3 | 496,0 – 501,9 |
| 120 s | 496,1 | 493,7 – 498,6 |
| 240 s | 497,3 | 496,0 – 498,5 (se paró solo a ~206 s) |

Mejora ≈ 0,7 % cada vez que se dobla el tiempo hasta 120 s; de 120 a 240 s,
nada. Todo el recorrido de 15 a 120 s son ≈ 10 mm de largo (≈ 1 % de la plancha).

**96 copias, 90°:** 30 s → 1007,6; 60 s → 1004,5; 120 s → 999,1 (−0,8 %).

**48 copias, según rotaciones (largo medio):**

| Tiempo | 90° | 45° | 15° | Libre |
| --- | --- | --- | --- | --- |
| 30 s | 502,7 | 505,0 | 510,2 | 511,0 |
| 60 s | 499,3 | 501,3 | 506,4 | 506,5 |
| 120 s | 496,1 | 499,8 | 503,1 | 498,9 |

Con más orientaciones el motor necesita más tiempo para llegar al mismo largo:
45° a 60 s ≈ 90° a 30 s (×2); 15° a 120 s ≈ 90° a ~35 s (×3–4); libre a 120 s ≈
90° a ~45 s (×3, con mucho ruido). Con estas piezas, a igual tiempo, 90° gana.

**Varios intentos (semillas) frente a un intento largo, 48 copias:** el mejor de
3 intentos de 15 s (45 s en total) = 501,9; el mejor de 3 de 30 s (90 s) = 501,9;
un solo intento de 120 s = 496,1 de media. **Un intento largo rinde más que
varios cortos.**

**Reparto exploración/compactación:** sin datos útiles; solo se midió con el
pedido real, que siempre llega al tope (189 mm). Se mantiene el 80/20 de spyrrow.

## Conclusiones para los perfiles

1. El tiempo útil depende del número de piezas: con pocas, 5–10 s bastan; con
   48 copias mejora hasta ~120 s; doblar más no aporta.
2. Más orientaciones permitidas → más tiempo: ×2 con 45°, ×3 con 15° o libre.
3. Los intentos múltiples no compensan: mejor dar ese tiempo a un único cálculo.
4. Las diferencias son pequeñas (≈ 1–2 % del largo): importan sobre todo cuando
   permiten ahorrar una plancha entera.
5. No medido: complejidad de las piezas (nº de vértices, formas irregulares) ni
   otro PC. Las fórmulas del modo automático son provisionales.

## Aplicado (15/10/2026)

Perfil de cálculo por defecto «Automático · Normal» (`nesting2d/engine/timing.py`):
1,25 s por copia (10–120 s) × rotaciones (×1–×3) × finura (Rápido ×0,25, Normal
×1, Fino ×2), entre 5 y 180 s por plancha. Mikel prefirió un máximo bajo: en
trabajos de una plancha prima tener un resultado rápido. Sin intentos múltiples.
