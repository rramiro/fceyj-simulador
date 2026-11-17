/*
 * Tablero docente del simulador.
 *
 * Lee el estado de cada equipo con la API REST de oTree:
 *   GET  /api/sessions                    sesiones (no incluye las de demo)
 *   POST /api/get_session/<código>        participantes + participant.vars pedidos
 *   POST /api/participant_vars/<código>   guarda el comentario del docente
 *
 * El juego guarda el estado de cada equipo en participant.vars['tablero'].
 * En el servidor, Caddy protege esta página y /api/ con contraseña y agrega la
 * clave REST que pide oTree (ver deploy/proxy/Caddyfile).
 *
 * Todo texto que viene de los equipos (por ejemplo, el nombre de la empresa)
 * se inserta como texto, nunca como HTML.
 */
(function () {
    'use strict';

    var INTERVALO = 10000;  // actualización automática (ms)
    var VARS = ['tablero', 'comentario_docente'];

    var estado = {codigo: null, datos: null, abierto: null, temporizador: null, borrador: false};

    // ---------------------------------------------------------------- utilidades
    var $ = function (id) { return document.getElementById(id); };
    var nf0 = new Intl.NumberFormat('es-AR', {maximumFractionDigits: 0});
    var nf2 = new Intl.NumberFormat('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    function pesos(x, dec) { return x == null ? '—' : (x < 0 ? '-$ ' : '$ ') + (dec ? nf2 : nf0).format(Math.abs(x)); }
    function numero(x) { return x == null ? '—' : nf0.format(x); }
    function pct(x) { return x == null ? '—' : nf0.format(x * 100) + ' %'; }

    /* Crea un elemento. hijos: texto o nodos (el texto siempre como texto, nunca HTML). */
    function el(tag, attrs, hijos) {
        var e = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                if (k === 'class') { e.className = attrs[k]; }
                else if (k.slice(0, 2) === 'on') { e.addEventListener(k.slice(2), attrs[k]); }
                else { e.setAttribute(k, attrs[k]); }
            });
        }
        [].concat(hijos == null ? [] : hijos).forEach(function (h) {
            if (h == null) { return; }
            e.appendChild(typeof h === 'string' || typeof h === 'number' ? document.createTextNode(String(h)) : h);
        });
        return e;
    }

    function vaciar(nodo) { while (nodo.firstChild) { nodo.removeChild(nodo.firstChild); } }

    function mostrarError(texto) {
        var e = $('error');
        if (texto) { e.textContent = texto; e.hidden = false; } else { e.hidden = true; }
    }

    function api(ruta, cuerpo) {
        var opciones = cuerpo === undefined ? {method: 'GET'}
            : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cuerpo)};
        opciones.credentials = 'same-origin';
        return fetch(ruta, opciones).then(function (r) {
            if (!r.ok) {
                return r.text().then(function (t) {
                    var msg = r.status === 403
                        ? 'oTree rechazó el acceso a su API (' + t + '). En el servidor, el acceso se habilita a través del proxy; ver DESPLIEGUE.md.'
                        : r.status === 404 ? 'No se encontró la sesión.' : 'Error ' + r.status + ': ' + t;
                    throw new Error(msg);
                });
            }
            return r.json();
        });
    }

    // ----------------------------------------------------------------- estados
    var ETAPAS = {
        'Instrucciones': ['decidiendo', 'Leyendo instrucciones'],
        'Investigación de mercado': ['decidiendo', 'Investigación'],
        'Decisión': ['decidiendo', 'Decidiendo'],
        'Esperando a las demás empresas': ['esperando', 'Decisión enviada'],
        'Resultados listos': ['resultados', 'Resultados listos'],
        'Viendo resultados': ['resultados', 'Viendo resultados'],
        'Terminó': ['termino', 'Terminó']
    };

    function etapa(t) {
        if (!t) { return {clase: 'sin-ingresar', texto: 'Sin ingresar'}; }
        var e = ETAPAS[t.pagina] || ['decidiendo', t.pagina];
        var texto = e[0] === 'termino' ? e[1] : 'T' + t.trimestre + ' · ' + e[1];
        return {clase: e[0], texto: texto};
    }

    function ultimo(t) { return t && t.historial && t.historial.length ? t.historial[t.historial.length - 1] : null; }

    // ----------------------------------------------------- enlaces de los equipos
    // El enlace personal lleva al equipo a la pantalla donde quedó, desde cualquier dispositivo.
    // Sirve para mandárselo si se les cerró el navegador o cambiaron de computadora.
    function enlaceEquipo(codigo) { return location.origin + '/InitializeParticipant/' + codigo; }

    var temporizadorAviso;
    function avisar(texto) {
        var a = $('aviso-copia');
        a.textContent = texto;
        a.hidden = false;
        clearTimeout(temporizadorAviso);
        temporizadorAviso = setTimeout(function () { a.hidden = true; }, 2500);
    }

    function copiarEnlace(codigo, nombre) {
        var url = enlaceEquipo(codigo);
        var listo = function () { avisar('Enlace de ' + nombre + ' copiado'); };
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(url).then(listo, function () { window.prompt('Copiar el enlace de ' + nombre + ':', url); });
        } else {
            window.prompt('Copiar el enlace de ' + nombre + ':', url);
        }
    }

    /* Botón "Copiar enlace" que no abre el detalle del equipo (la fila es clickeable). */
    function botonEnlace(codigo, nombre) {
        var detener = function (ev) { ev.stopPropagation(); };
        return el('button', {
            class: 'boton-enlace', type: 'button',
            title: 'Copiar el enlace de ' + nombre, 'aria-label': 'Copiar el enlace de ' + nombre,
            onclick: function (ev) { ev.stopPropagation(); copiarEnlace(codigo, nombre); },
            onkeydown: detener
        }, 'Copiar enlace');
    }

    // --------------------------------------------------------------- sesiones
    function cargarSesiones() {
        var lista = $('lista-sesiones');
        api('/api/sessions').then(function (sesiones) {
            vaciar(lista);
            sesiones = sesiones.filter(function (s) { return s.config_name === 'comercializacion'; }).reverse();
            if (!sesiones.length) {
                lista.appendChild(el('p', {class: 'nota'},
                    'No hay sesiones del simulador. Créelas desde el aula o el panel de oTree. ' +
                    '(Las partidas de prueba de "Demo" no aparecen en la lista: abra su código con el formulario.)'));
                return;
            }
            sesiones.forEach(function (s) {
                var fecha = s.created_at ? new Date(s.created_at * 1000).toLocaleString('es-AR', {dateStyle: 'short', timeStyle: 'short'}) : '';
                lista.appendChild(el('button', {class: 'tarjeta-sesion', type: 'button', onclick: function () { abrirSesion(s.code); }}, [
                    el('b', null, s.label || s.code),
                    el('span', {class: 'nota'}, [s.num_participants + ' equipos · ' + fecha, s.label ? ' · ' + s.code : ''])
                ]));
            });
        }).catch(function (e) {
            vaciar(lista);
            lista.appendChild(el('p', {class: 'nota'}, 'No se pudo leer la lista de sesiones.'));
            mostrarError(e.message);
        });
    }

    function abrirSesion(codigo) {
        codigo = (codigo || '').trim();
        if (!codigo) { return; }
        estado.codigo = codigo;
        estado.datos = null;
        estado.firma = null;
        if (location.hash !== '#sesion=' + codigo) { history.replaceState(null, '', '#sesion=' + codigo); }
        $('panel-sesiones').hidden = true;
        $('vista-sesion').hidden = false;
        $('titulo-sesion').textContent = 'Sesión ' + codigo;
        vaciar($('mercados'));
        vaciar($('resumen'));
        actualizar();
        clearInterval(estado.temporizador);
        estado.temporizador = setInterval(function () { if (!document.hidden) { actualizar(); } }, INTERVALO);
    }

    function volver() {
        clearInterval(estado.temporizador);
        estado.codigo = null;
        cerrarDetalle();
        history.replaceState(null, '', location.pathname);
        $('vista-sesion').hidden = true;
        $('panel-sesiones').hidden = false;
        mostrarError(null);
        cargarSesiones();
    }

    function actualizar() {
        var codigo = estado.codigo;
        if (!codigo) { return; }
        api('/api/get_session/' + encodeURIComponent(codigo), {participant_vars: VARS}).then(function (datos) {
            if (codigo !== estado.codigo) { return; }
            mostrarError(null);
            $('actualizado').textContent = 'Actualizado ' + new Date().toLocaleTimeString('es-AR');
            // Solo se redibuja si algo cambió: así no se pierden clics ni el foco del teclado.
            var firma = JSON.stringify(datos.participants);
            if (firma === estado.firma) { return; }
            estado.firma = firma;
            estado.datos = datos;
            if (datos.label) { $('titulo-sesion').textContent = datos.label + ' (' + codigo + ')'; }
            dibujarSesion();
            if (estado.abierto) { dibujarDetalle(false); }
        }).catch(function (e) { mostrarError(e.message); });
    }

    // ------------------------------------------------------------ vista sesión
    function dibujarSesion() {
        var participantes = estado.datos.participants || [];
        var mercados = {}, sinIngresar = [];
        participantes.forEach(function (p) {
            if (p.tablero) { (mercados[p.tablero.mercado] = mercados[p.tablero.mercado] || []).push(p); }
            else { sinIngresar.push(p); }
        });

        // Resumen
        var conTablero = participantes.filter(function (p) { return p.tablero; });
        var terminaron = conTablero.filter(function (p) { return p.tablero.pagina === 'Terminó'; }).length;
        var trimestres = conTablero.map(function (p) { return p.tablero.trimestre; });
        var total = conTablero.length ? conTablero[0].tablero.num_trimestres : null;
        var minT = trimestres.length ? Math.min.apply(null, trimestres) : null;
        var maxT = trimestres.length ? Math.max.apply(null, trimestres) : null;
        var resumen = $('resumen');
        vaciar(resumen);
        [
            [participantes.length, 'equipos en la sesión'],
            [conTablero.length + ' / ' + participantes.length, 'ingresaron'],
            [minT == null ? '—' : (minT === maxT ? 'T' + minT : 'T' + minT + '–T' + maxT) + (total ? ' de ' + total : ''), 'trimestre en curso'],
            [terminaron, 'terminaron el juego']
        ].forEach(function (d) { resumen.appendChild(el('div', {class: 'dato'}, [el('b', null, String(d[0])), el('span', null, d[1])])); });

        // Tamaño de los mercados (por si algún tablero viejo no lo informa).
        estado.tamMercado = Math.max.apply(null, [0].concat(Object.keys(mercados).map(function (m) {
            return mercados[m][0].tablero.empresas_por_mercado || mercados[m].length;
        })));

        // Mercados
        var contenedor = $('mercados');
        vaciar(contenedor);
        Object.keys(mercados).sort(function (a, b) { return a - b; }).forEach(function (m) {
            contenedor.appendChild(dibujarMercado(m, mercados[m]));
        });
        if (sinIngresar.length) {
            sinIngresar.sort(function (a, b) { return a.id_in_session - b.id_in_session; });
            contenedor.appendChild(el('div', {class: 'mercado'}, [
                el('div', {class: 'mercado-cabecera'}, el('h2', null, 'Todavía no ingresaron')),
                el('p', {class: 'nota'}, sinIngresar.length + ' lugar' + (sinIngresar.length > 1 ? 'es' : '') +
                    ' de la sesión sin usar. Si la sesión tiene más lugares que equipos, los mercados ' +
                    'incompletos no avanzan: conviene crearla con la cantidad exacta de equipos. ' +
                    'Un equipo que no pueda entrar por el enlace del aula puede usar el enlace de un lugar libre.'),
                el('div', {class: 'tabla-desplazable'}, el('table', {class: 'tabla'}, [
                    el('thead', null, el('tr', null, [el('th', null, 'Lugar'), el('th', null, 'Enlace')])),
                    el('tbody', null, sinIngresar.map(function (p) {
                        var nombre = 'Lugar ' + p.id_in_session + (p.label ? ' (' + p.label + ')' : '');
                        return el('tr', null, [el('td', null, nombre), el('td', null, botonEnlace(p.code, nombre))]);
                    }))
                ]))
            ]));
        }
    }

    function dibujarMercado(numeroMercado, equipos) {
        equipos.sort(function (a, b) { return a.tablero.id_en_mercado - b.tablero.id_en_mercado; });
        var t = Math.max.apply(null, equipos.map(function (p) { return p.tablero.trimestre; }));
        // Si alguien ya envió la decisión del trimestre, los que todavía deciden demoran al mercado.
        var hayEsperando = equipos.some(function (p) { return p.tablero.trimestre === t && p.tablero.pagina === 'Esperando a las demás empresas'; });
        var demoran = equipos.filter(function (p) {
            return hayEsperando && p.tablero.trimestre === t && etapa(p.tablero).clase === 'decidiendo';
        });
        // Equipos del mercado que todavía no abrieron el juego (no tienen tablero).
        var faltan = (equipos[0].tablero.empresas_por_mercado || estado.tamMercado || equipos.length) - equipos.length;

        var filas = equipos.map(function (p) {
            var tab = p.tablero, u = ultimo(tab), e = etapa(tab);
            var demora = demoran.indexOf(p) >= 0;
            return el('tr', {class: 'fila-equipo', tabindex: '0', role: 'button',
                             onclick: function () { abrirDetalle(p.code); },
                             onkeydown: function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abrirDetalle(p.code); } }}, [
                el('td', null, [el('span', {class: 'empresa'}, tab.empresa),
                                p.comentario_docente ? el('span', {class: 'marca-comentario', title: 'Tiene comentario del docente'}, ' ✎') : null]),
                el('td', null, el('span', {class: 'chip chip-' + (demora ? 'bloquea' : e.clase)}, demora ? e.texto + ' · lo esperan' : e.texto)),
                el('td', {class: 'num'}, u ? pct(u.participacion) : '—'),
                el('td', {class: 'num' + (u && u.resultado_acumulado < 0 ? ' negativo' : '')}, u ? pesos(u.resultado_acumulado) : '—'),
                el('td', {class: 'num'}, tab.puesto ? tab.puesto + '°' : '—'),
                el('td', null, botonEnlace(p.code, tab.empresa))
            ]);
        });

        return el('section', {class: 'mercado'}, [
            el('div', {class: 'mercado-cabecera'}, [
                el('h2', null, 'Mercado ' + numeroMercado),
                el('span', {class: 'nota'}, 'Trimestre ' + t)
            ]),
            demoran.length ? el('p', {class: 'aviso-espera'},
                'El mercado espera a: ' + demoran.map(function (p) { return p.tablero.empresa; }).join(', ') + '.') : null,
            faltan > 0 ? el('p', {class: 'aviso-espera'},
                (faltan === 1 ? 'Falta que ingrese 1 equipo' : 'Faltan que ingresen ' + faltan + ' equipos') +
                ' a este mercado: hasta entonces no avanza.') : null,
            el('div', {class: 'tabla-desplazable'}, el('table', {class: 'tabla'}, [
                el('thead', null, el('tr', null, [
                    el('th', null, 'Empresa'), el('th', null, 'Estado'), el('th', {class: 'num'}, 'Partic.'),
                    el('th', {class: 'num'}, 'Acumulado'), el('th', {class: 'num'}, 'Puesto'), el('th', null, 'Enlace')
                ])),
                el('tbody', null, filas)
            ]))
        ]);
    }

    // ----------------------------------------------------------------- detalle
    function participante(codigo) {
        var lista = (estado.datos && estado.datos.participants) || [];
        for (var i = 0; i < lista.length; i++) { if (lista[i].code === codigo) { return lista[i]; } }
        return null;
    }

    function abrirDetalle(codigo) {
        estado.abierto = codigo;
        estado.borrador = false;
        $('estado-comentario').textContent = '';
        dibujarDetalle(true);
        $('fondo-detalle').hidden = false;
        $('detalle').hidden = false;
        $('cerrar-detalle').focus();
    }

    function cerrarDetalle() {
        if (estado.borrador && !confirm('Hay un comentario sin guardar. ¿Cerrar igual?')) { return; }
        estado.abierto = null;
        estado.borrador = false;
        $('fondo-detalle').hidden = true;
        $('detalle').hidden = true;
    }

    function dibujarDetalle(primeraVez) {
        var p = participante(estado.abierto);
        if (!p || !p.tablero) { return; }
        var tab = p.tablero, e = etapa(tab);
        $('detalle-mercado').textContent = 'Mercado ' + tab.mercado;
        $('detalle-titulo').textContent = tab.empresa;
        var textoEstado = e.texto + (tab.puesto ? ' · puesto ' + tab.puesto + '° en su mercado' : '');
        if (tab.decision && tab.pagina === 'Esperando a las demás empresas') {
            textoEstado += ' · decidió precio ' + pesos(tab.decision.precio, 2) + ', publicidad ' + pesos(tab.decision.publicidad) +
                ', producción ' + numero(tab.decision.produccion) + ' u.' +
                (tab.decision.estudios.length ? ' (estudios: ' + tab.decision.estudios.join(', ') + ')' : '');
        }
        $('detalle-estado').textContent = textoEstado;

        // Enlace personal del equipo
        var enlace = $('detalle-enlace');
        vaciar(enlace);
        enlace.appendChild(el('code', null, enlaceEquipo(p.code)));
        enlace.appendChild(botonEnlace(p.code, tab.empresa));

        // Historial
        var tabla = $('detalle-historial');
        vaciar(tabla);
        var h = tab.historial || [];
        if (!h.length) {
            tabla.appendChild(el('tbody', null, el('tr', null, el('td', null, 'Todavía no hay trimestres con resultados.'))));
        } else {
            var columnas = ['T', 'Precio', 'Precio medio', 'Publicidad', 'Producción', 'Vendidas', 'Faltante', 'Stock final', 'Partic.', 'Resultado', 'Acumulado'];
            tabla.appendChild(el('thead', null, el('tr', null, columnas.map(function (c, i) { return el('th', {class: i ? 'num' : ''}, c); }))));
            tabla.appendChild(el('tbody', null, h.map(function (r) {
                var celdas = [
                    'T' + r.trimestre, pesos(r.precio, 2), pesos(r.precio_medio, 2), pesos(r.publicidad), numero(r.produccion),
                    numero(r.unidades), numero(r.faltante), numero(r.stock_final), pct(r.participacion), pesos(r.resultado), pesos(r.resultado_acumulado)
                ];
                return el('tr', null, celdas.map(function (c, i) {
                    var negativo = (i === 9 && r.resultado < 0) || (i === 10 && r.resultado_acumulado < 0);
                    return el('td', {class: (i ? 'num' : '') + (negativo ? ' negativo' : '')}, c);
                }));
            })));
        }
        $('detalle-nota-historial').textContent = h.length
            ? 'Importes en pesos de cada trimestre; el acumulado está en moneda constante (pesos de su último trimestre).' : '';

        // Devolución
        var dev = $('detalle-devolucion');
        vaciar(dev);
        (tab.devolucion || []).forEach(function (o) {
            dev.appendChild(el('div', {class: 'devolucion-item devolucion-' + o.tipo}, [el('b', null, o.tema), el('span', null, o.texto)]));
        });
        if (!(tab.devolucion || []).length) { dev.appendChild(el('p', {class: 'nota'}, 'Se genera cuando haya resultados.')); }

        // Comentario (no pisar lo que el docente está escribiendo)
        if (primeraVez || !estado.borrador) { $('comentario').value = p.comentario_docente || ''; }
    }

    function guardarComentario() {
        var codigo = estado.abierto, texto = $('comentario').value.trim(), boton = $('guardar-comentario');
        if (!codigo) { return; }
        boton.disabled = true;
        $('estado-comentario').textContent = 'Guardando…';
        api('/api/participant_vars/' + encodeURIComponent(codigo), {vars: {comentario_docente: texto}}).then(function () {
            var p = participante(codigo);
            if (p) { p.comentario_docente = texto; }
            estado.borrador = false;
            $('estado-comentario').textContent = 'Guardado ✓';
            dibujarSesion();
        }).catch(function (e) {
            $('estado-comentario').textContent = 'No se pudo guardar.';
            mostrarError(e.message);
        }).then(function () { boton.disabled = false; });
    }

    // ------------------------------------------------------------------ inicio
    $('form-codigo').addEventListener('submit', function (ev) { ev.preventDefault(); abrirSesion($('codigo').value); });
    $('volver').addEventListener('click', volver);
    $('actualizar').addEventListener('click', actualizar);
    $('cerrar-detalle').addEventListener('click', cerrarDetalle);
    $('fondo-detalle').addEventListener('click', cerrarDetalle);
    $('guardar-comentario').addEventListener('click', guardarComentario);
    $('comentario').addEventListener('input', function () { estado.borrador = true; $('estado-comentario').textContent = 'Sin guardar'; });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && estado.abierto) { cerrarDetalle(); } });

    var m = location.hash.match(/sesion=([\w-]+)/);
    if (m) { abrirSesion(m[1]); } else { cargarSesiones(); }
})();
