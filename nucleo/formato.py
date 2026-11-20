"""Formato de números al estilo argentino (punto de miles, coma decimal)."""


def numero(x, decimales=0):
    """1234567.891 -> '1.234.567,89' (con decimales=2)."""
    return f'{x:,.{decimales}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def pesos(x, decimales=0):
    """Formatea un número como pesos: $ 1.234.567,89 (o -$ 1.234 si es negativo)."""
    # Lo que redondea a cero se muestra sin signo (no "-$ 0").
    return ('-$ ' if round(x, decimales) < 0 else '$ ') + numero(abs(x), decimales)


def porcentaje(x, decimales=1):
    """0.1234 -> '12,3 %'."""
    return numero(100 * x, decimales) + ' %'
