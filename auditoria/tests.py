"""
Bots de prueba: recorren las cuatro etapas del encargo con decisiones al azar.
Ejecutar con:  otree test auditoria
"""
import json
import random

from otree.api import Bot, Submission, SubmissionMustFail, expect

from . import (Controles, Hallazgos, Informe, Instrucciones, Planeamiento, ResultadoControles, ResultadoFinal,
               Sustantivas, campo_ajuste, ciclos_probados, encontrados, escenario, modelo, montos, parametros,
               PROCEDIMIENTOS, RUBROS)


class PlayerBot(Bot):
    def play_round(self):
        esc = escenario(self.session)
        p = parametros(self.session)
        r = self.round_number

        if r == 1:
            expect(len(self.subsession.get_groups()), 1)
            yield Instrucciones, dict(nombre_equipo=f'Bot {self.player.id_in_group}')
            datos = dict(base_significatividad='resultado', pct_significatividad=5)
            datos.update({f'riesgo_{x}': random.choice(['bajo', 'medio', 'alto']) for x in RUBROS})
            yield Submission(Planeamiento, datos, check_html=False)
            expect(abs(self.player.significatividad - esc['significatividad']), '<', 1)

        elif r == 2:
            # Las casillas sin marcar no se envían. Sin calificar el control, la página no avanza.
            pruebas = {f'prueba_{x}': True for x in RUBROS if random.random() < 0.5}
            yield SubmissionMustFail(Controles, pruebas, check_html=False)
            datos = dict(pruebas)
            datos.update({f'calif_{x}': random.choice(list(modelo.CALIFICACIONES_CONTROL)) for x in RUBROS})
            yield Submission(Controles, datos, check_html=False)
            yield ResultadoControles

        elif r == 3:
            disponibles = set(modelo.procedimientos_disponibles(esc))
            ciclos = ciclos_probados(self.player)
            # Todo con alcance alto: si se pasa del presupuesto, la página lo rechaza.
            alto = {pr: (3 if pr in disponibles else 0) for pr in PROCEDIMIENTOS}
            if modelo.horas_totales(ciclos, alto, p, esc) > p['presupuesto_horas']:
                yield SubmissionMustFail(Sustantivas, {f'alcance_{pr}': a for pr, a in alto.items()}, check_html=False)
            # Con limitación al alcance, no se puede confirmar saldos de créditos.
            if esc['limitacion']:
                yield SubmissionMustFail(Sustantivas, {f'alcance_{pr}': (1 if pr == 'confirmacion' else 0)
                                                       for pr in PROCEDIMIENTOS}, check_html=False)
            elegidos = {pr: (random.randint(0, 2) if pr in disponibles else 0) for pr in PROCEDIMIENTOS}
            yield Submission(Sustantivas, {f'alcance_{pr}': a for pr, a in elegidos.items()}, check_html=False)
            # Ajustes: la mitad bien calculados (con el monto del error) y el resto mal o en blanco.
            ajustes = {}
            for e in encontrados(self.player):
                azar = random.random()
                if azar < 0.5:
                    ajustes[campo_ajuste(e)] = e['monto']
                elif azar < 0.8:
                    ajustes[campo_ajuste(e)] = round(e['monto'] * 1.2)
            yield Submission(Hallazgos, ajustes, check_html=False)
            m = montos(self.player)
            for e in encontrados(self.player):
                expect(modelo.ajuste_correcto(e, m[e['id']], p), ajustes.get(campo_ajuste(e)) == e['monto'])

        elif r == 4:
            yield SubmissionMustFail(Informe, dict(opinion='favorable'), check_html=False)
            yield Submission(Informe, dict(opinion=random.choice(modelo.OPINIONES), enfasis=random.random() < 0.5),
                             check_html=False)
            pl = self.player
            expect(pl.horas, '<=', p['presupuesto_horas'])
            expect(pl.comparacion in ('correcta', 'falla', 'severa'), True)
            ev = modelo.evaluar(esc, ciclos_probados(pl), {pr: getattr(pl.in_round(3), f'alcance_{pr}') for pr in PROCEDIMIENTOS},
                                pl.opinion, p, montos(pl), pl.enfasis)
            expect(abs(ev['puntaje'] - pl.puntaje), '<', 1e-6)
            tablero = self.participant.vars['tablero']
            json.dumps(tablero)
            expect(tablero['version'], 2)
            expect(tablero['juego'], 'auditoria')
            expect(len(tablero['historial']['filas']), 4)
            expect(len(tablero['devolucion']), '>', 0)
            # La página final no tiene botón "Siguiente".
            yield Submission(ResultadoFinal, check_html=False)
