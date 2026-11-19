"""
Devolución automática del juego de cartera.

Funciones puras (no dependen de oTree): reciben el historial del equipo, su
evaluación y la de las carteras de referencia, y devuelven observaciones en
texto para el equipo y el docente. Los umbrales están juntos al principio.

Cada observación es un dict:
    {'tipo': 'fortaleza' | 'alerta' | 'sugerencia', 'tema': str, 'texto': str}
"""

from nucleo.formato import numero, pesos, porcentaje

# --- Umbrales -----------------------------------------------------------------
CONCENTRADA = 0.80        # un activo con al menos este peso promedio: cartera concentrada
APUESTA_ACCIONES = 0.80   # acciones promedio desde la que un buen puesto se considera "apuesta"
LIQUIDEZ_ALTA = 0.50      # liquidez promedio considerada alta (pierde contra la inflación)
COMISIONES_ALTAS = 0.02   # comisiones totales / capital inicial
CAMBIO_GRANDE = 0.30      # cambio de porcentaje en acciones entre trimestres considerado grande
PUESTOS_ALTOS = 3


def _obs(tipo, tema, texto):
    return dict(tipo=tipo, tema=tema, texto=texto)


def _pct(x):
    return porcentaje(x, 0)


def _tasa(x):
    """Rentabilidades y volatilidades, con un decimal (como en las tablas)."""
    return porcentaje(x, 1)


def diagnosticar(filas, ev, refs, puesto_tea, puesto_sharpe, equipos, terminado, capital):
    """
    filas: historial por trimestre (acciones/bonos/liquidez en 0-1, rendimientos, comisión,
           crisis, noticia, ...). ev: modelo.evaluar() del equipo. refs: {nombre: evaluar()}.
    """
    obs = []
    n = len(filas)
    medio = {a: sum(f[a] for f in filas) / n for a in ('acciones', 'bonos', 'liquidez')}
    equilibrada = refs.get('Equilibrada 60/30/10')

    # Resultado y ranking
    periodo = 'del juego' if terminado else 'de lo que va del juego'
    texto = (f'Rentabilidad real {periodo}: {_tasa(ev["tea_real"])} anual (TEA), puesto {puesto_tea} de {equipos}. '
             f'Por rentabilidad ajustada por riesgo (Sharpe {numero(ev["sharpe"], 2)}) quedan {puesto_sharpe}°.')
    obs.append(_obs('fortaleza' if ev['tea_real'] > 0 else 'alerta', 'Resultado', texto))

    if puesto_tea <= PUESTOS_ALTOS and medio['acciones'] >= APUESTA_ACCIONES and equipos > 1:
        obs.append(_obs('alerta', 'Riesgo',
                        f'Llegaron arriba en el ranking con {_pct(medio["acciones"])} en acciones en promedio: '
                        f'una apuesta que en este escenario salió bien, pero con otro escenario podía salir muy mal '
                        f'(su caída máxima fue {_tasa(ev["caida_maxima"])}). La rentabilidad sola no muestra el riesgo.'))

    # Diversificación
    mayor = max(medio, key=medio.get)
    nombres = dict(acciones='acciones', bonos='bonos', liquidez='liquidez')
    if medio[mayor] >= CONCENTRADA:
        obs.append(_obs('alerta', 'Diversificación',
                        f'La cartera estuvo concentrada: en promedio {_pct(medio[mayor])} en {nombres[mayor]}. '
                        'Repartir entre activos que no se mueven juntos baja el riesgo sin resignar tanto rendimiento.'))
    elif min(medio.values()) >= 0.10:
        obs.append(_obs('fortaleza', 'Diversificación',
                        f'Mantuvieron una cartera diversificada (en promedio {_pct(medio["acciones"])} acciones, '
                        f'{_pct(medio["bonos"])} bonos y {_pct(medio["liquidez"])} liquidez).'))

    # Liquidez e inflación
    if medio['liquidez'] >= LIQUIDEZ_ALTA:
        liq = refs.get('Todo en liquidez')
        extra = f' Toda la cartera en plazo fijo habría rendido {_tasa(liq["tea_real"])} real anual.' if liq else ''
        obs.append(_obs('alerta', 'Inflación',
                        f'Tuvieron en promedio {_pct(medio["liquidez"])} en liquidez. El plazo fijo da seguridad '
                        f'nominal, pero con inflación suele perder en términos reales.{extra}'))

    # Comisiones y rotación
    if ev['comisiones'] / capital >= COMISIONES_ALTAS:
        cambios = sum(abs(filas[k]['acciones'] - filas[k - 1]['acciones']) >= CAMBIO_GRANDE for k in range(1, n))
        obs.append(_obs('alerta', 'Comisiones',
                        f'Pagaron {pesos(ev["comisiones"])} en comisiones ({_pct(ev["comisiones"] / capital)} del capital '
                        f'inicial), con {cambios} cambios grandes de cartera. Rebalancear seguido cuesta: conviene '
                        'moverse cuando hay una razón.'))
    elif n >= 4 and ev['comisiones'] >= 1:
        obs.append(_obs('fortaleza', 'Comisiones',
                        f'Gastaron poco en comisiones ({pesos(ev["comisiones"])}): no rotaron la cartera de más.'))

    # Crisis: ¿cómo los encontró?
    crisis = [f for f in filas if f['crisis']]
    if crisis:
        acc = sum(f['acciones'] for f in crisis) / len(crisis)
        trimestres = ', '.join(f'T{f["trimestre"]}' for f in crisis)
        if acc >= 0.6:
            texto = (f'La crisis ({trimestres}) los encontró con {_pct(acc)} en acciones. En dólares las acciones cayeron, '
                     'pero la suba del dólar amortiguó la caída en pesos: las acciones del exterior también protegen '
                     'contra la devaluación.')
            obs.append(_obs('sugerencia', 'Crisis', texto))
        else:
            obs.append(_obs('fortaleza', 'Crisis',
                            f'Cuando llegó la crisis ({trimestres}) tenían {_pct(acc)} en acciones: la cartera estaba protegida.'))

    # Noticias: ¿reaccionaron a los titulares?
    if n >= 3:
        a_favor = sum(1 for k in range(1, n) if
                      (filas[k]['noticia'] == 'optimista' and filas[k]['acciones'] > filas[k - 1]['acciones']) or
                      (filas[k]['noticia'] == 'pesimista' and filas[k]['acciones'] < filas[k - 1]['acciones']))
        if a_favor >= (n - 1) * 0.6:
            obs.append(_obs('sugerencia', 'Noticias',
                            f'Movieron la cartera según el titular en {a_favor} de {n - 1} trimestres. Los titulares '
                            'anticipan bien solo 2 de cada 3 veces y cada cambio paga comisión: ¿valió la pena?'))

    # Contra la cartera equilibrada
    if equilibrada and n >= 4:
        diferencia = ev['tea_real'] - equilibrada['tea_real']
        if abs(diferencia) < 0.001:
            obs.append(_obs('sugerencia', 'Comparación',
                            'Rindieron prácticamente lo mismo que una cartera equilibrada 60/30/10 sin tocar '
                            f'({_tasa(equilibrada["tea_real"])} real anual).'))
        elif diferencia > 0 and ev['volatilidad'] <= equilibrada['volatilidad'] * 1.1:
            obs.append(_obs('fortaleza', 'Comparación',
                            f'Le ganaron a la cartera equilibrada 60/30/10 ({_tasa(equilibrada["tea_real"])} real anual) '
                            'sin asumir más riesgo.'))
        elif diferencia < 0 and ev['volatilidad'] > equilibrada['volatilidad']:
            obs.append(_obs('sugerencia', 'Comparación',
                            f'Una cartera equilibrada 60/30/10 sin tocar habría rendido {_tasa(equilibrada["tea_real"])} '
                            f'real anual con menos riesgo que la suya ({_tasa(equilibrada["volatilidad"])} de volatilidad '
                            f'contra {_tasa(ev["volatilidad"])}).'))
    return obs
