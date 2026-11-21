"""
Bots de prueba: recorren los meses con políticas razonables y al azar.
Ejecutar con:  otree test deposito

Caso 'fuera_de_tiempo': el equipo 2 deja vencer el tiempo de la ronda 2 con una decisión
inválida; el sistema decide al azar (dentro de los límites) y la ronda queda marcada.
"""
import json
import random

from otree.api import Bot, Submission, SubmissionMustFail, expect

from . import Decision, Instrucciones, ResultadoFinal, Resultados, es_ultima_ronda, escenario, modelo, num_rondas, parametros


class PlayerBot(Bot):
    cases = ['a_tiempo', 'fuera_de_tiempo']

    def play_round(self):
        if self.round_number == 1:
            expect(len(self.subsession.get_groups()), 1)
            yield Instrucciones, dict(nombre_equipo=f'Bot {self.player.id_in_group}')
        if self.round_number > num_rondas(self.session):
            return

        p = parametros(self.session)
        esc = escenario(self.session)
        mes = self.round_number

        # Un lote de 0 unidades no se acepta.
        yield SubmissionMustFail(Decision, dict(lote=0, punto_pedido=30), check_html=False)

        if self.case == 'fuera_de_tiempo' and self.round_number == 2 and self.player.id_in_group == 2:
            # Vence el tiempo con una decisión inválida: se descarta y decide el sistema.
            yield Submission(Decision, dict(lote=0, punto_pedido=30), check_html=False, timeout_happened=True)
            expect(self.player.fuera_de_tiempo, True)
            expect(1 <= self.player.lote <= 5000, True)
            expect(self.player.field_maybe_none('respuesta'), None)
            expect(self.participant.vars['meses_deposito'][-1]['fuera_de_tiempo'], True)
            expect(self.participant.vars['fuera_de_tiempo'], [2])
            tablero = self.participant.vars['tablero']
            expect(tablero['fuera_de_tiempo'], [2])
            expect(tablero['historial']['filas'][-1]['envio'], '⏱ al azar')
            expect(any(o['tema'] == 'Tiempo' for o in tablero['devolucion']), True)
            yield Resultados
            if es_ultima_ronda(self.player):
                yield Submission(ResultadoFinal, check_html=False)
            return

        # El primer bot juega la política del modelo y responde bien; los demás, al azar.
        _, correcto, _ = modelo.pregunta_del_mes(mes, p, esc)
        if self.player.id_in_group == 1:
            n, r = modelo.politica_recomendada(mes, p, esc)
            datos = dict(lote=n, punto_pedido=r, respuesta=round(correcto, 2))
        else:
            datos = dict(lote=random.randint(10, 400), punto_pedido=random.randint(0, 100))
            if random.random() < 0.5:
                datos['respuesta'] = round(correcto * random.choice([1, 1.5]), 2)
        yield Submission(Decision, datos, check_html=False)

        # Lo guardado coincide con el modelo y el tablero tiene el formato común.
        r = self.participant.vars['meses_deposito'][-1]
        expect(abs(r['costo'] - self.player.costo), '<', 1e-6)
        expect(r['vendidas'] + r['perdidas'], r['demanda'])
        expect(r['pregunta']['acierto'], 'respuesta' in datos and datos['respuesta'] == round(correcto, 2))
        if self.player.id_in_group == 1:
            expect(abs(r['costo'] - r['recomendada']['costo']), '<', 1e-6)
        tablero = self.participant.vars['tablero']
        json.dumps(tablero)
        expect(tablero['version'], 2)
        expect(tablero['juego'], 'deposito')
        expect(len(tablero['historial']['filas']), mes)
        expect(len(tablero['devolucion']), '>', 0)
        expect(self.player.fuera_de_tiempo, False)
        expect(tablero['vence'], None)  # la configuración de prueba no tiene tiempo máximo
        yield Resultados

        if es_ultima_ronda(self.player):
            yield Submission(ResultadoFinal, check_html=False)
