/*
 * Gráficos simples en SVG, sin bibliotecas externas (funcionan sin internet).
 *
 *   Graficos.lineas(elemento, {etiquetas, series, formato, cero})
 *   Graficos.barras(elemento, {etiquetas, valores, formato, linea})
 *
 * series: [{nombre, valores (null = sin dato), color, ancho, punteada, solo_puntos}]
 * formato: función que convierte un número en texto (para ejes y valores).
 */
(function () {
    'use strict';

    var NS = 'http://www.w3.org/2000/svg';
    // El ancho se toma del contenedor en cada dibujo, así el texto se ve a tamaño real.
    var ANCHO = 560, ALTO = 260;
    var dibujados = [];  // para redibujar al cambiar el tamaño de la ventana

    function medir(contenedor) {
        ANCHO = Math.max(300, Math.round(contenedor.clientWidth || 560));
    }

    function recordar(fn, contenedor, cfg) {
        if (!dibujados.some(function (d) { return d[1] === contenedor; })) {
            dibujados.push([fn, contenedor, cfg]);
        }
    }

    var espera;
    window.addEventListener('resize', function () {
        clearTimeout(espera);
        espera = setTimeout(function () {
            dibujados.forEach(function (d) { d[0](d[1], d[2]); });
        }, 150);
    });
    var M = {izq: 78, der: 16, arr: 14, abj: 30};

    function nodo(tag, attrs, padre) {
        var el = document.createElementNS(NS, tag);
        for (var k in attrs) { el.setAttribute(k, attrs[k]); }
        if (padre) { padre.appendChild(el); }
        return el;
    }

    function texto(padre, x, y, contenido, attrs) {
        var t = nodo('text', Object.assign({x: x, y: y}, attrs || {}), padre);
        t.textContent = contenido;
        return t;
    }

    function titulo(el, contenido) {  // tooltip nativo
        var t = nodo('title', {}, el);
        t.textContent = contenido;
    }

    /* Escala "linda": devuelve [min, max, paso] con 4-5 divisiones redondas. */
    function escala(min, max, incluirCero) {
        if (incluirCero) { min = Math.min(0, min); max = Math.max(0, max); }
        if (min === max) { max = min + 1; }
        var rango = max - min;
        var paso = Math.pow(10, Math.floor(Math.log10(rango / 4)));
        var mult = [1, 2, 2.5, 5, 10];
        for (var i = 0; i < mult.length; i++) {
            if (rango / (paso * mult[i]) <= 5) { paso *= mult[i]; break; }
        }
        return [Math.floor(min / paso) * paso, Math.ceil(max / paso) * paso, paso];
    }

    function lienzo(contenedor) {
        contenedor.innerHTML = '';
        var svg = nodo('svg', {
            viewBox: '0 0 ' + ANCHO + ' ' + ALTO, role: 'img',
            'class': 'grafico-svg', preserveAspectRatio: 'xMidYMid meet'
        });
        contenedor.appendChild(svg);
        return svg;
    }

    function ejes(svg, etiquetas, lim, formato, xPos) {
        var y = function (v) { return M.arr + (ALTO - M.arr - M.abj) * (lim[1] - v) / (lim[1] - lim[0]); };
        for (var v = lim[0]; v <= lim[1] + lim[2] / 2; v += lim[2]) {
            var yy = y(v);
            nodo('line', {x1: M.izq, x2: ANCHO - M.der, y1: yy, y2: yy,
                          'class': Math.abs(v) < lim[2] / 1e6 ? 'eje-cero' : 'grilla'}, svg);
            texto(svg, M.izq - 8, yy + 4, formato(v), {'class': 'eje-texto', 'text-anchor': 'end'});
        }
        etiquetas.forEach(function (e, i) {
            texto(svg, xPos(i), ALTO - 8, e, {'class': 'eje-texto', 'text-anchor': 'middle'});
        });
        return y;
    }

    function leyenda(contenedor, series) {
        var div = document.createElement('div');
        div.className = 'grafico-leyenda';
        series.forEach(function (s) {
            var item = document.createElement('span');
            var marca = document.createElement('i');
            marca.style.background = s.color;
            if (s.punteada) { marca.className = 'punteada'; marca.style.background = 'none'; marca.style.borderColor = s.color; }
            if (s.solo_puntos) { marca.className = 'punto'; }
            item.appendChild(marca);
            item.appendChild(document.createTextNode(s.nombre));
            div.appendChild(item);
        });
        contenedor.appendChild(div);
    }

    function lineas(contenedor, cfg) {
        var formato = cfg.formato || String;
        var n = cfg.etiquetas.length;
        var todos = [];
        cfg.series.forEach(function (s) { s.valores.forEach(function (v) { if (v !== null) { todos.push(v); } }); });
        if (!todos.length) { return; }
        recordar(lineas, contenedor, cfg);
        medir(contenedor);
        var lim = escala(Math.min.apply(null, todos), Math.max.apply(null, todos), cfg.cero);
        var svg = lienzo(contenedor);
        var xPos = function (i) {
            return n === 1 ? (M.izq + ANCHO - M.der) / 2 : M.izq + 20 + (ANCHO - M.izq - M.der - 40) * i / (n - 1);
        };
        var y = ejes(svg, cfg.etiquetas, lim, formato, xPos);

        cfg.series.forEach(function (s) {
            var puntos = [];
            s.valores.forEach(function (v, i) { if (v !== null) { puntos.push([xPos(i), y(v), v, i]); } });
            if (!s.solo_puntos && puntos.length > 1) {
                nodo('polyline', {
                    points: puntos.map(function (p) { return p[0] + ',' + p[1]; }).join(' '),
                    fill: 'none', stroke: s.color, 'stroke-width': s.ancho || 2,
                    'stroke-dasharray': s.punteada ? '6 4' : 'none', 'stroke-linejoin': 'round'
                }, svg);
            }
            puntos.forEach(function (p) {
                var c = nodo('circle', {cx: p[0], cy: p[1], r: s.solo_puntos ? 5 : (s.ancho > 2 ? 4.5 : 3.5),
                                        fill: s.solo_puntos ? '#fff' : s.color, stroke: s.color, 'stroke-width': 2}, svg);
                titulo(c, s.nombre + ' — ' + cfg.etiquetas[p[3]] + ': ' + formato(p[2]));
            });
        });
        leyenda(contenedor, cfg.series);
    }

    function barras(contenedor, cfg) {
        var formato = cfg.formato || String;
        var n = cfg.etiquetas.length;
        var todos = cfg.valores.slice();
        if (cfg.linea) { todos = todos.concat(cfg.linea.valores); }
        recordar(barras, contenedor, cfg);
        medir(contenedor);
        var lim = escala(Math.min.apply(null, todos), Math.max.apply(null, todos), true);
        var svg = lienzo(contenedor);
        var ancho = (ANCHO - M.izq - M.der) / n;
        var xPos = function (i) { return M.izq + ancho * (i + 0.5); };
        var y = ejes(svg, cfg.etiquetas, lim, formato, xPos);
        var barra = Math.min(46, ancho * 0.55);

        cfg.valores.forEach(function (v, i) {
            var y0 = y(0), y1 = y(v);
            var r = nodo('rect', {
                x: xPos(i) - barra / 2, y: Math.min(y0, y1), width: barra,
                height: Math.max(1, Math.abs(y1 - y0)), rx: 3,
                'class': v < 0 ? 'barra-negativa' : 'barra-positiva'
            }, svg);
            titulo(r, cfg.nombre + ' — ' + cfg.etiquetas[i] + ': ' + formato(v));
        });
        var series = [{nombre: cfg.nombre, color: getComputedStyle(document.documentElement).getPropertyValue('--fceyj-azul') || '#4C84C3'}];
        if (cfg.linea) {
            var l = cfg.linea;
            var pts = l.valores.map(function (v, i) { return [xPos(i), y(v), v, i]; });
            if (pts.length > 1) {
                nodo('polyline', {points: pts.map(function (p) { return p[0] + ',' + p[1]; }).join(' '),
                                  fill: 'none', stroke: l.color, 'stroke-width': 2.5}, svg);
            }
            pts.forEach(function (p) {
                var c = nodo('circle', {cx: p[0], cy: p[1], r: 4.5, fill: l.color}, svg);
                titulo(c, l.nombre + ' — ' + cfg.etiquetas[p[3]] + ': ' + formato(p[2]));
            });
            series.push({nombre: l.nombre, color: l.color});
        }
        leyenda(contenedor, series);
    }

    /* Formatos al estilo argentino. */
    function miles(x, dec) {
        return Math.abs(x).toFixed(dec || 0).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }
    var formatos = {
        pesos: function (x) { return (x < 0 ? '-$ ' : '$ ') + miles(x); },
        millones: function (x) {
            var m = x / 1e6;
            return (m < 0 ? '-$ ' : '$ ') + miles(m, Math.abs(m) < 10 && m % 1 ? 1 : 0) + ' M';
        },
        porcentaje: function (x) { return miles(x * 100, 0) + ' %'; }
    };

    window.Graficos = {lineas: lineas, barras: barras, formatos: formatos};
})();
