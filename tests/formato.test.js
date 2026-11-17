// Pruebas de pulso/static/markdown.js con un DOM mínimo simulado (sin navegador).
// Se ejecutan con `node tests/formato.test.js` (también desde pytest, si hay node).
const fs = require('fs');
const path = require('path');
const assert = require('assert');

class Nodo {
  constructor(tag) { this.tag = tag; this.hijos = []; this.attrs = {}; this.style = {}; this.className = ''; }
  append(...h) { for (const x of h) this.hijos.push(x); }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener() {}
}
global.document = { createElement: t => new Nodo(t) };
global.performance = { now: () => 0 };
global.setInterval = () => {};

const estaticos = path.join(__dirname, '..', 'pulso', 'static');
const codigo = ['comun.js', 'markdown.js']
  .map(f => fs.readFileSync(path.join(estaticos, f), 'utf8')).join('\n');
const formato = new Function(codigo + '; return formato;')();

// Serializa a una cadena legible; el texto se escapa para ver que NO es HTML real.
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function ser(n) {
  if (typeof n === 'string') return esc(n);
  const at = Object.entries(n.className ? { class: n.className, ...n.attrs } : n.attrs)
    .filter(([k]) => k !== 'rel' && k !== 'target' && k !== 'referrerpolicy')
    .map(([k, v]) => ` ${k}="${v}"`).join('');
  const al = n.style.textAlign ? ` align=${n.style.textAlign}` : '';
  return `<${n.tag}${at}${al}>${n.hijos.map(ser).join('')}</${n.tag}>`;
}
const md = (t, o) => formato(t, o).map(ser).join('');

const casos = [
  // --- en línea
  ['`código`', '<p><code>código</code></p>'],
  ['*cursiva* y _cursiva_', '<p><em>cursiva</em> y <em>cursiva</em></p>'],
  ['**negrita** y __negrita__', '<p><strong>negrita</strong> y <strong>negrita</strong></p>'],
  ['***ambas***', '<p><em><strong>ambas</strong></em></p>'],
  ['**negrita con *cursiva* dentro**', '<p><strong>negrita con <em>cursiva</em> dentro</strong></p>'],
  ['*cursiva con **negrita** dentro*', '<p><em>cursiva con <strong>negrita</strong> dentro</em></p>'],
  ['~~tachado~~', '<p><del>tachado</del></p>'],
  ['`*no cursiva*` y `<b>`', '<p><code>*no cursiva*</code> y <code>&lt;b&gt;</code></p>'],
  ['`` con ` dentro ``', '<p><code>con ` dentro</code></p>'],
  ['\\*no\\* y \\`no\\`', '<p>*no* y `no`</p>'],
  ['ruta `/home/ana/informe.txt` ok', '<p>ruta <code>/home/ana/informe.txt</code> ok</p>'],
  // --- lo que NO debe interpretarse
  ['2 * 3 * 4 = 24', '<p>2 * 3 * 4 = 24</p>'],
  ['variable snake_case_nombre y __init__.py', '<p>variable snake_case_nombre y <strong>init</strong>.py</p>'],
  ['mi_variable_larga', '<p>mi_variable_larga</p>'],
  ['Una `marca sin cerrar', '<p>Una `marca sin cerrar</p>'],
  ['Un *cursiva sin cerrar', '<p>Un *cursiva sin cerrar</p>'],
  ['**sin cerrar', '<p>**sin cerrar</p>'],
  ['****', '<hr></hr>'],
  // --- seguridad: HTML literal
  ['Texto con <b>negrita</b> y <script>alert(1)</script>',
    '<p>Texto con &lt;b&gt;negrita&lt;/b&gt; y &lt;script&gt;alert(1)&lt;/script&gt;</p>'],
  ['<img src=x onerror=alert(1)>', '<p>&lt;img src=x onerror=alert(1)&gt;</p>'],
  ['**<b>x</b>**', '<p><strong>&lt;b&gt;x&lt;/b&gt;</strong></p>'],
  // --- enlaces e imágenes
  ['[Python](https://python.org)', '<p><a href="https://python.org">Python</a></p>'],
  ['[x](javascript:alert(1))', '<p>x</p>'],
  ['[x](JAVASCRIPT:alert(1))', '<p>x</p>'],
  ['[x](data:text/html;base64,AAAA)', '<p>x</p>'],
  ['[x](/ruta/relativa)', '<p>x</p>'],
  ['[**x**](https://a.es/b_(c))', '<p><a href="https://a.es/b_(c)"><strong>x</strong></a></p>'],
  ['![alt](http://evil/x.png)', '<p>alt</p>'],
  ['[corchetes] sueltos [y (paréntesis)]', '<p>[corchetes] sueltos [y (paréntesis)]</p>'],
  // --- bloques
  ['Línea 1\nLínea 2', '<p>Línea 1<br></br>Línea 2</p>'],
  ['Párrafo uno\n\nPárrafo dos', '<p>Párrafo uno</p><p>Párrafo dos</p>'],
  ['# Título\ntexto', '<h2 class="md-t">Título</h2><p>texto</p>'],
  ['###### seis', '<h6 class="md-t">seis</h6>'],
  ['#hashtag no es título', '<p>#hashtag no es título</p>'],
  ['---', '<hr></hr>'],
  ['> cita\n> más *cursiva*', '<blockquote><p>cita<br></br>más <em>cursiva</em></p></blockquote>'],
  ['```\nls -l\n  uno\n```', '<pre><code>ls -l\n  uno</code></pre>'],
  ['```bash\necho "<hola>"\n```', '<pre><code>echo "&lt;hola&gt;"</code></pre>'],
  ['~~~\na `b`\n~~~', '<pre><code>a `b`</code></pre>'],
  ['```\nsin cerrar\nmás', '<pre><code>sin cerrar\nmás</code></pre>'],
  ['```\n# no título\n- no lista\n```', '<pre><code># no título\n- no lista</code></pre>'],
  // --- listas
  ['- a\n- b\n- c', '<ul><li><p>a</p></li><li><p>b</p></li><li><p>c</p></li></ul>'],
  ['1. uno\n2. dos', '<ol><li><p>uno</p></li><li><p>dos</p></li></ol>'],
  ['3. tres\n4. cuatro', '<ol start="3"><li><p>tres</p></li><li><p>cuatro</p></li></ol>'],
  ['- a\n  - b\n  - c\n- d',
    '<ul><li><p>a</p><ul><li><p>b</p></li><li><p>c</p></li></ul></li><li><p>d</p></li></ul>'],
  ['Elige:\n- a\n- b', '<p>Elige:</p><ul><li><p>a</p></li><li><p>b</p></li></ul>'],
  ['- a\n\n- b', '<ul><li><p>a</p></li><li><p>b</p></li></ul>'],
  ['- a\n\n  más de a\n- b', '<ul><li><p>a</p><p>más de a</p></li><li><p>b</p></li></ul>'],
  ['- paso\n  ```\n  ls\n  ```', '<ul><li><p>paso</p><pre><code>ls</code></pre></li></ul>'],
  ['Versión 2.\nOtra línea', '<p>Versión 2.<br></br>Otra línea</p>'],
  ['Es de 2020.\n2. no interrumpe', '<p>Es de 2020.<br></br>2. no interrumpe</p>'],
  ['1.5 litros', '<p>1.5 litros</p>'],
  ['-guion pegado', '<p>-guion pegado</p>'],
  // --- tablas
  ['| a | b |\n|---|:-:|\n| 1 | `x` |',
    '<table><thead><tr><th>a</th><th align=center>b</th></tr></thead><tbody><tr><td>1</td><td align=center><code>x</code></td></tr></tbody></table>'],
  ['a | b\n- | -\n1 | 2',
    '<table><thead><tr><th>a</th><th>b</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>'],
  ['uno | dos\n---', '<p>uno | dos</p><hr></hr>'],  // sin encabezados setext: --- es una regla
  // --- saltos de línea y espacios
  ['a\r\nb', '<p>a<br></br>b</p>'],
  ['   \n\n', ''],
  ['', ''],
];

let fallos = 0;
for (const [entrada, esperado] of casos) {
  let obtenido;
  try { obtenido = md(entrada); } catch (e) { obtenido = 'EXCEPCIÓN: ' + e.stack; }
  if (obtenido !== esperado) {
    fallos++;
    console.log(`FALLO ${JSON.stringify(entrada)}\n  esperado: ${esperado}\n  obtenido: ${obtenido}`);
  }
}

// opciones: enlaces desactivados y modo plano
assert.strictEqual(md('[x](https://a.es)', { enlaces: false }), '<p>x</p>');
assert.strictEqual(
  formato('a\nb\n\n- c\n- d', { plano: true }).map(ser).join(''),
  '<p>a b</p> <ul><li><p>c</p></li><li><p>d</p></li></ul>');

// robustez: ninguna entrada rara debe lanzar una excepción ni colgarse
const raros = ['*'.repeat(500), '`'.repeat(300), '['.repeat(200), '- '.repeat(200), '>'.repeat(100),
  '|'.repeat(50) + '\n' + '-|'.repeat(50), '_a_*b*~~c~~'.repeat(100), '\\', '[a](', '[a](b', '![', '1)', '#',
  '* * *\n- - -', '- \n-\n- x', '|\n|-\n|'];
for (const r of raros) {
  try { md(r); } catch (e) { fallos++; console.log('EXCEPCIÓN con', JSON.stringify(r.slice(0, 30)), e.message); }
}

if (fallos) { console.log(`${fallos} fallo(s)`); process.exit(1); }
console.log(`ok: ${casos.length} casos`);
