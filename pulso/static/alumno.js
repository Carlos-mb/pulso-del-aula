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
    el('h1', { class: 'enunciado' }, p.texto),
    p.imagen && el('img', { class: 'img-pregunta', src: p.imagen, alt: '' }),
  ];
}

function vistaAbierta(d) {
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
    el('button', {
      class: 'opcion nose' + (mia === NOSE ? ' elegida' : ''),
      onclick: () => enviar(NOSE),
    }, ETIQUETA_NOSE),
    mia !== undefined
      ? el('p', { class: 'estado ok' }, '✓ respuesta enviada · puedes cambiarla hasta que se cierre la votación')
      : el('p', { class: 'estado' }, 'elige una opción'),
  ];
}

const MENSAJE_CATEGORIA = {
  acierto: ['ok', '✓ Tu respuesta era correcta.'],
  error: ['mal', '✗ Tu respuesta no era la correcta. Mira la pantalla.'],
  nose: ['nose', '? Pediste que se explique. ¡Atento a la explicación!'],
};

function vistaCerrada(d) {
  const m = MENSAJE_CATEGORIA[d.mi_categoria];
  return [
    cabecera(d),
    el('h1', { class: 'enunciado' }, d.pregunta.texto),
    m
      ? el('p', { class: 'resultado ' + m[0] }, m[1])
      : el('p', { class: 'resultado' }, 'No respondiste a esta pregunta.'),
    el('p', { class: 'espera' }, 'votación cerrada · mira los resultados en la pantalla'),
  ];
}

function render(d) {
  let contenido;
  if (d.fase === 'abierta') contenido = vistaAbierta(d);
  else if (d.fase === 'cerrada') contenido = vistaCerrada(d);
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

refrescar = sondear(() => '/api/estado?token=' + encodeURIComponent(token), render);
