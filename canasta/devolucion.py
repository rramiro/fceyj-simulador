"""
Devolución automática del juego "La canasta de Soledad".

Funciones puras (no dependen de oTree): reciben los meses jugados y devuelven observaciones
para el equipo y el docente: {'tipo': 'fortaleza' | 'alerta' | 'sugerencia', 'tema': str, 'texto': str}.
"""
from nucleo.formato import numero, pesos, porcentaje

from . import modelo


def _obs(tipo, tema, texto):
    return dict(tipo=tipo, tema=tema, texto=texto)


def diagnosticar(rondas, params, tipo, puesto, equipos):
    obs = []
    t = modelo.TIPOS[tipo]
    optimas = sum(1 for r in rondas if r['distancia'] == 0)
    perdido = sum(r['ingreso_perdido'] for r in rondas)
    texto = (f'Eligieron la canasta óptima en {optimas} de {len(rondas)} meses. En total, sus elecciones '
             f'equivalen a haber perdido {pesos(perdido)} de ingreso.')
    if puesto:
        texto += f' Puesto {puesto} de {equipos}.'
    obs.append(_obs('fortaleza' if optimas >= len(rondas) * 0.75 else 'alerta', 'Resultado', texto))

    # ¿Se pasan o se quedan cortos con el cine?
    lejos = [r for r in rondas if r['distancia'] >= 2]
    if lejos:
        de_mas = sum(1 for r in lejos if r['x'] > r['x_opt'])
        r = max(lejos, key=lambda z: z['distancia'])
        sentido = 'más' if r['x'] > r['x_opt'] else 'menos'
        regla = ('la TMS de su canasta era menor que Px/Py: les convenía cambiar entradas por alimentos'
                 if r['x'] > r['x_opt'] else
                 'la TMS de su canasta era mayor que Px/Py: les convenía cambiar alimentos por entradas')
        obs.append(_obs('sugerencia', 'Tangencia',
                        f'En {len(lejos)} mes(es) quedaron a dos entradas o más del óptimo'
                        f'{" (casi siempre comprando de más)" if de_mas > len(lejos) / 2 else ""}. Por ejemplo, en '
                        f'{r["mes"].lower()} compraron {r["x"]} entradas, {r["distancia"]} {sentido} que las '
                        f'{r["x_opt"]} óptimas: {regla}. En el óptimo la curva de indiferencia toca la recta de '
                        'presupuesto (TMS = Px/Py).'))

    # Lo propio de cada tipo de consumidor.
    por_ronda = {r['ronda']: r for r in rondas}
    if tipo == 'equilibrado':
        obs.append(_obs('sugerencia', 'Su tipo de consumidor',
                        f'Como consumidor {t["nombre"].lower()} (Cobb-Douglas), gastar siempre la misma parte del '
                        f'ingreso en cine (alrededor del {porcentaje(t["a"], 0)}) era la regla óptima: la demanda '
                        'es X = a·I/Px, con elasticidad precio −1 y elasticidad ingreso 1.'))
    elif tipo == 'cinefilo' and 2 in por_ronda and 1 in por_ronda:
        r1, r2 = por_ronda[1], por_ronda[2]
        obs.append(_obs('sugerencia', 'Su tipo de consumidor',
                        f'Como consumidor {t["nombre"].lower()}, sus curvas de indiferencia eran casi rectas: con la '
                        f'promo el óptimo pasaba de {r1["x_opt"]} a {r2["x_opt"]} entradas (ustedes: de {r1["x"]} a '
                        f'{r2["x"]}). Cuando los bienes son buenos sustitutos, la demanda es elástica.'))
    elif tipo == 'combo' and 6 in por_ronda and 1 in por_ronda:
        r1, r6 = por_ronda[1], por_ronda[6]
        obs.append(_obs('sugerencia', 'Su tipo de consumidor',
                        f'Como consumidor {t["nombre"].lower()}, el cine y la comida se complementan: cuando subieron '
                        f'los alimentos, el óptimo pasaba de {r1["x_opt"]} a {r6["x_opt"]} entradas (ustedes: de '
                        f'{r1["x"]} a {r6["x"]}). Con curvas muy curvas, el efecto sustitución es chico.'))

    # Efecto sustitución (Slutsky).
    if 7 in por_ronda and 1 in por_ronda:
        r1, r7 = por_ronda[1], por_ronda[7]
        es = r7['x'] - r1['x']
        if r1['distancia'] != 0:
            # Si la canasta de marzo no era la óptima, la compensación no parte de un óptimo y el "efecto
            # sustitución" medido con sus cantidades puede salir positivo sin contradecir la teoría.
            obs.append(_obs('sugerencia', 'Efecto sustitución',
                            f'En septiembre el ingreso alcanzaba justo para su canasta de marzo ({r1["x"]} entradas), '
                            f'que no era la óptima ({r1["x_opt"]}). La teoría dice que, partiendo del óptimo, una suba '
                            'del precio compensada nunca aumenta la cantidad: el efecto sustitución es cero o negativo.'))
        elif es > 0:
            obs.append(_obs('alerta', 'Efecto sustitución',
                            f'En septiembre la entrada costaba el doble y con la ayuda les alcanzaba para la canasta '
                            f'de marzo, pero compraron más entradas ({r1["x"]} → {r7["x"]}). El efecto sustitución '
                            'de una suba de precio nunca es positivo: el bien que se encarece se reemplaza.'))
        else:
            obs.append(_obs('fortaleza', 'Efecto sustitución',
                            f'Con el ingreso compensado, su efecto sustitución fue de {es} entradas: ante la suba del '
                            'cine, lo reemplazaron por alimentos aunque podían repetir la canasta de marzo.'))

    # Preguntas.
    aciertos = sum(1 for r in rondas if r['pregunta']['acierto'])
    if aciertos == len(rondas):
        obs.append(_obs('fortaleza', 'Preguntas', f'Acertaron las {len(rondas)} preguntas.'))
    else:
        falla = next(r for r in rondas if not r['pregunta']['acierto'])
        p = falla['pregunta']
        valor = numero(p['correcto'], 2)
        if p['unidad'] != '(número)':
            valor += f' {p["unidad"]}'
        obs.append(_obs('sugerencia', 'Preguntas',
                        f'Acertaron {aciertos} de {len(rondas)} preguntas. Por ejemplo, en {falla["mes"].lower()} '
                        f'el valor era {valor}. Las elasticidades arco se calculan con el punto medio: '
                        '(ΔX / X medio) / (Δprecio / precio medio).'))
    return obs
