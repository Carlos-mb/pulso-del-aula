// Vista única del docente: lo que se proyecta y, ocultos, los controles.
// Atajos: Espacio/Intro = acción principal · ← → = anterior/siguiente ·
//         Esc = volver a los temas · 1-9, a-z = elegir tema (en la pantalla inicial; se saltan
//         las letras que son atajos, ver ATAJOS_LETRA) ·
//         H = ocultar / mostrar la barra de controles · P = pausar / reanudar el tiempo

const app = document.getElementById('app');
const pie = document.getElementById('pie');
const barra = document.getElementById('barra');
const botonMostrar = document.getElementById('mostrar');
const toast = document.getElementById('toast');
let vista = { fase: 'inicio', temas: [] };
let refrescar;

// ---------- acciones ----------
function avisar(msg) {
  toast.textContent = msg;
  toast.hidden = false;
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => { toast.hidden = true; }, 3000);
}

async function ejecutar(ruta) {
  try { await api('/api/docente/' + ruta, { method: 'POST' }); }
  catch (e) { avisar(e.message); }
  refrescar();
}

const elegirTema = id => ejecutar('tema/' + encodeURIComponent(id));

// Si el servidor pide la clave (modo remoto, o local si se configuró), se muestra el formulario.
async function entrarDocente(clave) {
  try {
    await api('/api/docente/entrar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clave }),
    });
  } catch (e) { return e.message; }
  refrescar();
  return null;
}

function pedirClave() {
  pie.replaceChildren();
  barra.replaceChildren();
  app.replaceChildren(
    el('h1', { class: 'titulo-inicio' }, 'pulso del aula'),
    formularioAcceso({ titulo: 'clave del docente', tipo: 'password', enviar: entrarDocente }));
}

function accionPrincipal() {
  if (vista.fase === 'sala') ejecutar('empezar');
  else if (vista.fase === 'enunciado') ejecutar('mostrar');
  else if (vista.fase === 'abierta') ejecutar('cerrar');
  else if (vista.fase === 'cerrada' || vista.fase === 'resumen') ejecutar('siguiente');
}

const ICONO = { acierto: '✓', error: '✗', nose: '?', parcial: '≈' };

// ---------- pantallas ----------
// Iconos monocromos (heredan el color del texto) para los datos de cada tema.
const SVG_TEMA = {
  preguntas: '<circle cx="12" cy="12" r="9.5"/><path d="M9.2 9.2a2.9 2.9 0 0 1 5.6 1c0 1.9-2.8 2.6-2.8 4"/><path d="M12 17.6v.01"/>',
  tiempo: '<circle cx="12" cy="13.5" r="8"/><path d="M12 9.5v4l2.6 1.8"/><path d="M9.5 2.5h5"/>',
  rapido: '<path d="M13 2.5 4 14h7l-1 7.5L19 10h-7z"/>',
  ranking: '<path d="M7 3.5h10V9a5 5 0 0 1-10 0z"/><path d="M7 5.5H4.5a3 3 0 0 0 3 4.3M17 5.5h2.5a3 3 0 0 1-3 4.3"/><path d="M12 14v3.5M8 21h8M9.5 17.5h5"/>',
};

function icono(nombre) {
  const s = document.createElement('span');
  s.className = 'icono';
  s.setAttribute('aria-hidden', 'true');
  s.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    + ' stroke-linecap="round" stroke-linejoin="round">' + SVG_TEMA[nombre] + '</svg>';
  return s;
}

const datoTema = (nombre, texto, titulo) =>
  el('span', { class: 'tema-dato', title: titulo }, icono(nombre), texto);

function pantallaInicio(d) {
  return [
    el('h1', { class: 'titulo-inicio' }, 'pulso del aula'),
    el('p', { class: 'eyebrow centrado legal' }, String.fromCharCode(169, 32, 50, 48, 50, 54, 32, 67, 97, 114, 108, 111, 115, 32, 77, 101, 108, 101, 114, 111)),
    el('p', { class: 'eyebrow centrado' }, 'elige el tema'),
    el('div', { class: 'temas' }, d.temas.map((t, i) =>
      el('button', { class: 'tema', onclick: () => elegirTema(t.id) },
        TECLAS_TEMA[i] ? el('span', { class: 'letra' }, TECLAS_TEMA[i]) : el('span', { class: 'letra vacia' }),
        el('span', { class: 'tema-cuerpo' },
          el('span', { class: 'tema-titulo' }, t.titulo),
          el('span', { class: 'tema-info' },
            datoTema('preguntas', String(t.n_preguntas), `${t.n_preguntas} preguntas`),
            t.tiempo > 0 && datoTema('tiempo', formatoTiempo(t.tiempo), `${formatoTiempo(t.tiempo)} por pregunta`),
            !!t.rapido && datoTema('rapido', 'rápido', 'preguntas rápidas'),
            !!t.identificacion && datoTema('ranking', 'ranking', 'con ranking')))))),
  ];
}

function pantallaSala(d) {
  const n = d.conectados;
  return [
    cabecera(d, `${d.total} preguntas`),
    el('p', { class: 'eyebrow centrado sala-titulo' }, 'esperando a los alumnos'),
    el('div', { class: 'conectados' },
      el('div', { class: 'conectados-n' }, String(n)),
      el('div', { class: 'conectados-etq' }, n === 1 ? 'persona conectada' : 'personas conectadas')),
    d.codigo
      ? el('div', { class: 'acceso-remoto' },
        el('img', { class: 'qr', src: '/api/docente/qr.svg?c=' + encodeURIComponent(d.codigo), alt: 'QR de acceso' }),
        el('div', { class: 'acceso-texto' },
          el('p', { class: 'sala-url' }, 'entrad en ', el('b', {}, d.url_alumnos)),
          el('p', { class: 'eyebrow' }, 'e introducid el código'),
          el('div', { class: 'codigo-sala' }, d.codigo)))
      : el('p', { class: 'sala-url' }, 'entrad en ', el('b', {}, d.url_alumnos)),
    el('p', { class: 'sala-pista' }, 'pulsa Espacio para empezar cuando estén listos'),
  ];
}

function cabecera(d, derecha) {
  return el('header', { class: 'cab' },
    el('span', { class: 'eyebrow' }, d.tema.titulo),
    el('span', { class: 'cab-der' }, derecha || [reloj(d), `pregunta ${d.indice + 1}/${d.total}`]));
}

function enunciado(p, compacto) {
  return [
    tituloEnunciado(p.texto, compacto ? 'compacto' : ''),
    p.imagen && el('img', { class: 'img-pregunta', src: p.imagen, alt: '' }),
  ];
}

function pantallaAbierta(d) {
  const p = d.pregunta;
  return [
    cabecera(d),
    enunciado(p),
    el('ol', { class: 'lista-opciones' }, [
      ...p.opciones.map((o, i) =>
        el('li', {}, el('span', { class: 'letra' }, LETRAS[i]), contenidoOpcion(o))),
      p.con_nose && el('li', { class: 'nose' }, el('span', { class: 'letra' }, '?'), ETIQUETA_NOSE),
    ]),
    el('p', { class: 'contador' },
      `${p.tipo === 'encuesta' ? 'encuesta · ' : ''}${p.multiple ? 'marca todas las que correspondan · ' : ''}`
      + `votación abierta · ${d.n_respuestas} respuesta${d.n_respuestas === 1 ? '' : 's'}`
      + ` · ${d.conectados} conectado${d.conectados === 1 ? '' : 's'}`),
  ];
}

// Pregunta rápida: solo el enunciado; las opciones salen cuando el docente pulsa Espacio.
function pantallaEnunciado(d) {
  return [
    cabecera(d),
    enunciado(d.pregunta),
    el('p', { class: 'contador' },
      `pregunta rápida · ${formatoTiempo(d.duracion)} para responder · pulsa Espacio para mostrar las respuestas`),
  ];
}

const MOTIVO_CIERRE = {
  todos: 'cerrada: han votado todos',
  tiempo: 'cerrada: tiempo agotado',
  docente: 'cerrada',
};

function fila(letra, o, r, correcta, esNose) {
  return el('li', { class: 'fila' + (correcta ? ' correcta' : '') + (esNose ? ' nose' : '') },
    el('span', { class: 'letra' }, letra),
    el('div', { class: 'fila-cuerpo' },
      el('div', { class: 'fila-texto' }, contenidoOpcion(o), correcta && el('b', { class: 'marca' }, ' ✓ correcta')),
      el('div', { class: 'pista' }, el('div', { class: 'relleno', style: `width:${r.pct}%` }))),
    el('span', { class: 'pct' }, `${Math.round(r.pct)}%`));
}

function tile(c, total) {
  return el('div', { class: 'tile ' + c.clave },
    el('div', { class: 'tile-pct' }, `${ICONO[c.clave] || ''} ${Math.round(c.pct)}%`),
    el('div', { class: 'tile-etq' }, c.etiqueta),
    el('div', { class: 'tile-n' }, `${c.n} de ${total}`));
}

// Ranking: solo alias y puntos, de más a menos (sin posiciones, así que no hay que desempatar).
function tablaRanking(filas, titulo) {
  return el('section', { class: 'ranking' },
    el('p', { class: 'eyebrow' }, titulo),
    el('ol', { class: 'ranking-lista' }, filas.map(f =>
      el('li', {}, el('span', { class: 'ranking-alias' }, f.alias),
        el('span', { class: 'ranking-puntos' }, String(f.puntos))))));
}

function pantallaResultados(d) {
  const p = d.pregunta, r = d.resultados;
  return [
    cabecera(d, `pregunta ${d.indice + 1}/${d.total} · ${MOTIVO_CIERRE[d.motivo_cierre] || 'cerrada'}`),
    enunciado(p, true),
    el('ol', { class: 'resultados' }, [
      ...p.opciones.map((o, i) => fila(LETRAS[i], o, r.opciones[i], r.correctas.includes(i), false)),
      r.nose && fila('?', { texto: ETIQUETA_NOSE }, r.nose, false, true),
    ]),
    p.tipo === 'encuesta'
      ? el('p', { class: 'contador' }, `encuesta · ${r.total} respuesta${r.total === 1 ? '' : 's'}`
        + (p.multiple ? ' · se podían marcar varias: los porcentajes no suman 100 %' : ''))
      : el('div', { class: 'resumen' }, r.categorias.map(c => tile(c, r.total))),
    p.multiple && p.tipo !== 'encuesta'
      && el('p', { class: 'contador' }, 'cada barra es el porcentaje de alumnos que marcó esa opción'),
    r.explicacion && el('div', { class: 'explicacion md' }, formato(r.explicacion)),
    d.ranking && d.ranking.length > 0 && tablaRanking(d.ranking, 'ranking'),
  ];
}

function barraApilada(q) {
  if (!q.total) return el('div', { class: 'sin-datos' }, 'sin respuestas');
  return el('div', { class: 'apilada' },
    q.categorias.map(c => c.pct > 0 && el('div', { class: 'seg ' + c.clave, style: `width:${c.pct}%` })));
}

// Respuestas de una pregunta con el porcentaje de alumnos que eligió cada una.
// Si se podían marcar varias, los porcentajes no suman 100 %.
function opcionesResumen(q) {
  return el('div', { class: 'fr-opciones' }, q.opciones.map((o, i) => {
    const pct = q.total ? Math.round(o.pct) : null;
    return el('span', {
      class: 'fr-op' + (o.correcta ? ' correcta' : '') + (o.nose ? ' nose' : ''),
      style: `--p:${o.pct}%`,
    },
      el('span', { class: 'letra-op' }, o.nose ? '?' : LETRAS[i]),
      el('span', { class: 'texto-op md' },
        o.imagen && el('img', { class: 'img-resumen', src: o.imagen, alt: '' }),
        o.texto && formato(o.texto, { enlaces: false, plano: true })),
      o.correcta && el('b', { class: 'marca' }, '✓'),
      el('span', { class: 'pct-op' }, pct === null ? '–%' : `${pct}%`));
  }));
}

function filaResumen(q) {
  const encuesta = q.tipo === 'encuesta';   // sin aciertos ni errores: solo el reparto de respuestas
  return el('li', { class: 'fr' },
    el('span', { class: 'letra' }, String(q.indice + 1)),
    el('div', { class: 'fr-cuerpo' },
      el('div', { class: 'fr-texto md' }, formato(q.texto, { enlaces: false, plano: true })),
      opcionesResumen(q),
      !encuesta && barraApilada(q)),
    !encuesta && el('div', { class: 'fr-nums' }, q.categorias.map(c =>
      el('span', { class: 'num ' + c.clave }, `${ICONO[c.clave] || ''} ${q.total ? Math.round(c.pct) : '–'}%`))));
}

function pantallaResumen(d) {
  const r = d.resumen;
  return [
    cabecera(d, 'resumen del test'),
    el('h1', { class: 'enunciado compacto' }, 'Resumen'),
    r.global.categorias.length > 0
      && el('div', { class: 'resumen' }, r.global.categorias.map(c => tile(c, r.global.total))),
    r.ranking && r.ranking.length > 0 && tablaRanking(r.ranking, 'ranking final'),
    el('ol', { class: 'tabla-resumen' }, r.preguntas.map(filaResumen)),
  ];
}

// En las pantallas de pregunta se reduce el tamaño de letra si el contenido no
// cabe en la ventana. El resumen y el menú de temas pueden ocupar varias
// pantallas: mantienen el tamaño de letra y se desplazan.
function ajustar() {
  const raiz = document.documentElement;
  let escala = 1;
  raiz.style.setProperty('--escala', escala);
  if (vista.fase === 'resumen' || vista.fase === 'inicio') return;
  while (escala > 0.45 && raiz.scrollHeight > window.innerHeight + 1) {
    escala = Math.max(0.45, Math.round((escala - 0.03) * 100) / 100);
    raiz.style.setProperty('--escala', escala);
  }
}
window.addEventListener('resize', ajustar);
app.addEventListener('load', ajustar, true); // las imágenes cambian la altura al cargar

function render(d) {
  vista = d;
  let contenido;
  if (d.fase === 'inicio') contenido = pantallaInicio(d);
  else if (d.fase === 'sala') contenido = pantallaSala(d);
  else if (d.fase === 'resumen') contenido = pantallaResumen(d);
  else if (d.fase === 'cerrada') contenido = pantallaResultados(d);
  else if (d.fase === 'enunciado') contenido = pantallaEnunciado(d);
  else contenido = pantallaAbierta(d);
  app.replaceChildren(...contenido.flat().filter(Boolean));

  pie.replaceChildren(['abierta', 'enunciado', 'inicio'].includes(d.fase)
    ? el('span', {}, 'alumnos, entrad en ', el('b', {}, d.url_alumnos),
      d.codigo && [' · código ', el('b', {}, d.codigo)])
    : '');
  actualizarBarra(d);
  ajustar();
}

// ---------- barra de controles (se oculta sola) ----------
function boton(texto, fn, extra) {
  // mousedown.preventDefault: el botón no toma el foco y así Espacio/Intro no lo activan dos veces
  return el('button', { class: 'btn' + (extra ? ' ' + extra : ''), onclick: fn,
    onmousedown: e => e.preventDefault() }, texto);
}

// Descarga el resumen en Markdown (lo genera el servidor; solo texto, sin imágenes).
function guardarResumen() {
  el('a', { href: '/api/docente/resumen.md', download: '' }).click();
}

function actualizarBarra(d) {
  const b = [];
  const borrar = () => {
    if (confirm('¿Borrar las respuestas de esta pregunta y abrirla de nuevo?')) ejecutar('reiniciar');
  };
  if (d.fase === 'sala') {
    b.push(boton('Empezar el test ▶', () => ejecutar('empezar'), 'principal'));
  } else if (d.fase === 'enunciado') {
    if (d.indice > 0) b.push(boton('◀ Anterior', () => ejecutar('anterior')));
    b.push(boton('Mostrar respuestas ▶', () => ejecutar('mostrar'), 'principal'));
    b.push(boton('Saltar pregunta', () => ejecutar('siguiente')));
  } else if (d.fase === 'abierta') {
    b.push(boton('Cerrar votación', () => ejecutar('cerrar'), 'principal'));
    if (d.tiempo) b.push(boton(d.tiempo.pausado ? '▶ Reanudar tiempo' : '⏸ Pausar tiempo', () => ejecutar('pausar')));
    b.push(boton('Borrar respuestas', borrar));
  } else if (d.fase === 'cerrada') {
    if (d.indice > 0) b.push(boton('◀ Anterior', () => ejecutar('anterior')));
    b.push(boton(d.indice + 1 === d.total ? 'Ver resumen ▶' : 'Siguiente pregunta ▶',
      () => ejecutar('siguiente'), 'principal'));
    b.push(boton('Reabrir votación', () => ejecutar('abrir')));
    b.push(boton('Borrar respuestas', borrar));
  } else if (d.fase === 'resumen') {
    b.push(boton('◀ Última pregunta', () => ejecutar('anterior')));
    b.push(boton('Volver a los temas ▶', () => ejecutar('siguiente'), 'principal'));
    b.push(boton('Guardar resumen (.md)', guardarResumen));
  }
  if (d.fase !== 'inicio') b.push(boton('Temas', () => ejecutar('inicio')));
  b.push(boton('Ocultar ▼', () => ponerBarraOculta(true)));
  b.push(el('span', { class: 'atajos' }, 'Espacio: avanzar · ← →: pregunta · P: pausar tiempo · Esc: temas · H: ocultar'));
  barra.replaceChildren(...b);
}

// La barra aparece al mover el ratón y se oculta sola. Si tapa contenido, el docente la puede
// ocultar del todo (botón «Ocultar» o tecla H): entonces, al mover el ratón, solo aparece un botoncito
// en la esquina para volver a mostrarla.
let ocultar;
let barraOculta = false;
function mostrarBarra() {
  (barraOculta ? botonMostrar : barra).classList.remove('oculta');
  document.body.classList.remove('sin-cursor');
  clearTimeout(ocultar);
  ocultar = setTimeout(() => {
    barra.classList.add('oculta');
    botonMostrar.classList.add('oculta');
    document.body.classList.add('sin-cursor');
  }, 3000);
}

function ponerBarraOculta(oculta) {
  barraOculta = oculta;
  barra.classList.add('oculta');
  botonMostrar.classList.add('oculta');
  if (!oculta) mostrarBarra();
}

botonMostrar.addEventListener('mousedown', e => e.preventDefault());
botonMostrar.addEventListener('click', () => ponerBarraOculta(false));
document.addEventListener('mousemove', mostrarBarra);
mostrarBarra();

// ---------- teclado ----------
// Atajos de una letra, activos en todas las pantallas. Sus teclas quedan reservadas: la numeración
// de los temas (1-9, a-z) se las salta, así que añadir aquí un atajo nuevo no choca con ningún tema.
const ATAJOS_LETRA = {
  h: () => ponerBarraOculta(!barraOculta),
  p: () => { if (vista.fase === 'abierta' && vista.tiempo) ejecutar('pausar'); },
};
const TECLAS_TEMA = [...'123456789abcdefghijklmnopqrstuvwxyz'].filter(k => !(k in ATAJOS_LETRA));

document.addEventListener('keydown', e => {
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  // Escribiendo en un campo (la clave): las teclas son suyas, no atajos (si no, Intro no envía el formulario).
  if (e.target instanceof Element && e.target.closest('input, textarea, select')) return;
  const enTema = vista.fase !== 'inicio';
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (Object.hasOwn(ATAJOS_LETRA, k)) ATAJOS_LETRA[k]();
  else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); accionPrincipal(); }
  else if (e.key === 'ArrowRight' && enTema) ejecutar('siguiente');
  else if (e.key === 'ArrowLeft' && enTema) ejecutar('anterior');
  else if (e.key === 'Escape' && enTema) ejecutar('inicio');
  else if (!enTema) {
    const i = TECLAS_TEMA.indexOf(k);
    const t = i >= 0 && vista.temas[i];
    if (t) elegirTema(t.id);
  }
});

refrescar = sondear(() => '/api/docente/estado', render, 700, pedirClave);
