# Juego de costos

Materia: **Costos para la Gestión** (Contador Público 3.3 y Lic. en Administración 3.2; 3.er año,
1.er cuatrimestre, 105 h). Diseño aprobado el 20/11/2026, a partir del material del curso de
Moodle 2026 (TP 9, 10 y 11, resumen "Gestión y decisiones"). Rama de trabajo: `costos`.

## Decisiones aprobadas

| # | Decisión | Aprobado |
|---|---|---|
| 1 | Empresa | "Confecciones del Caldén", taller de cortinas ficticio de Santa Rosa, con la estructura de los casos de la cátedra: proceso de **corte y costura** (horas hombre) y de **embolsado y terminado** (horas máquina), costos fijos de capacidad y de operación, tasas, capacidad máxima y nivel previsto. Líneas: comunes e infantiles; la hotelera puede sumarse con un evento. |
| 2 | Interacción | Cada equipo maneja su taller frente al mismo escenario (semilla); todos pasan juntos de mes; ranking. |
| 3 | Duración | 6 meses por defecto (3 a 12). |
| 4 | Decisiones mensuales | Precio y unidades a producir de cada línea, sin superar la capacidad de ningún proceso. Demanda según el precio, con variación aleatoria; lo no vendido queda en stock. |
| 5 | Evento mensual | Uno por mes, del catálogo de decisiones del capítulo IV: pedido especial Expopymes (B6), comprar o fabricar estuches (B1), nueva línea hotelera, eliminar la línea infantil ante un competidor (B3), equipo de embolsado alternativo (B5), procesamiento adicional (B4), suba de la tela. |
| 6 | Informe al empresario | Cada mes, antes de ver el resultado, un número calculado sobre la propia situación (punto de equilibrio, de indiferencia, de cierre, margen de seguridad). Puntos si acierta con ±5 %. |
| 7 | Resultados | Estados de resultados por costeo integral y variable lado a lado; costos indirectos aplicados contra reales; desvíos estándar (precio y rendimiento de la tela, eficiencia de la mano de obra, uso de la capacidad); punto de equilibrio y margen de seguridad. |
| 8 | Ranking | 70 puntos por el resultado acumulado por costeo variable (relativo al mejor) + 30 por los informes (5 por mes con 6 meses). |
| 9 | Inflación | 0 % por defecto, configurable. |
| 10 | Datos | Del orden de los TP 2026; la cátedra puede ajustarlos. |
| 11 | Devolución | Capacidad ociosa, pedidos especiales, líneas eliminadas que daban contribución, stock que infla el costeo integral, desvíos y los informes con la cuenta correcta. |

## Modelo y calibración (aprobada el 20/11/2026)

Detalle en `costos/modelo.py`; se calibra con `python scripts/simular_costos.py` (1.000 partidas de
6 meses). Datos del taller (mes de demanda promedio, a precio de referencia):

| Línea | Precio | Costo variable | CF absorbido | Contribución |
|---|---|---|---|---|
| Cortina común | $ 55.000 | $ 25.620 | $ 2.132 | $ 28.280 |
| Cortina infantil | $ 48.000 | $ 22.585 | $ 2.318 | $ 24.455 |
| Cortina para hoteles (evento) | $ 62.000 | $ 28.005 | $ 2.504 | $ 32.135 |

- Costos fijos del mes: $ 12,7 M (producción $ 2,2 M con las tasas del TP 9 b; administración
  $ 6 M; comercialización $ 2 M; directos de las líneas $ 2,5 M). Punto de equilibrio con la
  demanda base (950 cortinas): 474; margen de seguridad 50 %.
- Capacidad: corte 255 de 300 horas hombre; embolsado 190 de 220 horas máquina. Un pedido
  especial o la línea para hoteles obligan a pensar la capacidad (horas extra, precio).
- Cada evento tiene datos sorteados para que a veces convenga y a veces no (precio del pedido,
  costo de fabricar estuches, costos fijos y demanda de la línea hotelera, cuánto pega el
  competidor, costos del equipo y del bordado).

| Estrategia | Resultado variable | Resultado integral | Puntaje |
|---|---|---|---|
| **De manual** (precio según contribución y capacidad; decide con punto de indiferencia, de cierre y contribución diferencial; informa bien) | **54,8** | 55,1 | **99** |
| De manual, sin informes | 54,8 | 55,1 | 69 |
| Precio de referencia, rechaza todo | 51,5 | 51,8 | 64 |
| Precio de referencia, acepta todo | 46,5 | 47,0 | 52 |
| Llena la capacidad (sobreproduce) | 37,3 | **41,5** | 31 |
| Precio 20 % más bajo | 18,9 | 19,1 | 2 |

Sobreproducir "mejora" el resultado integral respecto del variable (los costos fijos quedan en el
stock): la lección clásica del TP 10 a sale sola. La identidad integral − variable = variación
del stock valuado por cada método se verifica en cada mes de cada partida.

## Prueba en el navegador

Una partida de 3 equipos y 6 meses en el servidor local: el plan que se pasa de la capacidad se
rechaza sin perder lo escrito; el contador de horas se actualiza mientras escriben; el informe
acertado suma puntos; los estados de resultados por los dos métodos y los desvíos cierran; el
tablero docente muestra ranking, historial "Mes a mes" y devolución. Ajustes que salieron de la
prueba: la devolución distingue "producción insuficiente" (demanda sin atender con capacidad
ociosa) de "falta capacidad"; los montos que redondean a cero ya no muestran "-$ 0"; la tolerancia
y los puntos del informe salen de los parámetros de la sesión.

## Estado

| Fase | Estado |
|---|---|
| Diseño | Aprobado (20/11/2026). |
| Modelo y calibración | Aprobados (20/11/2026). |
| App, catálogo, portada, CI | Hechos en la rama `costos`; probados en el navegador. |
| Testing y unión a `main` | Pendiente. |
