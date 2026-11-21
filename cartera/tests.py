"""
Bots de prueba: recorren todas las páginas con carteras al azar.
Ejecutar con:  otree test cartera

Caso 'fuera_de_tiempo': el equipo 2 deja vencer el tiempo del trimestre 2 con porcentajes que no
suman 100; el sistema reparte al azar y el trimestre queda marcado.
"""
import json
import random

from otree.api import Bot, Submission, SubmissionMustFail, expect

from . import Decision, InformeAnual, Instrucciones, ResultadoFinal, Resultados, es_ultima_ronda, num_rondas


def reparto_al_azar():
    a = random.randrange(0, 21)
    b = random.randrange(0, 21 - a)
    return dict(pct_acciones=a * 5, pct_bonos=b * 5, pct_liquidez=(20 - a - b) * 5)


class PlayerBot(Bot):
    cases = ['a_tiempo', 'fuera_de_tiempo']

    def play_round(self):
        if self.round_number == 1:
            # Todos los equipos juegan en un mismo grupo, frente al mismo escenario.
            expect(len(self.subsession.get_groups()), 1)
            yield Instrucciones, dict(nombre_equipo=f'Bot {self.player.id_in_group}')

        if self.round_number > num_rondas(self.session):
            return

        # Los porcentajes tienen que sumar 100 y venir de 5 en 5.
        yield SubmissionMustFail(Decision, dict(pct_acciones=50, pct_bonos=30, pct_liquidez=30), check_html=False)
        yield SubmissionMustFail(Decision, dict(pct_acciones=52, pct_bonos=28, pct_liquidez=20), check_html=False)
        if self.case == 'fuera_de_tiempo' and self.round_number == 2 and self.player.id_in_group == 2:
            # Vence el tiempo con un reparto inválido: se descarta y decide el sistema.
            yield Submission(Decision, dict(pct_acciones=50, pct_bonos=30, pct_liquidez=30), check_html=False,
                             timeout_happened=True)
            p = self.player
            expect(p.fuera_de_tiempo, True)
            expect(p.pct_acciones + p.pct_bonos + p.pct_liquidez, 100)
            expect(p.pct_acciones % 5 + p.pct_bonos % 5 + p.pct_liquidez % 5, 0)
            expect(self.participant.vars['fuera_de_tiempo'], [2])
            tablero = self.participant.vars['tablero']
            expect(tablero['fuera_de_tiempo'], [2])
            expect(tablero['historial']['filas'][-1]['envio'], '⏱ al azar')
            expect(any(o['tema'] == 'Tiempo' for o in tablero['devolucion']), True)
        else:
            yield Submission(Decision, reparto_al_azar(), check_html=False)

        p = self.player
        expect(abs(p.monto_acciones + p.monto_bonos + p.monto_liquidez - p.valor_final), '<', 1e-6)
        expect(p.comision, '>=', 0)
        # Sin comprar ni vender acciones o bonos no hay comisión.
        if self.round_number == 1 and p.pct_liquidez == 100:
            expect(p.comision, 0)
        expect(abs(p.valor_real - p.valor_final / self.group.indice), '<', 1e-6)

        # El tablero del docente: formato común (nucleo/tablero.py) y JSON.
        tablero = self.participant.vars['tablero']
        json.dumps(tablero)
        expect(tablero['version'], 2)
        expect(tablero['juego'], 'cartera')
        expect(len(tablero['historial']['filas']), self.round_number)
        expect(len(tablero['devolucion']), '>', 0)
        expect(tablero['vence'], None)  # la configuración de prueba no tiene tiempo máximo
        yield Resultados

        if self.round_number % 4 == 0 or es_ultima_ronda(p):
            yield InformeAnual
        if es_ultima_ronda(p):
            # La página final no tiene botón "Siguiente" (es la última).
            yield Submission(ResultadoFinal, check_html=False)
