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
    throw new Error(msg);
  }
  return r.json();
}

function avisoConexion(perdida) {
  const a = document.getElementById('aviso');
  if (a) a.hidden = !perdida;
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

function firma(datos) {
  const c = { ...datos };
  if (c.tiempo) c.tiempo = { total: c.tiempo.total };
  return JSON.stringify(c);
}

// Consulta `url()` cada `ms` y llama a render(datos) solo si algo ha cambiado.
// Devuelve una función para forzar una consulta inmediata.
function sondear(url, render, ms = 1000) {
  let ultimo = null, timer = null, gen = 0;
  async function tick() {
    clearTimeout(timer);
    const mia = ++gen;
    try {
      const datos = await api(url());
      if (mia !== gen) return;
      const s = firma(datos);
      if (s !== ultimo) { ultimo = s; render(datos); }
      fijarCuenta(datos.tiempo ? datos.tiempo.restante : null);
      avisoConexion(false);
    } catch (_) {
      if (mia !== gen) return;
      avisoConexion(true);
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
    o.texto && el('span', { class: 'texto-opcion' }, o.texto),
  ];
}
