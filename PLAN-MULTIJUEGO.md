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
| 1 | Acordar las decisiones de diseño. | Hecho (sección 5). |
| 2 | Sacar a `nucleo/` lo común, sin cambiar comportamiento. | Hecho: `nucleo/` con formato, inflación y ajustes de oTree; bots, simulación idéntica y huella `96a288a9b1ed499a` sin cambios. |
| 3 | Resumen y tablero genéricos, con gaseosas migrado al nuevo formato. | Hecho: `nucleo/tablero.py` define el resumen común (versión 2) y el tablero lo muestra sin código propio de cada juego; se ve igual que antes. |
| 4 | Catálogo: portada, selector de juego en "Nueva sesión" y salas. | Hecho: catálogo `_static/juegos/catalogo.json` (verificado en CI), selector de juego y aula en el tablero, aulas `aula`, `aula2` y `aula3` (oTree no admite guiones), portada con los dos juegos y encabezado según el juego. |
| 5 | Modelo de la cartera como funciones puras, más `scripts/simular_cartera.py`. | El docente revisa los números y la calibración. |
| 6 | App `cartera`: pantallas, gráficos, devolución, tablero y bots. | Se juega de punta a punta. |
| 7 | Integración y prueba en testing. | CI corre los bots de los dos juegos. Prueba en el aula antes de unir a `main`. |
| 8 | Documentación: portada y `DESPLIEGUE.md`. | — |

## 5. Decisiones (aprobadas el 2026-11-19)

| # | Decisión | Aprobado |
|---|---|---|
| 1 | Horizonte | 3 años (12 trimestres) por defecto; el docente elige de 1 a 4 años. Informe anual cada 4 trimestres. |
| 2 | Datos | Rendimientos simulados con parámetros de tipo histórico y semilla por sesión (escenario repetible). Datos reales, más adelante. |
| 3 | Moneda | Principal: pesos constantes (rentabilidad real). También se muestra en dólares. |
| 4 | Ranking | Rentabilidad real anual efectiva (TEA real) del período. Sharpe y caída máxima: informativos y en la devolución. |
| 5 | Costos | Comisión del 0,5 % sobre el monto comprado o vendido al rebalancear (configurable). |
| 6 | Restricciones | Pasos de 5 %, de 0 a 100 % por activo. Sin venta en descubierto ni endeudamiento. |
| 7 | Información | Inflación y tipo de cambio del trimestre anterior, tasas vigentes, rendimientos pasados y un titular de noticias que anticipa con error. Sin investigación paga en la primera versión. |
| 8 | Ritmo | Sincronizado: todos pasan juntos de trimestre (el escenario es común). |
| 9 | Salas | `aula`, `aula2` y `aula3`; el docente elige la sala al crear la sesión; cualquier juego en cualquier sala. |
| 10 | Despliegue de la rama | Disparo manual que despliega una rama elegida solo en testing. |

### Parámetros iniciales de la cartera (a calibrar en la fase 5)

| Concepto | Valor |
|---|---|
| Capital inicial | $10.000.000 |
| Inflación | Misma trayectoria configurable que gaseosas |
| Acciones internacionales | Media 2 % trimestral en dólares (≈ 8 % anual); volatilidad 8 % trimestral (≈ 16 % anual) |
| Tipo de cambio | Depreciación igual a la inflación, con desvío de ± 6 % trimestral |
| Bonos de renta fija | Inflación + 1 % real trimestral; duración 3 años |
| Liquidez (plazo fijo) | Inflación esperada − 0,5 % trimestral |
| Crisis | 8 % por trimestre: acciones −20 % en dólares, dólar +15 %, bonos −5 % |
| Carteras de referencia | 60/30/10, todo liquidez, todo acciones |
