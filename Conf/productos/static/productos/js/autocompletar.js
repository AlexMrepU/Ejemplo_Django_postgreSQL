/*
 * Buscador con autocompletado para "Agregar canción".
 *
 * Funcionamiento:
 * 1. El usuario escribe en el campo de texto.
 * 2. Tras 250 ms sin teclear (debounce) se pide al servidor
 *    /canciones/buscar/?q=texto&playlist=ID, que devuelve como máximo
 *    20 coincidencias en JSON.
 * 3. Al elegir una sugerencia, su id se copia al campo oculto "cancion"
 *    y se activa el botón Agregar.
 *
 * El debounce evita enviar una consulta por cada letra: escribir "despacito"
 * genera una sola petición en lugar de nueve.
 *
 * Teclado: flechas arriba/abajo para moverse, Enter para elegir, Esc para cerrar.
 */
(function () {
    const buscador = document.querySelector('[data-autocompletar]');
    if (!buscador) return;

    const entrada = buscador.querySelector('input[type="search"]');
    const oculto = buscador.querySelector('input[name="cancion"]');
    const lista = buscador.querySelector('.sugerencias');
    const boton = buscador.querySelector('button[type="submit"]');
    const url = buscador.dataset.url;

    let temporizador = null;
    let resultados = [];
    let seleccionado = -1;
    let controlador = null;   // permite cancelar una petición anterior

    function cerrar() {
        lista.hidden = true;
        entrada.setAttribute('aria-expanded', 'false');
        seleccionado = -1;
    }

    function texto(valor) {
        // Crea texto plano (evita inyectar HTML con títulos raros).
        return document.createTextNode(valor == null ? '' : String(valor));
    }

    function pintar() {
        lista.replaceChildren();
        if (!resultados.length) {
            const li = document.createElement('li');
            li.className = 'vacio';
            li.appendChild(texto('Sin coincidencias. Pruebe con otra palabra del título.'));
            lista.appendChild(li);
        }
        resultados.forEach(function (r, i) {
            const li = document.createElement('li');
            li.id = 'sug-' + r.id;
            li.setAttribute('role', 'option');
            li.setAttribute('aria-selected', i === seleccionado ? 'true' : 'false');
            li.appendChild(texto(r.titulo));
            const sub = document.createElement('small');
            sub.appendChild(texto(r.artista + (r.anio ? ' (' + r.anio + ')' : '')));
            li.appendChild(sub);
            li.addEventListener('mousedown', function (e) {
                e.preventDefault();   // evita que el input pierda el foco antes de elegir
                elegir(i);
            });
            lista.appendChild(li);
        });
        lista.hidden = false;
        entrada.setAttribute('aria-expanded', 'true');
    }

    function elegir(i) {
        const r = resultados[i];
        if (!r) return;
        entrada.value = r.titulo + ' - ' + r.artista;
        oculto.value = r.id;
        boton.disabled = false;
        cerrar();
        boton.focus();
    }

    async function buscar(q) {
        if (controlador) controlador.abort();
        controlador = new AbortController();
        try {
            const respuesta = await fetch(url + '&q=' + encodeURIComponent(q), {
                signal: controlador.signal,
                headers: { 'Accept': 'application/json' },
            });
            if (!respuesta.ok) return;
            const datos = await respuesta.json();
            resultados = datos.resultados;
            seleccionado = resultados.length ? 0 : -1;
            pintar();
        } catch (error) {
            if (error.name !== 'AbortError') console.error(error);
        }
    }

    entrada.addEventListener('input', function () {
        // Si el usuario vuelve a escribir, la selección anterior ya no vale.
        oculto.value = '';
        boton.disabled = true;
        clearTimeout(temporizador);
        const q = entrada.value.trim();
        if (q.length < 2) { cerrar(); return; }
        temporizador = setTimeout(function () { buscar(q); }, 250);
    });

    entrada.addEventListener('keydown', function (e) {
        if (lista.hidden) return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            const paso = e.key === 'ArrowDown' ? 1 : -1;
            seleccionado = (seleccionado + paso + resultados.length) % resultados.length;
            pintar();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            elegir(seleccionado);
        } else if (e.key === 'Escape') {
            cerrar();
        }
    });

    entrada.addEventListener('blur', cerrar);
})();
