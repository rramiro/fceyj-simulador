/*
 * Campos de importes con formato argentino mientras se escribe: 1.234.567,89
 *
 *   formatoImportes(['precio', 'publicidad']);              // 2 decimales, sin negativos
 *   formatoImportes(['informe'], {negativos: true});
 *
 * - El punto de miles lo pone la página; la coma separa los centavos (hasta `decimales`).
 * - La tecla decimal del teclado numérico escribe la coma.
 * - Al salir del campo completa los centavos (25.000 → 25.000,00).
 * - Al enviar el formulario el campo vuelve a ser un número simple (25000.00), que es lo que espera oTree.
 */
(function () {
    function agruparMiles(entero) {
        return entero.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }

    function formatear(texto, decimales, negativos) {
        var negativo = negativos && /^\s*-/.test(texto);
        var limpio = texto.replace(/[^\d,]/g, '');
        var coma = limpio.indexOf(',');
        var entero = coma < 0 ? limpio : limpio.slice(0, coma);
        entero = entero.replace(/^0+(?=\d)/, '');
        var res = agruparMiles(entero);
        if (coma >= 0 && decimales > 0) {
            res = (res || '0') + ',' + limpio.slice(coma + 1).replace(/,/g, '').slice(0, decimales);
        }
        return (negativo ? '-' : '') + res;
    }

    function aNumero(texto) {
        // '1.234,5' → '1234.5'
        var t = texto.replace(/\./g, '').replace(',', '.');
        return t === '-' ? '' : t;
    }

    function desdeServidor(valor, decimales) {
        // oTree devuelve el valor con coma o punto decimal según el idioma ('25000,0' o '25000.0').
        var t = String(valor).trim();
        t = t.indexOf(',') >= 0 ? t.replace(/\./g, '').replace(',', '.') : t;
        var n = parseFloat(t);
        if (isNaN(n)) return valor;
        var partes = Math.abs(n).toFixed(decimales).split('.');
        return (n < 0 ? '-' : '') + agruparMiles(partes[0]) + (partes[1] ? ',' + partes[1] : '');
    }

    function completar(texto, decimales) {
        if (!texto || texto === '-' || decimales === 0) return texto;
        var coma = texto.indexOf(',');
        var dec = coma < 0 ? '' : texto.slice(coma + 1);
        var base = coma < 0 ? texto : texto.slice(0, coma);
        if (base === '' || base === '-') base += '0';
        while (dec.length < decimales) dec += '0';
        return base + ',' + dec;
    }

    function preparar(campo, opciones) {
        var decimales = opciones.decimales === undefined ? 2 : opciones.decimales;
        var negativos = !!opciones.negativos;
        campo.type = 'text';
        campo.setAttribute('inputmode', 'decimal');
        campo.setAttribute('autocomplete', 'off');
        campo.classList.add('campo-importe');
        if (!campo.placeholder) campo.placeholder = decimales ? '0,00' : '0';
        if (campo.value !== '') campo.value = completar(desdeServidor(campo.value, decimales), decimales);

        campo.addEventListener('keydown', function (e) {
            if (e.code === 'NumpadDecimal' && e.key !== ',') {
                e.preventDefault();
                var i = campo.selectionStart, j = campo.selectionEnd;
                campo.setRangeText(',', i, j, 'end');
                campo.dispatchEvent(new Event('input'));
            }
        });
        campo.addEventListener('input', function () {
            // Se conserva la posición del cursor contando dígitos y comas antes de él.
            var antes = campo.value.slice(0, campo.selectionStart).replace(/[^\d,]/g, '').length;
            var nuevo = formatear(campo.value, decimales, negativos);
            if (nuevo === campo.value) return;
            campo.value = nuevo;
            var pos = 0, vistos = 0;
            while (pos < nuevo.length && vistos < antes) {
                if (/[\d,]/.test(nuevo[pos])) vistos++;
                pos++;
            }
            if (antes === 0 && nuevo[0] === '-') pos = 1;
            campo.setSelectionRange(pos, pos);
        });
        campo.addEventListener('blur', function () {
            campo.value = completar(campo.value, decimales);
        });
        if (campo.form && !campo.form.dataset.importes) {
            campo.form.dataset.importes = '1';
            campo.form.addEventListener('submit', function () {
                campo.form.querySelectorAll('input.campo-importe').forEach(function (c) {
                    c.value = aNumero(c.value);
                });
            }, true);
        }
    }

    window.formatoImportes = function (nombres, opciones) {
        (nombres || []).forEach(function (nombre) {
            document.querySelectorAll('input[name="' + nombre + '"]').forEach(function (campo) {
                preparar(campo, opciones || {});
            });
        });
    };
})();
