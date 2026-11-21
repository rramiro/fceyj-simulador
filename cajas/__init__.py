import random

from otree.api import *

from nucleo import ajustes_otree, tablero, tiempo
from nucleo.formato import numero, pesos, porcentaje

from . import devolucion, modelo

# Página propia para "aula completa" (ver nucleo/ajustes_otree.py).
ajustes_otree.aplicar()


doc = """
Las cajas del súper (FCEJ - UNLPam), Métodos Cuantitativos para la Administración.
Cada equipo gerencia la línea de cajas de un supermercado durante uno o más sábados.
En cada franja (mañana, mediodía, tarde, noche) decide cuántas cajas abre; los clientes
llegan según un proceso Poisson y se atienden en fila única con tiempo exponencial.
Costo = cajas abiertas + espera de los clientes. Un evento y una pregunta por franja.
"""

EMPRESA = 'Súper Quantum'


class C(BaseConstants):
    NAME_IN_URL = 'cajas'
    # Todos los equipos frente a los mismos clientes y pasando juntos de franja.
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 12
    TITULO_JUEGO = 'Las cajas del súper'
    SUBTITULO_JUEGO = f'Líneas de espera en {EMPRESA}'


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    nombre_equipo = models.StringField(label='Nombre del equipo', max_length=30, blank=True)

    # Decisión de la franja
    cajas = models.IntegerField(min=1, max=30, label='Cajas abiertas en la franja')
    respuesta = models.FloatField(label='Su respuesta', blank=True, min=-1e12, max=1e12)

    # Resultados de la franja
    costo = models.FloatField()
    costo_acumulado = models.FloatField()
    acierto = models.BooleanField()
    puntos_pregunta = models.IntegerField()
    # No enviaron a tiempo: la decisión la tomó el sistema al azar (ver nucleo/tiempo.py).
    fuera_de_tiempo = models.BooleanField(initial=False)


# --- Funciones auxiliares ---------------------------------------------------

def num_rondas(session):
    return min(session.config.get('num_rondas', 8), C.NUM_ROUNDS)


def ronda_activa(player):
    return player.round_number <= num_rondas(player.session)


def es_ultima_ronda(player):
    return player.round_number == num_rondas(player.session)


def parametros(session):
    return {k: session.config[k] for k in modelo.PARAMETROS}


def escenario(session):
    return session.vars['escenario']


def nombre(player):
    return player.participant.vars.get('nombre_equipo') or f'Equipo {player.id_in_group}'


def estado(player):
    """Estado del súper al empezar la franja (se guarda en participant.vars)."""
    return player.participant.vars.get('estado_cajas') or modelo.estado_inicial(parametros(player.session))


def rondas_jugadas(player):
    return player.participant.vars.get('rondas_cajas', [])


def nombre_ronda(ronda, session):
    """'Sábado 1 · Mañana (8 a 12 h)'."""
    d = modelo.datos_ronda(ronda, parametros(session), escenario(session))
    sabado = f'Sábado {d["sabado"]} · ' if num_rondas(session) > len(modelo.FRANJAS) else ''
    return f'{sabado}{d["nombre"]} ({d["inicio"]} a {d["inicio"] + d["horas"]} h)'


def texto_valor(valor, unidad):
    if valor is None:
        return 'sin respuesta'
    if unidad == 'cajas':
        return f'{numero(valor)} cajas'
    if unidad.startswith('(entre'):
        return numero(valor, 3)
    return f'{numero(valor, 2)} {unidad}'


def decimal_justo(x):
    """5 → '5'; 6.5 → '6,5'."""
    return numero(x, 0 if abs(x - round(x)) < 1e-9 else 1)


def minutos(x):
    return f'{numero(x, 1)} min'


def decision_al_azar(player):
    """Cajas de la franja al azar (cuando el equipo no envía a tiempo): de 1 al máximo del súper, sin respuesta."""
    player.cajas = random.randint(1, int(parametros(player.session)['max_cajas']))
    player.respuesta = None
    player.fuera_de_tiempo = True
    tiempo.marcar_fuera_de_tiempo(player.participant.vars, player.round_number)


# --- Creación de la sesión -------------------------------------------------------------

def creating_session(subsession: Subsession):
    session = subsession.session
    if subsession.round_number == 1:
        semilla = int(session.config.get('semilla') or 0) or random.randint(1, 999_999)
        session.vars['semilla'] = semilla
        session.vars['escenario'] = modelo.generar_escenario(parametros(session), num_rondas(session), semilla)


# --- Cierre de la franja ------------------------------------------------------------------

def cerrar_ronda(group: Group):
    p = parametros(group.session)
    esc = escenario(group.session)
    ronda = group.round_number
    pregunta, correcto, unidad = modelo.pregunta_de_la_ronda(ronda, p, esc)
    s_rec = modelo.cajas_recomendadas(ronda, p, esc)
    for pl in group.get_players():
        antes = estado(pl)
        nuevo, r = modelo.simular_ronda(ronda, pl.cajas, antes, p, esc)
        # Lo que habría costado la cantidad de cajas del modelo, con los mismos clientes y desde el mismo estado.
        _, rec = modelo.simular_ronda(ronda, s_rec, antes, p, esc)
        acierto = modelo.acierta(pl.field_maybe_none('respuesta'), correcto, p)
        nuevo['aciertos'] = antes['aciertos'] + (1 if acierto else 0)
        r.update(pregunta=dict(texto=pregunta, correcto=correcto, unidad=unidad,
                               respuesta=pl.field_maybe_none('respuesta'), acierto=acierto),
                 recomendada=dict(cajas=s_rec, costo=rec['costo'], wq=rec['wq_observada']),
                 en_sistema_inicial=len(antes['fila']) + len(antes['en_caja'])
                 if antes.get('sabado', 1) == r['sabado'] else 0)
        pl.participant.vars['estado_cajas'] = nuevo
        r['fuera_de_tiempo'] = bool(pl.fuera_de_tiempo)
        pl.participant.vars['rondas_cajas'] = rondas_jugadas(pl) + [r]
        pl.costo = r['costo']
        pl.costo_acumulado = nuevo['costo_acumulado']
        pl.acierto = acierto
        pl.puntos_pregunta = nuevo['aciertos'] * p['puntos_pregunta']
    # El reloj de la ronda siguiente corre desde ahora, igual para todos.
    if group.round_number < num_rondas(group.session):
        tiempo.abrir_ronda([pl.participant.vars for pl in group.get_players()], group.round_number + 1,
                           group.session.config)
    for pl in group.get_players():
        actualizar_tablero(pl, 'Resultados listos')


def puntajes(player):
    """Puntaje de cada equipo con lo acumulado hasta ahora: {id_in_group: puntos}."""
    equipos = [q for q in player.group.get_players() if q.participant.vars.get('rondas_cajas')]
    if not equipos:
        return {}
    p = parametros(player.session)
    ests = [q.participant.vars['estado_cajas'] for q in equipos]
    pts = modelo.puntaje_final([e['costo_acumulado'] for e in ests],
                               [e['aciertos'] * p['puntos_pregunta'] for e in ests], p)
    return {q.id_in_group: x for q, x in zip(equipos, pts)}


def puesto(player):
    pts = puntajes(player)
    if player.id_in_group not in pts:
        return None
    orden = sorted(pts, key=pts.get, reverse=True)
    return orden.index(player.id_in_group) + 1


# --- Datos para las pantallas ----------------------------------------------------------

def texto_evento(ronda, params, esc):
    d = modelo.datos_ronda(ronda, params, esc)
    p = params
    ev = d['evento']
    if ev == 'lluvia':
        return (f'Llueve: se espera {porcentaje(-p["efecto_lluvia"], 0)} menos de clientes, unos '
                f'{numero(d["lam"])} por hora.')
    if ev == 'promocion':
        return (f'La radio anuncia una promoción del súper: se espera {porcentaje(p["efecto_promocion"], 0)} más de '
                f'clientes, unos {numero(d["lam"])} por hora.')
    if ev == 'partido':
        return (f'Juega la Selección: se espera {porcentaje(-p["efecto_partido"], 0)} menos de clientes, unos '
                f'{numero(d["lam"])} por hora.')
    if ev == 'cajero_nuevo':
        return (f'Empieza un cajero nuevo en la caja 1: atiende un {porcentaje(p["lentitud_nuevo"], 0)} más lento que '
                'los demás (si abren esa caja). Las otras cajas atienden como siempre.')
    if ev == 'falla':
        return (f'El sistema de cobro anda lento: todas las cajas tardan un {porcentaje(p["lentitud_falla"], 0)} más, '
                f'{decimal_justo(d["minutos"])} minutos por cliente en promedio.')
    return 'Sin novedades: llegan los clientes de siempre para esta franja.'


def datos_tabla(ronda, params, esc):
    d = modelo.datos_ronda(ronda, params, esc)
    filas = [
        ('Duración de la franja', f'{d["horas"]} horas (de {d["inicio"]} a {d["inicio"] + d["horas"]} h)'),
        ('Llegadas λ', f'{numero(d["lam"])} clientes por hora en promedio (proceso Poisson)'),
        ('Atención 1/μ', f'{decimal_justo(d["minutos"])} minutos por cliente en promedio (exponencial): '
                         f'μ = {numero(d["mu"], 1)} clientes por hora y caja'),
        ('Costo de una caja Cs', f'{pesos(d["cs"])} por hora (se paga toda la franja)'),
        ('Costo de espera Cc', f'{pesos(d["cc"])} por cliente y por hora en el súper (en fila o en caja)'),
        ('Cajas disponibles', f'de 1 a {int(params["max_cajas"])}; fila única'),
    ]
    return [dict(concepto=a, valor=b) for a, b in filas]


def medidas_comparadas(r, params, esc):
    """Medidas observadas en la franja frente a las del modelo M/M/s con las cajas que abrió el equipo."""
    d = modelo.datos_ronda(r['ronda'], params, esc)
    m = modelo.mms(d['lam'], d['mu'], r['cajas'])
    rho = d['lam'] / (r['cajas'] * d['mu'])

    def mod(k, f):
        return 'la cola crece sin límite' if m is None else f(m[k])
    return [
        dict(medida='Llegadas λ (por hora)', observada=numero(r['lam_observada'], 1), modelo=numero(d['lam'], 1)),
        dict(medida='Utilización ρ = λ / (s·μ)', observada=numero(r['rho_observada'], 3), modelo=numero(rho, 3)),
        dict(medida='Clientes en la fila Lq', observada=numero(r['lq_observada'], 2), modelo=mod('lq', lambda v: numero(v, 2))),
        dict(medida='Clientes en el súper Ls', observada=numero(r['ls_observada'], 2), modelo=mod('ls', lambda v: numero(v, 2))),
        dict(medida='Espera en la fila Wq', observada=minutos(r['wq_observada']), modelo=mod('wq', lambda v: minutos(v * 60))),
        dict(medida='Probabilidad de esperar', observada=porcentaje(r['pw_observada'], 0),
             modelo=mod('pw', lambda v: porcentaje(v, 0))),
    ]


def curva_costos(ronda, params, esc, elegidas):
    f = modelo.formulas(ronda, params, esc)
    filas = []
    for c in f['curva']:
        if c['s'] != elegidas and (c['s'] < f['s_min'] - 1 or c['s'] > f['s_opt'] + 3):
            continue
        filas.append(dict(s=c['s'], rho=numero(c['rho'], 2),
                          costo=pesos(c['costo']) if c['estable'] else 'inestable (ρ ≥ 1)',
                          wq=minutos(c['wq_min']) if c['estable'] else '—',
                          optimo=c['s'] == f['s_opt'], elegida=c['s'] == elegidas))
    return filas


# --- Tablero del docente y devolución --------------------------------------------------

ETAPAS_TABLERO = {
    'Instrucciones': ('decidiendo', 'Leyendo instrucciones'),
    'Decisión': ('decidiendo', 'Decidiendo las cajas de la franja'),
    'Esperando a los demás equipos': ('esperando', 'Decisión enviada'),
    'Resultados listos': ('resultados', 'Resultados de la franja listos'),
    'Viendo resultados': ('resultados', 'Viendo resultados'),
    'Terminó': ('termino', 'Terminó'),
}

COLUMNAS_TABLERO = [
    tablero.columna('ronda', 'F', 'ronda'),
    tablero.columna('franja', 'Franja', 'texto'),
    tablero.columna('evento', 'Evento', 'texto'),
    tablero.columna('cajas', 'Cajas (modelo)', 'texto'),
    tablero.columna('costo', 'Costo', 'pesos'),
    tablero.columna('espera', 'Espera media', 'texto'),
    tablero.columna('pregunta', 'Pregunta', 'texto'),
    tablero.columna('envio', 'Envío', 'texto'),
]


def historial(player):
    return [dict(ronda=r['ronda'], franja=r['nombre'], evento=modelo.EVENTOS[r['evento']],
                 cajas=f'{r["cajas"]} ({r["recomendada"]["cajas"]})', costo=r['costo'],
                 espera=minutos(r['wq_observada']), pregunta='✓' if r['pregunta']['acierto'] else '✗',
                 envio='⏱ al azar' if r.get('fuera_de_tiempo') else 'a tiempo')
            for r in rondas_jugadas(player)]


def devolucion_de(player):
    rondas = rondas_jugadas(player)
    if not rondas:
        return []
    obs = devolucion.diagnosticar(rondas, parametros(player.session), escenario(player.session),
                                  puesto(player), len(player.group.get_players()))
    return obs + tiempo.observaciones(player.participant.vars, 'F')


def actualizar_tablero(player, pagina):
    etapa, estado_txt = ETAPAS_TABLERO[pagina]
    est = estado(player)
    pts = puntajes(player)
    jugo = bool(rondas_jugadas(player))
    player.participant.vars['tablero'] = tablero.resumen(
        juego=C.NAME_IN_URL,
        equipo=nombre(player),
        grupo_numero=player.group.id_in_subsession,
        grupo_tipo='grupo',
        grupo_tamano=len(player.group.get_players()),
        posicion=player.id_in_group,
        ronda=player.round_number,
        rondas=num_rondas(player.session),
        nombre_ronda='franja', abrev_ronda='F',
        etapa=etapa,
        estado=estado_txt,
        puesto=puesto(player),
        indicadores=[
            tablero.indicador('Costo acumulado', est['costo_acumulado'] if jugo else None, 'pesos'),
            tablero.indicador('Preguntas', est['aciertos'] if jugo else None, 'numero'),
            tablero.indicador('Puntaje', numero(pts[player.id_in_group], 1) if player.id_in_group in pts else None, 'texto'),
        ],
        decision=None,
        columnas=COLUMNAS_TABLERO,
        filas=historial(player),
        nota_historial='Costo de la franja = cajas abiertas + espera de los clientes; entre paréntesis, las cajas '
                       'óptimas del modelo M/M/s. El ranking usa el costo acumulado.',
        devolucion=devolucion_de(player),
        vence=tiempo.vence_pendiente(player.participant.vars, player.session.config, player.round_number,
                                     etapa, es_ultima_ronda(player)),
        fuera_de_tiempo=tiempo.rondas_fuera_de_tiempo(player.participant.vars),
    )


# --- Páginas --------------------------------------------------------------------------

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
        n = num_rondas(player.session)
        franjas = len(modelo.FRANJAS)
        return dict(
            **tiempo.contexto(player.session.config, 'franja', femenino=True),
            empresa=EMPRESA, num_rondas=n,
            sabados=(n + franjas - 1) // franjas,
            num_equipos=len(player.group.get_players()),
            franjas=[dict(nombre=f['nombre'], horario=f'{f["inicio"]} a {f["inicio"] + f["horas"]} h',
                          llegadas=numero(p[f['clave']] * p['escala_llegadas'])) for f in modelo.FRANJAS],
            minutos_atencion=decimal_justo(p['minutos_atencion']), costo_caja=pesos(p['costo_caja']),
            costo_espera=pesos(p['costo_espera']), max_cajas=int(p['max_cajas']),
            tolerancia=porcentaje(p['tolerancia_pregunta'], 0), puntos_pregunta=p['puntos_pregunta'],
            puntos_resultado=p['puntos_resultado'],
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        texto = (player.nombre_equipo or '').strip()
        if texto:
            player.participant.vars['nombre_equipo'] = texto


class Decision(Page):
    form_model = 'player'
    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        return tiempo.segundos_decision(player.participant.vars, player.session.config, player.round_number)
    form_fields = ['cajas', 'respuesta']

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def error_message(player: Player, values):
        maximo = int(parametros(player.session)['max_cajas'])
        if values['cajas'] > maximo:
            return f'El súper tiene {maximo} cajas.'

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decisión')
        p = parametros(player.session)
        esc = escenario(player.session)
        ronda = player.round_number
        d = modelo.datos_ronda(ronda, p, esc)
        est = estado(player)
        mismo_sabado = est.get('sabado', 1) == d['sabado']
        pregunta, _, unidad = modelo.pregunta_de_la_ronda(ronda, p, esc)
        anterior = rondas_jugadas(player)[-1] if rondas_jugadas(player) else None
        return dict(
            **tiempo.contexto(player.session.config, 'franja', femenino=True),
            empresa=EMPRESA, num_rondas=num_rondas(player.session), franja=nombre_ronda(ronda, player.session),
            evento=modelo.EVENTOS[d['evento']], texto_evento=texto_evento(ronda, p, esc),
            evento_normal=d['evento'] == 'normal',
            datos=datos_tabla(ronda, p, esc),
            en_fila=len(est['fila']) if mismo_sabado else 0,
            en_caja=len(est['en_caja']) if mismo_sabado else 0,
            sabado_nuevo=anterior is not None and not mismo_sabado,
            cajas_anteriores=anterior['cajas'] if anterior else None,
            max_cajas=int(p['max_cajas']),
            pregunta=pregunta, unidad=unidad,
            tolerancia=porcentaje(p['tolerancia_pregunta'], 0), puntos_pregunta=p['puntos_pregunta'],
            acumulado=pesos(est['costo_acumulado']) if anterior else None,
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if timeout_happened:
            decision_al_azar(player)
        actualizar_tablero(player, 'Esperando a los demás equipos')


class EsperaRonda(WaitPage):
    title_text = 'Esperando a los demás equipos'
    body_text = 'La franja se simula cuando todos los equipos hayan decidido cuántas cajas abren.'
    after_all_players_arrive = cerrar_ronda

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)


class Resultados(Page):
    timer_text = tiempo.TEXTO_LECTURA

    @staticmethod
    def get_timeout_seconds(player: Player):
        # El reloj de la ronda siguiente ya corre mientras leen los resultados.
        return tiempo.segundos_lectura(player.participant.vars, player.round_number, es_ultima_ronda(player))

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Viendo resultados')
        r = rondas_jugadas(player)[-1]
        p = parametros(player.session)
        esc = escenario(player.session)
        d = modelo.datos_ronda(r['ronda'], p, esc)
        preg = r['pregunta']
        rec = r['recomendada']
        horas_cajas = r['cajas'] * d['horas']
        return dict(
            **tiempo.contexto(player.session.config, 'franja', femenino=True),
            t_fuera=r.get('fuera_de_tiempo', False),
            empresa=EMPRESA, num_rondas=num_rondas(player.session), franja=nombre_ronda(r['ronda'], player.session),
            evento=modelo.EVENTOS[r['evento']], cajas=r['cajas'],
            llegaron=numero(r['llegaron']), atendidos=numero(r['atendidos']), quedan=numero(r['quedan']),
            hay_quedan=r['quedan'] > 0, en_sistema_inicial=r['en_sistema_inicial'],
            espera_media=minutos(r['wq_observada']), espera_max=minutos(r['espera_max']), fila_max=r['fila_max'],
            cierre_extra=minutos(r['cierre_extra']) if r['cierre_extra'] > 0.5 else None,
            medidas=medidas_comparadas(r, p, esc),
            cajero_nuevo=r['evento'] == 'cajero_nuevo',
            curva=curva_costos(r['ronda'], p, esc, r['cajas']),
            costo_cajas=pesos(r['costo_cajas']), detalle_cajas=f'{r["cajas"]} cajas × {d["horas"]} h × {pesos(d["cs"])}',
            horas_cajas=horas_cajas,
            costo_espera=pesos(r['costo_espera']),
            detalle_espera=f'{numero(r["costo_espera"] / d["cc"], 1)} horas-cliente × {pesos(d["cc"])}',
            costo=pesos(r['costo']),
            rec_cajas=rec['cajas'], rec_costo=pesos(rec['costo']), rec_espera=minutos(rec['wq']),
            mejor_que_rec=r['costo'] <= rec['costo'] + 1,
            pregunta=preg['texto'], correcto=texto_valor(preg['correcto'], preg['unidad']),
            respuesta=texto_valor(preg['respuesta'], preg['unidad']), acierto=preg['acierto'],
            puntos_pregunta=p['puntos_pregunta'],
            acumulado=pesos(player.costo_acumulado),
            puesto=puesto(player), num_equipos=len(player.group.get_players()),
        )

    @staticmethod
    def js_vars(player: Player):
        r = rondas_jugadas(player)[-1]
        d = modelo.datos_ronda(r['ronda'], parametros(player.session), escenario(player.session))
        return dict(serie=[[x['minuto'], x['fila'], x['caja']] for x in r['serie']], cajas=r['cajas'],
                    inicio=d['inicio'], minutos=d['horas'] * 60)


class ResultadoFinal(Page):
    @staticmethod
    def is_displayed(player: Player):
        return es_ultima_ronda(player)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Terminó')
        p = parametros(player.session)
        pts = puntajes(player)
        equipos = sorted(player.group.get_players(), key=lambda q: pts.get(q.id_in_group, 0), reverse=True)
        filas = []
        for i, q in enumerate(equipos):
            e = q.participant.vars.get('estado_cajas') or modelo.estado_inicial(p)
            rs = q.participant.vars.get('rondas_cajas', [])
            filas.append(dict(puesto=i + 1, nombre=nombre(q), es_propia=q.id_in_group == player.id_in_group,
                              puntaje=numero(pts.get(q.id_in_group, 0), 1), costo=pesos(e['costo_acumulado']),
                              espera=minutos(sum(x['wq_observada'] for x in rs) / max(1, len(rs))),
                              preguntas=e['aciertos']))
        est = estado(player)
        rondas = rondas_jugadas(player)
        return dict(
            t_fuera_lista=tiempo.lista(player.participant.vars, 'F'),
            empresa=EMPRESA, ranking=filas,
            costo=pesos(est['costo_acumulado']),
            costo_recomendado=pesos(sum(r['recomendada']['costo'] for r in rondas)),
            aciertos=est['aciertos'], num_rondas=len(rondas),
            rondas=[dict(ronda=r['ronda'], franja=nombre_ronda(r['ronda'], player.session),
                         evento=modelo.EVENTOS[r['evento']], cajas=r['cajas'], rec=r['recomendada']['cajas'],
                         costo=pesos(r['costo']), costo_rec=pesos(r['recomendada']['costo']),
                         espera=minutos(r['wq_observada']),
                         pregunta='✓' if r['pregunta']['acierto'] else '✗') for r in rondas],
            devolucion=devolucion_de(player),
            comentario_docente=(player.participant.vars.get('comentario_docente') or '').strip(),
            semilla=player.session.vars.get('semilla'),
            puntos_resultado=p['puntos_resultado'],
        )


page_sequence = [Instrucciones, Decision, EsperaRonda, Resultados, ResultadoFinal]
