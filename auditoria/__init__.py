import random

from otree.api import *

from nucleo import ajustes_otree, tablero, tiempo
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
CIERRE = '30 de junio de 2026'
MAX_AJUSTES = 12   # a lo sumo 2 errores por rubro
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


def _calificacion(rubro):
    return models.StringField(choices=list(modelo.CALIFICACIONES_CONTROL.items()), widget=widgets.RadioSelect,
                              label=modelo.RUBROS[rubro]['ciclo'])


def _ajuste():
    return models.FloatField(blank=True, min=0, max=1e12, label='Ajuste propuesto ($)')


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

    # Etapa 2: evaluación del control interno (a partir del relato) y pruebas de controles
    calif_caja = _calificacion('caja')
    calif_creditos = _calificacion('creditos')
    calif_bienes_cambio = _calificacion('bienes_cambio')
    calif_bienes_uso = _calificacion('bienes_uso')
    calif_inversiones = _calificacion('inversiones')
    calif_deudas = _calificacion('deudas')
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

    # Fin de la etapa 3: ajustes calculados a partir de los papeles de trabajo (uno por error encontrado;
    # el campo ajuste_N corresponde al error eN del escenario)
    ajuste_1 = _ajuste()
    ajuste_2 = _ajuste()
    ajuste_3 = _ajuste()
    ajuste_4 = _ajuste()
    ajuste_5 = _ajuste()
    ajuste_6 = _ajuste()
    ajuste_7 = _ajuste()
    ajuste_8 = _ajuste()
    ajuste_9 = _ajuste()
    ajuste_10 = _ajuste()
    ajuste_11 = _ajuste()
    ajuste_12 = _ajuste()

    # Etapa 4: informe
    opinion = models.StringField(choices=OPCIONES_OPINION, label='Opinión del informe', widget=widgets.RadioSelect)
    enfasis = models.BooleanField(
        choices=[[True, 'Sí'], [False, 'No']], widget=widgets.RadioSelectHorizontal,
        label='¿Incluyen la sección «Incertidumbre significativa relacionada con empresa en funcionamiento»?')

    # Resultado (se completa al cerrar el encargo)
    horas = models.FloatField()
    puntaje = models.FloatField()
    opinion_correcta = models.StringField()
    comparacion = models.StringField()
    # No enviaron a tiempo la decisión de la etapa: la tomó el sistema al azar (ver nucleo/tiempo.py).
    fuera_de_tiempo = models.BooleanField(initial=False)


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


def campo_ajuste(error):
    return f'ajuste_{error["id"][1:]}'


def montos(player):
    """Ajustes cargados por el equipo al ver los hallazgos: {id del error: $ o None}."""
    if player.round_number < 3:
        return {}
    p3 = en_etapa(player, 3)
    return {e['id']: p3.field_maybe_none(campo_ajuste(e)) for e in encontrados(player)}


def calificaciones(player):
    """Cómo calificó el equipo el control de cada ciclo (etapa 2)."""
    if player.round_number < 2:
        return {}
    p2 = en_etapa(player, 2)
    return {r: p2.field_maybe_none(f'calif_{r}') for r in RUBROS if p2.field_maybe_none(f'calif_{r}')}


def enfasis_de(player):
    return player.in_round(4).field_maybe_none('enfasis') if player.round_number >= 4 else None


def base_valor(esc, base):
    return dict(resultado=esc['resultado'], ventas=esc['ventas'], activo=esc['activo'])[base]


# --- Decisión al azar (cuando el estudio no envía a tiempo) -----------------------------

def marcar_al_azar(player):
    player.fuera_de_tiempo = True
    tiempo.marcar_fuera_de_tiempo(player.participant.vars, player.round_number)


def planeamiento_al_azar(player):
    player.base_significatividad = random.choice(list(BASES_SIGNIFICATIVIDAD))
    player.pct_significatividad = round(random.uniform(0.5, 10), 1)
    for r in RUBROS:
        setattr(player, f'riesgo_{r}', random.choice([o for o, _ in OPCIONES_RIESGO]))
    marcar_al_azar(player)


def controles_al_azar(player):
    for r in RUBROS:
        setattr(player, f'calif_{r}', random.choice(list(modelo.CALIFICACIONES_CONTROL)))
        setattr(player, f'prueba_{r}', random.random() < 0.5)
    marcar_al_azar(player)


def sustantivas_al_azar(player):
    """Alcances al azar que respetan la limitación del cliente y el presupuesto de horas."""
    p = parametros(player.session)
    esc = escenario(player.session)
    probados = ciclos_probados(player)
    a = {pr: random.choice([x for x, _ in OPCIONES_ALCANCE]) for pr in PROCEDIMIENTOS}
    if esc['limitacion']:
        a['confirmacion'] = 0
    disponibles = p['presupuesto_horas'] - p['horas_planeamiento'] - modelo.horas_controles(probados, p)
    while modelo.horas_sustantivas(a, p, esc, probados) > disponibles + 1e-9 and any(a.values()):
        a[random.choice([pr for pr, x in a.items() if x])] -= 1
    for pr, x in a.items():
        setattr(player, f'alcance_{pr}', x)
    marcar_al_azar(player)


def informe_al_azar(player):
    player.opinion = random.choice(modelo.OPINIONES)
    player.enfasis = random.random() < 0.5
    marcar_al_azar(player)


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
            ev = modelo.evaluar(esc, ciclos_probados(pl), alcances(pl), pl.opinion, p, montos(pl), pl.enfasis)
            pl.horas = ev['horas']
            pl.puntaje = ev['puntaje']
            pl.opinion_correcta = ev['opinion_correcta']
            pl.comparacion = ev['comparacion']
    # El reloj de la etapa siguiente corre desde ahora, igual para todos.
    if group.round_number < C.NUM_ROUNDS:
        tiempo.abrir_ronda([pl.participant.vars for pl in group.get_players()], group.round_number + 1,
                           group.session.config)
    for pl in group.get_players():
        actualizar_tablero(pl, 'Resultados listos')


def evaluacion(player):
    return modelo.evaluar(escenario(player.session), ciclos_probados(player), alcances(player),
                          player.field_maybe_none('opinion') or 'favorable', parametros(player.session),
                          montos(player), enfasis_de(player))


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


ESTADOS_AJUSTE = dict(
    aceptado=('El cliente lo registró', 'text-success'),
    rechazado=('Bien calculado, pero el cliente no lo registró', 'text-danger fw-bold'),
    devuelto=('Mal calculado: el cliente lo devolvió', 'text-danger fw-bold'),
    sin_proponer=('No lo propusieron', 'text-danger fw-bold'),
)


def filas_hallazgos(player, con_respuesta=True):
    """Errores encontrados con su papel de trabajo y, si ya se propusieron, la respuesta del cliente."""
    p = parametros(player.session)
    m = montos(player) if con_respuesta else {}
    filas = []
    for e in encontrados(player):
        papel = modelo.papel_de_trabajo(e)
        # El monto del error es la respuesta: no se manda a la pantalla de hallazgos.
        f = dict(id=e['id'], campo=campo_ajuste(e), rubro=modelo.RUBROS[e['rubro']]['nombre'],
                 error=modelo.ERRORES[e['tipo']]['nombre'],
                 procedimiento=papel['procedimiento'], nota=papel['nota'], pregunta=papel['pregunta'],
                 lineas=[dict(concepto=l['concepto'], valor=pesos(l['importe']) if l['importe'] is not None else l['texto'])
                         for l in papel['lineas']])
        if con_respuesta:
            est = modelo.estado_ajuste(e, m, p)
            f.update(estado=ESTADOS_AJUSTE[est][0], clase=ESTADOS_AJUSTE[est][1], registrado=est == 'aceptado',
                     propuesto=pesos(m[e['id']]) if m.get(e['id']) is not None else '—')
        filas.append(f)
    return filas


# --- Informe redactado (RT 37 modificada por la RT 53, modelo de la cátedra) -----------------------

TITULOS_OPINION = dict(favorable='Opinión', salvedades='Opinión con salvedades', adversa='Opinión adversa',
                       abstencion='Abstención de opinión')


def informe_redactado(opinion, enfasis, esc, sin_corregir, saldo_creditos):
    """Secciones del informe: [{titulo, parrafos}]. `sin_corregir`: errores que menciona el fundamento."""
    ee = f'los estados contables adjuntos de {CLIENTE} al {CIERRE}'
    razonable = ('presentan razonablemente, en todos los aspectos significativos, la situación patrimonial, '
                 'los resultados, la evolución del patrimonio neto y el flujo de efectivo, de conformidad con '
                 'las normas contables profesionales argentinas')
    texto_opinion = dict(
        favorable=f'En mi opinión, {ee} {razonable}.',
        salvedades=(f'En mi opinión, excepto por los efectos de las cuestiones descriptas en la sección '
                    f'«Fundamento de la opinión con salvedades», {ee} {razonable}.'),
        adversa=(f'En mi opinión, debido a la significatividad de las cuestiones descriptas en la sección '
                 f'«Fundamento de la opinión adversa», {ee} no presentan razonablemente la situación patrimonial '
                 'ni los resultados de conformidad con las normas contables profesionales argentinas.'),
        abstencion=(f'No expreso una opinión sobre {ee}. Debido a la significatividad de la cuestión descripta en '
                    'la sección «Fundamento de la abstención de opinión», no he podido obtener elementos de juicio '
                    'suficientes y adecuados para proporcionar una base para una opinión de auditoría.'),
    )[opinion]
    base = ('He llevado a cabo mi auditoría de conformidad con las normas de auditoría establecidas en la '
            'Resolución Técnica N.° 37 de la FACPCE. Soy independiente de la Sociedad y he cumplido las demás '
            'responsabilidades de ética.')
    fundamento = []
    if opinion == 'abstencion':
        fundamento.append(f'La Sociedad no me permitió confirmar los saldos de Créditos por ventas '
                          f'({pesos(saldo_creditos)}) y no pude aplicar procedimientos alternativos.')
    elif opinion in ('salvedades', 'adversa'):
        if sin_corregir:
            detalle = '; '.join(f'{modelo.ERRORES[e["tipo"]]["nombre"].lower()} ({pesos(e["monto"])})' for e in sin_corregir)
            total = sum(e['monto'] for e in sin_corregir)
            fundamento.append(f'Los estados contables no reconocen los siguientes ajustes: {detalle}. En conjunto, '
                              f'el resultado del ejercicio y el patrimonio neto están sobrevaluados en {pesos(total)}.')
        else:
            fundamento.append('(No hay ajustes sin registrar que fundamenten esta opinión.)')
    if opinion == 'abstencion':
        fundamento.append(base)
    else:
        fundamento.append(base + ' Considero que los elementos de juicio que he obtenido proporcionan una base '
                          'suficiente y adecuada para mi opinión.')
    secciones = [dict(titulo=TITULOS_OPINION[opinion], parrafos=[texto_opinion]),
                 dict(titulo='Fundamento de la ' + TITULOS_OPINION[opinion].lower(), parrafos=fundamento)]
    if enfasis:
        secciones.append(dict(titulo='Incertidumbre significativa relacionada con empresa en funcionamiento', parrafos=[
            'Llamo la atención sobre la nota 12 de los estados contables, que indica que la Sociedad tuvo pérdidas '
            'operativas en los dos últimos ejercicios y que su principal deuda bancaria venció y está en '
            'refinanciación. Estos hechos indican la existencia de una incertidumbre significativa que puede '
            'generar dudas importantes sobre la capacidad de la Sociedad para continuar como empresa en '
            'funcionamiento. Mi opinión no ha sido modificada en relación con esta cuestión.']))
    secciones.append(dict(titulo='Informe sobre otros requerimientos legales y reglamentarios', parrafos=[
        f'Según surge de los registros contables, el pasivo devengado al {CIERRE} a favor del Sistema Integrado '
        f'Previsional Argentino en concepto de aportes y contribuciones ascendía a {pesos(esc["legales"]["sipa"])} '
        'y no era exigible a esa fecha.',
        'Conforme al artículo 32 del Código Fiscal de la Provincia de La Pampa, el saldo de deuda por el Impuesto '
        f'sobre los Ingresos Brutos devengado al {CIERRE} ascendía a {pesos(esc["legales"]["iibb"])}.',
        'He aplicado los procedimientos sobre prevención de lavado de activos de origen delictivo y financiación '
        'del terrorismo previstos en la Resolución N.° 420/11 de la FACPCE.']))
    return secciones


NOTA_EMPRESA_FUNCIONAMIENTO = {
    True: ('Nota 12 de los estados contables: la Sociedad tuvo pérdidas operativas en los dos últimos ejercicios '
           'y su principal deuda bancaria venció en mayo; la dirección está negociando una refinanciación que '
           'todavía no se firmó.'),
    False: ('Nota 12 de los estados contables: la Sociedad renovó en marzo su línea de crédito bancario por tres '
            'años y el resultado de los últimos ejercicios fue positivo.'),
}


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
    tablero.columna('envio', 'Envío', 'texto'),
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
        confia = sum(1 for c in calificaciones(player).values() if c == 'confio')
        return (f'confía en {confia} de {len(RUBROS)} ciclos; '
                + (('probó ' + ', '.join(modelo.RUBROS[r]['ciclo'] for r in probados)) if probados else 'no probó controles'))
    if etapa == 3:
        a = alcances(player)
        aplicados = sum(1 for v in a.values() if v)
        texto = f'{aplicados} procedimientos'
        m = montos(player)
        if any(v is not None for v in m.values()):
            p = parametros(player.session)
            bien = sum(1 for e in encontrados(player) if modelo.ajuste_correcto(e, m.get(e['id']), p))
            texto += f'; {bien} de {len(m)} ajustes bien calculados'
        return texto
    if etapa == 4:
        op = pe.field_maybe_none('opinion')
        if not op:
            return None
        return modelo.NOMBRES_OPINION[op] + (' + empresa en funcionamiento' if pe.field_maybe_none('enfasis') else '')


def historial(player):
    filas = []
    for etapa in range(1, player.round_number + 1):
        texto = texto_decision_etapa(player, etapa)
        if texto is None:
            continue
        filas.append(dict(etapa=etapa, nombre_etapa=ETAPAS[etapa], decision=texto,
                          horas=horas_usadas(player, etapa),
                          envio='⏱ al azar' if en_etapa(player, etapa).fuera_de_tiempo else 'a tiempo'))
    return filas


def devolucion_de(player):
    if player.round_number < 4 or player.field_maybe_none('puntaje') is None:
        return []
    esc = escenario(player.session)
    return devolucion.diagnosticar(
        esc, riesgos_propios(player), significatividad_propia(player), ciclos_probados(player),
        alcances(player), evaluacion(player), parametros(player.session), puesto(player),
        len(player.group.get_players()), calificaciones(player)) + tiempo.observaciones(player.participant.vars, 'E')


def ajustes_bien(player):
    p = parametros(player.session)
    m = montos(player)
    return sum(1 for e in encontrados(player) if modelo.ajuste_correcto(e, m.get(e['id']), p))


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
            tablero.indicador('Ajustes bien calculados', ajustes_bien(player) if player.round_number >= 4 else None, 'numero'),
            tablero.indicador('Puntaje', player.field_maybe_none('puntaje') if terminado else None, 'pesos', signo=True),
        ],
        decision=texto_decision_etapa(player, player.round_number),
        columnas=COLUMNAS_TABLERO,
        filas=historial(player),
        nota_historial='Horas acumuladas al cerrar cada etapa.',
        devolucion=devolucion_de(player),
        vence=tiempo.vence_pendiente(player.participant.vars, player.session.config, player.round_number,
                                     etapa, player.round_number == C.NUM_ROUNDS),
        fuera_de_tiempo=tiempo.rondas_fuera_de_tiempo(player.participant.vars),
    )


# --- Páginas --------------------------------------------------------------------

class Instrucciones(Page):
    form_model = 'player'
    form_fields = ['nombre_equipo']
    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        return tiempo.segundos_decision(player.participant.vars, player.session.config, player.round_number)

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Instrucciones')
        p = parametros(player.session)
        return dict(
            **tiempo.contexto(player.session.config, 'etapa', femenino=True),
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
            penalidad_enfasis=pesos(p['penalidad_enfasis'] * p['honorarios']),
            bonificacion=pesos(p['bonificacion_ajuste']),
            penalidad_ajuste=pesos(p['penalidad_ajuste']),
            tolerancia=porcentaje(p['tolerancia_ajuste'], 0),
            cierre=CIERRE,
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        texto = (player.nombre_equipo or '').strip()
        if texto:
            player.participant.vars['nombre_equipo'] = texto


class Planeamiento(Page):
    form_model = 'player'
    form_fields = ['base_significatividad', 'pct_significatividad'] + [f'riesgo_{r}' for r in RUBROS]

    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        return tiempo.segundos_decision(player.participant.vars, player.session.config, player.round_number)

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decidiendo')
        esc = escenario(player.session)
        return dict(
            **tiempo.contexto(player.session.config, 'etapa', femenino=True),
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
        if timeout_happened:
            planeamiento_al_azar(player)
        esc = escenario(player.session)
        player.significatividad = base_valor(esc, player.base_significatividad) * player.pct_significatividad / 100
        actualizar_tablero(player, 'Esperando a los demás estudios')


class Controles(Page):
    form_model = 'player'
    form_fields = [f'calif_{r}' for r in RUBROS] + [f'prueba_{r}' for r in RUBROS]

    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        return tiempo.segundos_decision(player.participant.vars, player.session.config, player.round_number)

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
            **tiempo.contexto(player.session.config, 'etapa', femenino=True),
            nombre=nombre(player),
            horas_usadas=numero(horas_usadas(player, 1)),
            presupuesto=numero(p['presupuesto_horas']),
            horas_prueba=numero(p['horas_prueba_control']),
            reduccion=porcentaje(p['reduccion_control_fuerte'], 0),
            riesgo={r: dict(OPCIONES_RIESGO).get(riesgos[r], '—') for r in RUBROS},
            senal={r: esc['rubros'][r]['senal'] for r in RUBROS},
            ciclos=[dict(rubro=r, ciclo=modelo.RUBROS[r]['ciclo'], relato=esc['rubros'][r]['relato'],
                         riesgo=dict(OPCIONES_RIESGO).get(riesgos[r], '—'),
                         calif=f'calif_{r}', prueba=f'prueba_{r}') for r in RUBROS],
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if timeout_happened:
            controles_al_azar(player)
        actualizar_tablero(player, 'Esperando a los demás estudios')


class Sustantivas(Page):
    form_model = 'player'
    form_fields = [f'alcance_{pr}' for pr in PROCEDIMIENTOS]

    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        return tiempo.segundos_decision(player.participant.vars, player.session.config, player.round_number)

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
            **tiempo.contexto(player.session.config, 'etapa', femenino=True),
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
        if timeout_happened:
            sustantivas_al_azar(player)
        actualizar_tablero(player, 'Esperando a los demás estudios')


class Informe(Page):
    form_model = 'player'
    form_fields = ['enfasis', 'opinion']

    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        return tiempo.segundos_decision(player.participant.vars, player.session.config, player.round_number)

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 4

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decidiendo')
        p = parametros(player.session)
        esc = escenario(player.session)
        halls = encontrados(player)
        acepta = modelo.respuesta_cliente(halls, p, montos(player))
        a = alcances(player)
        return dict(
            **tiempo.contexto(player.session.config, 'etapa', femenino=True),
            nombre=nombre(player),
            hallazgos=filas_hallazgos(player),
            hay_hallazgos=bool(halls),
            sin_registrar=pesos(sum(e['monto'] for e in halls if not acepta[e['id']])),
            nota_ef=NOTA_EMPRESA_FUNCIONAMIENTO[bool(esc['empresa_funcionamiento'])],
            explicacion={o: modelo.EXPLICACION_OPINION[o] for o in modelo.OPINIONES},
            significatividad=pesos(significatividad_propia(player)),
            limitacion=esc['limitacion'],
            sin_alternativa=modelo.sin_alternativa_por_limitacion(esc, a),
            sin_evidencia=', '.join(modelo.RUBROS[r]['nombre'] for r in modelo.rubros_sin_evidencia(esc, a)),
            horas=numero(horas_usadas(player, 3)),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if timeout_happened:
            informe_al_azar(player)
        actualizar_tablero(player, 'Esperando a los demás estudios')


class EsperaEtapa(WaitPage):
    title_text = 'Esperando a los demás estudios'
    body_text = 'La etapa se cierra cuando todos los estudios hayan enviado su decisión.'
    after_all_players_arrive = cerrar_etapa


class ResultadoControles(Page):
    timer_text = tiempo.TEXTO_LECTURA

    @staticmethod
    def get_timeout_seconds(player: Player):
        # El reloj de la etapa siguiente ya corre mientras leen los resultados.
        return tiempo.segundos_lectura(player.participant.vars, player.round_number, player.round_number == 4)

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
            **tiempo.contexto(player.session.config, 'etapa', femenino=True),
            t_fuera=player.fuera_de_tiempo,
            nombre=nombre(player),
            resultados=[dict(ciclo=modelo.RUBROS[r]['ciclo'], rubro=modelo.RUBROS[r]['nombre'],
                             fuerte=esc['rubros'][r]['control'] == 'fuerte',
                             calificado=modelo.CALIFICACIONES_CONTROL.get(calificaciones(player).get(r), '—'),
                             acerto=(calificaciones(player).get(r) == 'confio') == (esc['rubros'][r]['control'] == 'fuerte'))
                        for r in probados],
            no_probados=', '.join(modelo.RUBROS[r]['ciclo'] for r in RUBROS if r not in probados),
            horas=numero(horas_usadas(player, 2)),
            reduccion=porcentaje(p['reduccion_control_fuerte'], 0),
        )


class Hallazgos(Page):
    form_model = 'player'

    timer_text = tiempo.TEXTO_LECTURA

    @staticmethod
    def get_timeout_seconds(player: Player):
        # El reloj de la etapa siguiente ya corre mientras leen los resultados.
        return tiempo.segundos_lectura(player.participant.vars, player.round_number, player.round_number == 4)

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 3

    @staticmethod
    def get_form_fields(player: Player):
        return [campo_ajuste(e) for e in encontrados(player)]

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Viendo resultados')
        esc = escenario(player.session)
        p = parametros(player.session)
        return dict(
            **tiempo.contexto(player.session.config, 'etapa', femenino=True),
            t_fuera=player.fuera_de_tiempo,
            nombre=nombre(player),
            cierre=CIERRE,
            tolerancia=porcentaje(p['tolerancia_ajuste'], 0),
            bonificacion=pesos(p['bonificacion_ajuste']),
            penalidad_ajuste=pesos(p['penalidad_ajuste']),
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
        textos_estado = dict(aceptado='Detectado y ajustado', rechazado='Detectado, el cliente no ajustó',
                             devuelto='Detectado, ajuste mal calculado', sin_proponer='Detectado, no propusieron ajuste')
        m = montos(player)
        errores = [dict(rubro=modelo.RUBROS[e['rubro']]['nombre'], error=modelo.ERRORES[e['tipo']]['nombre'],
                        monto=pesos(e['monto']), importante=e['monto'] >= esc['significatividad'],
                        estado=textos_estado[ev['estados'][e['id']]] if e['id'] in ids else 'No detectado',
                        propuesto=pesos(m[e['id']]) if m.get(e['id']) is not None else '—',
                        no_detectado=e['id'] not in ids)
                   for e in esc['errores']]
        calif = calificaciones(player)
        rubros = [dict(rubro=modelo.RUBROS[r]['nombre'], riesgo=d['riesgo'].capitalize(),
                       control='Fuerte' if d['control'] == 'fuerte' else 'Débil',
                       evaluado=dict(OPCIONES_RIESGO).get(riesgos_propios(player)[r], '—'),
                       confio='Confiaron' if calif.get(r) == 'confio' else 'No confiaron' if calif.get(r) else '—',
                       acerto_control=(calif.get(r) == 'confio') == (d['control'] == 'fuerte'))
                  for r, d in esc['rubros'].items()]
        conocidos = ev['rechazados'] + ev['devueltos']
        todos_sin_corregir = conocidos + ev['no_detectados']
        informe_propio = informe_redactado(player.opinion, bool(player.enfasis), esc, conocidos,
                                           esc['saldos']['creditos'])
        informe_correcto = informe_redactado(player.opinion_correcta, bool(esc['empresa_funcionamiento']), esc,
                                             todos_sin_corregir, esc['saldos']['creditos'])
        filas_rank = [dict(puesto=i + 1, nombre=nombre(q), es_propia=q.id_in_group == player.id_in_group,
                           puntaje=pesos(q.puntaje), negativo=q.puntaje < 0, horas=numero(q.horas),
                           opinion=modelo.NOMBRES_OPINION[q.opinion], acerto=q.comparacion == 'correcta')
                      for i, q in enumerate(ranking(player))]
        return dict(
            t_fuera_lista=tiempo.lista(player.participant.vars, 'E'),
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
            penalidad_enfasis=pesos(ev['penalidades']['enfasis']),
            penalidad_ajustes=pesos(ev['penalidades']['ajustes']),
            hay_penalidad_ajustes=ev['penalidades']['ajustes'] > 0,
            num_mal=len(ev['encontrados']) - ev['bien_calculados'],
            hay_enfasis=ev['penalidades']['enfasis'] > 0,
            bonificacion=pesos(ev['bonificacion']),
            bien_calculados=ev['bien_calculados'],
            num_encontrados=len(ev['encontrados']),
            controles_bien=modelo.evaluacion_control(esc, calif),
            num_ciclos=len(RUBROS),
            informe_propio=informe_propio,
            informe_correcto=informe_correcto,
            mismo_informe=(player.opinion == player.opinion_correcta
                           and bool(player.enfasis) == bool(esc['empresa_funcionamiento'])),
            puntaje=pesos(player.puntaje),
            puntaje_neg=player.puntaje < 0,
            ranking=filas_rank,
            devolucion=devolucion_de(player),
            comentario_docente=(player.participant.vars.get('comentario_docente') or '').strip(),
            semilla=player.session.vars.get('semilla'),
        )


page_sequence = [Instrucciones, Planeamiento, Controles, Sustantivas, Informe, EsperaEtapa,
                 ResultadoControles, Hallazgos, ResultadoFinal]
