# Juego "Las cajas del súper" (líneas de espera)

Materia: **Métodos Cuantitativos para la Administración** (3.6), unidades 4 (líneas de espera) y 5
(simulación). Diseño aprobado el 21/11/2026 a partir de la Guía de Formación Práctica 2025 (ejercicios
4.1 banco, 4.2 supermercado, III.1 Pizza Pampita) y del teórico de colas de la cátedra
(CT = Cs·s + Cc·Ls). Rama de trabajo: `colas`. App: `cajas`.

## Decisiones aprobadas

| # | Tema | Decisión |
|---|---|---|
| 1 | Empresa y rondas | Súper Quantum. Cada ronda es una franja de un sábado: mañana 8–12, mediodía 12–14, tarde 14–18, noche 18–22. 2 sábados (8 rondas) por defecto, de 1 a 3. |
| 2 | Decisión del equipo | Cuántas cajas abre en la franja (1 a 15). Fila única. |
| 3 | Llegadas | Poisson: 40, 80, 60 y 100 clientes por hora según la franja. Las mismas para todos los equipos (semilla). |
| 4 | Servicio | Exponencial, 5 minutos de media (μ = 12 por hora y caja). |
| 5 | Costos | Cs = $ 15.000 por caja y hora (toda la franja); Cc = $ 20.000 por cliente y hora en el sistema. |
| 6 | Eventos | Uno por franja, anunciado: lluvia (−25 %), promoción (+30 %), cajero nuevo (una caja 30 % más lenta), falla del sistema de cobro (todas 20 % más lentas), partido de fútbol (noche −40 %), normal. |
| 7 | Pregunta de la franja | ρ, Ls, Lq, Wq, Pw o s óptimo del modelo M/M/s; ±5 %, 5 puntos. |
| 8 | Resultados | Cola minuto a minuto, medidas observadas frente a las del modelo, curva de costo total por cantidad de cajas. |
| 9 | Ranking | Hasta 70 puntos por costo acumulado relativo + 5 por pregunta. |
| 10 | Caja rápida | Fuera de esta versión (rompe el servicio exponencial). |

Reglas de la simulación: si se cierran cajas, cada cajero termina su cliente; los clientes que quedan
al terminar la franja pasan a la siguiente; a las 22 se cierran las puertas y se atiende a los que
quedaron (esa espera cuenta, las horas de caja no). Cada sábado empieza vacío.

## Calibración (21/11/2026)

Con `python scripts/simular_cajas.py` (1.000 partidas de 8 franjas). Ajuste respecto del diseño:
**máximo 15 cajas** (no 12), porque con promoción a la noche (λ = 130) el óptimo es 14 y con falla, 13.

Verificaciones: fórmulas M/M/s contra la guía (banco 4.1: P0 0,0377, Lq 1,528; Quantum 3.2;
Pizza Pampita), conservación de clientes y simulación de 400 h contra el modelo
(λ = 80, s = 9: Ls 7,77 simulada contra 7,56 del modelo).

Modelo sin eventos:

| Franja | λ | s óptimo | ρ | Wq | Con una caja menos |
|---|---|---|---|---|---|
| Mañana | 40 | 5 | 0,67 | 1,0 min | Wq 4,9 min |
| Mediodía | 80 | 9 | 0,74 | 0,7 min | 2,0 min; con dos menos, 12,9 min y el doble de costo |
| Tarde | 60 | 7 | 0,71 | 0,8 min | 2,9 min |
| Noche | 100 | 11 | 0,76 | 0,6 min | 1,5 min; con dos menos, 5,7 min |

| Estrategia | Costo (miles) | Wq peor franja | Gana |
|---|---|---|---|
| **De manual** (s óptimo del modelo con el evento) | **6.925** | 1,9 min | **94 %** |
| Dos cajas más que el óptimo | 7.393 | 0,3 min | 1 % |
| Regla ρ ≤ 0,85 | 7.402 | 6,4 min | 4 % |
| Una caja menos que el óptimo | 7.481 | 6,8 min | 0 % |
| Óptimo sin mirar eventos | 7.566 | 5,4 min | 2 % |
| Mínimo estable (ρ < 1) | 8.759 | 11,7 min | 0 % |
| 8 cajas todo el día | 11.098 | 22,3 min | 0 % |

El óptimo simulado coincide con el del modelo en mañana, mediodía y tarde; a la noche la simulación da
12 cajas casi empatadas con 11 (los que quedan a las 22 se atienden sin costo de caja). Con el cajero
nuevo el modelo M/M/s no cambia (supone cajas iguales): es un tema para la devolución.

## Estado

| Fase | Estado |
|---|---|
| Diseño | Aprobado (21/11/2026). |
| Calibración | Aprobada (21/11/2026). |
| App, catálogo, portada, CI | Hechos en la rama `colas`; bots y prueba en el navegador (3 equipos, 8 franjas). |
| Testing y unión a `main` | Pendiente. |
