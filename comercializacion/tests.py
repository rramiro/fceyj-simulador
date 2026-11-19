"""
Bots de prueba: recorren todas las páginas con decisiones aleatorias y
compras de estudios al azar.
Ejecutar con:  otree test comercializacion
"""
import json
import random

from otree.api import Bot, Submission, expect

from . import (Instrucciones, Investigacion, Decision, Resultados, ResultadoFinal,
               mercado, num_rondas)


class PlayerBot(Bot):
    def play_round(self):
        cfg = self.session.config
        if self.round_number == 1:
            # Mercados repartidos parejos según el tamaño objetivo de la configuración.
            tamanos = sorted((len(g.get_players()) for g in self.subsession.get_groups()), reverse=True)
            esperado = mercado.repartir_mercados(len(self.subsession.get_players()), cfg['empresas_por_mercado'])
            expect(tamanos, esperado)
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
        yield Decision, self.decision(cfg, self.group.indice)

        expect(self.player.unidades, '>=', 0)
        expect(self.player.stock_final, '>=', 0)
        expect(abs(self.player.stock_inicial + self.player.produccion
                   - self.player.unidades - self.player.stock_final), '<', 1e-6)
        # Valor del stock: lo que había + lo producido = costo de ventas + valor final (PPP).
        costo_produccion = self.player.produccion * cfg['costo_variable'] * self.group.indice
        expect(abs(self.player.valor_stock_inicial + costo_produccion
                   - self.player.costo_ventas - self.player.valor_stock_final), '<', 1e-3)
        # El tablero del docente: tiene que existir y ser JSON (lo lee la API REST).
        tablero = self.participant.vars['tablero']
        json.dumps(tablero)
        expect(tablero['version'], 2)
        expect(tablero['etapa'], 'resultados')
        expect(tablero['ronda']['actual'], self.round_number)
        expect(len(tablero['historial']['filas']), self.round_number)
        claves = [c['clave'] for c in tablero['historial']['columnas']]
        expect(all(set(f) == set(claves) for f in tablero['historial']['filas']), True)
        expect(len(tablero['devolucion']), '>', 0)
        yield Resultados

        if self.round_number == num_rondas(self.session):
            expect(self.player.baja_stock, '>=', 0)
            # La página final no tiene botón "Siguiente" (es la última).
            yield Submission(ResultadoFinal, check_html=False)

    def decision(self, cfg, indice):
        # Decisiones en términos reales, expresadas en pesos del trimestre.
        return dict(
            precio=round(random.uniform(1500, 3500) * indice, 2),
            publicidad=round(random.uniform(0, 5_000_000) * indice),
            produccion=random.randint(5000, int(cfg['capacidad'])),
        )
