# Plan multijuego

Objetivo: que el sitio admita varios simuladores de negocios. El primero es el de
comercialización (mercado de gaseosas). El segundo será la administración de una cartera de
inversión con acciones internacionales, bonos de renta fija y liquidez.

Rama de trabajo: `multijuego`.

## 1. Qué está atado hoy al juego de gaseosas

| Pieza | Qué está atado a gaseosas |
|---|---|
| `settings.py` | Tiene una sola configuración de sesión y una sola sala, `aula`. |
| Encabezado, bienvenida del aula, aula llena | El texto dice "Mercado de gaseosas". |
| Tablero docente (`_static/docente/docente.js`) | Supone mercados, precio, publicidad y stock. El formulario "Nueva sesión" tiene campos fijos (empresas por mercado, estación de inicio). El CSV pide `app=comercializacion`. |
| Portada para docentes y estudiantes | Describe un único juego. |
| `comercializacion/` | Contiene cosas que sirven para cualquier juego mezcladas con lo propio del juego: la inflación y el índice, el formato de montos, `ajustes_otree` y el armado de lo que lee el tablero. |
| CI y bots | Prueban solo `comercializacion`. |

La infraestructura no cambia: Docker, Caddy, la API y los despliegues se quedan como están. Una
app nueva cambia la huella del esquema de base de datos (`scripts/esquema.py`), así que testing
borra y recrea su base sola. Producción todavía no se usa, así que no afecta.

## 2. Arquitectura propuesta

- **Cada juego es una app de oTree con su configuración de sesión:** `comercializacion/` (no
  cambia de nombre) y `cartera/`.
- **Paquete común `nucleo/`** (Python común, no es una app):
  - inflación, índice y moneda constante;
  - formato de montos y porcentajes;
  - `ajustes_otree` (la página de aula llena);
  - un armador del resumen que lee el tablero.
- **Ficha de cada juego** (`juego.py` dentro de cada app):
  - nombre, descripción y nombre de las rondas (trimestres);
  - campos del formulario "Nueva sesión";
  - indicadores y columnas que muestra el tablero;
  - cómo se agrupan los participantes: mercados o individual.
- **Resumen común para el tablero.** Cada juego deja en el participante el mismo formato de
  resumen:
  - juego, ronda, página y si terminó;
  - indicadores, cada uno con etiqueta, valor y formato;
  - historial con columnas y filas;
  - devolución automática y comentario del docente.

  Con eso el tablero muestra cualquier juego sin código específico de cada uno. Primero se migra
  gaseosas a ese formato, sin que cambie nada visible.
- **Tablero docente:**
  - "Nueva sesión" empieza con un selector de juego y arma sus campos según la ficha;
  - la lista de sesiones muestra de qué juego es cada una;
  - el CSV se descarga de la app que corresponda.
- **Plantillas genéricas:** el encabezado y la bienvenida del aula toman el nombre del juego de la
  sesión.
- **Portada como catálogo:** una tarjeta por juego, cada una con su página de "cómo se juega".
- **Salas.** Una sala de oTree tiene una sola sesión activa a la vez. Hay que decidir el esquema
  (decisión 9).

## 3. Segundo juego: cartera de inversión (propuesta inicial)

- **Decisión trimestral:** qué porcentaje va a acciones internacionales, a bonos de renta fija y
  a liquidez. Los tres suman 100 %.
- **Horizonte:** por ejemplo 2 a 3 años (8 a 12 trimestres), con un informe anual cada 4
  trimestres.
- **Escenario:** todos los equipos de la sesión enfrentan los mismos rendimientos, generados al
  crear la sesión. No compiten en un mercado común: cada equipo juega solo y hay un ranking de
  toda la sesión.
- **Modelo de rendimientos:**
  - **Acciones:** rendimiento en dólares con media y volatilidad. En pesos, se suma la variación
    del tipo de cambio.
  - **Bonos:** cupón conocido más un efecto de precio cuando cambian las tasas, a través de la
    duración. Esto conecta con Matemática Financiera.
  - **Liquidez:** tasa de plazo fijo o caución, con poco riesgo, pero puede perder contra la
    inflación.
  - Correlaciones entre los tres activos y, opcionalmente, episodios de crisis.
- **Información por trimestre:** tasas vigentes, rendimientos pasados y, opcionalmente, noticias
  o pronósticos.
- **Evaluación anual:**
  - rentabilidad nominal y real, en pesos y en dólares;
  - volatilidad, índice de Sharpe y caída máxima;
  - comparación contra carteras de referencia: 60/40, todo en liquidez, todo en acciones.
- **Devolución automática:** por ejemplo diversificación, exceso de rebalanceo o costo de
  mantener liquidez con inflación.
- **Pantallas:** Instrucciones, Situación del trimestre, Decisión, Resultado del trimestre,
  Informe anual, Resultado final.

## 4. Fases

| # | Fase | Cuándo está terminada |
|---|---|---|
| 0 | Crear la rama `multijuego` desde `main`. | Hecho. |
| 1 | Acordar las decisiones de diseño. | El docente aprueba. |
| 2 | Sacar a `nucleo/` lo común, sin cambiar comportamiento. | Pasan los bots y la huella del esquema queda igual. |
| 3 | Resumen y tablero genéricos, con gaseosas migrado al nuevo formato. | El tablero se ve exactamente igual que hoy. |
| 4 | Catálogo: portada, selector de juego en "Nueva sesión" y salas. | Se puede crear una sesión de gaseosas desde el selector. |
| 5 | Modelo de la cartera como funciones puras, más `scripts/simular_cartera.py`. | El docente revisa los números y la calibración. |
| 6 | App `cartera`: pantallas, gráficos, devolución, tablero y bots. | Se juega de punta a punta. |
| 7 | Integración y prueba en testing. | CI corre los bots de los dos juegos. Prueba en el aula antes de unir a `main`. |
| 8 | Documentación: portada y `DESPLIEGUE.md`. | — |

## 5. Decisiones pendientes (del docente)

1. **Horizonte:** ¿cuántos años y trimestres? ¿El docente lo configura?
2. **Datos:** ¿rendimientos simulados con parámetros, o históricos reales, por ejemplo un período
   elegido al azar?
3. **Moneda de evaluación:** pesos reales, dólares o ambas.
4. **Métrica del ranking:** rentabilidad real, Sharpe o una combinación.
5. **Costos:** ¿hay comisión por rebalancear?
6. **Restricciones:** ¿hay mínimos o máximos por activo? ¿Los porcentajes van en pasos de 5 %?
7. **Información:** ¿noticias o pronósticos por trimestre? ¿Investigación paga, como en gaseosas?
8. **Ritmo:** ¿cada equipo avanza libre, o todos esperan para pasar juntos de trimestre, como en
   los mercados?
9. **Salas:** ¿una sola `aula` para todo, o una por comisión o docente, para que haya clases en
   paralelo?
10. **Despliegue de la rama:** ¿la subimos a testing antes de unirla a `main`? Hoy el despliegue
    solo corre desde `main`; habría que agregar un disparo manual por rama.
