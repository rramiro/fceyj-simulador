"""
Devolución automática del juego de costos.

Funciones puras (no dependen de oTree): reciben los resultados de cada mes y el estado
final del taller, y devuelven observaciones en texto para el equipo y el docente.

Cada observación es un dict:
    {'tipo': 'fortaleza' | 'alerta' | 'sugerencia', 'tema': str, 'texto': str}
"""

from nucleo.formato import numero, pesos, porcentaje

from . import modelo

OCIOSIDAD_ALTA = 0.25      # capacidad ociosa promedio de corte considerada alta
FALTANTE_ALTO = 0.10       # demanda no atendida / demanda
DESVIO_ALTO = 0.03         # desvíos / ventas
STOCK_ALTO = 0.5           # stock final / ventas promedio del mes (en unidades)


def _obs(tipo, tema, texto):
    return dict(tipo=tipo, tema=tema, texto=texto)


def _decision(tipo, valor):
    if tipo == 'bordado':
        return f'bordar el {porcentaje(valor or 0, 0)}'
    return 'sí' if valor else 'no'


def diagnosticar(meses, estado, params, puesto, equipos, terminado):
    obs = []
    n = len(meses)
    periodo = 'del juego' if terminado else 'hasta ahora'
    obs.append(_obs('fortaleza' if estado['resultado_var'] > 0 else 'alerta', 'Resultado',
                    f'Resultado acumulado {periodo} por costeo variable: {pesos(estado["resultado_var"])} '
                    f'(por costeo integral: {pesos(estado["resultado_int"])}). Puesto {puesto} de {equipos}.'))

    # Tiempo máximo por mes
    tarde = [r['mes'] for r in meses if r.get('fuera_de_tiempo')]
    if tarde:
        lista = ', '.join(str(m) for m in tarde)
        obs.append(_obs('alerta', 'Tiempo',
                        f'No enviaron el plan a tiempo en {len(tarde)} mes{"es" if len(tarde) > 1 else ""} ({lista}): '
                        'el sistema decidió al azar. Conviene repartir el tiempo y enviar un plan razonable antes '
                        'del cierre, aunque no esté perfecto.'))

    # Informes al empresario
    aciertos = [r for r in meses if r['informe']['acierto']]
    errados = [r for r in meses if not r['informe']['acierto']]
    texto = f'Acertaron {len(aciertos)} de {n} informes al empresario.'
    if errados:
        r = errados[-1]
        inf = r['informe']
        correcto = pesos(inf['correcto']) if inf['unidad'] == '$' else f'{numero(inf["correcto"] or 0)} {inf["unidad"]}'
        texto += f' Por ejemplo, en el mes {r["mes"]} ({inf["pregunta"].lower()}) el valor correcto era {correcto}.'
    obs.append(_obs('fortaleza' if len(aciertos) >= n * 0.8 else 'sugerencia', 'Informes', texto))

    # Decisiones de los eventos
    for r in meses:
        if r['recomendada'] is None:
            continue
        if _decision(r['evento'], r['decision']) != _decision(r['evento'], r['recomendada']):
            obs.append(_obs('alerta', modelo.NOMBRES_EVENTO[r['evento']],
                            f'En el mes {r["mes"]} decidieron {_decision(r["evento"], r["decision"])} y, con los datos que '
                            f'tenían, convenía {_decision(r["evento"], r["recomendada"])}.'))
    bien = sum(1 for r in meses if r['recomendada'] is not None
               and _decision(r['evento'], r['decision']) == _decision(r['evento'], r['recomendada']))
    total = sum(1 for r in meses if r['recomendada'] is not None)
    if total and bien == total:
        obs.append(_obs('fortaleza', 'Decisiones', f'Resolvieron bien los {total} eventos con decisión.'))

    # Capacidad ociosa y faltantes
    ocio = sum(r['ociosidad_corte'] for r in meses) / n
    faltante = sum(f['faltante'] for r in meses for f in r['filas'].values())
    demanda = sum(f['demanda'] for r in meses for f in r['filas'].values()) or 1
    if ocio >= OCIOSIDAD_ALTA and faltante / demanda >= FALTANTE_ALTO:
        # Las dos cosas a la vez: produjeron menos de lo que podían y de lo que se pedía.
        obs.append(_obs('alerta', 'Producción insuficiente',
                        f'Quedó sin atender el {porcentaje(faltante / demanda, 0)} de la demanda mientras la capacidad de '
                        f'corte estaba ociosa en un {porcentaje(ocio, 0)} en promedio: producir más (o usar el stock) '
                        'habría sumado contribución marginal sin costos fijos adicionales.'))
    elif ocio >= OCIOSIDAD_ALTA:
        obs.append(_obs('sugerencia', 'Capacidad',
                        f'En promedio quedó ociosa el {porcentaje(ocio, 0)} de la capacidad de corte: los costos fijos de '
                        'capacidad se pagan igual. ¿Había lugar para bajar el precio o aceptar trabajos adicionales?'))
    elif faltante / demanda >= FALTANTE_ALTO:
        obs.append(_obs('sugerencia', 'Demanda no atendida',
                        f'Quedó sin atender el {porcentaje(faltante / demanda, 0)} de la demanda. Si la capacidad no alcanza, '
                        'conviene subir el precio antes que dejar clientes sin atender.'))

    # Stock e integral contra variable
    ventas_mes = sum(f['vendidas'] for r in meses for f in r['filas'].values()) / n or 1
    stock_final = sum(estado['stock'].values())
    if stock_final / ventas_mes >= STOCK_ALTO:
        cf_en_stock = sum(estado['valor_int'].values()) - sum(estado['valor_var'].values())
        obs.append(_obs('alerta', 'Stock',
                        f'Terminaron con {numero(stock_final)} cortinas en stock. Por costeo integral, el stock "guarda" '
                        f'{pesos(cf_en_stock)} de costos fijos y mejora el resultado; por costeo variable, no. '
                        'Producir de más no genera ganancia.'))

    # Desvíos
    ventas = sum(r['ventas'] for r in meses) or 1
    desvios = sum(sum(r['desvios'].values()) for r in meses)
    if desvios / ventas >= DESVIO_ALTO:
        mayor = max(('precio_tela', 'consumo_tela', 'eficiencia_mo'),
                    key=lambda k: sum(r['desvios'][k] for r in meses))
        nombre = dict(precio_tela='precio de la tela', consumo_tela='consumo de tela',
                      eficiencia_mo='eficiencia de la mano de obra')[mayor]
        obs.append(_obs('sugerencia', 'Desvíos',
                        f'Los desvíos desfavorables sumaron {pesos(desvios)}, sobre todo por {nombre}. Si una suba es '
                        'permanente, corresponde revisar el estándar y los precios.'))
    return obs
