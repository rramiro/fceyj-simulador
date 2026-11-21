"""
Resumen de cada equipo para el tablero del docente (formato común a todos los juegos).

El tablero (_static/docente/docente.js) lee los participantes con la API REST de
oTree, que solo expone participant.vars. Cada juego guarda en
participant.vars['tablero'] el dict que arma `resumen()` y el tablero lo
muestra sin saber de qué juego se trata.

Formato (versión 2; todo en tipos JSON):

    version       2
    juego         nombre de la app ('comercializacion', 'cartera', ...)
    equipo        nombre del equipo o empresa
    rotulo_equipo cómo llama el juego a los equipos en el tablero ('Empresa', 'Equipo')
    grupo         {numero, tipo, tamano, posicion}: equipos que avanzan juntos.
                  `tipo` es un sustantivo masculino ('mercado', 'grupo') que el
                  tablero usa en frases como "este mercado" o "su mercado".
    ronda         {actual, total, nombre, abrev}, p. ej. {3, 4, 'trimestre', 'T'}
    etapa         'decidiendo' | 'esperando' | 'resultados' | 'termino'
    estado        texto corto de la pantalla en la que está ('Decidiendo')
    puesto        posición dentro del grupo (o None si todavía no hay resultados)
    indicadores   [{etiqueta, valor, formato, signo}] columnas de la tabla del grupo
    decision      texto de la decisión enviada (se muestra mientras espera) o None
    historial     {columnas: [{clave, etiqueta, formato, signo}], filas: [{clave: valor}], nota}
    devolucion    [{tipo, tema, texto}] (ver devolucion.py de cada juego)
    vence         segundos desde 1970 en que vence el tiempo para enviar la decisión
                  que el equipo tiene pendiente, o None (sin límite, o nada pendiente)
    fuera_de_tiempo  rondas en las que no envió a tiempo y decidió el sistema (lista)
    actualizado   segundos desde 1970

`vence` y `fuera_de_tiempo` son opcionales: un tablero que no los trae se muestra igual.

Formatos de número que entiende el tablero: 'pesos', 'pesos2' (con centavos),
'numero', 'pct' (0.25 -> 25 %), 'pct1' (con un decimal: 4,6 %), 'ronda' (3 -> T3) y 'texto'. `signo=True`
marca en rojo los valores negativos.
"""
import time

VERSION = 2
ETAPAS = ('decidiendo', 'esperando', 'resultados', 'termino')
FORMATOS = ('pesos', 'pesos2', 'numero', 'pct', 'pct1', 'ronda', 'texto')


def columna(clave, etiqueta, formato='texto', signo=False):
    """Columna del historial."""
    assert formato in FORMATOS, formato
    return dict(clave=clave, etiqueta=etiqueta, formato=formato, signo=signo)


def indicador(etiqueta, valor, formato='texto', signo=False):
    """Dato de la tabla del grupo (una columna por indicador)."""
    assert formato in FORMATOS, formato
    return dict(etiqueta=etiqueta, valor=valor, formato=formato, signo=signo)


def resumen(*, juego, equipo, grupo_numero, grupo_tipo, grupo_tamano, posicion,
            ronda, rondas, etapa, estado, puesto=None, indicadores=(), decision=None,
            columnas=(), filas=(), nota_historial='', devolucion=(),
            nombre_ronda='trimestre', abrev_ronda='T', rotulo_equipo='Equipo',
            vence=None, fuera_de_tiempo=()):
    assert etapa in ETAPAS, etapa
    claves = [c['clave'] for c in columnas]
    return dict(
        version=VERSION,
        juego=juego,
        equipo=equipo,
        rotulo_equipo=rotulo_equipo,
        grupo=dict(numero=grupo_numero, tipo=grupo_tipo, tamano=grupo_tamano, posicion=posicion),
        ronda=dict(actual=ronda, total=rondas, nombre=nombre_ronda, abrev=abrev_ronda),
        etapa=etapa,
        estado=estado,
        puesto=puesto,
        indicadores=list(indicadores),
        decision=decision,
        historial=dict(columnas=list(columnas),
                       filas=[{k: f.get(k) for k in claves} for f in filas],
                       nota=nota_historial if filas else ''),
        devolucion=list(devolucion),
        vence=vence,
        fuera_de_tiempo=list(fuera_de_tiempo),
        actualizado=time.time(),
    )
