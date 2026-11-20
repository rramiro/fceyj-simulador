import random

from otree.api import *

from nucleo import ajustes_otree, tablero
from nucleo.formato import numero, pesos, porcentaje

from . import devolucion, modelo

# Página propia para "aula completa" (ver nucleo/ajustes_otree.py).
ajustes_otree.aplicar()


doc = """
Simulador de auditoría (FCEJ - UNLPam).
Cada equipo es un estudio de auditoría contratado para dictaminar sobre los
estados contables de un cliente con errores sorteados. El encargo tiene cuatro
etapas: planeamiento, evaluación del control interno, pruebas sustantivas e
informe. Las horas son limitadas.
"""

CLIENTE = 'Agroinsumos del Oeste S.A.'
ETAPAS = {1: 'Planeamiento', 2: 'Control interno', 3: 'Pruebas sustantivas', 4: 'Informe'}
RUBROS = list(modelo.RUBROS)
PROCEDIMIENTOS = list(modelo.PROCEDIMIENTOS)
OPCIONES_RIESGO = [('bajo', 'Bajo'), ('medio', 'Medio'), ('alto', 'Alto')]
OPCIONES_ALCANCE = [(a, d[0]) for a, d in modelo.ALCANCES.items()]
OPCIONES_OPINION = [(o, modelo.NOMBRES_OPINION[o]) for o in modelo.OPINIONES]
BASES_SIGNIFICATIVIDAD = dict(resultado='Resultado antes de impuestos', ventas='Ventas', activo='Activo total')


class C(BaseConstants):
    NAME_IN_URL = 'auditoria'
    # Todos los estudios auditan el mismo cliente y pasan juntos de etapa.
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 4   # una ronda por etapa del encargo
    TITULO_JUEGO = 'Simulador de auditoría'
    SUBTITULO_JUEGO = f'Encargo: {CLIENTE}'


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


def _riesgo(rubro):
    return models.StringField(choices=OPCIONES_RIESGO, label=modelo.RUBROS[rubro]['nombre'])


def _prueba(rubro):
    return models.BooleanField(initial=False, blank=True, widget=widgets.CheckboxInput,
                               label=f'Probar los controles de {modelo.RUBROS[rubro]["ciclo"]}')


def _alcance(proc):
    return models.IntegerField(choices=OPCIONES_ALCANCE, initial=0, label=modelo.PROCEDIMIENTOS[proc]['nombre'])


class Player(BasePlayer):
    nombre_equipo = models.StringField(label='Nombre del estudio', max_length=30, blank=True)

    # Etapa 1: planeamiento
    base_significatividad = models.StringField(
        choices=list(BASES_SIGNIFICATIVIDAD.items()), label='Base para la significatividad')
    pct_significatividad = models.FloatField(min=0.1, max=20, label='Porcentaje sobre la base (%)')
    significatividad = models.FloatField()
    riesgo_caja = _riesgo('caja')
    riesgo_creditos = _riesgo('creditos')
    riesgo_bienes_cambio = _riesgo('bienes_cambio')
    riesgo_bienes_uso = _riesgo('bienes_uso')
    riesgo_inversiones = _riesgo('inversiones')
    riesgo_deudas = _riesgo('deudas')

    # Etapa 2: pruebas de controles (una por ciclo)
    prueba_caja = _prueba('caja')
    prueba_creditos = _prueba('creditos')
    prueba_bienes_cambio = _prueba('bienes_cambio')
    prueba_bienes_uso = _prueba('bienes_uso')
    prueba_inversiones = _prueba('inversiones')
    prueba_deudas = _prueba('deudas')

    # Etapa 3: alcance de cada procedimiento sustantivo (0 = no se aplica)
    alcance_arqueo = _alcance('arqueo')
    alcance_conciliacion = _alcance('conciliacion')
    alcance_confirmacion = _alcance('confirmacion')
    alcance_antiguedad = _alcance('antiguedad')
    alcance_corte = _alcance('corte')
    alcance_observacion = _alcance('observacion')
    alcance_valuacion = _alcance('valuacion')
    alcance_inspeccion = _alcance('inspeccion')
    alcance_recalculo = _alcance('recalculo')
    alcance_custodio = _alcance('custodio')
    alcance_pasivos_omitidos = _alcance('pasivos_omitidos')
    alcance_cargas_sociales = _alcance('cargas_sociales')

    # Etapa 4: informe
    opinion = models.StringField(choices=OPCIONES_OPINION, label='Opinión del informe', widget=widgets.RadioSelect)

    # Resultado (se completa al cerrar el encargo)
    horas = models.FloatField()
    puntaje = models.FloatField()
    opinion_correcta = models.StringField()
    comparacion = models.StringField()


# --- Funciones auxiliares ---------------------------------------------------

def parametros(session):
    return {k: session.config[k] for k in modelo.PARAMETROS}


def escenario(session):
    return session.vars['escenario']


def nombre(player):
    return player.participant.vars.get('nombre_equipo') or f'Estudio {player.id_in_group}'


def en_etapa(player, etapa):
    return player.in_round(etapa)


def ciclos_probados(player):
    """Rubros cuyo ciclo de control probó el equipo (etapa 2)."""
    if player.round_number < 2:
        return []
    p2 = en_etapa(player, 2)
    return [r for r in RUBROS if p2.field_maybe_none(f'prueba_{r}')]


def alcances(player):
    """Alcance de cada procedimiento (etapa 3); antes de decidir, todo en 0."""
    if player.round_number < 3:
        return {pr: 0 for pr in PROCEDIMIENTOS}
    p3 = en_etapa(player, 3)
    return {pr: p3.field_maybe_none(f'alcance_{pr}') or 0 for pr in PROCEDIMIENTOS}


def significatividad_propia(player):
    return en_etapa(player, 1).field_maybe_none('significatividad')


def riesgos_propios(player):
    p1 = en_etapa(player, 1)
    return {r: p1.field_maybe_none(f'riesgo_{r}') for r in RUBROS}


def horas_usadas(player, hasta_etapa):
    """Horas acumuladas hasta la etapa indicada (incluida)."""
    p = parametros(player.session)
    esc = escenario(player.session)
    horas = p['horas_planeamiento']
    if hasta_etapa >= 2 and player.round_number >= 2:
        horas += modelo.horas_controles(ciclos_probados(player), p)
    if hasta_etapa >= 3 and player.round_number >= 3:
        horas += modelo.horas_sustantivas(alcances(player), p, esc, ciclos_probados(player))
    return horas


def encontrados(player):
    if player.round_number < 3:
        return []
    return modelo.detectados(escenario(player.session), alcances(player))


def base_valor(esc, base):
    return dict(resultado=esc['resultado'], ventas=esc['ventas'], activo=esc['activo'])[base]


# --- Creación de la sesión: el encargo ----------------------------------------------

def creating_session(subsession: Subsession):
    session = subsession.session
    if subsession.round_number == 1:
        semilla = int(session.config.get('semilla') or 0) or random.randint(1, 999_999)
        session.vars['semilla'] = semilla
        session.vars['escenario'] = modelo.generar_escenario(parametros(session), semilla)


# --- Cierre de cada etapa (cuando todos los estudios enviaron su decisión) ----------------

def cerrar_etapa(group: Group):
    if group.round_number == 4:
        p = parametros(group.session)
        esc = escenario(group.session)
        for pl in group.get_players():
            ev = modelo.evaluar(esc, ciclos_probados(pl), alcances(pl), pl.opinion, p)
            pl.horas = ev['horas']
            pl.puntaje = ev['puntaje']
            pl.opinion_correcta = ev['opinion_correcta']
            pl.comparacion = ev['comparacion']
    for pl in group.get_players():
        actualizar_tablero(pl, 'Resultados listos')


def evaluacion(player):
    return modelo.evaluar(escenario(player.session), ciclos_probados(player), alcances(player),
                          player.field_maybe_none('opinion') or 'favorable', parametros(player.session))


def ranking(player):
    """Estudios ordenados por puntaje (solo al terminar el encargo)."""
    equipos = [p.in_round(4) for p in player.group.get_players()]
    return sorted(equipos, key=lambda p: p.field_maybe_none('puntaje') or 0, reverse=True)


def puesto(player):
    if player.round_number < 4 or player.field_maybe_none('puntaje') is None:
        return None
    return [p.id_in_group for p in ranking(player)].index(player.id_in_group) + 1


# --- Datos para las pantallas ---------------------------------------------------------

def estados_contables(esc):
    filas = [dict(nombre=modelo.RUBROS[r]['nombre'], saldo=pesos(esc['saldos'][r])) for r in modelo.ACTIVO]
    pn = esc['activo'] - esc['saldos']['deudas']
    return dict(
        activo=filas,
        total_activo=pesos(esc['activo']),
        deudas=pesos(esc['saldos']['deudas']),
        patrimonio=pesos(pn),
        ventas=pesos(esc['ventas']),
        resultado=pesos(esc['resultado']),
    )


def tabla_procedimientos(player):
    """Procedimientos por rubro, con sus horas por alcance (con la reducción si el control es confiable)."""
    p = parametros(player.session)
    esc = escenario(player.session)
    confianza = modelo.rubros_con_confianza(esc, ciclos_probados(player))
    disponibles = set(modelo.procedimientos_disponibles(esc))
    grupos = []
    for r in RUBROS:
        factor = 1 - p['reduccion_control_fuerte'] if r in confianza else 1.0
        procs = []
        for pr, d in modelo.PROCEDIMIENTOS.items():
            if d['rubro'] != r:
                continue
            procs.append(dict(
                id=pr, campo=f'alcance_{pr}', nombre=d['nombre'], disponible=pr in disponibles,
                horas=[numero(modelo.horas_procedimiento(pr, a) * factor, 1) for a in (1, 2, 3)],
            ))
        grupos.append(dict(rubro=modelo.RUBROS[r]['nombre'], confianza=r in confianza,
                           control=esc['rubros'][r]['control'] if r in ciclos_probados(player) else None,
                           procedimientos=procs))
    return grupos


def horas_js(player):
    """Horas por procedimiento y alcance para la suma en vivo de la etapa 3."""
    p = parametros(player.session)
    esc = escenario(player.session)
    confianza = modelo.rubros_con_confianza(esc, ciclos_probados(player))
    return {pr: [modelo.horas_procedimiento(pr, a) * (1 - p['reduccion_control_fuerte'] if d['rubro'] in confianza else 1)
                 for a in (0, 1, 2, 3)]
            for pr, d in modelo.PROCEDIMIENTOS.items()}


def filas_hallazgos(player, con_respuesta=True):
    halls = encontrados(player)
    acepta = modelo.respuesta_cliente(halls, parametros(player.session)) if con_respuesta else {}
    return [dict(rubro=modelo.RUBROS[e['rubro']]['nombre'], error=modelo.ERRORES[e['tipo']]['nombre'],
                 monto=pesos(e['monto']), acepta=acepta.get(e['id'])) for e in halls]


# --- Tablero del docente y devolución ---------------------------------------------------

ETAPAS_TABLERO = {
    'Instrucciones': ('decidiendo', 'Leyendo instrucciones'),
    'Decidiendo': ('decidiendo', 'Decidiendo'),
    'Esperando a los demás estudios': ('esperando', 'Decisión enviada'),
    'Resultados listos': ('resultados', 'Resultados de la etapa listos'),
    'Viendo resultados': ('resultados', 'Viendo resultados'),
    'Terminó': ('termino', 'Terminó'),
}

COLUMNAS_TABLERO = [
    tablero.columna('etapa', 'E', 'ronda'),
    tablero.columna('nombre_etapa', 'Etapa', 'texto'),
    tablero.columna('decision', 'Decisión', 'texto'),
    tablero.columna('horas', 'Horas acumuladas', 'numero'),
]


def texto_decision_etapa(player, etapa):
    if player.round_number < etapa:
        return None
    pe = en_etapa(player, etapa)
    if etapa == 1:
        if pe.field_maybe_none('significatividad') is None:
            return None
        altos = [modelo.RUBROS[r]['nombre'] for r, v in riesgos_propios(player).items() if v == 'alto']
        return (f'significatividad {pesos(pe.significatividad)}'
                + (f'; riesgo alto: {", ".join(altos)}' if altos else ''))
    if etapa == 2:
        probados = ciclos_probados(player)
        return ('probó ' + ', '.join(modelo.RUBROS[r]['ciclo'] for r in probados)) if probados else 'no probó controles'
    if etapa == 3:
        a = alcances(player)
        aplicados = sum(1 for v in a.values() if v)
        return f'{aplicados} procedimientos'
    if etapa == 4:
        op = pe.field_maybe_none('opinion')
        return modelo.NOMBRES_OPINION[op] if op else None


def historial(player):
    filas = []
    for etapa in range(1, player.round_number + 1):
        texto = texto_decision_etapa(player, etapa)
        if texto is None:
            continue
        filas.append(dict(etapa=etapa, nombre_etapa=ETAPAS[etapa], decision=texto,
                          horas=horas_usadas(player, etapa)))
    return filas


def devolucion_de(player):
    if player.round_number < 4 or player.field_maybe_none('puntaje') is None:
        return []
    esc = escenario(player.session)
    return devolucion.diagnosticar(
        esc, riesgos_propios(player), significatividad_propia(player), ciclos_probados(player),
        alcances(player), evaluacion(player), parametros(player.session), puesto(player),
        len(player.group.get_players()))


def actualizar_tablero(player, pagina):
    etapa, estado = ETAPAS_TABLERO[pagina]
    terminado = player.round_number == 4 and player.field_maybe_none('puntaje') is not None
    halls = encontrados(player)
    player.participant.vars['tablero'] = tablero.resumen(
        juego=C.NAME_IN_URL,
        equipo=nombre(player),
        rotulo_equipo='Estudio',
        grupo_numero=player.group.id_in_subsession,
        grupo_tipo='grupo',
        grupo_tamano=len(player.group.get_players()),
        posicion=player.id_in_group,
        ronda=player.round_number,
        rondas=C.NUM_ROUNDS,
        nombre_ronda='etapa',
        abrev_ronda='E',
        etapa=etapa,
        estado=f'{ETAPAS[player.round_number]}: {estado.lower()}' if etapa != 'termino' else estado,
        puesto=puesto(player),
        indicadores=[
            tablero.indicador('Horas', horas_usadas(player, player.round_number), 'numero'),
            tablero.indicador('Hallazgos', len(halls) if player.round_number >= 3 else None, 'numero'),
            tablero.indicador('Puntaje', player.field_maybe_none('puntaje') if terminado else None, 'pesos', signo=True),
        ],
        decision=texto_decision_etapa(player, player.round_number),
        columnas=COLUMNAS_TABLERO,
        filas=historial(player),
        nota_historial='Horas acumuladas al cerrar cada etapa.',
        devolucion=devolucion_de(player),
    )


# --- Páginas --------------------------------------------------------------------

class Instrucciones(Page):
    form_model = 'player'
    form_fields = ['nombre_equipo']

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Instrucciones')
        p = parametros(player.session)
        return dict(
            cliente=CLIENTE,
            num_equipos=len(player.group.get_players()),
            honorarios=pesos(p['honorarios']),
            costo_hora=pesos(p['costo_hora']),
            presupuesto=numero(p['presupuesto_horas']),
            horas_planeamiento=numero(p['horas_planeamiento']),
            horas_prueba_control=numero(p['horas_prueba_control']),
            reduccion=porcentaje(p['reduccion_control_fuerte'], 0),
            penalidad_falla=pesos(p['penalidad_falla'] * p['honorarios']),
            penalidad_severa=pesos(p['penalidad_severa'] * p['honorarios']),
            penalidad_sin_evidencia=pesos(p['penalidad_sin_evidencia'] * p['honorarios']),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        texto = (player.nombre_equipo or '').strip()
        if texto:
            player.participant.vars['nombre_equipo'] = texto


class Planeamiento(Page):
    form_model = 'player'
    form_fields = ['base_significatividad', 'pct_significatividad'] + [f'riesgo_{r}' for r in RUBROS]

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decidiendo')
        esc = escenario(player.session)
        return dict(
            nombre=nombre(player), cliente=CLIENTE,
            ec=estados_contables(esc),
            senal={r: esc['rubros'][r]['senal'] for r in RUBROS},
            bases=[dict(id=k, nombre=v, valor=pesos(base_valor(esc, k))) for k, v in BASES_SIGNIFICATIVIDAD.items()],
        )

    @staticmethod
    def js_vars(player: Player):
        esc = escenario(player.session)
        return dict(bases={k: base_valor(esc, k) for k in BASES_SIGNIFICATIVIDAD})

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        esc = escenario(player.session)
        player.significatividad = base_valor(esc, player.base_significatividad) * player.pct_significatividad / 100
        actualizar_tablero(player, 'Esperando a los demás estudios')


class Controles(Page):
    form_model = 'player'
    form_fields = [f'prueba_{r}' for r in RUBROS]

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 2

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decidiendo')
        p = parametros(player.session)
        esc = escenario(player.session)
        riesgos = riesgos_propios(player)
        return dict(
            nombre=nombre(player),
            horas_usadas=numero(horas_usadas(player, 1)),
            presupuesto=numero(p['presupuesto_horas']),
            horas_prueba=numero(p['horas_prueba_control']),
            reduccion=porcentaje(p['reduccion_control_fuerte'], 0),
            riesgo={r: dict(OPCIONES_RIESGO).get(riesgos[r], '—') for r in RUBROS},
            senal={r: esc['rubros'][r]['senal'] for r in RUBROS},
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        actualizar_tablero(player, 'Esperando a los demás estudios')


class Sustantivas(Page):
    form_model = 'player'
    form_fields = [f'alcance_{pr}' for pr in PROCEDIMIENTOS]

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 3

    @staticmethod
    def error_message(player: Player, valores):
        p = parametros(player.session)
        esc = escenario(player.session)
        a = {pr: valores[f'alcance_{pr}'] for pr in PROCEDIMIENTOS}
        if esc['limitacion'] and a.get('confirmacion'):
            return 'El cliente no permite confirmar saldos con clientes: elijan otro procedimiento para Créditos.'
        total = (p['horas_planeamiento'] + modelo.horas_controles(ciclos_probados(player), p)
                 + modelo.horas_sustantivas(a, p, esc, ciclos_probados(player)))
        if total > p['presupuesto_horas'] + 1e-9:
            return (f'Con esos alcances el encargo lleva {numero(total)} horas y el presupuesto es de '
                    f'{numero(p["presupuesto_horas"])}. Reduzcan algún alcance.')

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decidiendo')
        p = parametros(player.session)
        esc = escenario(player.session)
        probados = ciclos_probados(player)
        return dict(
            nombre=nombre(player),
            limitacion=esc['limitacion'],
            horas_previas=numero(horas_usadas(player, 2)),
            presupuesto=numero(p['presupuesto_horas']),
            significatividad=pesos(significatividad_propia(player)),
            controles=[dict(ciclo=modelo.RUBROS[r]['ciclo'], fuerte=esc['rubros'][r]['control'] == 'fuerte')
                       for r in probados],
            horas_txt={g['id']: ' · '.join(f'{n} {h} h' for n, h in zip(('bajo', 'medio', 'alto'), g['horas']))
                       for gr in tabla_procedimientos(player) for g in gr['procedimientos']},
            confianza={r: r in modelo.rubros_con_confianza(esc, probados) for r in RUBROS},
            reduccion=porcentaje(p['reduccion_control_fuerte'], 0),
        )

    @staticmethod
    def js_vars(player: Player):
        p = parametros(player.session)
        return dict(horas=horas_js(player), previas=horas_usadas(player, 2), presupuesto=p['presupuesto_horas'])

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        actualizar_tablero(player, 'Esperando a los demás estudios')


class Informe(Page):
    form_model = 'player'
    form_fields = ['opinion']

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 4

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decidiendo')
        p = parametros(player.session)
        esc = escenario(player.session)
        halls = encontrados(player)
        acepta = modelo.respuesta_cliente(halls, p)
        rechazado = sum(e['monto'] for e in halls if not acepta[e['id']])
        a = alcances(player)
        return dict(
            nombre=nombre(player),
            hallazgos=filas_hallazgos(player),
            hay_hallazgos=bool(halls),
            rechazado=pesos(rechazado),
            significatividad=pesos(significatividad_propia(player)),
            limitacion=esc['limitacion'],
            sin_alternativa=modelo.sin_alternativa_por_limitacion(esc, a),
            sin_evidencia=', '.join(modelo.RUBROS[r]['nombre'] for r in modelo.rubros_sin_evidencia(esc, a)),
            horas=numero(horas_usadas(player, 3)),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        actualizar_tablero(player, 'Esperando a los demás estudios')


class EsperaEtapa(WaitPage):
    title_text = 'Esperando a los demás estudios'
    body_text = 'La etapa se cierra cuando todos los estudios hayan enviado su decisión.'
    after_all_players_arrive = cerrar_etapa


class ResultadoControles(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 2

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Viendo resultados')
        p = parametros(player.session)
        esc = escenario(player.session)
        probados = ciclos_probados(player)
        return dict(
            nombre=nombre(player),
            resultados=[dict(ciclo=modelo.RUBROS[r]['ciclo'], rubro=modelo.RUBROS[r]['nombre'],
                             fuerte=esc['rubros'][r]['control'] == 'fuerte') for r in probados],
            no_probados=', '.join(modelo.RUBROS[r]['ciclo'] for r in RUBROS if r not in probados),
            horas=numero(horas_usadas(player, 2)),
            reduccion=porcentaje(p['reduccion_control_fuerte'], 0),
        )


class Hallazgos(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 3

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Viendo resultados')
        esc = escenario(player.session)
        return dict(
            nombre=nombre(player),
            hallazgos=filas_hallazgos(player, con_respuesta=False),
            horas=numero(horas_usadas(player, 3)),
            sin_evidencia=', '.join(modelo.RUBROS[r]['nombre'] for r in modelo.rubros_sin_evidencia(esc, alcances(player))),
        )


class ResultadoFinal(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 4

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Terminó')
        p = parametros(player.session)
        esc = escenario(player.session)
        ev = evaluacion(player)
        ids = {e['id'] for e in ev['encontrados']}
        aceptados = {e['id'] for e in ev['aceptados']}
        errores = [dict(rubro=modelo.RUBROS[e['rubro']]['nombre'], error=modelo.ERRORES[e['tipo']]['nombre'],
                        monto=pesos(e['monto']), importante=e['monto'] >= esc['significatividad'],
                        estado='Detectado y ajustado' if e['id'] in aceptados
                        else 'Detectado, el cliente no ajustó' if e['id'] in ids else 'No detectado',
                        no_detectado=e['id'] not in ids)
                   for e in esc['errores']]
        rubros = [dict(rubro=modelo.RUBROS[r]['nombre'], riesgo=d['riesgo'].capitalize(),
                       control='Fuerte' if d['control'] == 'fuerte' else 'Débil',
                       evaluado=dict(OPCIONES_RIESGO).get(riesgos_propios(player)[r], '—'))
                  for r, d in esc['rubros'].items()]
        filas_rank = [dict(puesto=i + 1, nombre=nombre(q), es_propia=q.id_in_group == player.id_in_group,
                           puntaje=pesos(q.puntaje), negativo=q.puntaje < 0, horas=numero(q.horas),
                           opinion=modelo.NOMBRES_OPINION[q.opinion], acerto=q.comparacion == 'correcta')
                      for i, q in enumerate(ranking(player))]
        return dict(
            nombre=nombre(player),
            errores=errores,
            hay_errores=bool(errores),
            rubros=rubros,
            significatividad_ref=pesos(esc['significatividad']),
            significatividad=pesos(significatividad_propia(player)),
            opinion=modelo.NOMBRES_OPINION[player.opinion],
            opinion_correcta=modelo.NOMBRES_OPINION[player.opinion_correcta],
            acerto=player.comparacion == 'correcta',
            falla=player.comparacion == 'falla',
            clase_alerta=dict(correcta='alert-success', falla='alert-danger').get(player.comparacion, 'alert-warning'),
            honorarios=pesos(p['honorarios']),
            costo_horas=pesos(ev['costo_horas']),
            horas=numero(ev['horas']),
            penalidad_falla=pesos(ev['penalidades']['falla']),
            penalidad_severa=pesos(ev['penalidades']['severa']),
            penalidad_sin_evidencia=pesos(ev['penalidades']['sin_evidencia']),
            hay_falla=ev['penalidades']['falla'] > 0,
            diligente=ev['diligente'],
            hay_severa=ev['penalidades']['severa'] > 0,
            hay_sin_evidencia=ev['penalidades']['sin_evidencia'] > 0,
            puntaje=pesos(player.puntaje),
            puntaje_neg=player.puntaje < 0,
            ranking=filas_rank,
            devolucion=devolucion_de(player),
            comentario_docente=(player.participant.vars.get('comentario_docente') or '').strip(),
            semilla=player.session.vars.get('semilla'),
        )


page_sequence = [Instrucciones, Planeamiento, Controles, Sustantivas, Informe, EsperaEtapa,
                 ResultadoControles, Hallazgos, ResultadoFinal]
