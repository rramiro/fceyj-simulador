"""
Bots de prueba: recorren las franjas con la cantidad de cajas del modelo y al azar.
Ejecutar con:  otree test cajas

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
        ronda = self.round_number

        # Cero cajas o más cajas de las que hay no se aceptan.
        yield SubmissionMustFail(Decision, dict(cajas=0), check_html=False)
        yield SubmissionMustFail(Decision, dict(cajas=int(p['max_cajas']) + 1), check_html=False)

        if self.case == 'fuera_de_tiempo' and self.round_number == 2 and self.player.id_in_group == 2:
            # Vence el tiempo con una decisión inválida: se descarta y decide el sistema.
            yield Submission(Decision, dict(cajas=0), check_html=False, timeout_happened=True)
            expect(self.player.fuera_de_tiempo, True)
            expect(1 <= self.player.cajas <= int(p['max_cajas']), True)
            expect(self.player.field_maybe_none('respuesta'), None)
            expect(self.participant.vars['rondas_cajas'][-1]['fuera_de_tiempo'], True)
            expect(self.participant.vars['fuera_de_tiempo'], [2])
            tablero = self.participant.vars['tablero']
            expect(tablero['fuera_de_tiempo'], [2])
            expect(tablero['historial']['filas'][-1]['envio'], '⏱ al azar')
            expect(any(o['tema'] == 'Tiempo' for o in tablero['devolucion']), True)
            yield Resultados
            if es_ultima_ronda(self.player):
                yield Submission(ResultadoFinal, check_html=False)
            return

        # El primer bot abre las cajas del modelo y responde bien; los demás, al azar (a veces con ρ ≥ 1).
        _, correcto, _ = modelo.pregunta_de_la_ronda(ronda, p, esc)
        if self.player.id_in_group == 1:
            datos = dict(cajas=modelo.cajas_recomendadas(ronda, p, esc), respuesta=correcto)
        else:
            datos = dict(cajas=random.randint(1, int(p['max_cajas'])))
            if random.random() < 0.5:
                datos['respuesta'] = correcto * random.choice([1, 1.5])
        yield Submission(Decision, datos, check_html=False)

        # Lo guardado coincide con el modelo y el tablero tiene el formato común.
        r = self.participant.vars['rondas_cajas'][-1]
        expect(abs(r['costo'] - self.player.costo), '<', 1e-6)
        expect(abs(r['costo'] - r['costo_cajas'] - r['costo_espera']), '<', 1e-6)
        expect(r['pregunta']['acierto'], 'respuesta' in datos and datos['respuesta'] == correcto)
        if r['franja'] == len(modelo.FRANJAS) - 1:
            expect(r['quedan'], 0)
        if self.player.id_in_group == 1:
            expect(abs(r['costo'] - r['recomendada']['costo']), '<', 1e-6)
        tablero = self.participant.vars['tablero']
        json.dumps(tablero)
        expect(tablero['version'], 2)
        expect(tablero['juego'], 'cajas')
        expect(len(tablero['historial']['filas']), ronda)
        expect(len(tablero['devolucion']), '>', 0)
        expect(self.player.fuera_de_tiempo, False)
        expect(tablero['vence'], None)  # la configuración de prueba no tiene tiempo máximo
        yield Resultados

        if es_ultima_ronda(self.player):
            yield Submission(ResultadoFinal, check_html=False)
