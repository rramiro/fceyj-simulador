/*
 * Tablero docente del simulador.
 *
 * Lee el estado de cada equipo con la API REST de oTree:
 *   GET  /api/sessions                    sesiones (no incluye las de demo)
 *   POST /api/get_session/<código>        participantes + participant.vars pedidos
 *   POST /api/participant_vars/<código>   guarda el comentario del docente
 *
 * Cada juego guarda el estado de cada equipo en participant.vars['tablero'], con
 * un formato común a todos los juegos (ver nucleo/tablero.py): el tablero no
 * sabe de qué juego se trata, solo muestra grupos, indicadores e historial.
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
    var nf1 = new Intl.NumberFormat('es-AR', {minimumFractionDigits: 1, maximumFractionDigits: 1});
    var nf2 = new Intl.NumberFormat('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    function pesos(x, dec) { return x == null ? '—' : (x < 0 ? '-$ ' : '$ ') + (dec ? nf2 : nf0).format(Math.abs(x)); }
    function numero(x) { return x == null ? '—' : nf0.format(x); }
    function pct(x) { return x == null ? '—' : nf0.format(x * 100) + ' %'; }

    /* Formatos que declara cada juego en su resumen (nucleo/tablero.py). */
    function formatear(valor, formato, tab) {
        if (valor == null) { return '—'; }
        switch (formato) {
            case 'pesos': return pesos(valor);
            case 'pesos2': return pesos(valor, true);
            case 'numero': return numero(valor);
            case 'pct': return pct(valor);
            case 'pct1': return nf1.format(valor * 100) + ' %';
            case 'ronda': return tab.ronda.abrev + valor;
            default: return String(valor);
        }
    }

    function claseNumero(valor, def) {
        if (def.formato === 'texto') { return ''; }
        return 'num' + (def.signo && valor != null && valor < 0 ? ' negativo' : '');
    }

    function mayuscula(texto) { return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : ''; }

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

    /* Un pedido a la API. X-Tablero es la marca que exige el proxy (ver deploy/proxy/Caddyfile). */
    function pedir(ruta, cuerpo) {
        var opciones = cuerpo === undefined
            ? {method: 'GET', headers: {'X-Tablero': '1'}}
            : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tablero': '1'}, body: JSON.stringify(cuerpo)};
        opciones.credentials = 'same-origin';
        return fetch(ruta, opciones).then(function (r) {
            if (r.status === 401) {
                var e = new Error('Hay que iniciar sesión.');
                e.sinSesion = true;
                throw e;
            }
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

    /* Como pedir(), pero si no hay sesión iniciada muestra la ventana de ingreso y reintenta. */
    function api(ruta, cuerpo) {
        return pedir(ruta, cuerpo).catch(function (e) {
            if (!e.sinSesion) { throw e; }
            return pedirIngreso().then(function () { return pedir(ruta, cuerpo); });
        });
    }

    // ------------------------------------------------------------------ ingreso
    // Se usa el login de oTree (usuario "admin" y la contraseña de administración del
    // ambiente): un solo ingreso sirve para el tablero y para el panel de oTree.
    // Si varios pedidos descubren a la vez que falta la sesión, se abre una sola ventana.
    var ingresoPendiente = null;

    function pedirIngreso() {
        if (!ingresoPendiente) {
            ingresoPendiente = new Promise(function (resolver) {
                var modal = $('modal-ingreso');
                $('ingreso-error').hidden = true;
                $('ingreso-clave').value = '';
                modal._alIngresar = resolver;
                if (!modal.open) { modal.showModal(); }
                ($('ingreso-usuario').value ? $('ingreso-clave') : $('ingreso-usuario')).focus();
            }).then(function () { ingresoPendiente = null; });
        }
        return ingresoPendiente;
    }

    function ingresar(ev) {
        ev.preventDefault();
        var boton = $('ingreso-boton'), error = $('ingreso-error');
        var usuario = $('ingreso-usuario').value.trim(), clave = $('ingreso-clave').value;
        if (!usuario || !clave) { error.textContent = 'Complete el usuario y la contraseña.'; error.hidden = false; return; }
        boton.disabled = true;
        boton.textContent = 'Ingresando…';
        error.hidden = true;
        // El formulario de oTree pide su código anti-falsificación (csrftoken): se lee de su página de login.
        fetch('/login', {credentials: 'same-origin'}).then(function (r) { return r.text(); }).then(function (html) {
            var doc = new DOMParser().parseFromString(html, 'text/html');
            var token = doc.querySelector('input[name="csrftoken"]');
            var datos = new URLSearchParams({username: usuario, password: clave});
            if (token) { datos.set('csrftoken', token.value); }
            return fetch('/login', {method: 'POST', body: datos, credentials: 'same-origin'});
        }).then(function (r) {
            // Si el ingreso es correcto, oTree redirige a otra página; si no, vuelve a mostrar /login.
            if (new URL(r.url).pathname === '/login') {
                throw new Error('Usuario o contraseña incorrectos.');
            }
            var modal = $('modal-ingreso');
            modal.close();
            $('ingreso-clave').value = '';
            if (modal._alIngresar) { var f = modal._alIngresar; modal._alIngresar = null; f(); }
        }).catch(function (e) {
            error.textContent = e.message === 'Failed to fetch' ? 'No se pudo conectar con el servidor.' : e.message;
            error.hidden = false;
            $('ingreso-clave').select();
        }).then(function () {
            boton.disabled = false;
            boton.textContent = 'Ingresar';
        });
    }

    $('form-ingreso').addEventListener('submit', ingresar);
    $('cerrar-sesion').addEventListener('click', function () {
        // /logout de oTree borra la sesión (y redirige a su login, que acá no hace falta mostrar).
        fetch('/logout', {credentials: 'same-origin'}).then(function () { location.reload(); });
    });
    // Sin sesión el tablero no puede mostrar nada: Esc no cierra la ventana de ingreso.
    $('modal-ingreso').addEventListener('cancel', function (ev) { ev.preventDefault(); });

    // ------------------------------------------------------- catálogo de juegos
    // Los juegos, sus campos y las aulas están en /static/juegos/catalogo.json (lo usa
    // también la portada). scripts/verificar_catalogo.py controla que coincida con settings.py.
    var catalogo = null;
    function cargarCatalogo() {
        if (!catalogo) {
            catalogo = fetch('/static/juegos/catalogo.json', {cache: 'no-cache'}).then(function (r) {
                if (!r.ok) { throw new Error('No se pudo leer el catálogo de juegos.'); }
                return r.json();
            }).catch(function (e) { catalogo = null; throw e; });
        }
        return catalogo;
    }
    function juegoDe(cat, config) {
        return cat.juegos.filter(function (j) { return j.config === config; })[0] || null;
    }
    function rotuloSala(cat, nombre) {
        var sala = cat.salas.filter(function (s) { return s.nombre === nombre; })[0];
        return sala ? sala.rotulo : nombre;
    }

    // ------------------------------------------------------------ nueva sesión
    // Crea la sesión en el aula elegida con la API de oTree (/api/sessions con room_name) y
    // los cambios de configuración que haga el docente (modified_session_config_fields).
    var configs = null;      // valores por defecto de cada juego, de /api/session_configs (por nombre)
    var nueva = {cat: null, juego: null, base: {}};

    /* Igual que mercado.repartir_mercados (Python): parejos y sin superar el objetivo. */
    function repartirMercados(total, objetivo) {
        if (total < 1) { return []; }
        objetivo = Math.max(1, objetivo);
        var mercados = Math.ceil(total / objetivo), base = Math.floor(total / mercados), resto = total % mercados;
        var tamanos = [];
        for (var i = 0; i < mercados; i++) { tamanos.push(i < resto ? base + 1 : base); }
        return tamanos;
    }

    function enteroDe(id) { return parseInt($(id).value, 10); }

    function actualizarVistaPrevia() {
        var caja = $('vista-mercados');
        vaciar(caja);
        var g = nueva.juego && nueva.juego.grupo;
        if (g && g.texto && !g.campo) { caja.appendChild(el('b', null, g.texto)); return; }
        if (!g || !g.campo || !$('nueva-grupo')) { return; }
        var equipos = enteroDe('nueva-equipos'), objetivo = enteroDe('nueva-grupo');
        if (!(equipos >= 1) || !(objetivo >= 1)) {
            caja.appendChild(el('span', null, 'Indique la cantidad de equipos y el tamaño de cada ' + g.tipo + '.'));
            return;
        }
        var t = repartirMercados(equipos, objetivo), u = g.unidad || ['equipo', 'equipos'];
        var lista = t.length === 1 ? 'un ' + g.tipo + ' de ' + t[0] + ' ' + (t[0] === 1 ? u[0] : u[1])
            : t.length + ' ' + g.tipo + 's, de ' + t.slice(0, -1).join(', ') + ' y ' + t[t.length - 1] + ' ' + u[1];
        caja.appendChild(el('b', null, 'Se arma' + (t.length === 1 ? ' ' : 'n ') + lista + '.'));
        if (t.indexOf(1) >= 0) {
            caja.appendChild(el('span', {class: 'advertencia'}, ' Un ' + g.tipo + ' de un solo equipo no tiene competencia.'));
        }
    }

    function campoNumero(id, rotulo, valor, min, max) {
        var input = el('input', {type: 'number', id: id, min: String(min), max: String(max), step: '1', value: String(valor), required: 'required'});
        input.addEventListener('input', actualizarVistaPrevia);
        return el('label', {class: 'campo'}, [el('span', null, rotulo), input]);
    }

    /* Campos propios del juego elegido: tamaño de los grupos, rondas y opciones. */
    function dibujarCamposJuego() {
        var juego = nueva.juego, base = nueva.base, caja = $('campos-juego');
        vaciar(caja);
        $('nueva-juego-resumen').textContent = juego.resumen || '';
        if (juego.grupo && juego.grupo.campo) {
            caja.appendChild(campoNumero('nueva-grupo', juego.grupo.rotulo, base[juego.grupo.campo] || juego.grupo.max,
                                         juego.grupo.min, juego.grupo.max));
        }
        if (juego.rondas) {   // algunos juegos tienen una cantidad fija de rondas (p. ej., las etapas de un encargo)
            caja.appendChild(campoNumero('nueva-rondas', juego.rondas.rotulo, base[juego.rondas.campo] || juego.rondas.max,
                                         juego.rondas.min, juego.rondas.max));
        }
        (juego.campos || []).forEach(function (c) {
            var select = el('select', {'data-clave': c.clave}, c.opciones.map(function (o) {
                return el('option', {value: String(o[0])}, o[1]);
            }));
            if (c.clave in base) { select.value = String(base[c.clave]); }
            caja.appendChild(el('label', {class: 'campo'}, [el('span', null, c.rotulo), select]));
        });
        $('parametros-titulo').textContent = (juego.parametros_titulo || 'Parámetros') + ' (opcional)';
        dibujarParametros();
        actualizarVistaPrevia();
    }

    function dibujarParametros() {
        var caja = $('campos-parametros'), base = nueva.base;
        vaciar(caja);
        var lista = (nueva.juego.parametros || []).filter(function (p) { return p.clave in base; });
        if (!lista.length) { caja.appendChild(el('p', {class: 'nota'}, 'Este juego no tiene parámetros para cambiar.')); }
        lista.forEach(function (p) {
            var valor = base[p.clave];
            var mostrado = p.porcentaje ? Math.round(valor * 1000) / 10 : valor;
            var minimo = p.min == null ? 0 : p.min;   // en las unidades que se muestran (p. ej. % trimestral)
            var input = el('input', {type: 'number', step: String(p.paso), min: String(minimo), value: String(mostrado),
                                     'data-clave': p.clave, 'data-porcentaje': p.porcentaje ? '1' : '0', 'data-min': String(minimo)});
            var ayuda = el('small', {class: 'nota'});
            // Debajo, el valor con separador de miles (6000000 -> $ 6.000.000), para leerlo fácil.
            var describir = function () {
                var v = parseFloat(input.value);
                var texto = !(v >= minimo) ? 'Valor inválido'
                    : p.porcentaje ? nf2.format(v) + ' ' + p.unidad
                    : p.unidad.charAt(0) === '$' ? pesos(v) + p.unidad.slice(1)
                    : numero(v) + ' ' + p.unidad;
                ayuda.textContent = texto;
            };
            input.addEventListener('input', describir);
            describir();
            caja.appendChild(el('label', {class: 'campo'}, [el('span', null, p.rotulo), input, ayuda]));
        });
    }

    function elegirJuego() {
        nueva.juego = juegoDe(nueva.cat, $('nueva-juego').value);
        nueva.base = configs[nueva.juego.config] || {};
        dibujarCamposJuego();
    }

    function abrirNueva() {
        clearInterval(estado.temporizador);
        estado.codigo = null;
        history.replaceState(null, '', '#nueva');
        $('panel-sesiones').hidden = true;
        $('vista-sesion').hidden = true;
        $('vista-nueva').hidden = false;
        $('nueva-error').hidden = true;
        mostrarError(null);
        $('nueva-nombre').focus();

        Promise.all([cargarCatalogo(), configs ? configs : api('/api/session_configs'), api('/api/rooms')]).then(function (r) {
            var cat = r[0], aulas = r[2];
            if (!configs) {
                configs = {};
                r[1].forEach(function (c) { configs[c.name] = c; });
            }
            nueva.cat = cat;

            // Juegos: los disponibles se pueden elegir; los próximos se ven, deshabilitados.
            var anterior = $('nueva-juego').value;
            var selJuego = $('nueva-juego');
            vaciar(selJuego);
            cat.juegos.forEach(function (j) {
                var disponible = j.estado === 'disponible' && configs[j.config];
                selJuego.appendChild(el('option', disponible ? {value: j.config} : {value: j.config, disabled: 'disabled'},
                    j.nombre + ' — ' + j.subtitulo + (disponible ? '' : ' (próximamente)')));
            });
            var elegible = juegoDe(cat, anterior);
            selJuego.value = elegible && elegible.estado === 'disponible' && configs[anterior] ? anterior
                : cat.juegos.filter(function (j) { return j.estado === 'disponible' && configs[j.config]; })[0].config;
            elegirJuego();

            // Aulas, con su estado: una sesión nueva reemplaza a la que tenga abierta el aula.
            var selSala = $('nueva-sala'), salaAnterior = selSala.value;
            vaciar(selSala);
            nueva.ocupadas = {};
            aulas.forEach(function (a) { if (a.session_code) { nueva.ocupadas[a.name] = a.session_code; } });
            cat.salas.forEach(function (s) {
                selSala.appendChild(el('option', {value: s.nombre}, s.rotulo + (nueva.ocupadas[s.nombre] ? ' (con una sesión abierta)' : ' (libre)')));
            });
            var libre = cat.salas.filter(function (s) { return !nueva.ocupadas[s.nombre]; })[0];
            selSala.value = salaAnterior && cat.salas.some(function (s) { return s.nombre === salaAnterior; })
                ? salaAnterior : (libre || cat.salas[0]).nombre;
            avisoAulaOcupada();
        }).catch(function (e) { mostrarError(e.message); });
    }

    // ¿El aula elegida ya tiene una sesión abierta? La nueva la reemplaza para quienes entren por el enlace.
    function avisoAulaOcupada() {
        var aviso = $('aviso-aula-ocupada'), sala = $('nueva-sala').value, codigo = (nueva.ocupadas || {})[sala];
        aviso.hidden = true;
        if (!codigo) { return; }
        api('/api/get_session/' + encodeURIComponent(codigo), {participant_labels: []}).then(function (s) {
            if ($('nueva-sala').value !== sala) { return; }
            var juego = juegoDe(nueva.cat, s.config_name);
            vaciar(aviso);
            aviso.appendChild(el('span', null, [
                rotuloSala(nueva.cat, sala) + ' tiene abierta la sesión ', el('b', null, s.label || s.code),
                ' (' + (juego ? juego.nombre + ', ' : '') + s.num_participants + ' equipos). Al crear una nueva, ' +
                'los equipos que entren por el enlace de esa aula irán a la nueva; la anterior sigue en la lista con sus datos.'
            ]));
            aviso.hidden = false;
        }).catch(function () { /* el aviso es opcional */ });
    }

    function crearSesion(ev) {
        ev.preventDefault();
        var error = $('nueva-error'), boton = $('crear-sesion'), juego = nueva.juego;
        if (!juego) { return; }
        var fuera = function (v, d) { return !(v >= d.min && v <= d.max); };
        var equipos = enteroDe('nueva-equipos'), rondas = juego.rondas ? enteroDe('nueva-rondas') : null;
        var grupo = juego.grupo && juego.grupo.campo ? enteroDe('nueva-grupo') : null;
        var problema = !(equipos >= 1 && equipos <= 200) ? 'La cantidad de equipos tiene que estar entre 1 y 200.'
            : grupo !== null && fuera(grupo, juego.grupo) ? '"' + juego.grupo.rotulo + '" tiene que estar entre ' + juego.grupo.min + ' y ' + juego.grupo.max + '.'
            : juego.rondas && fuera(rondas, juego.rondas) ? '"' + juego.rondas.rotulo + '" tiene que estar entre ' + juego.rondas.min + ' y ' + juego.rondas.max + '.'
            : null;
        if (problema) { error.textContent = problema; error.hidden = false; return; }

        var cambios = {};
        if (juego.rondas) { cambios[juego.rondas.campo] = rondas; }
        if (grupo !== null) { cambios[juego.grupo.campo] = grupo; }
        [].forEach.call(document.querySelectorAll('#campos-juego select'), function (sel) {
            cambios[sel.getAttribute('data-clave')] = parseInt(sel.value, 10);
        });
        var invalido = null;
        [].forEach.call(document.querySelectorAll('#campos-parametros input'), function (inp) {
            var v = parseFloat(inp.value);
            if (!(v >= parseFloat(inp.getAttribute('data-min')))) { invalido = inp.parentNode.querySelector('span').textContent; return; }
            if (inp.getAttribute('data-porcentaje') === '1') { v = v / 100; }
            var clave = inp.getAttribute('data-clave');
            if (Math.abs(v - nueva.base[clave]) > 1e-9) { cambios[clave] = v; }
        });
        if (invalido) { error.textContent = 'Revise el valor de "' + invalido + '".'; error.hidden = false; return; }

        var sala = $('nueva-sala').value;
        error.hidden = true;
        boton.disabled = true;
        boton.textContent = 'Creando…';
        api('/api/sessions', {
            session_config_name: juego.config, num_participants: equipos, room_name: sala,
            label: $('nueva-nombre').value.trim(), modified_session_config_fields: cambios
        }).then(function (s) {
            avisar('Sesión creada: los equipos ya pueden entrar por el enlace de ' + rotuloSala(nueva.cat, sala));
            $('nueva-nombre').value = '';
            abrirSesion(s.code);
        }).catch(function (e) {
            error.textContent = 'No se pudo crear la sesión. ' + e.message;
            error.hidden = false;
        }).then(function () {
            boton.disabled = false;
            boton.textContent = 'Crear la sesión';
        });
    }

    // ---------------------------------------------------------- descarga de datos
    function descargarDatos() {
        var codigo = estado.codigo;
        if (!codigo) { return; }
        var app = estado.app;
        if (!app) { return; }
        var url = '/api/export_app?app=' + encodeURIComponent(app) + '&session_code=' + encodeURIComponent(codigo) + '&format=csv_bom';
        var bajar = function () {
            return fetch(url, {headers: {'X-Tablero': '1'}, credentials: 'same-origin'}).then(function (r) {
                if (r.status === 401) { return pedirIngreso().then(bajar); }
                if (!r.ok) { throw new Error('No se pudieron descargar los datos (error ' + r.status + ').'); }
                return r.blob().then(function (blob) {
                    var a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = app + '-' + codigo + '.csv';
                    document.body.appendChild(a);
                    a.click();
                    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
                    avisar('Datos descargados');
                });
            });
        };
        bajar().catch(function (e) { mostrarError(e.message); });
    }

    // ----------------------------------------------------------------- estados
    function etapa(t) {
        if (!t) { return {clase: 'sin-ingresar', texto: 'Sin ingresar'}; }
        var texto = t.etapa === 'termino' ? t.estado : t.ronda.abrev + t.ronda.actual + ' · ' + t.estado;
        return {clase: t.etapa, texto: texto};
    }

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
    // ---------------------------------------------------------- confirmación
    // Ventana modal propia (<dialog>) en lugar de confirm(): devuelve una promesa con true/false.
    // El foco arranca en "Cancelar" para que un Enter distraído no confirme una acción.
    var resolverModal = null;

    function confirmar(o) {
        var modal = $('modal');
        $('modal-titulo').textContent = o.titulo;
        $('modal-texto').textContent = o.texto || '';
        $('modal-detalle').textContent = o.detalle || '';
        $('modal-detalle').hidden = !o.detalle;
        $('modal-aceptar').textContent = o.aceptar || 'Aceptar';
        $('modal-aceptar').className = 'boton' + (o.peligro ? ' boton-peligro' : '');
        $('modal-cancelar').textContent = o.cancelar || 'Cancelar';
        $('modal-icono').hidden = !o.peligro;
        return new Promise(function (resolver) {
            resolverModal = resolver;
            modal.showModal();
            $('modal-cancelar').focus();
        });
    }

    function cerrarModal(resultado) {
        var modal = $('modal');
        if (modal.open) { modal.close(); }
        if (resolverModal) { var r = resolverModal; resolverModal = null; r(resultado); }
    }

    $('modal-aceptar').addEventListener('click', function () { cerrarModal(true); });
    $('modal-cancelar').addEventListener('click', function () { cerrarModal(false); });
    // Esc (evento "cancel" del diálogo) y clic fuera de la ventana: cancelar.
    $('modal').addEventListener('cancel', function (ev) { ev.preventDefault(); cerrarModal(false); });
    $('modal').addEventListener('click', function (ev) { if (ev.target === ev.currentTarget) { cerrarModal(false); } });

    // ---------------------------------------------------------------- papelera
    // Borrado lógico: "eliminar" guarda en session.vars['papelera'] la fecha en que se movió
    // a la papelera; no se borra ningún dato y "Recuperar" quita la marca. Se usa la API REST
    // (/api/session_vars), así que en el servidor la protege la misma contraseña del tablero.
    function fecha(segundos) {
        return segundos ? new Date(segundos * 1000).toLocaleString('es-AR', {dateStyle: 'short', timeStyle: 'short'}) : '';
    }

    function marcarPapelera(sesion, enPapelera) {
        var valor = enPapelera ? {eliminada: Date.now() / 1000} : null;
        return api('/api/session_vars/' + encodeURIComponent(sesion.code), {vars: {papelera: valor}});
    }

    function moverAPapelera(sesion, alTerminar) {
        var nombre = sesion.label || sesion.code;
        confirmar({
            titulo: '¿Mover a la papelera?',
            texto: 'La sesión "' + nombre + '" deja de aparecer en la lista.',
            detalle: 'No se borra ningún dato: se puede recuperar en cualquier momento desde la papelera.',
            aceptar: 'Mover a la papelera',
            peligro: true
        }).then(function (ok) {
            if (!ok) { return; }
            marcarPapelera(sesion, true).then(function () {
                avisar('Sesión "' + nombre + '" movida a la papelera');
                alTerminar();
            }).catch(function (e) { mostrarError(e.message); });
        });
    }

    function recuperar(sesion, alTerminar) {
        var nombre = sesion.label || sesion.code;
        marcarPapelera(sesion, false).then(function () {
            avisar('Sesión "' + nombre + '" recuperada');
            alTerminar();
        }).catch(function (e) { mostrarError(e.message); });
    }

    function tarjetaSesion(s, enPapelera) {
        var info = s.num_participants + ' equipos · creada ' + fecha(s.created_at) + (s.label ? ' · ' + s.code : '');
        if (enPapelera) { info += ' · eliminada ' + fecha(s.papelera.eliminada); }
        return el('div', {class: 'tarjeta-sesion' + (enPapelera ? ' en-papelera' : '')}, [
            el('button', {class: 'abrir-sesion', type: 'button', onclick: function () { abrirSesion(s.code); }}, [
                el('b', null, [s.juego ? el('span', {class: 'etiqueta-juego'}, s.juego.nombre) : null, s.label || s.code]),
                el('span', {class: 'nota'}, info)
            ]),
            enPapelera
                ? el('button', {class: 'boton-enlace', type: 'button', title: 'Recuperar la sesión',
                                onclick: function () { recuperar(s, cargarSesiones); }}, 'Recuperar')
                : el('button', {class: 'boton-eliminar', type: 'button', title: 'Mover a la papelera',
                                'aria-label': 'Mover a la papelera la sesión ' + (s.label || s.code),
                                onclick: function () { moverAPapelera(s, cargarSesiones); }}, 'Eliminar')
        ]);
    }

    function cargarSesiones() {
        var lista = $('lista-sesiones');
        var verPapelera = estado.verPapelera;
        var cat = null;
        cargarCatalogo().then(function (c) { cat = c; return api('/api/sessions'); }).then(function (sesiones) {
            sesiones = sesiones.filter(function (s) { return juegoDe(cat, s.config_name); }).reverse();
            sesiones.forEach(function (s) { s.juego = juegoDe(cat, s.config_name); });
            // La marca de papelera vive en session.vars: hay que pedirla sesión por sesión.
            return Promise.all(sesiones.map(function (s) {
                return api('/api/get_session/' + encodeURIComponent(s.code), {participant_labels: [], session_vars: ['papelera']})
                    .then(function (d) { s.papelera = d.papelera || null; return s; });
            }));
        }).then(function (sesiones) {
            var activas = sesiones.filter(function (s) { return !s.papelera; });
            var eliminadas = sesiones.filter(function (s) { return s.papelera; })
                .sort(function (a, b) { return b.papelera.eliminada - a.papelera.eliminada; });
            var boton = $('ver-papelera');
            boton.textContent = verPapelera ? '← Volver a las sesiones' : 'Papelera (' + eliminadas.length + ')';
            $('titulo-sesiones').textContent = verPapelera ? 'Papelera' : 'Sesiones';

            vaciar(lista);
            var mostrar = verPapelera ? eliminadas : activas;
            if (!mostrar.length) {
                lista.appendChild(el('p', {class: 'nota'}, verPapelera
                    ? 'La papelera está vacía.'
                    : 'No hay sesiones del simulador. Créelas desde el aula o el panel de oTree. ' +
                      '(Las partidas de prueba de "Demo" no aparecen en la lista: abra su código con el formulario.)'));
            }
            if (verPapelera && mostrar.length) {
                lista.appendChild(el('p', {class: 'nota nota-papelera'},
                    'Las sesiones de la papelera conservan todos sus datos. Recuperarlas las devuelve a la lista. ' +
                    'Si un equipo tiene el enlace de una sesión eliminada, todavía puede entrar.'));
            }
            mostrar.forEach(function (s) { lista.appendChild(tarjetaSesion(s, verPapelera)); });
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
        estado.app = null;
        estado.datos = null;
        estado.firma = null;
        if (location.hash !== '#sesion=' + codigo) { history.replaceState(null, '', '#sesion=' + codigo); }
        $('panel-sesiones').hidden = true;
        $('vista-nueva').hidden = true;
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
        $('vista-nueva').hidden = true;
        $('panel-sesiones').hidden = false;
        mostrarError(null);
        estado.verPapelera = false;   // "← Sesiones" vuelve siempre a la lista de sesiones
        cargarSesiones();
    }

    function actualizar() {
        var codigo = estado.codigo;
        if (!codigo) { return; }
        api('/api/get_session/' + encodeURIComponent(codigo), {participant_vars: VARS, session_vars: ['papelera']}).then(function (datos) {
            if (codigo !== estado.codigo) { return; }
            mostrarError(null);
            $('actualizado').textContent = 'Actualizado ' + new Date().toLocaleTimeString('es-AR');
            // Papelera: aviso con "Recuperar" si la sesión está eliminada; si no, botón para eliminarla.
            estado.sesionActual = {code: codigo, label: datos.label, papelera: datos.papelera || null};
            estado.app = (datos.config && datos.config.app_sequence || [])[0] || null;
            // Si la sesión es la del aula, su enlace para proyectar.
            $('enlace-aula-sesion').hidden = !datos.room_url;
            if (datos.room_url) { $('enlace-aula-texto').textContent = datos.room_url; }
            $('aviso-papelera').hidden = !datos.papelera;
            $('eliminar-sesion').hidden = !!datos.papelera;
            if (datos.papelera) {
                $('texto-papelera').textContent = 'Esta sesión está en la papelera (eliminada el ' +
                    fecha(datos.papelera.eliminada) + '). Sus datos están intactos.';
            }
            // Solo se redibuja si algo cambió: así no se pierden clics ni el foco del teclado.
            var firma = JSON.stringify(datos.participants);
            if (firma === estado.firma) { return; }
            estado.firma = firma;
            // Resúmenes de una versión anterior del simulador: se ignoran (formato distinto).
            (datos.participants || []).forEach(function (p) {
                if (p.tablero && p.tablero.version !== 2) { p.tablero = null; }
            });
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
            if (p.tablero) { (mercados[p.tablero.grupo.numero] = mercados[p.tablero.grupo.numero] || []).push(p); }
            else { sinIngresar.push(p); }
        });

        // Resumen
        var conTablero = participantes.filter(function (p) { return p.tablero; });
        var terminaron = conTablero.filter(function (p) { return p.tablero.etapa === 'termino'; }).length;
        var trimestres = conTablero.map(function (p) { return p.tablero.ronda.actual; });
        var ronda = conTablero.length ? conTablero[0].tablero.ronda : {total: null, nombre: 'trimestre', abrev: 'T'};
        var total = ronda.total;
        var minT = trimestres.length ? Math.min.apply(null, trimestres) : null;
        var maxT = trimestres.length ? Math.max.apply(null, trimestres) : null;
        var resumen = $('resumen');
        vaciar(resumen);
        [
            [participantes.length, 'equipos en la sesión'],
            [conTablero.length + ' / ' + participantes.length, 'ingresaron'],
            [minT == null ? '—' : (minT === maxT ? ronda.abrev + minT : ronda.abrev + minT + '–' + ronda.abrev + maxT) +
                (total ? ' de ' + total : ''), ronda.nombre + ' en curso'],
            [terminaron, 'terminaron el juego']
        ].forEach(function (d) { resumen.appendChild(el('div', {class: 'dato'}, [el('b', null, String(d[0])), el('span', null, d[1])])); });

        // Tamaño de los mercados (por si algún tablero viejo no lo informa).
        estado.tamMercado = Math.max.apply(null, [0].concat(Object.keys(mercados).map(function (m) {
            return mercados[m][0].tablero.grupo.tamano || mercados[m].length;
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
        equipos.sort(function (a, b) { return a.tablero.grupo.posicion - b.tablero.grupo.posicion; });
        var primero = equipos[0].tablero, tipo = primero.grupo.tipo;
        var t = Math.max.apply(null, equipos.map(function (p) { return p.tablero.ronda.actual; }));
        // Si alguien ya envió la decisión de la ronda, los que todavía deciden demoran al grupo.
        var hayEsperando = equipos.some(function (p) { return p.tablero.ronda.actual === t && p.tablero.etapa === 'esperando'; });
        var demoran = equipos.filter(function (p) {
            return hayEsperando && p.tablero.ronda.actual === t && p.tablero.etapa === 'decidiendo';
        });
        // Equipos del grupo que todavía no abrieron el juego (no tienen tablero).
        var faltan = (primero.grupo.tamano || estado.tamMercado || equipos.length) - equipos.length;

        var filas = equipos.map(function (p) {
            var tab = p.tablero, e = etapa(tab);
            var demora = demoran.indexOf(p) >= 0;
            return el('tr', {class: 'fila-equipo', tabindex: '0', role: 'button',
                             onclick: function () { abrirDetalle(p.code); },
                             onkeydown: function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abrirDetalle(p.code); } }}, [
                el('td', null, [el('span', {class: 'empresa'}, tab.equipo),
                                p.comentario_docente ? el('span', {class: 'marca-comentario', title: 'Tiene comentario del docente'}, ' ✎') : null]),
                el('td', null, el('span', {class: 'chip chip-' + (demora ? 'bloquea' : e.clase)}, demora ? e.texto + ' · lo esperan' : e.texto))
            ].concat((tab.indicadores || []).map(function (d) {
                return el('td', {class: claseNumero(d.valor, d)}, formatear(d.valor, d.formato, tab));
            })).concat([
                el('td', {class: 'num'}, tab.puesto ? tab.puesto + '°' : '—'),
                el('td', null, botonEnlace(p.code, tab.equipo))
            ]));
        });

        return el('section', {class: 'mercado'}, [
            el('div', {class: 'mercado-cabecera'}, [
                el('h2', null, mayuscula(tipo) + ' ' + numeroMercado),
                el('span', {class: 'nota'}, mayuscula(primero.ronda.nombre) + ' ' + t)
            ]),
            demoran.length ? el('p', {class: 'aviso-espera'},
                'El ' + tipo + ' espera a: ' + demoran.map(function (p) { return p.tablero.equipo; }).join(', ') + '.') : null,
            faltan > 0 ? el('p', {class: 'aviso-espera'},
                (faltan === 1 ? 'Falta que ingrese 1 equipo' : 'Faltan que ingresen ' + faltan + ' equipos') +
                ' a este ' + tipo + ': hasta entonces no avanza.') : null,
            el('div', {class: 'tabla-desplazable'}, el('table', {class: 'tabla'}, [
                el('thead', null, el('tr', null, [el('th', null, primero.rotulo_equipo || 'Equipo'), el('th', null, 'Estado')]
                    .concat((primero.indicadores || []).map(function (d) {
                        return el('th', {class: d.formato === 'texto' ? '' : 'num'}, d.etiqueta);
                    }))
                    .concat([el('th', {class: 'num'}, 'Puesto'), el('th', null, 'Enlace')]))),
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
        if (estado.borrador) {
            confirmar({
                titulo: 'Hay un comentario sin guardar',
                texto: 'Si cierra el detalle, se pierde lo que escribió para este equipo.',
                aceptar: 'Cerrar sin guardar',
                cancelar: 'Seguir editando',
                peligro: true
            }).then(function (ok) {
                if (ok) { estado.borrador = false; cerrarDetalle(); }
            });
            return;
        }
        estado.abierto = null;
        estado.borrador = false;
        $('fondo-detalle').hidden = true;
        $('detalle').hidden = true;
    }

    function dibujarDetalle(primeraVez) {
        var p = participante(estado.abierto);
        if (!p || !p.tablero) { return; }
        var tab = p.tablero, e = etapa(tab);
        $('detalle-mercado').textContent = mayuscula(tab.grupo.tipo) + ' ' + tab.grupo.numero;
        $('detalle-titulo').textContent = tab.equipo;
        var textoEstado = e.texto + (tab.puesto ? ' · puesto ' + tab.puesto + '° en su ' + tab.grupo.tipo : '');
        if (tab.decision && tab.etapa === 'esperando') { textoEstado += ' · decidió ' + tab.decision; }
        $('detalle-estado').textContent = textoEstado;

        // Enlace personal del equipo
        var enlace = $('detalle-enlace');
        vaciar(enlace);
        enlace.appendChild(el('code', null, enlaceEquipo(p.code)));
        enlace.appendChild(botonEnlace(p.code, tab.equipo));

        // Historial ("Mes a mes", "Trimestre a trimestre", según el juego)
        $('detalle-titulo-historial').textContent = mayuscula(tab.ronda.nombre) + ' a ' + tab.ronda.nombre;
        var tabla = $('detalle-historial');
        vaciar(tabla);
        var h = (tab.historial && tab.historial.filas) || [], columnas = (tab.historial && tab.historial.columnas) || [];
        if (!h.length) {
            tabla.appendChild(el('tbody', null, el('tr', null, el('td', null, 'Todavía no hay ' + tab.ronda.nombre + 's con resultados.'))));
        } else {
            tabla.appendChild(el('thead', null, el('tr', null, columnas.map(function (c) {
                return el('th', {class: c.formato === 'texto' || c.formato === 'ronda' ? '' : 'num'}, c.etiqueta);
            }))));
            tabla.appendChild(el('tbody', null, h.map(function (fila) {
                return el('tr', null, columnas.map(function (c) {
                    var v = fila[c.clave];
                    return el('td', {class: c.formato === 'ronda' ? '' : claseNumero(v, c)}, formatear(v, c.formato, tab));
                }));
            })));
        }
        $('detalle-nota-historial').textContent = tab.historial ? tab.historial.nota : '';

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
    $('ver-papelera').addEventListener('click', function () { estado.verPapelera = !estado.verPapelera; cargarSesiones(); });
    $('eliminar-sesion').addEventListener('click', function () {
        if (estado.sesionActual) { moverAPapelera(estado.sesionActual, actualizar); }
    });
    $('recuperar-sesion').addEventListener('click', function () {
        if (estado.sesionActual) { recuperar(estado.sesionActual, actualizar); }
    });
    $('actualizar').addEventListener('click', actualizar);
    $('cerrar-detalle').addEventListener('click', cerrarDetalle);
    $('fondo-detalle').addEventListener('click', cerrarDetalle);
    $('guardar-comentario').addEventListener('click', guardarComentario);
    $('comentario').addEventListener('input', function () { estado.borrador = true; $('estado-comentario').textContent = 'Sin guardar'; });
    document.addEventListener('keydown', function (ev) {
        // Con la ventana de confirmación abierta, Esc la cierra a ella (no al detalle).
        if (ev.key === 'Escape' && estado.abierto && !$('modal').open) { cerrarDetalle(); }
    });

    $('nueva-sesion').addEventListener('click', abrirNueva);
    $('cancelar-nueva').addEventListener('click', volver);
    $('cancelar-nueva-2').addEventListener('click', volver);
    $('form-nueva').addEventListener('submit', crearSesion);
    $('nueva-equipos').addEventListener('input', actualizarVistaPrevia);
    $('nueva-juego').addEventListener('change', elegirJuego);
    $('nueva-sala').addEventListener('change', avisoAulaOcupada);
    $('descargar-datos').addEventListener('click', descargarDatos);
    $('copiar-enlace-aula').addEventListener('click', function () {
        var url = $('enlace-aula-texto').textContent;
        var listo = function () { avisar('Enlace del aula copiado'); };
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(url).then(listo, function () { window.prompt('Copiar el enlace del aula:', url); });
        } else { window.prompt('Copiar el enlace del aula:', url); }
    });

    // Si cambia el código en la dirección (por ejemplo, desde un enlace), se abre esa sesión.
    window.addEventListener('hashchange', function () {
        var h = location.hash.match(/sesion=([\w-]+)/);
        if (h && h[1] !== estado.codigo) { abrirSesion(h[1]); }
    });

    var m = location.hash.match(/sesion=([\w-]+)/);
    if (m) { abrirSesion(m[1]); }
    else if (location.hash === '#nueva') { cargarSesiones(); abrirNueva(); }
    else { cargarSesiones(); }
})();
