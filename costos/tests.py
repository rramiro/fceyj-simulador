"""
Bots de prueba: recorren los meses con planes razonables y decisiones al azar.
Ejecutar con:  otree test costos
"""
import json
import random

from otree.api import Bot, Submission, SubmissionMustFail, expect

from . import (Decision, Instrucciones, ResultadoFinal, Resultados, EVENTOS_SI_NO, es_ultima_ronda, escenario,
               estado, evento_del_mes, modelo, num_rondas, parametros)


class PlayerBot(Bot):
    def play_round(self):
        if self.round_number == 1:
            expect(len(self.subsession.get_groups()), 1)
            yield Instrucciones, dict(nombre_equipo=f'Bot {self.player.id_in_group}')
        if self.round_number > num_rondas(self.session):
            return

        p = parametros(self.session)
        esc = escenario(self.session)
        est = estado(self.player)
        tipo = evento_del_mes(self.player)
        mes = self.round_number

        # Un plan que se pasa de la capacidad se rechaza.
        exceso = {}
        for l in est['lineas']:
            exceso.update({f'precio_{l}': modelo.LINEAS[l]['precio_ref'], f'prod_{l}': 5000})
        if tipo in EVENTOS_SI_NO:
            exceso['evento_si'] = False
        elif tipo == 'bordado':
            exceso['bordado_pct'] = 0
        yield SubmissionMustFail(Decision, exceso, check_html=False)

        # Plan razonable: precio de referencia ± 10 % y producción ≈ demanda prevista, dentro de la capacidad.
        datos = {}
        prod = {}
        for l in est['lineas']:
            precio = round(modelo.LINEAS[l]['precio_ref'] * random.uniform(0.9, 1.1))
            q = modelo.demanda_prevista(l, mes, est, p, esc) * (precio / modelo.LINEAS[l]['precio_ref']) ** (-modelo.LINEAS[l]['elasticidad'])
            prod[l] = max(0, int(q - est['stock'][l]))
            datos[f'precio_{l}'] = precio
        acepta = random.random() < 0.5
        for _ in range(60):
            if modelo.validar_produccion(prod, est, p, esc, pedido=(tipo == 'pedido_especial' and acepta)) is None:
                break
            prod = {l: int(q * 0.95) for l, q in prod.items()}
        datos.update({f'prod_{l}': q for l, q in prod.items()})
        if tipo in EVENTOS_SI_NO:
            datos['evento_si'] = acepta
        elif tipo == 'bordado':
            datos['bordado_pct'] = random.choice([0, 20, 50])
        _, correcto, _ = modelo.informe_correcto(tipo, None, mes, est, p, esc)
        if correcto is not None and random.random() < 0.5:
            datos['informe'] = round(correcto, 2)
        yield Submission(Decision, datos, check_html=False)

        # Lo guardado coincide con el modelo y el tablero es JSON con el formato común.
        r = self.participant.vars['meses_costos'][-1]
        expect(abs(r['resultado_var'] - self.player.resultado_var), '<', 1e-6)
        expect(abs(self.participant.vars['estado_costos']['resultado_var'] - self.player.acumulado_var), '<', 1e-6)
        if correcto is not None and 'informe' in datos:
            expect(r['informe']['acierto'], True)
        tablero = self.participant.vars['tablero']
        json.dumps(tablero)
        expect(tablero['version'], 2)
        expect(tablero['juego'], 'costos')
        expect(len(tablero['historial']['filas']), mes)
        expect(len(tablero['devolucion']), '>', 0)
        yield Resultados

        if es_ultima_ronda(self.player):
            yield Submission(ResultadoFinal, check_html=False)
