/*
 * Gráficos del juego "La canasta de Soledad", en SVG y sin bibliotecas.
 *
 *   Canasta.mapa(svg, cfg, {campo})       curvas de indiferencia y recta de presupuesto.
 *       cfg: {a, sigma, ingreso, px, py, x_max, y_max, niveles, x_marcado, x_opt, u_opt}
 *       campo: input de las entradas; al cambiarlo se mueve la canasta (página de decisión).
 *   Canasta.puntos(svg, {series, ejeX, ejeY, fmtY})   curvas punto a punto (demanda, Engel).
 *       series: [{nombre, color, puntos: [[x, y], ...], punteada}]
 */
(function () {
    'use strict';
    var NS = 'http://www.w3.org/2000/svg';
    var AZUL = '#0b5cad', ROJO = '#c62828', VERDE = '#2e7d32', GRIS = '#9aa4b1', TEXTO = '#5f6b7a';

    function nodo(svg, tag, attrs, contenido) {
        var e = document.createElementNS(NS, tag);
        for (var k in attrs) { e.setAttribute(k, attrs[k]); }
        if (contenido !== undefined) { e.textContent = contenido; }
        svg.appendChild(e);
        return e;
    }

    function pasoLindo(max) {
        var crudo = max / 5, p = Math.pow(10, Math.floor(Math.log10(crudo)));
        var n = crudo / p;
        return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
    }

    function utilidad(x, y, a, s) {
        if (x <= 0 || y <= 0) { return 0; }
        if (Math.abs(s - 1) < 1e-12) { return Math.pow(x, a) * Math.pow(y, 1 - a); }
        var r = (s - 1) / s;
        return Math.pow(a * Math.pow(x, r) + (1 - a) * Math.pow(y, r), 1 / r);
    }

    function yIndiferencia(x, u, a, s) {
        if (x <= 0) { return null; }
        if (Math.abs(s - 1) < 1e-12) { return Math.pow(u / Math.pow(x, a), 1 / (1 - a)); }
        var r = (s - 1) / s, resto = Math.pow(u, r) - a * Math.pow(x, r);
        if (resto <= 0) { return null; }
        return Math.pow(resto / (1 - a), 1 / r);
    }

    function ejes(svg, maxX, maxY, rotX, rotY) {
        var M = {izq: 46, der: 14, arr: 12, abj: 40}, W = 560, H = 360;
        var px = function (v) { return M.izq + (W - M.izq - M.der) * v / maxX; };
        var py = function (v) { return H - M.abj - (H - M.arr - M.abj) * v / maxY; };
        var sx = pasoLindo(maxX), sy = pasoLindo(maxY), v;
        for (v = 0; v <= maxY + 1e-9; v += sy) {
            nodo(svg, 'line', {x1: px(0), x2: px(maxX), y1: py(v), y2: py(v), stroke: '#eceff2'});
            nodo(svg, 'text', {x: px(0) - 6, y: py(v) + 4, 'text-anchor': 'end', 'font-size': 11, fill: TEXTO},
                 rotY.fmt ? rotY.fmt(v) : +v.toFixed(2));
        }
        for (v = 0; v <= maxX + 1e-9; v += sx) {
            nodo(svg, 'line', {x1: px(v), x2: px(v), y1: py(0), y2: py(maxY), stroke: '#f3f5f7'});
            nodo(svg, 'text', {x: px(v), y: py(0) + 15, 'text-anchor': 'middle', 'font-size': 11, fill: TEXTO},
                 rotX.fmt ? rotX.fmt(v) : +v.toFixed(2));
        }
        nodo(svg, 'line', {x1: px(0), x2: px(maxX), y1: py(0), y2: py(0), stroke: GRIS});
        nodo(svg, 'line', {x1: px(0), x2: px(0), y1: py(0), y2: py(maxY), stroke: GRIS});
        nodo(svg, 'text', {x: px(maxX), y: H - 6, 'text-anchor': 'end', 'font-size': 12, fill: '#3d4752'}, rotX.texto);
        nodo(svg, 'text', {x: px(0) + 4, y: M.arr + 10, 'font-size': 12, fill: '#3d4752'}, rotY.texto);
        return {px: px, py: py};
    }

    function camino(fx, fy, puntos) {
        return puntos.map(function (p, i) { return (i ? 'L' : 'M') + fx(p[0]).toFixed(1) + ',' + fy(p[1]).toFixed(1); }).join(' ');
    }

    function curva(svg, e, u, cfg, maxX, maxY, attrs) {
        var pts = [], n = 240;
        for (var i = 1; i <= n; i++) {
            var x = maxX * i / n, y = yIndiferencia(x, u, cfg.a, cfg.sigma);
            if (y === null || !isFinite(y)) { continue; }
            if (y > maxY * 1.05) { continue; }
            pts.push([x, y]);
        }
        if (pts.length > 1) { nodo(svg, 'path', Object.assign({d: camino(e.px, e.py, pts), fill: 'none'}, attrs)); }
    }

    var Canasta = {};

    Canasta.mapa = function (svg, cfg, opciones) {
        opciones = opciones || {};
        var maxX = Math.max(cfg.x_max * 1.15, cfg.x_max + 1), maxY = cfg.y_max * 1.15;
        function dibujar() {
            while (svg.firstChild) { svg.removeChild(svg.firstChild); }
            var e = ejes(svg, maxX, maxY, {texto: 'X: entradas al cine'}, {texto: 'Y: canastas de alimentos'});
            // Curvas de indiferencia de referencia.
            cfg.niveles.forEach(function (u) { curva(svg, e, u, cfg, maxX, maxY, {stroke: '#b9c3ce', 'stroke-width': 1.2}); });
            // Recta de presupuesto.
            nodo(svg, 'line', {x1: e.px(0), y1: e.py(cfg.ingreso / cfg.py), x2: e.px(cfg.ingreso / cfg.px), y2: e.py(0),
                               stroke: '#3d4752', 'stroke-width': 2});
            // Canastas posibles (entradas enteras sobre la recta).
            for (var x = 0; x <= cfg.x_max; x++) {
                nodo(svg, 'circle', {cx: e.px(x), cy: e.py((cfg.ingreso - cfg.px * x) / cfg.py), r: 2.5, fill: '#3d4752'});
            }
            if (cfg.x_opt !== null && cfg.x_opt !== undefined) {
                var yo = (cfg.ingreso - cfg.px * cfg.x_opt) / cfg.py;
                curva(svg, e, cfg.u_opt, cfg, maxX, maxY, {stroke: VERDE, 'stroke-width': 2});
                nodo(svg, 'circle', {cx: e.px(cfg.x_opt), cy: e.py(yo), r: 7, fill: VERDE});
                nodo(svg, 'text', {x: e.px(cfg.x_opt) + 10, y: e.py(yo) + 16, 'font-size': 12, fill: VERDE,
                                   stroke: '#fff', 'stroke-width': 3, 'paint-order': 'stroke'}, 'óptima');
            }
            var xm = cfg.x_marcado;
            if (opciones.campo && opciones.campo.value !== '') { xm = parseInt(opciones.campo.value, 10); }
            if (xm !== null && xm !== undefined && !isNaN(xm) && xm >= 0 && xm <= cfg.x_max) {
                var ym = (cfg.ingreso - cfg.px * xm) / cfg.py, um = utilidad(xm, ym, cfg.a, cfg.sigma);
                if (um > 0) { curva(svg, e, um, cfg, maxX, maxY, {stroke: AZUL, 'stroke-width': 2, 'stroke-dasharray': '6 4'}); }
                nodo(svg, 'circle', {cx: e.px(xm), cy: e.py(ym), r: 6, fill: AZUL});
                nodo(svg, 'text', {x: e.px(xm) + 10, y: e.py(ym) - 8, 'font-size': 12, fill: AZUL, stroke: '#fff',
                                   'stroke-width': 3, 'paint-order': 'stroke'},
                     opciones.campo ? 'su canasta' : 'la de ustedes');
            }
        }
        dibujar();
        if (opciones.campo) { opciones.campo.addEventListener('input', dibujar); }
    };

    Canasta.puntos = function (svg, cfg) {
        var maxX = 1, maxY = 1;
        cfg.series.forEach(function (s) { s.puntos.forEach(function (p) { maxX = Math.max(maxX, p[0]); maxY = Math.max(maxY, p[1]); }); });
        maxX *= 1.15; maxY *= 1.15;
        var e = ejes(svg, maxX, maxY, {texto: cfg.ejeX}, {texto: cfg.ejeY, fmt: cfg.fmtY});
        cfg.series.forEach(function (s, k) {
            var pts = s.puntos.slice().sort(function (p, q) { return p[1] - q[1]; });
            nodo(svg, 'path', {d: camino(e.px, e.py, pts), fill: 'none', stroke: s.color, 'stroke-width': 2,
                               'stroke-dasharray': s.punteada ? '6 4' : ''});
            pts.forEach(function (p) { nodo(svg, 'circle', {cx: e.px(p[0]), cy: e.py(p[1]), r: 4, fill: s.color}); });
            nodo(svg, 'text', {x: 560 - 16, y: 26 + 16 * k, 'text-anchor': 'end', 'font-size': 12, fill: s.color}, '■ ' + s.nombre);
        });
    };

    Canasta.miles = function (v) { return '$' + Math.round(v / 1000) + ' mil'; };
    Canasta.AZUL = AZUL; Canasta.VERDE = VERDE; Canasta.ROJO = ROJO;
    window.Canasta = Canasta;
})();
