"""
Bots de prueba: recorren todas las páginas con decisiones aleatorias.
Ejecutar con:  otree test comercializacion
"""
import random

from otree.api import Bot, Submission, expect

from . import Instrucciones, Decision, Resultados, ResultadoFinal, num_rondas


class PlayerBot(Bot):
    def play_round(self):
        cfg = self.session.config
        if self.round_number == 1:
            yield Instrucciones, dict(nombre_empresa=f'Bot {self.player.id_in_group}')

        if self.round_number > num_rondas(self.session):
            return

        yield Decision, dict(
            precio=round(random.uniform(cfg['precio_min'], cfg['precio_max']), 2),
            publicidad=round(random.uniform(0, cfg['publicidad_max'])),
        )
        expect(self.player.unidades, '>=', 0)
        yield Resultados

        if self.round_number == num_rondas(self.session):
            # La página final no tiene botón "Siguiente" (es la última).
            yield Submission(ResultadoFinal, check_html=False)
