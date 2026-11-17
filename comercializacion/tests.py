"""
Bots de prueba: recorren todas las páginas con decisiones aleatorias y
compras de estudios al azar.
Ejecutar con:  otree test comercializacion
"""
import random

from otree.api import Bot, Submission, expect

from . import (Instrucciones, Investigacion, Decision, Resultados, ResultadoFinal,
               num_rondas)


class PlayerBot(Bot):
    def play_round(self):
        cfg = self.session.config
        if self.round_number == 1:
            yield Instrucciones, dict(nombre_empresa=f'Bot {self.player.id_in_group}')

        if self.round_number > num_rondas(self.session):
            return

        compras = dict(compra_pronostico=random.random() < 0.5)
        if self.round_number > 1:
            compras.update(compra_competencia=random.random() < 0.5,
                           compra_sensibilidad=random.random() < 0.5)
        # Las casillas están escritas a mano en la plantilla.
        yield Submission(Investigacion, {k: v for k, v in compras.items() if v}, check_html=False)

        if compras.get('compra_pronostico'):
            expect(self.player.pronostico, '>', 0)
        yield Decision, self.decision(cfg)

        expect(self.player.unidades, '>=', 0)
        expect(self.player.stock_final, '>=', 0)
        expect(abs(self.player.stock_inicial + self.player.produccion
                   - self.player.unidades - self.player.stock_final), '<', 1e-6)
        yield Resultados

        if self.round_number == num_rondas(self.session):
            expect(self.player.baja_stock, '>=', 0)
            # La página final no tiene botón "Siguiente" (es la última).
            yield Submission(ResultadoFinal, check_html=False)

    def decision(self, cfg):
        return dict(
            precio=round(random.uniform(1500, 3500), 2),
            publicidad=round(random.uniform(0, 5_000_000)),
            produccion=random.randint(5000, int(cfg['capacidad'])),
        )
