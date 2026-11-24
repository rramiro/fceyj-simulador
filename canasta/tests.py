"""
Bots de prueba: recorren los meses con la canasta óptima y al azar.
Ejecutar con:  otree test canasta

Caso 'fuera_de_tiempo': el equipo 2 deja vencer el tiempo del mes 2 con una decisión
inválida; el sistema decide al azar (dentro del presupuesto) y el mes queda marcado.
"""
import json
import random

from otree.api import Bot, Submission, SubmissionMustFail, expect

from . import (Decision, Instrucciones, ResultadoFinal, Resultados, datos_del_mes, es_ultima_ronda, modelo,
               num_rondas, parametros, tipo, x_marzo)


class PlayerBot(Bot):
    cases = ['a_tiempo', 'fuera_de_tiempo']

    def play_round(self):
        if self.round_number == 1:
            expect(len(self.subsession.get_groups()), 1)
            yield Instrucciones, dict(nombre_equipo=f'Bot {self.player.id_in_group}')
        if self.round_number > num_rondas(self.session):
            return

        p = parametros(self.session)
        ronda = self.round_number
        d = datos_del_mes(self.player)
        t = tipo(self.player)

        # Más entradas de las que alcanza el ingreso no se aceptan.
        yield SubmissionMustFail(Decision, dict(entradas=d['x_max'] + 1), check_html=False)
        yield SubmissionMustFail(Decision, dict(entradas=-1), check_html=False)

        if self.case == 'fuera_de_tiempo' and ronda == 2 and self.player.id_in_group == 2:
            yield Submission(Decision, dict(entradas=-1), check_html=False, timeout_happened=True)
            expect(self.player.fuera_de_tiempo, True)
            expect(0 <= self.player.entradas <= d['x_max'], True)
            expect(self.player.field_maybe_none('respuesta'), None)
            expect(self.participant.vars['rondas_canasta'][-1]['fuera_de_tiempo'], True)
            expect(self.participant.vars['fuera_de_tiempo'], [2])
            tablero = self.participant.vars['tablero']
            expect(tablero['historial']['filas'][-1]['envio'], '⏱ al azar')
            yield Resultados
            if es_ultima_ronda(self.player):
                yield Submission(ResultadoFinal, check_html=False)
            return

        # El primer bot elige la canasta óptima y responde bien; los demás, al azar.
        if self.player.id_in_group == 1:
            x = modelo.optimo(d, t)[0]
            xm = x if ronda == 1 else x_marzo(self.player)
            _, correcto, _, _ = modelo.pregunta_de_la_ronda(ronda, p, xm, x)
            datos = dict(entradas=x)
            if correcto is not None:
                datos['respuesta'] = correcto
        else:
            x = random.randint(0, d['x_max'])
            datos = dict(entradas=x)
            if random.random() < 0.5:
                datos['respuesta'] = random.choice([0.5, 1, 2, -1])
        yield Submission(Decision, datos, check_html=False)

        r = self.participant.vars['rondas_canasta'][-1]
        expect(r['x'], x)
        expect(abs(r['px'] * r['x'] + r['py'] * r['y'] - r['ingreso']), '<', 1e-6)
        expect(r['u'], '<=', r['u_opt'] + 1e-9)
        if self.player.id_in_group == 1:
            expect(r['distancia'], 0)
            expect(r['pregunta']['acierto'], True)
            expect(abs(self.player.puntaje - 100), '<', 1e-9)
        if ronda == 7:
            # Slutsky: con el ingreso compensado alcanza justo para la canasta de marzo.
            m = self.participant.vars['rondas_canasta'][0]
            expect(abs(r['px'] * m['x'] + r['py'] * m['y'] - r['ingreso']), '<', 1e-6)
        tablero = self.participant.vars['tablero']
        json.dumps(tablero)
        expect(tablero['version'], 2)
        expect(tablero['juego'], 'canasta')
        expect(len(tablero['historial']['filas']), ronda)
        expect(len(tablero['devolucion']), '>', 0)
        expect(self.player.fuera_de_tiempo, False)
        yield Resultados

        if es_ultima_ronda(self.player):
            yield Submission(ResultadoFinal, check_html=False)
