// Markdown para enunciados, opciones y explicaciones.
//
// Construye nodos DOM con el(), createElement y textContent: NUNCA usa innerHTML,
// así que el HTML escrito en el YAML (<b>, <script>…) se muestra literal.
// Los enlaces solo admiten http(s). Las imágenes de Markdown no se admiten
// (se usa el campo `imagen:` de la pregunta): se muestra su texto alternativo.
//
// Bloques: párrafos, encabezados (#), listas (- * + / 1.) anidadas, citas (>),
//   bloques de código (``` o ~~~), reglas (---) y tablas (| a | b |).
// En línea: `código`, *cursiva*, **negrita**, ~~tachado~~, _cursiva_, __negrita__,
//   [texto](https://…) y escapes con \.
// Un salto de línea dentro de un párrafo se respeta (como en los comentarios de GitHub).
// Sin bloques de código por sangría, HTML, notas ni listas de tareas.
//
// formato(texto, { enlaces: true, plano: false })
//   enlaces: false -> el texto de un enlace se muestra sin ser pulsable (opciones).
//   plano: true    -> una sola línea: saltos y bloques se separan con espacios (resumen).

const URL_SEGURA = /^https?:\/\/[^\s<>"]+$/i;
const PUNTUACION = /[\p{P}\p{S}]/u;

const esEspacio = c => c === undefined || c === '' || /\s/.test(c);
const esPuntuacion = c => c !== undefined && c !== '' && PUNTUACION.test(c);
const esAlfanum = c => c !== undefined && c !== '' && /[\p{L}\p{N}]/u.test(c);

// ---------- en línea ----------

// Posición del cierre de un bloque de `código` de `largo` acentos graves, o -1.
function cierreCodigo(txt, desde, largo) {
  let p = txt.indexOf('`', desde);
  while (p >= 0) {
    let q = p;
    while (txt[q] === '`') q++;
    if (q - p === largo) return p;
    p = txt.indexOf('`', q);
  }
  return -1;
}

// Posición del `]` que cierra el `[` de la posición `abre`, o -1.
function cierreCorchete(txt, abre) {
  let prof = 0;
  for (let i = abre; i < txt.length; i++) {
    const c = txt[i];
    if (c === '\\') { i++; continue; }
    if (c === '`') {
      let k = i;
      while (txt[k] === '`') k++;
      const cierre = cierreCodigo(txt, k, k - i);
      if (cierre >= 0) { i = cierre + (k - i) - 1; } else { i = k - 1; }
      continue;
    }
    if (c === '[') prof++;
    else if (c === ']' && --prof === 0) return i;
  }
  return -1;
}

// Lee `(destino "título")` desde `abre`. Devuelve { url, fin } o null.
function destinoEnlace(txt, abre) {
  let prof = 0;
  for (let i = abre; i < txt.length; i++) {
    const c = txt[i];
    if (c === '\\') { i++; continue; }
    if (c === '(') prof++;
    else if (c === ')' && --prof === 0) {
      const url = txt.slice(abre + 1, i).trim().split(/\s+/)[0] || '';
      return { url, fin: i + 1 };
    }
  }
  return null;
}

function aNodos(tokens) {
  const out = [];
  for (const t of tokens) {
    if (typeof t === 'string') out.push(t);
    else if (t.nodo) out.push(...[].concat(t.nodo));
    else if (t.n > 0) out.push(t.ch.repeat(t.n));
  }
  return out;
}

// Reglas de CommonMark: qué delimitadores (* _ ~) pueden abrir o cerrar énfasis.
function delimitador(ch, n, previo, siguiente) {
  const izq = !esEspacio(siguiente) && (!esPuntuacion(siguiente) || esEspacio(previo) || esPuntuacion(previo));
  const der = !esEspacio(previo) && (!esPuntuacion(previo) || esEspacio(siguiente) || esPuntuacion(siguiente));
  let abre = izq, cierra = der;
  if (ch === '_') {
    abre = izq && (!der || esPuntuacion(previo));
    cierra = der && (!izq || esPuntuacion(siguiente));
  }
  return { ch, n, orig: n, abre, cierra };
}

function enfasis(tokens) {
  for (let c = 0; c < tokens.length; c++) {
    const cierre = tokens[c];
    if (typeof cierre === 'string' || !cierre.ch || !cierre.cierra) continue;
    while (cierre.n > 0) {
      let a = c - 1;
      for (; a >= 0; a--) {
        const ap = tokens[a];
        if (typeof ap === 'string' || !ap.ch || ap.ch !== cierre.ch || !ap.abre || ap.n === 0) continue;
        if (cierre.ch === '~' && ap.n !== cierre.n) continue;
        const suma = ap.orig + cierre.orig;
        if ((ap.cierra || cierre.abre) && suma % 3 === 0 && !(ap.orig % 3 === 0 && cierre.orig % 3 === 0)) continue;
        break;
      }
      if (a < 0) break;
      const ap = tokens[a];
      const usa = cierre.ch === '~' ? 2 : (ap.n >= 2 && cierre.n >= 2 ? 2 : 1);
      const etiqueta = cierre.ch === '~' ? 'del' : (usa === 2 ? 'strong' : 'em');
      const dentro = aNodos(tokens.slice(a + 1, c));
      ap.n -= usa;
      cierre.n -= usa;
      tokens.splice(a + 1, c - a - 1, { nodo: el(etiqueta, {}, dentro) });
      c = a + 2; // el nodo nuevo está en a+1; `cierre` sigue en a+2
      if (ap.n === 0) { tokens.splice(a, 1); c--; }
    }
  }
  return aNodos(tokens);
}

function enLinea(txt, o) {
  const tokens = [];
  let buf = '';
  const vaciar = () => { if (buf) { tokens.push(buf); buf = ''; } };
  let i = 0;
  while (i < txt.length) {
    const c = txt[i];
    if (c === '\\' && i + 1 < txt.length && /[!-/:-@[-`{-~]/.test(txt[i + 1])) {
      buf += txt[i + 1]; i += 2; continue;
    }
    if (c === '\n') {
      vaciar();
      tokens.push(o.plano ? ' ' : { nodo: el('br') });
      i++; continue;
    }
    if (c === '`') {
      let k = i;
      while (txt[k] === '`') k++;
      const cierre = cierreCodigo(txt, k, k - i);
      if (cierre < 0) { buf += txt.slice(i, k); i = k; continue; }
      let cod = txt.slice(k, cierre).replace(/\n/g, ' ');
      if (cod.length > 2 && cod[0] === ' ' && cod.endsWith(' ') && cod.trim()) cod = cod.slice(1, -1);
      vaciar();
      tokens.push({ nodo: el('code', {}, cod) });
      i = cierre + (k - i); continue;
    }
    if (c === '[' || (c === '!' && txt[i + 1] === '[')) {
      const imagen = c === '!';
      const abre = imagen ? i + 1 : i;
      const cierre = cierreCorchete(txt, abre);
      const dest = cierre > 0 && txt[cierre + 1] === '(' ? destinoEnlace(txt, cierre + 1) : null;
      if (dest) {
        const etiqueta = txt.slice(abre + 1, cierre);
        vaciar();
        if (imagen) {
          tokens.push(etiqueta);
        } else {
          const hijos = enLinea(etiqueta, { ...o, enlaces: false });
          if (o.enlaces !== false && URL_SEGURA.test(dest.url)) {
            tokens.push({ nodo: el('a', {
              href: dest.url, target: '_blank', rel: 'noopener noreferrer', referrerpolicy: 'no-referrer',
            }, hijos) });
          } else {
            tokens.push({ nodo: hijos });
          }
        }
        i = dest.fin; continue;
      }
    }
    if (c === '*' || c === '_' || c === '~') {
      let k = i;
      while (txt[k] === c) k++;
      const n = k - i;
      if ((c === '~' && n !== 2) || n > 3 && c !== '~') { buf += txt.slice(i, k); i = k; continue; }
      vaciar();
      tokens.push(delimitador(c, n, txt[i - 1], txt[k]));
      i = k; continue;
    }
    buf += c; i++;
  }
  vaciar();
  return enfasis(tokens);
}

// ---------- bloques ----------

const RE_FENCE = /^ {0,3}(`{3,}|~{3,})\s*([^`]*)$/;
const RE_TITULO = /^ {0,3}(#{1,6})(?:\s+(.*?))?(?:\s+#+)?\s*$/;
const RE_REGLA = /^ {0,3}([-*_])(?: *\1){2,} *$/;
const RE_CITA = /^ {0,3}>/;
const RE_ITEM = /^( {0,3})([-*+]|\d{1,9}[.)])( +|$)(.*)$/;
const RE_SEPARADOR = /^ *\|? *:?-+:?(?: *\| *:?-+:? *)*\|? *$/;

const sangria = l => l.length - l.trimStart().length;

function iniciaBloque(l) {
  if (RE_FENCE.test(l) || RE_TITULO.test(l) || RE_REGLA.test(l) || RE_CITA.test(l)) return true;
  const m = RE_ITEM.exec(l);
  // en un párrafo solo interrumpen las listas con contenido y, si son numeradas, la que empieza en 1
  return !!m && m[4].trim() !== '' && (/^[-*+]$/.test(m[2]) || parseInt(m[2], 10) === 1);
}

function celdas(linea) {
  let t = linea.trim();
  if (t.startsWith('|')) t = t.slice(1);
  if (t.endsWith('|') && !t.endsWith('\\|')) t = t.slice(0, -1);
  return t.split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, '|'));
}

function esTabla(lineas, i) {
  if (i + 1 >= lineas.length || !lineas[i].includes('|')) return false;
  if (!RE_SEPARADOR.test(lineas[i + 1]) || !lineas[i + 1].includes('-')) return false;
  if (!lineas[i + 1].includes('|') && !lineas[i].trim().startsWith('|')) return false;
  return celdas(lineas[i]).length === celdas(lineas[i + 1]).length;
}

function tabla(lineas, i, o) {
  const alinear = celdas(lineas[i + 1]).map(c =>
    c.startsWith(':') && c.endsWith(':') ? 'center' : c.endsWith(':') ? 'right' : c.startsWith(':') ? 'left' : '');
  const fila = (linea, tag) => {
    const cs = celdas(linea);
    return el('tr', {}, alinear.map((al, k) => {
      const e = el(tag, {}, enLinea(cs[k] || '', o));
      if (al) e.style.textAlign = al;
      return e;
    }));
  };
  let j = i + 2;
  const cuerpo = [];
  while (j < lineas.length && lineas[j].trim() !== '' && lineas[j].includes('|')) cuerpo.push(fila(lineas[j++], 'td'));
  const t = el('table', {}, el('thead', {}, fila(lineas[i], 'th')), cuerpo.length ? el('tbody', {}, cuerpo) : null);
  return [t, j];
}

function lista(lineas, i, o) {
  const primero = RE_ITEM.exec(lineas[i]);
  const ordenada = /\d/.test(primero[2]);
  const items = [];
  let j = i;
  while (j < lineas.length) {
    const m = RE_ITEM.exec(lineas[j]);
    if (!m || /\d/.test(m[2]) !== ordenada || RE_REGLA.test(lineas[j])) break;
    let espacios = m[3].length;
    if (!m[4].trim() || espacios > 4) espacios = 1;
    const cont = m[1].length + m[2].length + espacios;
    const cuerpo = [m[4]];
    j++;
    while (j < lineas.length) {
      const l = lineas[j];
      if (l.trim() === '') {
        let k = j;
        while (k < lineas.length && lineas[k].trim() === '') k++;
        if (k < lineas.length && sangria(lineas[k]) >= cont) { for (; j < k; j++) cuerpo.push(''); continue; }
        break;
      }
      if (sangria(l) >= cont) { cuerpo.push(l.slice(cont)); j++; continue; }
      if (cuerpo[cuerpo.length - 1].trim() !== '' && !iniciaBloque(l) && !RE_ITEM.test(l)) {
        cuerpo.push(l.trim()); j++; continue; // continuación del párrafo sin sangría
      }
      break;
    }
    items.push(el('li', {}, bloques(cuerpo, o)));
    // los huecos entre elementos no cortan la lista si sigue otro elemento del mismo tipo
    let k = j;
    while (k < lineas.length && lineas[k].trim() === '') k++;
    const sig = k < lineas.length ? RE_ITEM.exec(lineas[k]) : null;
    if (sig && /\d/.test(sig[2]) === ordenada && !RE_REGLA.test(lineas[k])) j = k;
  }
  const inicio = ordenada ? parseInt(primero[2], 10) : 1;
  const e = el(ordenada ? 'ol' : 'ul', { start: ordenada && inicio !== 1 ? inicio : null }, items);
  return [e, j];
}

function bloques(lineas, o) {
  const out = [];
  let i = 0;
  while (i < lineas.length) {
    const l = lineas[i];
    if (l.trim() === '') { i++; continue; }

    let m = RE_FENCE.exec(l);
    if (m) {
      const marca = m[1], sang = sangria(l);
      const cierre = new RegExp(`^ {0,3}${marca[0] === '`' ? '`' : '~'}{${marca.length},}\\s*$`);
      const cod = [];
      i++;
      while (i < lineas.length && !cierre.test(lineas[i])) {
        cod.push(lineas[i].slice(Math.min(sang, sangria(lineas[i])))); i++;
      }
      i++; // línea de cierre (si no hay, se llegó al final)
      out.push(el('pre', {}, el('code', {}, cod.join('\n'))));
      continue;
    }
    m = RE_TITULO.exec(l);
    if (m) {
      out.push(el('h' + Math.min(m[1].length + 1, 6), { class: 'md-t' }, enLinea(m[2] || '', o)));
      i++; continue;
    }
    if (RE_REGLA.test(l)) { out.push(el('hr')); i++; continue; }
    if (RE_CITA.test(l)) {
      const dentro = [];
      while (i < lineas.length && RE_CITA.test(lineas[i])) dentro.push(lineas[i++].replace(/^ {0,3}> ?/, ''));
      out.push(el('blockquote', {}, bloques(dentro, o)));
      continue;
    }
    if (RE_ITEM.test(l)) {
      const [e, j] = lista(lineas, i, o);
      out.push(e); i = j; continue;
    }
    if (esTabla(lineas, i)) {
      const [e, j] = tabla(lineas, i, o);
      out.push(e); i = j; continue;
    }
    const parrafo = [l.trim()];
    i++;
    while (i < lineas.length && lineas[i].trim() !== '' && !iniciaBloque(lineas[i]) && !esTabla(lineas, i)) {
      parrafo.push(lineas[i].trim()); i++;
    }
    out.push(el('p', {}, enLinea(parrafo.join('\n'), o)));
  }
  return out;
}

function formato(texto, opciones) {
  const o = opciones || {};
  const lineas = String(texto).replace(/\r\n?/g, '\n').replace(/\t/g, '    ').split('\n');
  const nodos = bloques(lineas, o);
  if (!o.plano) return nodos;
  return nodos.flatMap((n, k) => (k ? [' ', n] : [n]));
}
