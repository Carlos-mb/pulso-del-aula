// Vista única del docente: lo que se proyecta y, ocultos, los controles.
// Atajos: Espacio/Intro = acción principal · ← → = anterior/siguiente ·
//         Esc = volver a los temas · 1-9 = elegir tema (en la pantalla inicial)

const app = document.getElementById('app');
const pie = document.getElementById('pie');
const barra = document.getElementById('barra');
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

function accionPrincipal() {
  if (vista.fase === 'sala') ejecutar('empezar');
  else if (vista.fase === 'abierta') ejecutar('cerrar');
  else if (vista.fase === 'cerrada' || vista.fase === 'resumen') ejecutar('siguiente');
}

const ICONO = { acierto: '✓', error: '✗', nose: '?', parcial: '≈' };

// ---------- pantallas ----------
function formatoDuracion(s) {
  return s ? ` · ${formatoTiempo(s)} por pregunta` : '';
}

function pantallaInicio(d) {
  return [
    el('h1', { class: 'titulo-inicio' }, 'pulso del aula'),
    el('p', { class: 'eyebrow centrado' }, 'elige el tema'),
    el('div', { class: 'temas' }, d.temas.map((t, i) =>
      el('button', { class: 'tema', onclick: () => elegirTema(t.id) },
        el('span', { class: 'letra' }, String(i + 1)),
        el('span', { class: 'tema-titulo' }, t.titulo),
        el('span', { class: 'tema-n' }, `${t.n_preguntas} preguntas${formatoDuracion(t.tiempo)}`)))),
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
    el('p', { class: 'sala-url' }, 'entrad en ', el('b', {}, d.url_alumnos)),
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
  ];
}

function barraApilada(q) {
  if (!q.total) return el('div', { class: 'sin-datos' }, 'sin respuestas');
  return el('div', { class: 'apilada' },
    q.categorias.map(c => c.pct > 0 && el('div', { class: 'seg ' + c.clave, style: `width:${c.pct}%` })));
}

// Una encuesta no tiene aciertos ni errores: su barra reparte los votos por opción.
function etiquetasReparto(q) {
  return q.reparto.map((_, i) => (q.con_nose && i === q.reparto.length - 1 ? '?' : LETRAS[i]));
}

function barraReparto(q) {
  if (!q.total) return el('div', { class: 'sin-datos' }, 'sin respuestas');
  if (q.multiple) {   // los porcentajes no suman 100 %: una columna por opción en lugar de una barra apilada
    return el('div', { class: 'columnas' }, q.reparto.map((o, i) =>
      el('div', { class: 'col' },
        el('div', {
          class: 'col-relleno ' + (q.con_nose && i === q.reparto.length - 1 ? 'nose' : 'o' + (i % 5)),
          style: `height:${o.pct}%`,
        }))));
  }
  return el('div', { class: 'apilada' },
    q.reparto.map((o, i) => o.pct > 0 && el('div', {
      class: 'seg ' + (q.con_nose && i === q.reparto.length - 1 ? 'nose' : 'o' + (i % 5)),
      style: `width:${o.pct}%`,
    })));
}

function filaResumen(q) {
  const encuesta = q.tipo === 'encuesta';
  const nums = encuesta
    ? etiquetasReparto(q).map((l, i) => el('span', { class: 'num ' + (l === '?' ? 'nose' : 'o' + (i % 5)) },
      `${l} ${q.total ? Math.round(q.reparto[i].pct) : '–'}%`))
    : q.categorias.map(c =>
      el('span', { class: 'num ' + c.clave }, `${ICONO[c.clave] || ''} ${q.total ? Math.round(c.pct) : '–'}%`));
  return el('li', { class: 'fr' },
    el('span', { class: 'letra' }, String(q.indice + 1)),
    el('div', { class: 'fr-cuerpo' },
      el('div', { class: 'fr-texto md' }, formato(q.texto, { enlaces: false, plano: true })),
      encuesta ? barraReparto(q) : barraApilada(q)),
    el('div', { class: 'fr-nums' }, nums));
}

function pantallaResumen(d) {
  const r = d.resumen;
  return [
    cabecera(d, 'resumen del test'),
    el('h1', { class: 'enunciado compacto' }, 'Resumen'),
    r.global.categorias.length > 0
      && el('div', { class: 'resumen' }, r.global.categorias.map(c => tile(c, r.global.total))),
    el('ol', { class: 'tabla-resumen' }, r.preguntas.map(filaResumen)),
  ];
}

// La pantalla se proyecta y no se puede desplazar: si el contenido no cabe en la
// ventana, se reduce el tamaño de letra hasta que quepa (mínimo 45 %).
function ajustar() {
  const raiz = document.documentElement;
  let escala = 1;
  raiz.style.setProperty('--escala', escala);
  while (escala > 0.45 && raiz.scrollHeight > window.innerHeight + 1) {
    escala = Math.round((escala - 0.03) * 100) / 100;
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
  else contenido = pantallaAbierta(d);
  app.replaceChildren(...contenido.flat().filter(Boolean));

  pie.replaceChildren(d.fase === 'abierta' || d.fase === 'inicio'
    ? el('span', {}, 'alumnos, entrad en ', el('b', {}, d.url_alumnos))
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

function actualizarBarra(d) {
  const b = [];
  const borrar = () => {
    if (confirm('¿Borrar las respuestas de esta pregunta y abrirla de nuevo?')) ejecutar('reiniciar');
  };
  if (d.fase === 'sala') {
    b.push(boton('Empezar el test ▶', () => ejecutar('empezar'), 'principal'));
  } else if (d.fase === 'abierta') {
    b.push(boton('Cerrar votación', () => ejecutar('cerrar'), 'principal'));
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
  }
  if (d.fase !== 'inicio') b.push(boton('Temas', () => ejecutar('inicio')));
  b.push(el('span', { class: 'atajos' }, 'Espacio: avanzar · ← →: pregunta · Esc: temas'));
  barra.replaceChildren(...b);
}

let ocultar;
function mostrarBarra() {
  barra.classList.remove('oculta');
  document.body.classList.remove('sin-cursor');
  clearTimeout(ocultar);
  ocultar = setTimeout(() => {
    barra.classList.add('oculta');
    document.body.classList.add('sin-cursor');
  }, 3000);
}
document.addEventListener('mousemove', mostrarBarra);
mostrarBarra();

// ---------- teclado ----------
document.addEventListener('keydown', e => {
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  const enTema = vista.fase !== 'inicio';
  if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); accionPrincipal(); }
  else if (e.key === 'ArrowRight' && enTema) ejecutar('siguiente');
  else if (e.key === 'ArrowLeft' && enTema) ejecutar('anterior');
  else if (e.key === 'Escape' && enTema) ejecutar('inicio');
  else if (!enTema && /^[1-9]$/.test(e.key)) {
    const t = vista.temas[Number(e.key) - 1];
    if (t) elegirTema(t.id);
  }
});

refrescar = sondear(() => '/api/docente/estado', render, 700);
