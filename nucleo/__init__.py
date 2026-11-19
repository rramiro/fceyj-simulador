"""
Núcleo común de los simuladores de negocios de la FCEyJ.

Lo que comparten todos los juegos y no depende de ninguno en particular:
    formato        montos en pesos, números y porcentajes al estilo argentino
    inflacion      índice de precios, moneda constante y senda de inflación de la sesión
    tablero        resumen de cada equipo para el tablero del docente (formato común)
    ajustes_otree  ajustes puntuales sobre oTree (página propia de aula completa)

No es una app de oTree (no figura en app_sequence) y salvo ajustes_otree no
importa oTree: así los scripts de simulación pueden usarlo sin el servidor.
"""
