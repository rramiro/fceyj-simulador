"""
Devolución automática del juego "El depósito".

Funciones puras (no dependen de oTree): reciben los meses jugados y devuelven observaciones
para el equipo y el docente: {'tipo': 'fortaleza' | 'alerta' | 'sugerencia', 'tema': str, 'texto': str}.
"""
from nucleo.formato import numero, pesos, porcentaje

from . import modelo

SERVICIO_BAJO = 0.95       # nivel de servicio por debajo de esto: faltan unidades
LOTE_LEJOS = 0.5           # lote más de 50 % lejos de n0 (en promedio)
SOBRECOSTO = 0.25          # costo más de 25 % por encima de la política de manual


def _obs(tipo, tema, texto):
    return dict(tipo=tipo, tema=tema, texto=texto)


def diagnosticar(meses, estado, params, escenario, puesto, equipos, terminado):
    obs = []
    costo = sum(m['costo'] for m in meses)
    costo_rec = sum(m['recomendada']['costo'] for m in meses)
    texto = (f'Costo de gestión acumulado {pesos(costo)}; con la política de manual (n0 y R para la demora máxima) '
             f'habría sido {pesos(costo_rec)}.')
    if puesto:
        texto += f' Puesto {puesto} de {equipos}.'
    tipo = 'fortaleza' if costo <= costo_rec * (1 + SOBRECOSTO) else 'alerta'
    obs.append(_obs(tipo, 'Resultado', texto))

    # Lote frente a n0
    desvios = []
    for m in meses:
        n0 = modelo.formulas(m['mes'], params, escenario)['n0']
        if m['evento'] == 'descuento' and m['con_descuento']:
            continue
        desvios.append(abs(m['lote'] - n0) / n0)
    if desvios:
        promedio = sum(desvios) / len(desvios)
        if promedio > LOTE_LEJOS:
            obs.append(_obs('sugerencia', 'Tamaño del lote',
                            f'En promedio, su lote se alejó {porcentaje(promedio, 0)} del lote óptimo n0 = √(2·co·D/(cm·T)). '
                            'La curva de costos es plana cerca del óptimo, pero no tan lejos.'))
        else:
            obs.append(_obs('fortaleza', 'Tamaño del lote',
                            f'Su lote estuvo cerca del lote óptimo (desvío promedio {porcentaje(promedio, 0)}).'))

    # Faltantes y stock de protección
    demanda = sum(m['demanda'] for m in meses) or 1
    vendidas = sum(m['vendidas'] for m in meses)
    servicio = vendidas / demanda
    perdidas = sum(m['perdidas'] for m in meses)
    if servicio < SERVICIO_BAJO:
        obs.append(_obs('alerta', 'Faltantes',
                        f'Atendieron el {porcentaje(servicio, 0)} de la demanda: perdieron {numero(perdidas)} ventas. '
                        'El punto de pedido tiene que cubrir la demanda durante la demora, más un stock de protección '
                        'para las demoras largas y los días de mucha demanda.'))
    else:
        exceso = [m for m in meses if m['punto_pedido'] > 1.5 * modelo.formulas(m['mes'], params, escenario)['demanda_demora_max']]
        if len(exceso) >= max(1, len(meses) // 2):
            obs.append(_obs('sugerencia', 'Stock de protección',
                            'Casi no tuvieron faltantes, pero con un punto de pedido muy alto: el stock de protección '
                            'también cuesta (cm por cada unidad y cada día).'))
        else:
            obs.append(_obs('fortaleza', 'Faltantes',
                            f'Atendieron el {porcentaje(servicio, 0)} de la demanda con un stock de protección razonable.'))

    # Eventos
    for m in meses:
        ev = m['evento']
        f = modelo.formulas(m['mes'], params, escenario)
        if ev == 'descuento':
            c = modelo.conviene_descuento(m['mes'], params, escenario)
            if c['ahorro'] > 0 and not m['con_descuento']:
                obs.append(_obs('sugerencia', 'Descuento por cantidad',
                                f'En el mes {m["mes"]} convenía pedir lotes de {numero(m["recomendada"]["lote"])} con el '
                                f'descuento (ahorro anual estimado {pesos(c["ahorro"])}) y no lo aprovecharon.'))
            elif c['ahorro'] <= 0 and m['con_descuento']:
                obs.append(_obs('alerta', 'Descuento por cantidad',
                                f'En el mes {m["mes"]} tomaron el descuento, pero el lote mínimo era tan grande que el costo '
                                f'de mantenerlo superaba el ahorro (ahorro anual estimado {pesos(c["ahorro"])}).'))
        elif ev == 'huelga' and m['punto_pedido'] < f['demanda_demora_max'] * 0.9:
            obs.append(_obs('sugerencia', 'Huelga del proveedor',
                            f'En el mes {m["mes"]} la demora máxima subió y su punto de pedido ({numero(m["punto_pedido"])}) '
                            f'no cubría la demanda de esa demora ({numero(f["demanda_demora_max"])}).'))
        elif ev == 'campania' and m['lote'] < f['n0'] * 0.8 and m['punto_pedido'] < f['demanda_demora_max'] * 0.9:
            obs.append(_obs('sugerencia', 'Campaña de ventas',
                            f'En el mes {m["mes"]} la demanda subió y no ajustaron ni el lote ni el punto de pedido.'))

    # Preguntas
    aciertos = sum(1 for m in meses if m['pregunta']['acierto'])
    if aciertos == len(meses):
        obs.append(_obs('fortaleza', 'Preguntas', f'Acertaron las {len(meses)} preguntas del modelo.'))
    else:
        falla = next(m for m in meses if not m['pregunta']['acierto'])
        p = falla['pregunta']
        valor = pesos(p['correcto']) if p['unidad'].startswith('$') else f'{numero(p["correcto"], 1)} {p["unidad"]}'
        obs.append(_obs('sugerencia', 'Preguntas',
                        f'Acertaron {aciertos} de {len(meses)} preguntas. Por ejemplo, en el mes {falla["mes"]} '
                        f'({p["texto"].split(" (")[0]}) el valor era {valor}.'))
    return obs
