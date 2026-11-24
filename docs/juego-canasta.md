# Juego "La canasta de Soledad" (comportamiento del consumidor)

Materia: **Microeconomía** (2.7, ambas carreras), unidades II (comportamiento del consumidor) y III (demanda).
Diseño aprobado el 24/11/2026 a partir de los TP 1 a 3 de la cátedra (Soledad y López: ingreso 16, Px 2,
Py 1; precio-consumo, ingreso-consumo, Engel, efectos sustitución e ingreso). Rama de trabajo: `consumidor`.
App: `canasta`. Propuesta de juegos para la cátedra: https://claude.ai/artifact/CXrbLcD9hJ81uoHeLQPeGM

## Decisiones aprobadas

| # | Tema | Decisión |
|---|---|---|
| 1 | Consumidor y bienes | Cada equipo reparte su ingreso del mes entre entradas al cine (X, enteras) y alimentos (Y, canastas divisibles). |
| 2 | Decisión | Cuántas entradas compra; los alimentos son lo que queda: siempre sobre la recta de presupuesto. |
| 3 | Lo que ve el equipo | Su mapa de indiferencia (5 curvas de referencia, ninguna tangente), la recta de presupuesto y la curva a la que llega la canasta que elige. La función de utilidad no se muestra. |
| 4 | Tipos de consumidor | Tres, CES y repartidos en orden: equilibrado (Cobb-Douglas, a = 0,4), cinéfilo (a = 0,45, σ = 2: sustitutos) y combo (a = 0,2, σ = 0,5: complementos). |
| 5 | Meses | 8: marzo base (I $160.000, Px $20.000, Py $10.000); abril promo del cine (Px/2); mayo sube el cine (Px×2); junio baja el ingreso (−25 %); julio aguinaldo (+50 %); agosto suben los alimentos (Py×2); septiembre sube el cine con compensación de Slutsky (el ingreso alcanza justo para la canasta de marzo del equipo); octubre cambia todo (I +25 %, Px/2, Py×2). |
| 6 | Pregunta del mes | TMS en el óptimo (marzo y octubre), elasticidad arco precio (abril y mayo, se acepta con o sin signo), ingreso (junio y julio), cruzada (agosto) y efecto sustitución en entradas (septiembre). Las elasticidades y el efecto sustitución se calculan con las cantidades **del propio equipo**. ±5 %, 5 puntos. Si no se puede calcular (cero entradas en los dos meses) se anula y suma. |
| 7 | Puntos de la decisión | 10 si es la cantidad óptima entera, 6 a una entrada, 2 a dos, 0 más lejos. |
| 8 | Ranking | (decisiones + preguntas) / máximo posible × 100. Tiempo máximo por ronda como en los demás juegos. |
| 9 | Resultados | Canasta óptima con su curva tangente, "ingreso real logrado" U/U* (la utilidad es homogénea de grado 1) y el ingreso equivalente perdido, TMS de la canasta frente a Px/Py; demanda (meses 1-3) y curva de Engel (meses 1, 4 y 5) del equipo frente al modelo; al final, la demanda de la clase como suma horizontal. |
| 10 | Fuera de esta versión | Bien inferior y Giffen (piden otra función de utilidad; quedan para la devolución con el adicional del TP 2) y la ronda cardinal con la tabla de Soledad. |

## Calibración (24/11/2026)

Con `python scripts/simular_canasta.py` (desde el entorno virtual). Verificaciones: en el óptimo continuo
TMS = Px/Py, el óptimo entero queda a menos de una entrada del continuo, la canasta cumple la recta de
presupuesto y la compensación de Slutsky alcanza para la canasta de marzo; elasticidad arco del TP (4 → 8
entradas cuando el precio baja a la mitad) = −1.

Ajuste respecto del diseño: el tipo combo pasó de a = 0,4 a **a = 0,2**, porque con 0,4 "mitad del ingreso
en cine" sacaba 62 de 80 puntos.

Entradas óptimas por mes:

| Mes | Equilibrado | Cinéfilo | Combo |
|---|---|---|---|
| Marzo | 3 | 2 | 3 |
| Abril (promo) | 6 | 6 | 5 |
| Mayo (sube el cine) | 2 | 1 | 2 |
| Junio (−25 % ingreso) | 2 | 2 | 2 |
| Julio (aguinaldo) | 5 | 3 | 5 |
| Agosto (suben alimentos) | 3 | 3 | 3 |
| Septiembre (compensada) | 2 | 1 | 3 |
| Octubre (todo junto) | 8 | 11 | 5 |

Puntos de la decisión (de 80) por estrategia:

| Estrategia | Equilibrado | Cinéfilo | Combo |
|---|---|---|---|
| **De manual (TMS = Px/Py)** | **80** | **80** | **80** |
| Misma participación del gasto que en marzo | 76 | 58 | 58 |
| Mitad del ingreso en cine | 44 | 30 | 44 |
| Repetir las entradas de marzo | 40 | 44 | 48 |
| Al azar | 23 | 23 | 24 |

Con Cobb-Douglas, gastar siempre la misma parte del ingreso es casi óptimo (76): es justamente lo que enseña
la demanda X = a·I/Px, y la devolución lo explica.

Nota sobre Slutsky: si la canasta de marzo del equipo no era la óptima, la compensación no parte de un
óptimo y el efecto sustitución medido puede salir positivo sin contradecir la teoría (por ejemplo, el
equilibrado con 1 entrada en marzo tiene óptimo 2 en septiembre). La devolución solo marca la alerta cuando
marzo fue óptimo.

## Prueba

- `otree test canasta 3` y `otree test canasta 6`: los dos casos (a tiempo y fuera de tiempo) pasan; el bot 1
  elige siempre el óptimo y saca 100.
- En el navegador (24/11/2026): instrucciones, decisión con el mapa interactivo, resultados con la tangente,
  resultado final con demanda, Engel y demanda de la clase.

## Estado

Hecho en la rama `consumidor` (desde `main`), sin commit al 24/11/2026. Falta: commit, despliegue a testing y
revisarlo con la cátedra.
