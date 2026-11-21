// Vista del alumno. El token es anónimo: un número aleatorio que solo sirve
// para que cada navegador cuente un único voto por pregunta.

function nuevoToken() {
  const a = new Uint8Array(16);
  if (window.crypto && crypto.getRandomValues) crypto.getRandomValues(a);
  else a.forEach((_, i) => { a[i] = Math.floor(Math.random() * 256); });
  return Array.from(a, b => b.toString(16).padStart(2, '0')).join('');
}

function obtenerToken() {
  try {
    let t = localStorage.getItem('pulso_token');
    if (!t) { t = nuevoToken(); localStorage.setItem('pulso_token', t); }
    return t;
  } catch (_) {
    return nuevoToken(); // sin almacenamiento: vale para esta carga de página
  }
}

const token = obtenerToken();
const app = document.getElementById('app');
let refrescar;

// Modo remoto: el QR trae el código en la dirección (?c=…). Se usa una vez y se borra de la barra.
let codigoDelQR = new URLSearchParams(location.search).get('c');
if (codigoDelQR) history.replaceState(null, '', location.pathname);

async function entrar(codigo) {
  try {
    await api('/api/entrar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, codigo }),
    });
  } catch (e) { return e.message; }
  refrescar();
  return null;
}

function pedirCodigo(mensaje) {
  const form = formularioAcceso({
    titulo: 'código de la sesión',
    ayuda: 'Lo verás en la pantalla del aula. También puedes leer el QR.',
    clase: 'codigo',
    enviar: codigo => entrar(codigo),
  });
  if (mensaje) form.querySelector('.estado.mal').textContent = mensaje;
  app.replaceChildren(form);
}

// El servidor pide el código de sala (modo remoto): primero se prueba el del QR, si lo hay.
function sinAcceso() {
  if (!codigoDelQR) { pedirCodigo(); return; }
  const c = codigoDelQR;
  codigoDelQR = null;
  app.replaceChildren(el('p', { class: 'espera' }, 'entrando…'));
  entrar(c).then(error => { if (error) pedirCodigo(error); });
}

// Test con identificación: el alumno elige un alias (único) que saldrá en el ranking.
async function ponerAlias(alias) {
  try {
    await api('/api/alias', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, alias }),
    });
  } catch (e) { return e.message; }
  refrescar();
  return null;
}

function pedirAlias() {
  // La página se redibuja cuando llegan datos nuevos: no se pisa el formulario mientras se escribe.
  if (app.querySelector('input.alias')) return;
  app.replaceChildren(formularioAcceso({
    titulo: 'elige tu alias',
    ayuda: 'Es el nombre que verán todos en el ranking. No puede repetirse.',
    clase: 'alias', maximo: 20, boton: 'Continuar',
    enviar: ponerAlias,
  }));
}

async function enviar(valor) {
  try {
    await api('/api/responder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, respuesta: valor }),
    });
  } catch (e) { /* la votación se cerró justo ahora: el sondeo lo reflejará */ }
  refrescar();
}

function cabecera(d) {
  return el('header', { class: 'cab' },
    el('span', { class: 'eyebrow' }, d.tema.titulo),
    el('span', { class: 'cab-der' }, reloj(d), `pregunta ${d.indice + 1}/${d.total}`));
}

function enunciado(p) {
  return [
    tituloEnunciado(p.texto),
    p.imagen && el('img', { class: 'img-pregunta', src: p.imagen, alt: '' }),
  ];
}

function vistaAbierta(d) {
  return d.pregunta.multiple ? vistaAbiertaMultiple(d) : vistaAbiertaUna(d);
}

function vistaAbiertaUna(d) {
  const p = d.pregunta;
  const mia = d.mi_respuesta;
  return [
    cabecera(d),
    enunciado(p),
    el('div', { class: 'opciones' }, p.opciones.map((o, i) =>
      el('button', {
        class: 'opcion' + (mia === i ? ' elegida' : ''),
        onclick: () => enviar(i),
      }, el('span', { class: 'letra' }, LETRAS[i]), contenidoOpcion(o)))),
    p.con_nose && el('button', {
      class: 'opcion nose' + (mia === NOSE ? ' elegida' : ''),
      onclick: () => enviar(NOSE),
    }, ETIQUETA_NOSE),
    mia !== undefined
      ? el('p', { class: 'estado ok' }, '✓ respuesta enviada · puedes cambiarla hasta que se cierre la votación')
      : el('p', { class: 'estado' }, p.tipo === 'encuesta' ? 'encuesta · no hay respuesta correcta' : 'elige una opción'),
  ];
}

// Varias opciones: marcar no envía nada; la respuesta cuenta al pulsar «Enviar».
// La selección se guarda aquí (no en el DOM) porque la página se redibuja cuando
// llegan datos nuevos del servidor, y no debe perderse lo que el alumno aún no ha enviado.
let seleccion = { id: null, nose: false, marcas: new Set() };

function seleccionDe(d) {
  const id = d.pregunta.id;
  if (seleccion.id !== id) {
    const mia = d.mi_respuesta;
    seleccion = {
      id,
      nose: mia === NOSE,
      marcas: new Set(Array.isArray(mia) ? mia : []),
    };
  }
  return seleccion;
}

function respuestaDe(sel) {
  return sel.nose ? NOSE : [...sel.marcas].sort((a, b) => a - b);
}

function igualesRespuestas(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function vistaAbiertaMultiple(d) {
  const p = d.pregunta;
  const sel = seleccionDe(d);
  const mia = d.mi_respuesta;
  const botones = [];
  const botonNose = p.con_nose && el('button', {
    class: 'opcion nose', role: 'checkbox',
    onclick: () => { sel.nose = !sel.nose; if (sel.nose) sel.marcas.clear(); sincronizar(); },
  }, ETIQUETA_NOSE);
  const botonEnviar = el('button', {
    class: 'enviar',
    onclick: () => enviar(respuestaDe(sel)),
  }, 'Enviar');
  const estado = el('p', { class: 'estado' });

  p.opciones.forEach((o, i) => {
    const marca = el('span', { class: 'casilla' });
    botones.push([i, marca, el('button', {
      class: 'opcion', role: 'checkbox',
      onclick: () => {
        if (sel.marcas.has(i)) sel.marcas.delete(i); else sel.marcas.add(i);
        sel.nose = false;           // «no lo sé» es exclusiva
        sincronizar();
      },
    }, marca, el('span', { class: 'letra' }, LETRAS[i]), contenidoOpcion(o))]);
  });

  function sincronizar() {
    for (const [i, marca, b] of botones) {
      const on = sel.marcas.has(i);
      b.classList.toggle('elegida', on);
      b.setAttribute('aria-checked', on);
      marca.textContent = on ? '☑' : '☐';
    }
    if (botonNose) {
      botonNose.classList.toggle('elegida', sel.nose);
      botonNose.setAttribute('aria-checked', sel.nose);
    }
    const actual = respuestaDe(sel);
    const hayMarcas = sel.nose || sel.marcas.size > 0;
    const enviada = mia !== undefined && igualesRespuestas(actual, mia);
    botonEnviar.disabled = !hayMarcas || enviada;
    estado.className = 'estado' + (enviada ? ' ok' : '');
    estado.textContent = enviada
      ? '✓ respuesta enviada · puedes cambiarla y volver a enviar hasta que se cierre la votación'
      : mia !== undefined
        ? 'has cambiado la respuesta · pulsa Enviar para que cuente'
        : (p.tipo === 'encuesta' ? 'encuesta · ' : '') + 'marca todas las que correspondan y pulsa Enviar';
  }
  sincronizar();

  return [
    cabecera(d),
    enunciado(p),
    el('div', { class: 'opciones', role: 'group' }, botones.map(x => x[2])),
    botonNose,
    botonEnviar,
    estado,
  ];
}

// Pregunta rápida: el enunciado se ve antes que las opciones, que aparecen cuando el docente lo indique.
function vistaEnunciado(d) {
  return [
    cabecera(d),
    enunciado(d.pregunta),
    el('p', { class: 'espera' }, 'pregunta rápida · prepárate: las respuestas aparecerán enseguida'),
  ];
}

const MENSAJE_CATEGORIA = {
  acierto: ['ok', '✓ Tu respuesta era correcta.'],
  error: ['mal', '✗ Tu respuesta no era la correcta. Mira la pantalla.'],
  parcial: ['parcial', '≈ Tu respuesta era parcialmente correcta. Mira la pantalla.'],
  nose: ['nose', ETIQUETA_NOSE],
};

function mensajeCerrada(d) {
  if (d.pregunta.tipo === 'encuesta') {   // sin respuesta correcta: no hay acierto ni error
    return d.mi_respuesta === undefined
      ? el('p', { class: 'resultado' }, 'No respondiste a esta pregunta.')
      : el('p', { class: 'resultado ok' }, '✓ Tu respuesta quedó registrada.');
  }
  const m = MENSAJE_CATEGORIA[d.mi_categoria];
  return m
    ? el('p', { class: 'resultado ' + m[0] }, m[1])
    : el('p', { class: 'resultado' }, 'No respondiste a esta pregunta.');
}

function vistaCerrada(d) {
  return [
    cabecera(d),
    tituloEnunciado(d.pregunta.texto),
    mensajeCerrada(d),
    el('p', { class: 'espera' }, 'votación cerrada · mira los resultados en la pantalla'),
  ];
}

function render(d) {
  if (d.identificacion && !d.alias) { pedirAlias(); return; }
  let contenido;
  if (d.fase === 'abierta') contenido = vistaAbierta(d);
  else if (d.fase === 'cerrada') contenido = vistaCerrada(d);
  else if (d.fase === 'enunciado') contenido = vistaEnunciado(d);
  else if (d.fase === 'sala') {
    contenido = [
      el('header', { class: 'cab' }, el('span', { class: 'eyebrow' }, d.tema.titulo)),
      el('p', { class: 'resultado ok' }, '✓ Conectado'),
      el('p', { class: 'espera' }, 'el test empezará enseguida · atento a la pantalla'),
    ];
  } else if (d.fase === 'resumen') {
    contenido = [el('p', { class: 'espera' }, 'test terminado · mira el resumen en la pantalla')];
  } else {
    contenido = [el('p', { class: 'espera' }, 'esperando a que el docente empiece…')];
  }
  app.replaceChildren(...contenido.flat().filter(Boolean));
}

refrescar = sondear(() => '/api/estado?token=' + encodeURIComponent(token), render, 1000, sinAcceso);
