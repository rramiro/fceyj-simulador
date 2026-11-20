"""
Devolución automática del juego de auditoría.

Funciones puras (no dependen de oTree): reciben el encargo, lo que decidió el estudio
y su evaluación, y devuelven observaciones en texto para el equipo y el docente.

Cada observación es un dict:
    {'tipo': 'fortaleza' | 'alerta' | 'sugerencia', 'tema': str, 'texto': str}
"""

from nucleo.formato import numero, pesos

from . import modelo

# --- Umbrales -----------------------------------------------------------------
SIGNIF_MIN = 0.5      # significatividad propia / referencia por debajo de esto: muy baja
SIGNIF_MAX = 2.0      # por encima de esto: muy alta
HORAS_BAJO_RIESGO = 0.35   # parte de las horas sustantivas en rubros de riesgo bajo y control fuerte


def _obs(tipo, tema, texto):
    return dict(tipo=tipo, tema=tema, texto=texto)


def _nombres(rubros):
    return ', '.join(modelo.RUBROS[r]['nombre'] for r in rubros)


def diagnosticar(esc, riesgos_propios, significatividad, ciclos, alcances, ev, params, puesto, equipos,
                 calificaciones=None):
    obs = []

    # Resultado
    texto = (f'Puntaje {pesos(ev["puntaje"])}, puesto {puesto} de {equipos}. Usaron {numero(ev["horas"])} horas y '
             f'detectaron {ev["importantes_detectados"]} de {ev["importantes"]} errores importantes.')
    obs.append(_obs('fortaleza' if ev['comparacion'] == 'correcta' else 'alerta', 'Resultado', texto))

    # Opinión
    correcta = modelo.NOMBRES_OPINION[ev['opinion_correcta']].lower()
    elegida = modelo.NOMBRES_OPINION[ev['opinion']].lower()
    if ev['comparacion'] == 'correcta':
        obs.append(_obs('fortaleza', 'Opinión', f'Emitieron la opinión que correspondía ({elegida}).'))
    elif ev['comparacion'] == 'falla':
        no_det = [e for e in ev['no_detectados'] if e['monto'] >= esc['significatividad']]
        motivo = (f' Quedaron sin detectar errores importantes en {_nombres({e["rubro"] for e in no_det})}.'
                  if no_det else '')
        if ev.get('diligente'):
            obs.append(_obs('sugerencia', 'Opinión',
                            f'Firmaron una {elegida} y correspondía una {correcta}.{motivo} Pero actuaron '
                            'con la debida diligencia: decidieron bien con lo que sabían y revisaron esos rubros con '
                            'procedimientos adecuados, así que la penalidad se redujo a la mitad. El riesgo de detección '
                            'nunca es cero.'))
        else:
            obs.append(_obs('alerta', 'Opinión',
                            f'Firmaron una {elegida} y correspondía una {correcta}: es una falla de '
                            f'auditoría, con responsabilidad profesional.{motivo}'))
    else:
        obs.append(_obs('sugerencia', 'Opinión',
                        f'Su opinión ({elegida}) fue más severa de lo necesario: correspondía {correcta}. '
                        'Un informe más grave que la realidad también tiene costo: el cliente se va.'))

    # Significatividad
    if significatividad:
        ratio = significatividad / esc['significatividad']
        if ratio < SIGNIF_MIN:
            obs.append(_obs('sugerencia', 'Significatividad',
                            f'Fijaron una significatividad de {pesos(significatividad)}, muy baja frente a una referencia '
                            f'de {pesos(esc["significatividad"])} (5 % del resultado): obliga a trabajar de más.'))
        elif ratio > SIGNIF_MAX:
            obs.append(_obs('alerta', 'Significatividad',
                            f'Fijaron una significatividad de {pesos(significatividad)}, muy alta frente a una referencia '
                            f'de {pesos(esc["significatividad"])}: errores importantes pueden parecer menores.'))
        else:
            obs.append(_obs('fortaleza', 'Significatividad',
                            f'Su significatividad ({pesos(significatividad)}) está en un rango razonable.'))

    # Lectura del riesgo inherente
    aciertos = sum(1 for r, d in esc['rubros'].items() if riesgos_propios.get(r) == d['riesgo'])
    subestimados = [r for r, d in esc['rubros'].items()
                    if d['riesgo'] == 'alto' and riesgos_propios.get(r) == 'bajo']
    texto = f'Calificaron bien el riesgo inherente de {aciertos} de {len(esc["rubros"])} rubros.'
    if subestimados:
        texto += f' Subestimaron rubros de riesgo alto: {_nombres(subestimados)}.'
    obs.append(_obs('fortaleza' if aciertos >= 4 and not subestimados else 'sugerencia', 'Riesgo inherente', texto))

    # Control interno
    debiles = [r for r, d in esc['rubros'].items() if d['control'] == 'debil']
    if not ciclos:
        obs.append(_obs('sugerencia', 'Control interno',
                        'No probaron ningún control. Probarlos cuesta pocas horas: si el control es fuerte, se '
                        'reducen las pruebas sustantivas; si es débil, se sabe dónde concentrar el trabajo.'))
    else:
        debiles_vistos = [r for r in ciclos if r in debiles]
        texto = f'Probaron {len(ciclos)} ciclos de control.'
        if debiles_vistos:
            texto += f' Encontraron controles débiles en {_nombres(debiles_vistos)}.'
        obs.append(_obs('fortaleza', 'Control interno', texto))

    # Evaluación del control interno a partir del relato
    if calificaciones:
        bien = modelo.evaluacion_control(esc, calificaciones)
        confiaron_debiles = [r for r, c in calificaciones.items() if c == 'confio' and esc['rubros'][r]['control'] == 'debil']
        texto = f'Evaluaron bien el control interno de {bien} de {len(esc["rubros"])} ciclos a partir del relato.'
        if confiaron_debiles:
            texto += (f' Confiaron en controles que eran débiles: {_nombres(confiaron_debiles)}. Fíjense en la '
                      'oposición de intereses: quien custodia no debe registrar ni autorizar.')
        sin_probar = [r for r, c in calificaciones.items() if c == 'confio' and r not in ciclos]
        if sin_probar:
            texto += (f' Dijeron confiar en {_nombres(sin_probar)} sin probarlo: para reducir las pruebas '
                      'sustantivas hay que probar el control (NIA 330).')
        obs.append(_obs('fortaleza' if bien >= 5 and not confiaron_debiles else 'sugerencia', 'Evaluación del control', texto))

    # Ajustes calculados con los papeles de trabajo
    if ev['encontrados']:
        n = len(ev['encontrados'])
        mal = [e for e in ev['encontrados'] if ev['estados'][e['id']] in ('devuelto', 'sin_proponer')]
        if not mal:
            obs.append(_obs('fortaleza', 'Ajustes', ('Calcularon bien el ajuste propuesto.' if n == 1 else f'Calcularon bien los {n} ajustes propuestos.')))
        else:
            detalle = '; '.join(f'{modelo.ERRORES[e["tipo"]]["nombre"].lower()}: {pesos(e["monto"])}' for e in mal)
            obs.append(_obs('alerta', 'Ajustes',
                            f'Calcularon bien {n - len(mal)} de {n} ajustes. Los que no ({detalle}) quedaron sin '
                            'corregir en los estados contables y pesan en la opinión.'))

    # Empresa en funcionamiento
    if ev.get('empresa_funcionamiento'):
        if ev.get('enfasis'):
            obs.append(_obs('fortaleza', 'Empresa en funcionamiento',
                            'Incluyeron la sección sobre la incertidumbre significativa relacionada con empresa en '
                            'funcionamiento: no modifica la opinión, pero el lector tiene que saberlo.'))
        else:
            obs.append(_obs('alerta', 'Empresa en funcionamiento',
                            'La nota 12 revelaba pérdidas recurrentes y una deuda bancaria vencida en refinanciación: '
                            'el informe debía incluir la sección «Incertidumbre significativa relacionada con empresa '
                            'en funcionamiento».'))
    elif ev.get('enfasis'):
        obs.append(_obs('sugerencia', 'Empresa en funcionamiento',
                        'Incluyeron la sección sobre empresa en funcionamiento, pero no había una incertidumbre '
                        'significativa: usar esos párrafos sin necesidad les quita peso (RT 37).'))

    # Rubros sin evidencia
    if ev['sin_evidencia']:
        obs.append(_obs('alerta', 'Evidencia',
                        f'No aplicaron ningún procedimiento en {_nombres(ev["sin_evidencia"])}: firmar sin evidencia '
                        'suficiente es una falta profesional, aunque no haya errores.'))

    # Horas mal distribuidas: mucho alcance en rubros de riesgo bajo y control fuerte
    p = params
    sust = modelo.horas_sustantivas(alcances, p, esc, ciclos) or 1
    tranquilos = [r for r, d in esc['rubros'].items() if d['riesgo'] == 'bajo' and d['control'] == 'fuerte']
    horas_tranquilos = sum(modelo.horas_sustantivas({pr: a}, p, esc, ciclos)
                           for pr, a in alcances.items() if modelo.PROCEDIMIENTOS[pr]['rubro'] in tranquilos)
    if tranquilos and horas_tranquilos / sust >= HORAS_BAJO_RIESGO:
        obs.append(_obs('sugerencia', 'Horas',
                        f'Destinaron {numero(100 * horas_tranquilos / sust)} % de las horas de pruebas sustantivas a '
                        f'rubros de riesgo bajo y control fuerte ({_nombres(tranquilos)}).'))

    # Procedimientos que no servían para el error que había
    for e in ev['no_detectados']:
        aplicados = [pr for pr, a in alcances.items() if a and modelo.PROCEDIMIENTOS[pr]['rubro'] == e['rubro']]
        if aplicados and all(modelo.PROCEDIMIENTOS[pr]['eficacia'].get(e['tipo'], 0) == 0 for pr in aplicados):
            utiles = [d['nombre'] for d in modelo.PROCEDIMIENTOS.values() if d['eficacia'].get(e['tipo'], 0) >= 0.9]
            obs.append(_obs('sugerencia', 'Procedimientos',
                            f'En {modelo.RUBROS[e["rubro"]]["nombre"]} había "{modelo.ERRORES[e["tipo"]]["nombre"]}" y '
                            f'los procedimientos que aplicaron no sirven para detectarlo. El indicado: {", ".join(utiles)}.'))

    # Limitación al alcance
    if esc['limitacion']:
        if alcances.get('antiguedad'):
            obs.append(_obs('fortaleza', 'Limitación al alcance',
                            'El cliente no dejó confirmar saldos de créditos y aplicaron un procedimiento alternativo.'))
        else:
            obs.append(_obs('alerta', 'Limitación al alcance',
                            'El cliente no dejó confirmar saldos de créditos y no aplicaron un procedimiento '
                            'alternativo: sin evidencia sobre un rubro tan importante, correspondía abstenerse.'))
    return obs
