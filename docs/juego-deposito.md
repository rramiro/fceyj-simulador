# Juego "El depósito" (gestión de inventarios)

Materia: **Métodos Cuantitativos para la Administración** (3.6), unidades 3 (inventarios) y 5
(simulación). Diseño aprobado el 20/11/2026 a partir de la Guía de Formación Práctica 2025 de la
cátedra. Rama de trabajo: `inventarios`. App: `deposito`.

## Decisiones aprobadas

| # | Tema | Decisión |
|---|---|---|
| 1 | Rondas | 6 meses por defecto (3 a 12); cada mes se simula día por día (25 días hábiles). |
| 2 | Decisión del equipo | Tamaño del lote n y punto de pedido R (revisión continua: si stock + en camino ≤ R, se pide n). |
| 3 | Incertidumbre | Demanda diaria Poisson (media 8); demora del proveedor uniforme de 2 a 6 días. Igual para todos los equipos (semilla). |
| 4 | Faltantes | Venta perdida con costo c2. |
| 5 | Costos | Notación de la cátedra: co por orden, cm por unidad y día (24 % anual del precio), c2 por faltante. La compra ca·D no entra en el ranking, salvo el ahorro del descuento. |
| 6 | Eventos | Uno por mes: descuento por cantidad, suba de co 15 %, campaña (demanda +50 %), huelga (+4 días de demora), suba de la tasa (48 % anual), mes normal. |
| 7 | Pregunta del mes | n0, CT0, h0, t0, sp, R de la huelga, ahorro anual del descuento; ±5 %, 5 puntos. |
| 8 | Resultados | Gráfico de diente de sierra (stock, R, órdenes, llegadas, faltantes), costos y la política del modelo simulada desde el mismo stock. |
| 9 | Ranking | Hasta 70 puntos por costo acumulado relativo + 5 por pregunta. |

## Calibración (aprobada el 20/11/2026)

Con `python scripts/simular_deposito.py` (1.000 partidas de 6 meses). Ajustes respecto del diseño:

- **Descuento 3 %** (no 10 %): con 10 % el descuento decidía el juego (un 10 % del precio equivale a
  5 meses de mantener).
- **c2 = $ 60.000** (no $ 120.000): con 120.000 cualquier stock de más convenía y "mucha protección"
  empataba con la política de manual.
- Umbrales del descuento: 150, 300, 600 o 1.000 unidades (con 1.000 no conviene).
- En la prueba en el navegador: el descuento vale para **una sola orden** del mes y **no cae en los dos
  últimos meses** (lo comprado al final no llegaba a mantenerse y el ahorro salía gratis).

Mes normal: D = 2.400 u/año; n0 = 87; h0 = 27,7; t0 = 10,8 días; CT0 = $ 8,3 M/año; demanda en la
demora: media 32, máxima 48.

| Estrategia | Costo (M) | Servicio | Gana |
|---|---|---|---|
| **De manual** (n0; R = demanda media × demora máxima; descuento si conviene) | **5,9** | 98 % | **89 %** |
| Mucha protección (R al doble) | 7,5 | 100 % | 8 % |
| n0 del primer mes, sin mirar eventos | 9,4 | 94 % | 3 % |
| n0 sin stock de protección | 11,1 | 91 % | 0 % |
| Pide mucho (n = 400) | 12,1 | 99 % | 0 % |
| Pide seguido (n = 15) | 19,6 | 91 % | 0 % |

## Tiempo máximo por ronda (21/11/2026, rama `modalidad_juego`)

El docente puede fijar al crear la sesión los minutos de cada mes. Si un equipo no envía la política a tiempo, el sistema elige un lote entre la mitad y el doble de la demanda del mes y un punto de pedido entre 0 y 1,5 veces la demanda durante la demora máxima, sin responder la pregunta del mes. La ronda queda marcada como fuera de tiempo (tablero, CSV, resultados y devolución) y no cambia el puntaje. Funcionamiento común: `DESPLIEGUE.md`, sección *Tiempo máximo por ronda*.

## Estado

| Fase | Estado |
|---|---|
| Diseño y calibración | Aprobados (20/11/2026). |
| App, catálogo, portada, CI | Hechos en la rama `inventarios`; probados en el navegador. |
| Testing y unión a `main` | Pendiente. |
