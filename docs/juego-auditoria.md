# Juego de auditoría

Materia: **Control Interno y Auditoría** (Contador Público, 5.º año, 1.er cuatrimestre, 120 h).
Se apoya también en Estadística (muestreo) y Estados Contables y su Análisis.
Rama de trabajo: `auditoria`. Diseño aprobado el 20/11/2026.

## La idea

Cada equipo es un **estudio de auditoría** contratado para dictaminar sobre los estados contables de
un cliente que tiene **errores sorteados al crear la sesión**. Las **horas son limitadas**: auditar
de más hace perder dinero; auditar de menos deja pasar un error importante y lleva a firmar una
opinión equivocada.

## Decisiones aprobadas

| # | Decisión | Aprobado |
|---|---|---|
| 1 | Roles | Cada equipo es un estudio; todos auditan el mismo cliente, con los mismos errores (semilla). |
| 2 | Cliente | "Agroinsumos del Oeste S.A.", distribuidora pampeana ficticia. Rubros: Caja y bancos, Créditos por ventas, Bienes de cambio, Bienes de uso, Inversiones y Deudas. |
| 3 | Rondas | 4 etapas del encargo: Planeamiento, Control interno, Pruebas sustantivas e Informe. Todos pasan juntos de etapa. |
| 4 | Planeamiento | El equipo fija la significatividad y califica el riesgo inherente de cada rubro a partir de la información del cliente. |
| 5 | Control interno | Pruebas de controles por ciclo; cuestan horas y revelan si el control es fuerte o débil. |
| 6 | Pruebas sustantivas | Procedimientos por rubro con un alcance (tamaño de muestra). Cada procedimiento sirve para ciertos errores. |
| 7 | Detección | Probabilística: depende de la eficacia del procedimiento para ese error y del alcance. |
| 8 | Informe | Ajustes propuestos al cliente y opinión: favorable, con salvedades, adversa o abstención. |
| 9 | Puntaje | Honorarios − horas × costo − penalidades (grande por opinión favorable con error importante; menor por opinión más severa de lo necesario). Calidad y eficiencia por separado. |
| 10 | Dificultad | El docente elige cantidad de errores, calidad del control interno y presupuesto de horas. Segundo cliente opcional (más adelante). |
| 11 | Normativa | Lenguaje de la RT 37 (FACPCE) y las NIA, simplificado. |
| 12 | Devolución | Horas en rubros de bajo riesgo, rubros sin evidencia, procedimientos que no servían, significatividad, opinión elegida frente a la correcta. |

## Modelo (propuesta para calibrar)

Detalle en `auditoria/modelo.py`; se calibra con `python scripts/simular_auditoria.py`.

- **Ciclos y rubros:** cada rubro tiene su ciclo de control (Caja ↔ Tesorería, Créditos ↔ Ventas y
  cobranzas, Bienes de cambio ↔ Inventarios, Bienes de uso ↔ Activo fijo, Inversiones ↔ Custodia de
  inversiones, Deudas ↔ Compras y pagos).
- **Riesgo inherente** de cada rubro (bajo, medio o alto), sorteado. El equipo no lo ve: ve
  **señales** en la información del cliente (por ejemplo, "las ventas crecieron 40 % con los mismos
  clientes").
- **Control** de cada ciclo, fuerte o débil (sorteado). Solo se conoce si se prueba.
- **Errores:** la probabilidad de que un rubro tenga un error crece con el riesgo inherente y con el
  control débil. Cada error tiene un tipo (por ejemplo, faltante de caja, créditos incobrables sin
  previsión, inventario inexistente, amortización omitida, pasivo omitido) y un monto en relación con
  la significatividad de referencia. Todos sobrevalúan el resultado.
- **Procedimientos:** 12 en total (2 o 3 por rubro), con alcance nulo, bajo, medio o alto. Cada uno
  tiene una eficacia alta, media o nula para cada tipo de error. Probabilidad de detectar un error:
  1 − Π (1 − eficacia × cobertura del alcance) sobre los procedimientos aplicados. Los números
  aleatorios están fijados en el escenario, así que la misma decisión da el mismo resultado en
  cualquier equipo.
- **Limitación al alcance** (evento opcional): el cliente no permite confirmar saldos de créditos;
  hay procedimientos alternativos.
- **Respuesta del cliente:** acepta cada ajuste con cierta probabilidad.
- **Opinión correcta**, según lo que queda sin corregir (errores rechazados más errores no
  detectados) frente a la significatividad de referencia: menos de 1 vez → favorable; de 1 a 3 veces
  → con salvedades; 3 veces o más → adversa. Con limitación al alcance en un rubro importante y sin
  procedimiento alternativo → abstención.
- **Puntaje:** honorarios − horas × costo de la hora − penalidades: opinión menos severa que la
  correcta (falla de auditoría), opinión más severa que la correcta (pérdida del cliente) y cada rubro
  sin ningún procedimiento sustantivo (evidencia insuficiente).

## Calibración (fase de modelo, 20/11/2026) — para revisar

Con `python scripts/simular_auditoria.py` (2.000 encargos). Ajustes respecto de la primera versión:

- **Coberturas del alcance** bajo 35 %, medio 70 %, alto 95 %; procedimientos eficaces al 95 %.
- **El control pesa más:** con control débil la probabilidad de error se duplica; con control
  fuerte se reduce a la mitad. Los rubros de riesgo bajo casi no tienen errores (5 %).
- **Señales imperfectas:** la señal del planeamiento refleja el riesgo verdadero el 60 % de las
  veces; si no, muestra un nivel vecino.
- **Confianza en los controles (NIA 330):** si se probó un ciclo y su control resultó fuerte, los
  procedimientos de ese rubro llevan 30 % menos horas.
- **Valores:** honorarios $ 12 M; hora $ 20.000; presupuesto 400 h; planeamiento 20 h; 5 h por
  ciclo probado; penalidad por falla de auditoría = 1 vez los honorarios; por opinión más severa =
  0,5; por rubro sin evidencia = 0,1.

- **Debida diligencia** (decidido en la prueba del 20/11/2026): la penalidad por falla baja a la
  mitad si el estudio decidió bien con lo que sabía y cada error que se le escapó estaba en un rubro
  revisado con un procedimiento eficaz para ese error y el alcance que exige su riesgo inherente
  (bajo → bajo, medio → medio, alto → alto).

Resultados (puntaje medio en millones de pesos):

| Estrategia | Puntaje | Horas | Opinión correcta | Fallas | Errores importantes detectados |
|---|---|---|---|---|---|
| Sin procedimientos (firma favorable) | −5,6 | 20 | 17 % | 83 % | 0 % |
| Todo con alcance bajo | 2,5 | 132 | 42 % | 58 % | 38 % |
| Todo con alcance medio | 4,4 | 233 | 70 % | 30 % | 71 % |
| Todo con alcance alto (se pasa del presupuesto en el 19 %) | 4,0 | 371 | 90 % | 10 % | 91 % |
| **Por riesgo inherente** | **4,7** | 245 | 73 % | 27 % | 75 % |
| **Por riesgo y control** | **4,7** | 242 | 75 % | 25 % | 77 % |
| Por riesgo, firma siempre favorable | 1,9 | 242 | 52 % | 48 % | 77 % |

"Todo con alcance bajo" sale primero en cerca del 40 % de los encargos individuales (cuando hay
pocos errores, gastar poco gana), pero falla el 58 % de las veces: buen tema para el cierre de la
clase.

## Versión 2: ajustes con monto, control interno y RT 53 (20/11/2026)

A partir del material del curso de Moodle 2026 de la cátedra (prácticos por rubro, TP 3 de control
interno, modelos de informe de la RT 53). Decisiones aprobadas:

| # | Cambio | Detalle |
|---|---|---|
| 1 | **Ajustes con monto** | Cada error encontrado trae su papel de trabajo (arqueo, conciliación, antigüedad y concurso, circularización, corte, recuento, VNR, recálculo de amortizaciones, baja de un bien, cotización neta, pagos posteriores, cargas sociales), con datos generados por el encargo. El estudio calcula el ajuste; bien calculado (±1 %) suma $ 300.000 y el cliente lo considera; mal calculado o en blanco, el error queda sin corregir. |
| 2 | **Re-trabajo** | Decidido en la calibración: cada error encontrado sin un ajuste bien calculado cuesta $ 300.000. Sin esto, no proponer ajustes rendía lo mismo que calcularlos (5,2 M contra 5,2 M). |
| 3 | **Evaluación del control interno** | Cada ciclo trae un relato de dos rasgos al estilo del TP 3 (oposición de intereses, documentación, controles periódicos); cada rasgo refleja el control real el 80 % de las veces. El estudio califica "confío / no confío"; solo se reducen horas si probó el control y resultó fuerte (NIA 330). Indicador en la devolución, sin puntaje. |
| 4 | **Informe según la RT 37 mod. por la RT 53** | Opinión favorable (no modificada), con salvedades, adversa ("significativo y generalizado"), abstención. Evento de empresa en funcionamiento (30 % de los encargos): si no incluyen la sección «Incertidumbre significativa relacionada con empresa en funcionamiento», 10 % de los honorarios. La pantalla final muestra el informe firmado y el que correspondía, con el modelo de la cátedra (incluye requerimientos legales: SIPA, Ingresos Brutos de La Pampa, Res. FACPCE 420/11). |

Calibración (2.000 encargos; puntaje medio en millones; salvo indicación, ajustes bien calculados y
sección de empresa en funcionamiento cuando corresponde):

| Estrategia | Puntaje |
|---|---|
| Por riesgo y control | **5,2** |
| La misma, calcula mal la mitad de los ajustes | 4,8 |
| La misma, sin proponer ajustes | 4,7 |
| La misma, sin la sección de empresa en funcionamiento | 4,8 |
| Todo con alcance medio | 4,8 |
| Todo con alcance bajo | 2,7 |
| Sin procedimientos (firma favorable) | −5,6 |

`scripts/simular_auditoria.py` verifica además que cada papel de trabajo permita calcular su ajuste
(3.741 papeles en 2.000 encargos). Se probó una partida completa en el navegador.

## Tiempo máximo por ronda (21/11/2026, rama `modalidad_juego`)

El docente puede fijar al crear la sesión los minutos de cada etapa. Si un estudio no envía a tiempo, el sistema decide al azar la etapa: base y porcentaje de significatividad y riesgos (planeamiento); calificación y prueba de cada ciclo (control interno); alcances que respetan la limitación del cliente y el presupuesto de horas (pruebas sustantivas); opinión y párrafo de empresa en funcionamiento (informe). Los ajustes de la pantalla de hallazgos cuentan para el reloj de la etapa 4: si vence, se guardan los que estaban bien cargados. La ronda queda marcada como fuera de tiempo (tablero, CSV, resultados y devolución) y no cambia el puntaje. Funcionamiento común: `DESPLIEGUE.md`, sección *Tiempo máximo por ronda*.

## Estado

| Fase | Estado |
|---|---|
| Diseño | Aprobado (20/11/2026). |
| Modelo y calibración | Aprobados; debida diligencia agregada en la prueba. |
| App, catálogo, portada, CI | Hechos en la rama `auditoria`; probados en el navegador. |
| Versión 2 (material de la cátedra) | Hecha en la rama `auditoria`; probada en el navegador. |
| Testing y unión a `main` | Pendiente. |
