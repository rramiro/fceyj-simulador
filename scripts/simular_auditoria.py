"""
Verificaciones y calibración del modelo de auditoría (auditoria/modelo.py).

    python scripts/simular_auditoria.py
    python scripts/simular_auditoria.py presupuesto_horas=350 factor_errores=1.5   # probar otros valores

1) Verificaciones: más alcance nunca detecta menos, horas, opinión, puntaje y que cada papel de
   trabajo permita calcular su ajuste.
2) Encargos: cuántos errores hay, cuántos importantes y qué opinión corresponde.
3) Estrategias típicas de los equipos en muchos encargos: puntaje, horas, opinión correcta,
   fallas de auditoría y errores importantes detectados.
"""
import importlib.util
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))   # nucleo/ y auditoria/ sin importar oTree

from auditoria import modelo  # noqa: E402

PARAMETROS_DEFECTO = dict(
    escala=1_000_000,
    honorarios=12_000_000,
    costo_hora=20_000,
    presupuesto_horas=400,
    horas_planeamiento=20,
    horas_prueba_control=5,
    reduccion_control_fuerte=0.3,
    prob_control_debil=0.4,
    precision_senales=0.6,
    factor_errores=1.0,
    monto_min=0.3,
    monto_max=2.5,
    pct_significatividad=0.05,
    prob_limitacion=0.25,
    prob_acepta_ajuste=0.7,
    penalidad_falla=1.0,
    factor_diligencia=0.5,
    penalidad_severa=0.5,
    penalidad_sin_evidencia=0.1,
    tolerancia_ajuste=0.01,
    bonificacion_ajuste=300_000,
    penalidad_ajuste=300_000,
    precision_relatos=0.8,
    prob_empresa_funcionamiento=0.3,
    penalidad_enfasis=0.1,
)
ENCARGOS = 2000


def cargar_parametros():
    """La configuración 'auditoria' de settings.py si ya existe; si no, los valores de arriba."""
    spec = importlib.util.spec_from_file_location('settings', RAIZ / 'settings.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = next((c for c in mod.SESSION_CONFIGS if c['name'] == 'auditoria'), None)
    return {k: cfg[k] for k in modelo.PARAMETROS} if cfg else dict(PARAMETROS_DEFECTO)


def leer_parametros(argv):
    cfg = cargar_parametros()
    for arg in argv:
        clave, valor = arg.split('=')
        if clave not in cfg:
            sys.exit(f'Parámetro desconocido: {clave}')
        cfg[clave] = float(valor)
    return cfg


def pct(x, dec=0):
    return f'{x * 100:.{dec}f} %'.replace('.', ',')


def millones(x):
    return f'{x / 1e6:,.1f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


# --- Estrategias típicas -----------------------------------------------------------------
# Cada una recibe el escenario y devuelve (ciclos probados, alcances, regla de opinión).
# Leen el riesgo según la señal del planeamiento (que a veces no es la verdadera).

NIVEL = dict(bajo=1, medio=2, alto=3)


def todos(alcance):
    return {pr: alcance for pr in modelo.PROCEDIMIENTOS}


def por_rubro(niveles):
    return {pr: niveles[d['rubro']] for pr, d in modelo.PROCEDIMIENTOS.items()}


def sin_procedimientos(esc):
    return [], todos(0), 'favorable'


def todo_bajo(esc):
    return [], todos(1), 'conocida'


def todo_medio(esc):
    return list(modelo.RUBROS), todos(2), 'conocida'


def todo_alto(esc):
    return list(modelo.RUBROS), todos(3), 'conocida'


def por_riesgo_inherente(esc):
    return [], por_rubro({r: NIVEL[d['nivel_senal']] for r, d in esc['rubros'].items()}), 'conocida'


def por_riesgo_y_control(esc):
    niveles = {}
    for r, d in esc['rubros'].items():
        n = NIVEL[d['nivel_senal']] + (1 if d['control'] == 'debil' else -1)
        niveles[r] = max(1, min(3, n))
    return list(modelo.RUBROS), por_rubro(niveles), 'conocida'


def por_riesgo_firma_favorable(esc):
    ciclos, alcances, _ = por_riesgo_y_control(esc)
    return ciclos, alcances, 'favorable'


def por_riesgo_con_alternativa(esc):
    """Por riesgo y control; si el cliente no deja confirmar créditos, aplica el procedimiento alternativo."""
    ciclos, alcances, regla = por_riesgo_y_control(esc)
    if esc['limitacion']:
        alcances['antiguedad'] = max(alcances['antiguedad'], 2)
    return ciclos, alcances, regla


def con_ajustes_mal(esc):
    """Como la mejor, pero calcula mal la mitad de los ajustes."""
    return (*por_riesgo_con_alternativa(esc), dict(ajustes='mitad'))


def sin_ajustes(esc):
    """Como la mejor, pero no propone ningún ajuste."""
    return (*por_riesgo_con_alternativa(esc), dict(ajustes='ninguno'))


def sin_empresa_funcionamiento(esc):
    """Como la mejor, pero nunca incluye la sección sobre empresa en funcionamiento."""
    return (*por_riesgo_con_alternativa(esc), dict(enfasis=False))


ESTRATEGIAS = {
    'Sin procedimientos (firma favorable)': sin_procedimientos,
    'Todo con alcance bajo': todo_bajo,
    'Todo con alcance medio': todo_medio,
    'Todo con alcance alto': todo_alto,
    'Por riesgo inherente': por_riesgo_inherente,
    'Por riesgo y control': por_riesgo_y_control,
    'Por riesgo y control + alternativa': por_riesgo_con_alternativa,
    'Por riesgo, firma siempre favorable': por_riesgo_firma_favorable,
    'La mejor, calcula mal la mitad de ajustes': con_ajustes_mal,
    'La mejor, sin proponer ajustes': sin_ajustes,
    'La mejor, sin empresa en funcionamiento': sin_empresa_funcionamiento,
}


def jugar(estrategia, esc, cfg):
    ciclos, alcances, regla, *extra = estrategia(esc)
    extra = extra[0] if extra else {}
    disponibles = set(modelo.procedimientos_disponibles(esc))
    alcances = {pr: (a if pr in disponibles else 0) for pr, a in alcances.items()}
    # Ajustes: bien calculados salvo que la estrategia diga otra cosa.
    montos = {}
    for i, e in enumerate(modelo.detectados(esc, alcances)):
        if extra.get('ajustes') == 'ninguno':
            montos[e['id']] = None
        elif extra.get('ajustes') == 'mitad' and i % 2 == 0:
            montos[e['id']] = e['monto'] * 1.2
        else:
            montos[e['id']] = e['monto']
    opinion = regla if regla != 'conocida' else modelo.opinion_conocida(esc, alcances, cfg, montos)
    return modelo.evaluar(esc, ciclos, alcances, opinion, cfg, montos, extra.get('enfasis'))


# --- 1) Verificaciones --------------------------------------------------------------------

def verificaciones(cfg):
    esc = modelo.generar_escenario(cfg, semilla=7)
    assert modelo.generar_escenario(cfg, semilla=7) == esc, 'la semilla no reproduce el encargo'

    # Más alcance nunca detecta menos (en muchos encargos y para cada procedimiento).
    for s in range(300):
        e = modelo.generar_escenario(cfg, semilla=s)
        for pr in modelo.PROCEDIMIENTOS:
            antes = set()
            for a in (0, 1, 2, 3):
                ids = {x['id'] for x in modelo.detectados(e, {pr: a})}
                assert antes <= ids, (s, pr, a)
                antes = ids

    # Horas: planeamiento + controles + procedimientos.
    h = modelo.horas_totales(['caja', 'creditos'], {'arqueo': 2, 'corte': 3}, cfg)
    assert abs(h - (cfg['horas_planeamiento'] + 2 * cfg['horas_prueba_control'] + 6 * 2 + 8 * 3.5)) < 1e-9

    # Sin procedimientos: todos los rubros sin evidencia y nada detectado.
    ev = modelo.evaluar(esc, [], todos(0), 'favorable', cfg)
    assert len(ev['sin_evidencia']) == len(modelo.RUBROS) and not ev['encontrados']

    # Comparación de opiniones.
    assert modelo.comparar_opinion('favorable', 'salvedades') == 'falla'
    assert modelo.comparar_opinion('adversa', 'salvedades') == 'severa'
    assert modelo.comparar_opinion('abstencion', 'favorable') == 'severa'
    assert modelo.comparar_opinion('salvedades', 'abstencion') == 'falla'

    # Puntaje = honorarios − horas × costo − penalidades.
    ev = modelo.evaluar(esc, list(modelo.RUBROS), todos(2), 'favorable', cfg)
    assert abs(ev['puntaje'] - (cfg['honorarios'] - ev['horas'] * cfg['costo_hora'] - sum(ev['penalidades'].values()))) < 1e-6
    # Con bonificación y penalidad por empresa en funcionamiento.
    e = next(x for x in (modelo.generar_escenario(cfg, semilla=s) for s in range(100)) if x['empresa_funcionamiento'])
    ev = modelo.evaluar(e, list(modelo.RUBROS), todos(2), 'favorable', cfg, None, False)
    assert ev['penalidades']['enfasis'] == cfg['penalidad_enfasis'] * cfg['honorarios']
    assert abs(ev['puntaje'] - (cfg['honorarios'] - ev['costo_horas'] - sum(ev['penalidades'].values())
                                + ev['bien_calculados'] * cfg['bonificacion_ajuste'])) < 1e-6

    # Un ajuste mal calculado vuelve devuelto y queda sin corregir.
    e = next(x for x in (modelo.generar_escenario(cfg, semilla=s) for s in range(100)) if x['errores'])
    err = e['errores'][0]
    assert modelo.estado_ajuste(err, {err['id']: err['monto'] * 1.5}, cfg) == 'devuelto'
    assert modelo.estado_ajuste(err, {err['id']: None}, cfg) == 'sin_proponer'
    assert modelo.estado_ajuste(err, {err['id']: err['monto']}, cfg) in ('aceptado', 'rechazado')

    # Cada papel de trabajo trae los datos para calcular el ajuste (el monto del error).
    n = 0
    for s in range(2000):
        for err in modelo.generar_escenario(cfg, semilla=s)['errores']:
            assert modelo.ajuste_correcto(err, calcular_ajuste(err), cfg), (s, err['tipo'])
            n += 1
    print(f'Verificaciones: OK (incluye {n} papeles de trabajo recalculados)\n')


def calcular_ajuste(error):
    """El ajuste que calcularía un estudiante a partir del papel de trabajo (como en los TP)."""
    papel = modelo.papel_de_trabajo(error)
    imp = [l['importe'] for l in papel['lineas']]
    txt = [l['texto'] for l in papel['lineas']]
    t = error['tipo']
    primero = lambda i: float(txt[i].split()[0])   # noqa: E731
    if t == 'faltante_caja':
        return imp[0] - sum(imp[1:])
    if t == 'partida_conciliacion':
        return imp[4] + imp[5] - imp[6]
    if t == 'incobrables':
        return imp[0] * (1 - primero(1) / 100) - imp[2]
    if t == 'ventas_ficticias':
        return imp[0] - imp[1] - imp[2]
    if t == 'corte_ventas':
        return primero(0) * (imp[1] - imp[2])
    if t == 'inventario_inexistente':
        return (primero(0) - primero(1)) * imp[2]
    if t == 'inventario_obsoleto':
        return primero(0) * (imp[1] - imp[2] * 0.9)
    if t == 'amortizacion_omitida':
        return imp[0] / primero(1) * primero(2) / 12
    if t == 'bien_inexistente':
        return imp[0] - imp[1]
    if t == 'inversion_sobrevaluada':
        return primero(0) * (imp[1] - imp[2] * 0.99)
    if t == 'pasivo_omitido':
        return imp[0]
    if t == 'cargas_omitidas':
        return imp[0] * primero(2) / 100
    raise ValueError(t)


# --- 2) Encargos ----------------------------------------------------------------------------

def informe_encargos(cfg, encargos):
    n_err = [len(e['errores']) for e in encargos]
    n_imp = [sum(x['monto'] >= e['significatividad'] for x in e['errores']) for e in encargos]
    perfecta = {}
    for e in encargos:
        # Opinión que corresponde si se detectara todo (y el cliente rechazara lo que rechaza).
        op = modelo.opinion_correcta(e, todos(3), cfg)
        perfecta[op] = perfecta.get(op, 0) + 1
    print(f'Encargos ({ENCARGOS}). Significatividad de referencia: {pct(cfg["pct_significatividad"])} del resultado '
          f'(≈ $ {millones(statistics.mean(e["significatividad"] for e in encargos))} M).')
    print(f'   Errores por encargo: media {statistics.mean(n_err):.1f}; importantes: media {statistics.mean(n_imp):.1f}; '
          f'encargos sin errores: {pct(sum(x == 0 for x in n_err) / ENCARGOS)}; '
          f'con limitación al alcance: {pct(sum(e["limitacion"] for e in encargos) / ENCARGOS)}')
    print('   Opinión que corresponde con una auditoría completa: ' +
          ', '.join(f'{modelo.NOMBRES_OPINION[o].lower()} {pct(perfecta.get(o, 0) / ENCARGOS)}' for o in modelo.OPINIONES))
    horas = {n: modelo.horas_totales(c, a, cfg) for n, (c, a, _) in
             [('todo bajo', ([], todos(1), 0)), ('todo medio', (list(modelo.RUBROS), todos(2), 0)),
              ('todo alto', (list(modelo.RUBROS), todos(3), 0))]}
    print(f'   Horas: presupuesto {cfg["presupuesto_horas"]:.0f}; todo bajo {horas["todo bajo"]:.0f}, '
          f'todo medio {horas["todo medio"]:.0f}, todo alto {horas["todo alto"]:.0f} (con todos los controles probados '
          f'en medio y alto). Una hora cuesta $ {cfg["costo_hora"]:,.0f}; honorarios $ {millones(cfg["honorarios"])} M.\n'
          .replace(',', '.'))


# --- 3) Estrategias -----------------------------------------------------------------------

def informe_estrategias(cfg, encargos):
    res = {n: [jugar(f, e, cfg) for e in encargos] for n, f in ESTRATEGIAS.items()}
    nombres = list(res)
    gana = dict.fromkeys(nombres, 0)
    for k in range(ENCARGOS):
        validos = [n for n in nombres if not res[n][k]['excede_presupuesto']]
        gana[max(validos, key=lambda n: res[n][k]['puntaje'])] += 1

    print(f'Estrategias ({ENCARGOS} encargos; puntaje en millones de pesos; salvo indicación, calculan bien '
          f'los ajustes e incluyen la sección sobre empresa en funcionamiento cuando corresponde):')
    print(f'   {"Estrategia":<42} {"puntaje":>8} {"P10":>7} {"horas":>6} {"excede":>7} {"opinión ok":>11} '
          f'{"fallas":>7} {"severas":>8} {"imp. detect.":>13} {"gana":>6}')
    for n in nombres:
        r = res[n]
        pts = [x['puntaje'] for x in r]
        q = statistics.quantiles(pts, n=10)
        imp = sum(x['importantes'] for x in r)
        print(f'   {n:<42} {millones(statistics.mean(pts)):>8} {millones(q[0]):>7} '
              f'{statistics.mean(x["horas"] for x in r):>6.0f} {pct(sum(x["excede_presupuesto"] for x in r) / ENCARGOS):>7} '
              f'{pct(sum(x["comparacion"] == "correcta" for x in r) / ENCARGOS):>11} '
              f'{pct(sum(x["comparacion"] == "falla" for x in r) / ENCARGOS):>7} '
              f'{pct(sum(x["comparacion"] == "severa" for x in r) / ENCARGOS):>8} '
              f'{pct(sum(x["importantes_detectados"] for x in r) / imp if imp else 0):>13} '
              f'{pct(gana[n] / ENCARGOS):>6}')
    print('   (puntaje medio y percentil 10; "excede" = encargos en los que la estrategia supera el presupuesto de horas,'
          ' que en el juego no se permite; "imp. detect." = errores importantes detectados sobre el total;'
          ' "gana" = mejor puntaje entre las que respetan el presupuesto)\n')


def main():
    cfg = leer_parametros(sys.argv[1:])
    print('Parámetros:', cfg, '\n')
    verificaciones(cfg)
    encargos = [modelo.generar_escenario(cfg, semilla=s) for s in range(ENCARGOS)]
    informe_encargos(cfg, encargos)
    informe_estrategias(cfg, encargos)


if __name__ == '__main__':
    main()
