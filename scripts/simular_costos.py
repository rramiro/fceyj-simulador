"""
Verificaciones y calibración del modelo de costos (costos/modelo.py).

    python scripts/simular_costos.py
    python scripts/simular_costos.py escala_demanda=1.2 cm_corte=320   # probar otros valores

1) Verificaciones: identidad entre costeo integral y variable, capacidad, informes.
2) El taller: costos unitarios, contribución, punto de equilibrio y capacidad a precio de referencia.
3) Estrategias típicas en muchas partidas: resultado (variable e integral), informes y puntaje.
"""
import importlib.util
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from costos import modelo  # noqa: E402

PARAMETROS_DEFECTO = dict(
    precio_tela=4_000, rendimiento_tela=0.90, costo_hora_mo=5_120, tasa_cv_corte=400,
    cv_hora_embolsado=3_700, estuche_compra=1_500,
    cm_corte=300, np_corte=280, cfc_corte=644_000, cfo_corte=400_000,
    cm_embolsado=220, np_embolsado=200, cfc_embolsado=636_000, cfo_embolsado=563_400,
    cf_administracion=6_000_000, cf_comercializacion=2_000_000,
    escala_demanda=1.0, desvio_demanda=0.08, desvio_precio_tela=0.04, desvio_rendimiento=0.015,
    desvio_eficiencia=0.05, tolerancia_informe=0.05, puntos_informe=5, puntos_resultado=70,
)
MESES = 6
PARTIDAS = 1000


def cargar_parametros():
    spec = importlib.util.spec_from_file_location('settings', RAIZ / 'settings.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = next((c for c in mod.SESSION_CONFIGS if c['name'] == 'costos'), None)
    return {k: cfg[k] for k in modelo.PARAMETROS} if cfg else dict(PARAMETROS_DEFECTO)


def leer_parametros(argv):
    cfg = cargar_parametros()
    for arg in argv:
        clave, valor = arg.split('=')
        if clave not in cfg:
            sys.exit(f'Parámetro desconocido: {clave}')
        cfg[clave] = float(valor)
    return cfg


def m(x):
    return f'{x / 1e6:,.1f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


# --- Estrategias ------------------------------------------------------------------------
# Cada una recibe (mes, estado, params, escenario) y devuelve las decisiones del mes.

def ajustar_a_capacidad(prod, estado, p, esc, pedido=False):
    """Reduce la producción en proporción hasta que entre en la capacidad."""
    prod = dict(prod)
    for _ in range(60):
        if modelo.validar_produccion(prod, estado, p, esc, pedido) is None:
            return prod
        prod = {l: int(q * 0.97) for l, q in prod.items()}
    return {l: 0 for l in prod}


def plan_de_venta(mes, estado, p, esc, precios):
    """Producción = demanda prevista al precio elegido menos el stock."""
    return {l: max(0, int(modelo.demanda_prevista(l, mes, estado, p, esc)
                          * (precios[l] / modelo.LINEAS[l]['precio_ref']) ** (-modelo.LINEAS[l]['elasticidad'])
                          - estado['stock'][l]))
            for l in estado['lineas']}


def decidir_evento_bien(tipo, mes, estado, p, esc, precios, prod):
    return modelo.decision_recomendada(tipo, mes, estado, p, esc, prod)


def informe_bien(tipo, mes, estado, p, esc, precios, prod):
    _, valor, _ = modelo.informe_correcto(tipo, None, mes, estado, p, esc)
    if valor is None:
        cf = sum(modelo.costos_fijos_periodo(estado, p, esc).values())
        valor = modelo.punto_equilibrio_mezcla(precios, {l: prod.get(l, 0) for l in estado['lineas']}, estado, p, esc, cf)
    return valor


def precios_con_capacidad(mes, estado, p, esc):
    """Precio óptimo de cada línea; si la producción no entra en la capacidad, se suben todos
    los precios de a 2 % hasta que entre (cobrar más es mejor que no poder entregar)."""
    precios = {l: modelo.precio_optimo(l, estado, p, esc) for l in modelo.LINEAS}
    for _ in range(40):
        if modelo.validar_produccion(plan_de_venta(mes, estado, p, esc, precios), estado, p, esc) is None:
            break
        precios = {l: v * 1.02 for l, v in precios.items()}
    return precios


def de_manual(mes, estado, p, esc):
    tipo = esc['meses'][mes - 1]['evento']
    precios = precios_con_capacidad(mes, estado, p, esc)
    prod = ajustar_a_capacidad(plan_de_venta(mes, estado, p, esc, precios), estado, p, esc)
    evento = decidir_evento_bien(tipo, mes, estado, p, esc, precios, prod)
    if tipo == 'pedido_especial' and evento:
        prod = ajustar_a_capacidad(prod, estado, p, esc, pedido=True)
    return dict(precios=precios, produccion=prod, evento=evento,
                informe=informe_bien(tipo, mes, estado, p, esc, precios, prod))


def sin_informes(mes, estado, p, esc):
    d = de_manual(mes, estado, p, esc)
    d['informe'] = None
    return d


def rechaza_todo(mes, estado, p, esc):
    precios = {l: modelo.LINEAS[l]['precio_ref'] for l in modelo.LINEAS}
    prod = ajustar_a_capacidad(plan_de_venta(mes, estado, p, esc, precios), estado, p, esc)
    tipo = esc['meses'][mes - 1]['evento']
    return dict(precios=precios, produccion=prod, evento=0 if tipo == 'bordado' else False, informe=None)


def acepta_todo(mes, estado, p, esc):
    d = rechaza_todo(mes, estado, p, esc)
    tipo = esc['meses'][mes - 1]['evento']
    d['evento'] = esc['eventos']['bordado']['tope'] if tipo == 'bordado' else True
    if tipo == 'pedido_especial':
        d['produccion'] = ajustar_a_capacidad(d['produccion'], estado, p, esc, pedido=True)
    return d


def llena_capacidad(mes, estado, p, esc):
    """Produce al máximo (con precio de referencia): el costeo integral lo "premia"."""
    precios = {l: modelo.LINEAS[l]['precio_ref'] for l in modelo.LINEAS}
    prod = ajustar_a_capacidad({l: 2_000 for l in estado['lineas']}, estado, p, esc)
    tipo = esc['meses'][mes - 1]['evento']
    return dict(precios=precios, produccion=prod, evento=0 if tipo == 'bordado' else False, informe=None)


def precio_bajo(mes, estado, p, esc):
    precios = {l: 0.8 * modelo.LINEAS[l]['precio_ref'] for l in modelo.LINEAS}
    prod = ajustar_a_capacidad(plan_de_venta(mes, estado, p, esc, precios), estado, p, esc)
    tipo = esc['meses'][mes - 1]['evento']
    return dict(precios=precios, produccion=prod, evento=0 if tipo == 'bordado' else False, informe=None)


ESTRATEGIAS = {
    'De manual (decide e informa bien)': de_manual,
    'De manual, sin informes': sin_informes,
    'Precio de referencia, rechaza todo': rechaza_todo,
    'Precio de referencia, acepta todo': acepta_todo,
    'Llena la capacidad (sobreproduce)': llena_capacidad,
    'Precio 20 % más bajo': precio_bajo,
}


def jugar(estrategia, esc, p):
    estado = modelo.estado_inicial()
    meses = []
    for mes in range(1, MESES + 1):
        dec = estrategia(mes, estado, p, esc)
        estado, r = modelo.simular_mes(mes, dec, estado, p, esc)
        meses.append(r)
    return estado, meses


# --- 1) Verificaciones ------------------------------------------------------------------

def verificaciones(p):
    esc = modelo.generar_escenario(p, MESES, semilla=3)
    assert modelo.generar_escenario(p, MESES, semilla=3) == esc
    for s in range(60):
        e = modelo.generar_escenario(p, MESES, semilla=s)
        for estrategia in ESTRATEGIAS.values():
            estado = modelo.estado_inicial()
            for mes in range(1, MESES + 1):
                dec = estrategia(mes, estado, p, e)
                antes = estado
                estado, r = modelo.simular_mes(mes, dec, estado, p, e)
                assert estado is not antes
                # Integral − variable = variación del stock valuado por cada método
                # (salvo el mes en que se elimina la línea infantil y su stock se liquida).
                if not (r['evento'] == 'competidor_infantil' and r['decision']):
                    d_stock = (sum(estado['valor_int'].values()) - sum(estado['valor_var'].values())) \
                        - (sum(antes['valor_int'].values()) - sum(antes['valor_var'].values()))
                    assert abs((r['resultado_int'] - r['resultado_var']) - d_stock) < 1e-3, (s, mes)
                # Nunca se vende más de lo disponible.
                for f in r['filas'].values():
                    assert f['vendidas'] <= f['produccion'] + antes['stock'][f['linea']] + 1e-9
    # Un informe exacto acierta; uno 10 % corrido no.
    assert modelo.acierta_informe(100, 100, p) and not modelo.acierta_informe(111, 100, p)
    print('Verificaciones: OK\n')


# --- 2) El taller ----------------------------------------------------------------------------

def informe_taller(p):
    esc = modelo.generar_escenario(p, MESES, semilla=1)
    est = modelo.estado_inicial()
    print('El taller a precio de referencia (mes promedio):')
    cf = sum(modelo.costos_fijos_periodo(est, p, esc).values())
    for l in modelo.LINEAS:
        d = modelo.LINEAS[l]
        cv = modelo.costo_variable(l, est, p, esc)
        cfu = modelo.costo_fijo_unitario(l, est, p, esc)
        cm = modelo.contribucion_unitaria(l, d['precio_ref'], est, p, esc)
        print(f'   {d["nombre"]:<22} precio $ {d["precio_ref"]:>7,.0f}  cv $ {cv:>7,.0f}  cf abs. $ {cfu:>6,.0f}'
              f'  contribución $ {cm:>7,.0f}  precio óptimo $ {modelo.precio_optimo(l, est, p, esc):>7,.0f}'
              .replace(',', '.'))
    q = {l: modelo.LINEAS[l]['demanda'] * p['escala_demanda'] for l in modelo.LINEAS_INICIALES}
    precios = {l: modelo.LINEAS[l]['precio_ref'] for l in modelo.LINEAS}
    pe = modelo.punto_equilibrio_mezcla(precios, q, est, p, esc, cf)
    hc = sum(q[l] * modelo.LINEAS[l]['horas_corte'] for l in q)
    he = sum(q[l] * modelo.LINEAS[l]['horas_embolsado'] for l in q)
    print(f'   Costos fijos del mes: $ {m(cf)} M. Demanda base: {sum(q.values()):.0f} cortinas; punto de equilibrio '
          f'{pe:.0f}; margen de seguridad {100 * (1 - pe / sum(q.values())):.0f} %.')
    print(f'   Horas a demanda base: corte {hc:.0f} de {p["cm_corte"]:.0f} (Cm); embolsado {he:.0f} de '
          f'{p["cm_embolsado"]:.0f}. Tasas de CF: corte $ {modelo.tasa_corte(p):,.0f}/hh, embolsado '
          f'$ {modelo.tasa_embolsado(p):,.0f}/hm.\n'.replace(',', '.'))


# --- 3) Estrategias --------------------------------------------------------------------------

def informe_estrategias(p):
    nombres = list(ESTRATEGIAS)
    res = {n: [] for n in nombres}
    for s in range(PARTIDAS):
        esc = modelo.generar_escenario(p, MESES, semilla=s)
        finales = {n: jugar(ESTRATEGIAS[n], esc, p)[0] for n in nombres}
        pts = modelo.puntaje_final([finales[n]['resultado_var'] for n in nombres],
                                   [finales[n]['puntos_informe'] for n in nombres], p)
        mejor = max(range(len(nombres)), key=lambda i: pts[i])
        for i, n in enumerate(nombres):
            res[n].append(dict(var=finales[n]['resultado_var'], int=finales[n]['resultado_int'],
                               inf=finales[n]['puntos_informe'], pts=pts[i], gana=i == mejor))
    print(f'Estrategias ({PARTIDAS} partidas de {MESES} meses; resultados acumulados en millones de pesos):')
    print(f'   {"Estrategia":<38} {"res. variable":>13} {"res. integral":>13} {"informes":>9} {"puntaje":>8} {"gana":>6}')
    for n in nombres:
        r = res[n]
        print(f'   {n:<38} {m(statistics.mean(x["var"] for x in r)):>13} {m(statistics.mean(x["int"] for x in r)):>13} '
              f'{statistics.mean(x["inf"] for x in r):>9.1f} {statistics.mean(x["pts"] for x in r):>8.1f} '
              f'{100 * sum(x["gana"] for x in r) / PARTIDAS:>5.0f} %')
    print('   (puntaje = 70 × resultado variable relativo entre estas estrategias + 5 por informe acertado)\n')


def main():
    p = leer_parametros(sys.argv[1:])
    print('Parámetros:', p, '\n')
    verificaciones(p)
    informe_taller(p)
    informe_estrategias(p)


if __name__ == '__main__':
    main()
