// Utilidades compartidas por la vista del alumno y la del docente.

const NOSE = 'nose';
const ETIQUETA_NOSE = 'No lo sé / quiero que se explique';
const LETRAS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

function el(tag, props, ...hijos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
  }
  for (const h of hijos.flat()) if (h != null && h !== false) e.append(h);
  return e;
}

async function api(ruta, opciones) {
  const r = await fetch(ruta, opciones);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) { /* sin cuerpo JSON */ }
    const e = new Error(msg);
    e.status = r.status;
    throw e;
  }
  return r.json();
}

const TEXTO_AVISO = 'Sin conexión con el servidor… reintentando';

function avisoConexion(perdida) {
  const a = document.getElementById('aviso');
  if (!a) return;
  a.textContent = TEXTO_AVISO;
  a.hidden = !perdida;
}

// Un fallo al dibujar no es una pérdida de conexión: se dice claramente y se deja el detalle en la consola.
function avisoError() {
  const a = document.getElementById('aviso');
  if (!a) return;
  a.textContent = 'Error al mostrar la pantalla. Recarga la página (F5).';
  a.hidden = false;
}

// ---------- cuenta atrás ----------
// El servidor envía los segundos restantes en cada consulta; entre consultas
// la cuenta avanza en local. Ese valor no cuenta como "cambio" (ver firma) para
// no redibujar la página cada segundo.
let finCuenta = null;

function formatoTiempo(s) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function pintarCuenta() {
  const e = document.getElementById('cuenta');
  if (!e || finCuenta === null) return;
  const s = Math.max(0, Math.ceil((finCuenta - performance.now()) / 1000));
  e.textContent = formatoTiempo(s);
  e.parentElement.classList.toggle('urgente', s <= 5);
}

function fijarCuenta(restante) {
  finCuenta = restante == null ? null : performance.now() + restante * 1000;
  pintarCuenta();
}
setInterval(pintarCuenta, 250);

function reloj(d) {
  return d.tiempo && el('span', { class: 'reloj' }, el('span', { id: 'cuenta' }, ''));
}

const SIN_ACCESO = 'sin-acceso';

function firma(datos) {
  const c = { ...datos };
  if (c.tiempo) c.tiempo = { total: c.tiempo.total };
  return JSON.stringify(c);
}

// Consulta `url()` cada `ms` y llama a render(datos) solo si algo ha cambiado.
// Si el servidor responde 401 (falta el código de sala o la clave), llama a sinAcceso() una vez
// y sigue consultando: cuando ya haya acceso, la siguiente respuesta se dibuja sola.
// Si el servidor se reinicia (cambia `arranque`) la página se recarga sola: así nunca sigue
// funcionando con un JavaScript antiguo frente a un servidor actualizado.
// Devuelve una función para forzar una consulta inmediata.
function sondear(url, render, ms = 1000, sinAcceso = null) {
  let ultimo = null, timer = null, gen = 0, arranque = null, falloAlDibujar = false;
  async function tick() {
    clearTimeout(timer);
    const mia = ++gen;
    try {
      const datos = await api(url());
      if (mia !== gen) return;
      if (datos.arranque) {
        if (arranque === null) arranque = datos.arranque;
        else if (datos.arranque !== arranque) { location.reload(); return; }
      }
      const s = firma(datos);
      if (s !== ultimo) {
        ultimo = s;
        try { render(datos); falloAlDibujar = false; }
        catch (err) { console.error('Error al dibujar la pantalla:', err); falloAlDibujar = true; }
      }
      fijarCuenta(datos.tiempo ? datos.tiempo.restante : null);
      if (falloAlDibujar) avisoError(); else avisoConexion(false);
    } catch (e) {
      if (mia !== gen) return;
      if (e.status === 401 && sinAcceso) {
        if (ultimo !== SIN_ACCESO) { ultimo = SIN_ACCESO; sinAcceso(); }
        fijarCuenta(null);
        avisoConexion(false);
      } else {
        avisoConexion(true);
      }
    }
    timer = setTimeout(tick, ms);
  }
  tick();
  return tick;
}

// Contenido de una opción: imagen opcional + texto opcional.
function contenidoOpcion(o) {
  return [
    o.imagen && el('img', { class: 'img-opcion', src: o.imagen, alt: '' }),
    o.texto && el('div', { class: 'texto-opcion md' }, formato(o.texto, { enlaces: false })),
  ];
}

// Contenedor del enunciado (formato() puede devolver párrafos, listas…, no vale un <h1>).
function tituloEnunciado(texto, clases) {
  return el('div', { class: 'enunciado md ' + (clases || ''), role: 'heading', 'aria-level': '1' }, formato(texto));
}

// Formulario de un solo campo (código de sala del alumno, clave del docente).
// `enviar(valor)` devuelve null si todo fue bien o el texto del error.
function formularioAcceso({ titulo, ayuda, tipo, clase, enviar }) {
  const campo = el('input', {
    class: 'campo-acceso ' + (clase || ''), type: tipo || 'text', maxlength: 200,
    autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false', 'aria-label': titulo,
  });
  const aviso = el('p', { class: 'estado mal', role: 'alert' });
  const boton = el('button', { class: 'enviar', type: 'submit' }, 'Entrar');
  const form = el('form', { class: 'acceso' },
    el('p', { class: 'eyebrow centrado' }, titulo), campo, boton, aviso,
    ayuda && el('p', { class: 'estado' }, ayuda));
  form.addEventListener('submit', async ev => {
    ev.preventDefault();
    const valor = campo.value.trim();
    if (!valor) return;
    boton.disabled = true;
    aviso.textContent = '';
    const error = await enviar(valor);
    if (error) { aviso.textContent = error; boton.disabled = false; campo.select(); }
  });
  setTimeout(() => campo.focus(), 0);
  return form;
}
