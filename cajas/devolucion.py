"""
Devolución automática del juego "Las cajas del súper".

Funciones puras (no dependen de oTree): reciben las franjas jugadas y devuelven observaciones
para el equipo y el docente: {'tipo': 'fortaleza' | 'alerta' | 'sugerencia', 'tema': str, 'texto': str}.
"""
from nucleo.formato import numero, pesos

from . import modelo

SOBRECOSTO = 0.10          # costo más de 10 % por encima del modelo
ESPERA_LARGA = 5           # minutos de espera media en una franja


def _obs(tipo, tema, texto):
    return dict(tipo=tipo, tema=tema, texto=texto)


def diagnosticar(rondas, params, escenario, puesto, equipos):
    obs = []
    costo = sum(r['costo'] for r in rondas)
    costo_rec = sum(r['recomendada']['costo'] for r in rondas)
    texto = (f'Costo acumulado {pesos(costo)}; con las cajas óptimas del modelo M/M/s (CT = Cs·s + Cc·Ls) '
             f'habría sido {pesos(costo_rec)}.')
    if puesto:
        texto += f' Puesto {puesto} de {equipos}.'
    obs.append(_obs('fortaleza' if costo <= costo_rec * (1 + SOBRECOSTO) else 'alerta', 'Resultado', texto))

    # Cajas de menos y de más.
    menos = [r for r in rondas if r['cajas'] < r['recomendada']['cajas']]
    mas = [r for r in rondas if r['cajas'] > r['recomendada']['cajas']]
    inestables = []
    for r in rondas:
        d = modelo.datos_ronda(r['ronda'], params, escenario)
        if d['lam'] >= r['cajas'] * d['mu']:
            inestables.append(r)
    if inestables:
        r = max(inestables, key=lambda x: x['espera_max'])
        obs.append(_obs('alerta', 'Utilización ρ ≥ 1',
                        f'En {len(inestables)} franja(s) abrieron menos cajas que las necesarias para que ρ = λ/(s·μ) '
                        f'sea menor que 1 (por ejemplo, la franja {r["ronda"]}, {r["nombre"].lower()}, con {r["cajas"]} '
                        f'cajas). Con ρ ≥ 1 la cola crece sin límite: la espera llegó a {numero(r["espera_max"], 0)} minutos.'))
    elif menos:
        sobre = sum(r['costo'] - r['recomendada']['costo'] for r in menos)
        obs.append(_obs('sugerencia', 'Cajas de menos',
                        f'En {len(menos)} franja(s) abrieron menos cajas que el óptimo del modelo; la espera extra costó '
                        f'{pesos(max(0, sobre))} más de lo que ahorraron en cajas. Cerca de ρ = 1 la cola crece muy rápido.'))
    if mas and len(mas) >= len(rondas) / 2:
        obs.append(_obs('sugerencia', 'Cajas de más',
                        f'En {len(mas)} de {len(rondas)} franjas abrieron más cajas que el óptimo. Los clientes casi no '
                        'esperaron, pero cada caja de más cuesta Cs por hora y reduce poco Ls.'))
    if not menos and not mas:
        obs.append(_obs('fortaleza', 'Cantidad de cajas',
                        'En todas las franjas abrieron exactamente las cajas que minimizan el costo total del modelo.'))
    elif not inestables and len(menos) + len(mas) <= len(rondas) / 3:
        obs.append(_obs('fortaleza', 'Cantidad de cajas',
                        f'En {len(rondas) - len(menos) - len(mas)} de {len(rondas)} franjas abrieron las cajas óptimas '
                        'del modelo.'))

    # Esperas largas.
    largas = [r for r in rondas if r['wq_observada'] > ESPERA_LARGA]
    if largas:
        r = max(largas, key=lambda x: x['wq_observada'])
        obs.append(_obs('alerta', 'Esperas largas',
                        f'En {len(largas)} franja(s) la espera media en la fila pasó los {ESPERA_LARGA} minutos '
                        f'(la peor: franja {r["ronda"]}, {numero(r["wq_observada"], 1)} minutos con {r["cajas"]} cajas).'))

    # Eventos que cambian λ o μ.
    for r in rondas:
        ev = r['evento']
        s_rec = r['recomendada']['cajas']
        if ev in ('promocion', 'falla') and r['cajas'] < s_rec:
            causa = 'llegaban más clientes' if ev == 'promocion' else 'cada caja atendía más lento (bajó μ)'
            obs.append(_obs('sugerencia', modelo.EVENTOS[ev],
                            f'En la franja {r["ronda"]} {causa} y abrieron {r["cajas"]} cajas; el modelo pedía {s_rec}.'))
        elif ev in ('lluvia', 'partido') and r['cajas'] > s_rec + 1:
            obs.append(_obs('sugerencia', modelo.EVENTOS[ev],
                            f'En la franja {r["ronda"]} llegaban menos clientes y abrieron {r["cajas"]} cajas; '
                            f'con {s_rec} alcanzaba.'))
        elif ev == 'cajero_nuevo':
            obs.append(_obs('sugerencia', 'Límites del modelo',
                            f'En la franja {r["ronda"]} una caja atendía más lento. El modelo M/M/s supone cajas iguales: '
                            'para un caso así conviene simular (unidad 5), como en Quantum Express.'))

    # Preguntas.
    aciertos = sum(1 for r in rondas if r['pregunta']['acierto'])
    if aciertos == len(rondas):
        obs.append(_obs('fortaleza', 'Preguntas', f'Acertaron las {len(rondas)} preguntas del modelo.'))
    else:
        falla = next(r for r in rondas if not r['pregunta']['acierto'])
        p = falla['pregunta']
        valor = numero(p['correcto'], 3 if p['unidad'].startswith('(') else 2)
        if not p['unidad'].startswith('('):
            valor += f' {p["unidad"]}'
        obs.append(_obs('sugerencia', 'Preguntas',
                        f'Acertaron {aciertos} de {len(rondas)} preguntas. Por ejemplo, en la franja {falla["ronda"]} '
                        f'el valor era {valor}.'))
    return obs

