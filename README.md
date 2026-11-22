# Pulso del aula

Sondeo anónimo de conocimientos en clase. El docente proyecta una pregunta,
los alumnos responden desde el navegador de su equipo y se muestran los
porcentajes de **aciertos**, **error** y **no lo sé / quiero que se explique**. También hay
**encuestas**, sin respuesta correcta, para sondear la experiencia u opinión del aula.
Al acabar el test se presenta un resumen de todas las preguntas.

## Instalación

Solo hace falta instalarlo en **un equipo: el del docente**, que actúa de servidor. Los alumnos solo
necesitan un navegador actual (Chrome, Edge o Firefox).

**Requisitos del equipo del docente:** [Git](https://git-scm.com/downloads) y
[Python](https://www.python.org/downloads/) 3.10 o superior (en Windows, al instalar Python se
recomienda marcar «Add python.exe to PATH»). Hace falta internet solo durante la instalación.

**Linux / macOS:**

```bash
git clone https://github.com/Carlos-mb/pulso-del-aula.git
cd pulso-del-aula
python3 -m venv .venv
.venv/bin/pip install -e .
```

**Windows (PowerShell o CMD):**

**Usuarios de Onedrive:** Si vas a sincronizar la carpeta entre diferentes ordenadores, no instales el entorno virtual en .venv

```bat
git clone https://github.com/Carlos-mb/pulso-del-aula.git
cd pulso-del-aula
py -m venv .venv
.venv\Scripts\pip install -e .
```

**Alternativa: lanzadores `pulso.sh` (Linux/macOS) y `pulso.cmd` (Windows).** Solo hace falta Git:
la primera vez descargan `uv` dentro del proyecto (`.tools/` o `tools\`), y `uv` prepara Python y las
dependencias en el entorno virtual que indiques; las siguientes veces lo reutilizan.

```bash
./pulso.sh --venv ~/.venvs/pulsodelaula                  # Linux / macOS
pulso.cmd --venv %USERPROFILE%\.venvs\pulsodelaula       # Windows
./pulso.sh --venv ~/.venvs/pulsodelaula --puerto 8001    # el resto de opciones van a pulso
./pulso.sh -- --help                                     # ayuda de pulso (-h: la del lanzador)
```

Para no escribir `--venv` cada vez, copia `.env.example` como `.env` y ajusta `PULSO_VENV` (`--venv`
tiene prioridad). Si el directorio no existe, el lanzador pregunta antes de crearlo; si existe pero
no es un entorno virtual, no lo toca. Una ruta relativa en `--venv` se toma desde donde lanzas el
script; en `.env`, desde la carpeta del proyecto. Con OneDrive, pon el entorno fuera de la carpeta
sincronizada.

Para actualizar más adelante: `git pull` dentro de la carpeta (no hay que reinstalar). Si el servidor
estaba en marcha, hay que pararlo y volver a arrancarlo para que cargue el código nuevo. Las pantallas
que estuvieran abiertas (docente y alumnos) se recargan solas en cuanto el servidor vuelve a estar en marcha.

## Arrancar

Desde la carpeta del proyecto (`pulso-del-aula`):

```bash
.venv/bin/python -m pulso            # Linux / macOS
.venv\Scripts\python -m pulso        # Windows
```

El programa carga las preguntas de la carpeta `preguntas/`, imprime dos direcciones y se queda
esperando (se para con `Ctrl+C`):

- **Docente** (en el propio equipo del servidor): <http://localhost:8000/docente>. Es la pantalla que
  se proyecta; solo funciona en ese equipo.
- **Alumnos**: la URL que aparece en la sala de espera (`http://IP-del-docente:8000/`).

Opciones: `--preguntas CARPETA` (por defecto `./preguntas`), `--puerto N`, `--host H`, y las del
[modo remoto](#modo-remoto-túnel-de-cloudflare): `--url-publica URL` y `--clave CLAVE`.

### Antes de la primera clase

1. En Windows, la primera vez el firewall pregunta si permite conexiones entrantes: hay que aceptar
   (en red privada).
2. Los equipos de los alumnos deben poder llegar al puerto 8000 del equipo del docente. Prueba antes con
   otro equipo o un móvil de la misma red: abre la URL de la sala de espera y mira si el contador de
   conectados sube.
3. Si la URL que aparece no es una IP de la red del aula (puede elegir una VPN o Docker), averigua la
   IP real con `ip addr` (Linux) o `ipconfig` (Windows) y pásasela a los alumnos.

### Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| Los alumnos no cargan la página | Firewall del equipo del docente, o la red del centro aísla los equipos entre sí |
| El contador de conectados no sube | Igual que arriba, o la IP mostrada no es la de la red del aula |
| `Error en las preguntas:` al arrancar | Algún fichero `.yaml` tiene un error; el mensaje indica fichero, tema y pregunta |
| `address already in use` | El puerto 8000 está ocupado (¿otro servidor en marcha?): usa `--puerto 8001` |
| Tras `git pull` no cambia nada | El servidor sigue ejecutando el código antiguo: páralo y arráncalo de nuevo |

## Desarrollo

```bash
.venv/bin/pip install -e ".[dev]"     # en Windows: .venv\Scripts\pip install -e ".[dev]"
.venv/bin/python -m pytest
```

## Cómo transcurre un test

1. El docente elige un tema (pantalla inicial).
2. **Sala de espera:** se proyecta el número de personas conectadas y la URL de acceso. Los alumnos ven
   «✓ Conectado». Cuando estén todos, el docente pulsa `Espacio` para empezar.
3. **La pregunta se presenta y la votación se abre sola.** Si tiene tiempo, aparece una cuenta atrás
   en la esquina superior derecha, también en la pantalla de los alumnos. El docente puede **pausar el
   tiempo** (botón «Pausar tiempo» o tecla `P`) y reanudarlo después: mientras está en pausa la cuenta
   queda detenida (con ⏸ en ambas pantallas), pero la votación sigue abierta. Las siguientes preguntas
   también se abren solas al avanzar.
   En las [preguntas rápidas](#tipos-de-test-tipos-de-pregunta-y-cómo-se-combinan) primero se proyecta solo
   el enunciado, y la votación y la cuenta atrás empiezan cuando el docente pulsa `Espacio`.
4. La votación se cierra, y se muestran los resultados, en el primero de estos casos:
   - **han votado todos los alumnos conectados** (aunque quede tiempo),
   - se agota el tiempo de la pregunta,
   - el docente la cierra.

   La pantalla indica el motivo (`cerrada: han votado todos`, `cerrada: tiempo agotado`) y, mientras se
   vota, muestra cuántas respuestas hay y cuántos conectados. El cierre por «todos han votado» necesita
   al menos un alumno conectado, y como cierra en el último voto, ese alumno ya no puede cambiar su respuesta.
   Un conectado que no vota mantiene abierta la votación hasta que responda, se agote el tiempo o
   pasen 10 s sin que su navegador consulte al servidor (entonces deja de contar).
   **Excepción: las encuestas.** Si la votación termina porque **han respondido todos**, no se muestran
   resultados: se pasa sola a la siguiente pregunta (o al resumen, si era la última). Sus resultados se ven
   en el resumen, o volviendo a la pregunta con `←`. Si termina por tiempo o porque la cierra el docente,
   se muestran los resultados como en cualquier otra pregunta.
5. Tras la última pregunta se muestra el **resumen**: aciertos, parciales (solo en `multiopcion`), errores y
   «no lo sé» del conjunto y de cada pregunta. Cada pregunta lista además **sus respuestas con el porcentaje
   de alumnos que eligió cada una** (la correcta, con ✓, y «no lo sé» aparte). Las encuestas solo muestran ese
   reparto y no cuentan en el conjunto. El botón **Guardar resumen (.md)** de la barra descarga ese resumen
   en Markdown, como documento de trabajo: solo texto (las imágenes no se incluyen) y el ranking, si lo hay.

### Identificación y ranking (opcional)

Un tema con `modo_competicion: true` deja de ser anónimo: cada alumno elige un **alias** al entrar y hay **ranking**.

```yaml
temas:
  redes:
    titulo: "Redes básicas"
    modo_competicion: true
```

- **Alias:** hasta 20 caracteres, **sin repetidos** (no distingue mayúsculas ni espacios de más). No se puede
  cambiar una vez elegido, ni responder sin él. Si el alumno recarga la página o pierde la conexión, **conserva**
  su alias y sus puntos (el navegador guarda el mismo token). Se pierde si borra los datos del navegador, usa otro
  dispositivo o se reinicia el servidor. Al volver a la lista de temas se olvidan todos los alias.
- **Conectados:** en un tema con identificación solo cuentan los alumnos que ya han puesto el alias. Quien aún
  lo está escribiendo no aparece en el contador ni retrasa el cierre por «han votado todos».
- **Puntos por pregunta:** 100 por acertar (en `multiopcion`, la parte proporcional de la puntuación) y un extra
  de **10, 8, 5, 2 y 1** para los cinco primeros en **acertar del todo**. Las encuestas no puntúan.
- **Orden de llegada:** cuenta el momento del **último envío**. Si un alumno cambia su respuesta, pasa al final
  de la cola; si acertó y luego la cambia a una incorrecta, pierde el acierto y el extra.
- **Ranking:** solo alias y puntos, de más a menos y **sin posiciones**, así que no hay desempate (los empates
  van juntos, por orden alfabético). Entre pregunta y pregunta se proyectan los **5 primeros** (o menos, si hay menos
  participantes), acumulando hasta esa pregunta; con un empate en el quinto puesto se corta ahí. El **resumen** final
  muestra el ranking completo. Los alumnos no reciben el ranking en su pantalla: solo lo ve el docente.

**Conectados:** cuenta los navegadores que han consultado al servidor en los últimos 10 segundos
(cada página lo hace cada segundo), identificados solo por su token aleatorio y sin guardar nada más.
Si un alumno cierra la pestaña o pierde la conexión, deja de contar a los 10 s. Un mismo navegador
no cuenta dos veces.

### Controles del docente (una sola vista)

La barra de controles aparece al mover el ratón y se oculta sola a los 3 segundos.

| Tecla | Acción |
|---|---|
| `Espacio` / `Intro` | Sala → empezar el test · enunciado de una pregunta rápida → mostrar las respuestas · votación abierta → cerrarla · cerrada → siguiente pregunta · resumen → volver a los temas |
| `←` / `→` | Pregunta anterior / siguiente (con la votación cerrada, o en el enunciado de una pregunta rápida) |
| `Esc` | Volver a la lista de temas |
| `1`–`9`, `a`–`z` | Elegir tema (pantalla inicial). Se saltan las letras que son atajos (`H`, `P`): el tema 10 es `a`, el 17 es `i`… |
| `P` | Pausar / reanudar el tiempo (votación abierta con tiempo) |
| `H` | Ocultar / mostrar la barra de controles |

- Volver a una pregunta ya cerrada conserva sus resultados y **no** la reabre.
- «Reabrir votación» conserva las respuestas y reinicia el tiempo. Esa pregunta ya no se cierra por
  «han votado todos» (los conectados ya habían votado): solo por tiempo o a mano.
- «Borrar respuestas» deja la pregunta a cero y la abre de nuevo.
- Si la barra tapa contenido, el botón **Ocultar** (o la tecla `H`) la oculta del todo: al mover el ratón solo
  aparece un botón «▲ Controles» en la esquina para volver a mostrarla (también con `H`). Los atajos de teclado
  siguen funcionando.
- La pantalla se ajusta sola: si el contenido no cabe en la ventana, reduce el tamaño de letra.

## Modo remoto (túnel de Cloudflare)

Para dar la clase con los alumnos conectados **por internet** (desde sus equipos o móviles, sin que lleguen
a la red del docente) se publica el servidor mediante un túnel inverso de Cloudflare:

```
alumnos ──► https://preguntas.ifct0109.online ──► Cloudflare ──► cloudflared (equipo del docente) ──► http://localhost:8000
```

El servidor no se expone directamente: solo `cloudflared`, que corre en el mismo equipo, llega a él.

### Arrancar en modo remoto

```bash
export PULSO_CLAVE='una-clave-larga-y-secreta'          # Windows (PowerShell): $env:PULSO_CLAVE = '...'
.venv/bin/python -m pulso --url-publica https://preguntas.ifct0109.online
```

`--url-publica` activa el modo remoto. Sin esa opción todo funciona como antes (red local, sin código).
En modo remoto:

- La **clave del docente es obligatoria**: si falta (`PULSO_CLAVE` o `--clave`), el servidor no arranca.
  Mejor la variable de entorno, porque `--clave` queda en el historial y en la lista de procesos.
- El servidor escucha solo en `127.0.0.1` (se puede cambiar con `--host`), de modo que nadie lo alcanza
  saltándose el túnel.
- Al arrancar imprime el **código de sala** (6 caracteres, sin `0 O 1 I L`). Vale para toda la sesión y
  **cambia cada vez que se arranca el servidor**.

### Cómo entran los alumnos

En la sala de espera, el docente proyecta un **QR**, la dirección y el **código**. Los alumnos pueden:

- **Leer el QR** con el móvil: la dirección ya lleva el código y entran directamente.
- **Teclear la dirección** en el navegador y escribir el código (admite minúsculas, espacios y guiones).

El código se comprueba una vez por alumno. Si el servidor se reinicia, el código cambia y a los alumnos
se les vuelve a pedir. La dirección y el código también aparecen en el pie de la pantalla durante la votación.
Sin el código no se puede ver el estado, votar ni contar como conectado.

### Panel del docente

El docente abre <http://localhost:8000/docente> en su equipo e introduce la **clave** (se pide siempre, también
en `localhost`, porque el túnel hace que cualquier petición parezca local; queda recordada en una cookie
durante 12 horas). El panel también se puede abrir por la dirección pública, con la misma clave.

### Configurar el túnel (una sola vez)

Con [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
instalado, y el dominio gestionado en Cloudflare:

```bash
cloudflared tunnel login                                   # autoriza la cuenta y el dominio
cloudflared tunnel create pulso                            # crea el túnel y su fichero de credenciales
cloudflared tunnel route dns pulso preguntas.ifct0109.online
```

Fichero `~/.cloudflared/config.yml`:

```yaml
tunnel: pulso
credentials-file: /home/USUARIO/.cloudflared/ID-DEL-TUNEL.json
ingress:
  - hostname: preguntas.ifct0109.online
    service: http://localhost:8000
  - service: http_status:404
```

Cada clase: arrancar el túnel (`cloudflared tunnel run pulso`) y el servidor (comando de arriba). Para probar
antes de tener el dominio, un túnel temporal da una dirección `https://….trycloudflare.com` sin configurar nada:
`cloudflared tunnel --url http://localhost:8000` (y pasar esa dirección a `--url-publica`).

### Seguridad

- **Código de sala** (≈ 9·10⁸ combinaciones). Los intentos erróneos se limitan **en conjunto** (120 por minuto
  entre todos), no por IP, porque todos los alumnos del aula salen con la misma IP pública. Si se supera,
  las entradas nuevas se rechazan durante un minuto (incluso con el código bueno); los alumnos que ya han
  entrado no se ven afectados.
- **Clave del docente**: se compara en tiempo constante y se limita a 10 fallos por minuto para cada origen
  (la IP real que indica Cloudflare en `Cf-Connecting-Ip`; el propio equipo del docente cuenta aparte).
  La cookie es `HttpOnly` y `SameSite=Strict` (y `Secure` cuando llega por el túnel).
- Los alumnos siguen siendo anónimos (salvo el alias, en los temas con identificación): se guarda un token aleatorio y nada más; no se guarda la IP.
- Las consultas cada segundo de cada alumno pasan por Cloudflare: con una clase normal (decenas de alumnos)
  es un tráfico pequeño. Las páginas se sirven con `Cache-Control: no-cache`; si tras actualizar
  el programa los alumnos siguen viendo una versión antigua, purga la caché del dominio en Cloudflare.
- En el panel de Cloudflare se pueden añadir reglas propias (límite de peticiones, WAF) sin tocar nada aquí.

## Preguntas

Cada `.yaml` de la carpeta `preguntas/` define uno o varios temas. Ver `preguntas/ejemplo.yaml`.

- **`correcta` cuenta desde 1** (la primera opción es la 1).
- **`modo_competicion`** (`true`/`false`, en el tema): alias de los alumnos y ranking; ver [Identificación y ranking](#identificación-y-ranking-opcional).
- **`tiempo`** (segundos para responder): en el tema es el valor por defecto de sus preguntas; en una
  pregunta lo sustituye (`tiempo: 0` = esa pregunta sin límite). Si no aparece en ninguno, sin límite.
- Las imágenes van en `preguntas/media/` y se referencian por ruta relativa, tanto en el enunciado
  (`imagen:`) como en las opciones.
- Los enunciados, las opciones y las explicaciones admiten **Markdown**:
  - en línea: `` `código` ``, `*cursiva*` / `_cursiva_`, `**negrita**` / `__negrita__`, `~~tachado~~`
    y `[texto](https://…)` (solo enlaces `http` y `https`);
  - bloques: párrafos, encabezados (`#`), listas (`-`, `1.`, también anidadas), citas (`>`), bloques de
    código (con ```` ``` ````), reglas (`---`) y tablas (`| a | b |`).

  Un salto de línea se respeta tal cual (no hace falta dejar dos espacios). Para varias líneas, usa un
  bloque YAML (`texto: |`). Si el valor empieza por `` ` `` o `*`, entrecomíllalo en el YAML. En el resumen
  final cada pregunta ocupa una línea, con el Markdown aplanado.
  Las imágenes de Markdown (`![](…)`) **no** se admiten: usa `imagen:`. Tampoco hay HTML: `<b>` o
  `<script>` se muestran literales. Los enlaces de las opciones no se pueden pulsar.
  Los nombres con guion bajo (`mi_variable`) se respetan, pero `__init__` se lee como negrita:
  pónlo entre acentos graves.
- La opción «No lo sé / quiero que se explique» la añade el sistema en las preguntas de test.

### Tipos de test, tipos de pregunta y cómo se combinan

Cada pregunta se configura en dos niveles: **el tema (test)**, que da valores por defecto a todas sus
preguntas, y **la propia pregunta**, que puede sustituirlos. Son configuraciones independientes que se
combinan entre sí.

**Tipos de test (pulso):** un tema es **normal** o **rápido** (`rapido: true`; por defecto, normal).
Por separado, puede ser anónimo o de **competición** (`modo_competicion: true`). Las dos cosas se
pueden combinar: un test rápido de competición es válido.

**Tipos de pregunta** (`tipo:` en la pregunta; por defecto `una_opcion`):

| `tipo` | Respuesta | Puntúa |
|---|---|---|
| `una_opcion` | una opción, con una correcta | sí |
| `multiopcion` | varias opciones, con varias correctas | sí, proporcional |
| `encuesta` | una opción (o varias con `multiple: true`), sin correcta | no |

**Preguntas rápidas.** En una pregunta rápida primero se proyecta **solo el enunciado**, también en la
pantalla de los alumnos, sin las opciones y sin que se pueda responder. Cuando el docente pulsa
`Espacio` / `Intro` (o el botón «Mostrar respuestas»), aparecen las opciones, se abre la votación y
**empieza la cuenta atrás**. A partir de ahí funciona como cualquier otra pregunta. Las opciones no se
envían a los alumnos hasta ese momento. Sirven para pruebas de velocidad.

**Herencia y combinación:**

| Configuración | En el tema | En la pregunta | Si no aparece |
|---|---|---|---|
| `tiempo` | valor por defecto de sus preguntas | lo sustituye (`0` = sin límite) | sin límite |
| `rapido` | valor por defecto de sus preguntas **de test** (`una_opcion`, `multiopcion`) | lo sustituye (`true` / `false`) | normal |
| `modo_competicion` | alias y ranking para todo el test | no se admite | anónimo |
| `tipo` | no se admite | tipo de la pregunta | `una_opcion` |

- **Encuestas en un tema rápido:** son **normales**, porque no heredan el `rapido` del tema.
- **El tiempo de una pregunta rápida** es el suyo (`tiempo` de la pregunta o, si no tiene, el del tema), y
  se cuenta desde que aparecen las respuestas, no desde que se proyecta el enunciado.
- **Una pregunta rápida necesita tiempo:** si la pregunta queda rápida (por herencia o explícitamente) y su
  tiempo resulta `0` o no hay, el servidor **no arranca** y da error con fichero, tema y pregunta.
- **Una encuesta no puede ser rápida:** `rapido: true` en una encuesta da error al arrancar.
- **En el enunciado** el docente puede cambiar de pregunta (`←` / `→`, o «Saltar pregunta») sin mostrar las
  respuestas; esa pregunta no queda cerrada, así que al volver a ella se presenta de nuevo.
- **Reabrir una pregunta rápida** vuelve a mostrar solo el enunciado y espera a que el docente pulse la
  tecla; las respuestas que ya había se conservan. «Borrar respuestas» también vuelve al enunciado.
- **Competición:** no cambia. El extra por rapidez depende del orden de llegada de las respuestas, no de
  los segundos; como durante el enunciado no se puede responder, el orden empieza a contar al mostrar las
  respuestas.

```yaml
temas:
  velocidad:
    titulo: "Repaso rápido"
    rapido: true            # sus preguntas de test son rápidas
    tiempo: 10              # 10 s desde que aparecen las respuestas
    preguntas:
      - texto: "¿Puerto de HTTPS?"
        opciones: ["80", "443", "22"]
        correcta: 2
      - texto: "¿Qué protocolo resuelve nombres de dominio?"
        rapido: false       # esta, normal
        tiempo: 0           # y sin límite
        opciones: ["DHCP", "DNS", "ARP"]
        correcta: 2
      - tipo: encuesta      # no hereda `rapido`: es normal
        texto: "¿Te ha resultado fácil?"
        opciones: ["Sí", "Regular", "No"]
```

### Encuestas

Una pregunta con `tipo: encuesta` sirve para empezar la sesión viendo el nivel de partida de la clase,
o para pedir una opinión. **No tiene respuesta correcta**: no lleva `correcta` (si se pone, da error).

```yaml
- tipo: encuesta
  texto: "La terminal de Linux"
  opciones: ["Nunca", "Lo he visto", "Lo he usado alguna vez", "Lo uso con soltura"]
```

- Cada alumno elige **una opción** (o varias, con `multiple: true`; ver abajo). La votación se cierra cuando
  han respondido todos, se agota el tiempo o la cierra el docente. En el primer caso **pasa sola a la
  siguiente pregunta**, sin mostrar resultados.
- Los resultados muestran el **reparto por opción** (número y porcentaje). No hay aciertos ni error,
  y el alumno no recibe ninguna solución, solo la confirmación de que su respuesta quedó registrada.
- «No lo sé / quiero que se explique» **no se añade**. Se activa con `nose: true`.
- En el resumen final se ve su reparto (cada respuesta con su porcentaje), pero **no cuentan** en los aciertos, errores y «no lo sé»
  del conjunto. Se pueden mezclar con preguntas de test en un mismo tema.
- Al arrancar se valida todo y se muestran los errores con fichero, tema y pregunta.

### Varias opciones marcables

El alumno puede marcar **varias opciones** en una misma pregunta, tanto en encuestas como en preguntas con
respuesta correcta.

```yaml
# Encuesta: el alumno marca todas las opciones que correspondan.
- tipo: encuesta
  multiple: true
  texto: "Estudios o trabajo previos (marca todos los que correspondan)"
  opciones: ["Ninguno", "Curso o FP", "Universidad", "He trabajado en el sector"]

# Test: varias opciones correctas (`correcta` es una lista, desde 1).
- tipo: multiopcion
  texto: "¿Cuáles de estas direcciones son IPv4 privadas?"
  opciones: ["10.0.0.5", "8.8.8.8", "192.168.1.20", "172.16.4.9"]
  correcta: [1, 3, 4]
```

- **Pantalla del alumno:** casillas en lugar de botones excluyentes y un botón **Enviar**. Hasta enviar
  se puede cambiar lo marcado, y después de enviar también se puede cambiar y volver a enviar mientras
  la votación siga abierta. Lo marcado y no enviado no cuenta.
- **«Han votado todos»** se cuenta cuando cada alumno ha **enviado**, no al marcar.
- **«No lo sé / quiero que se explique»** es exclusiva: al marcarla se desmarcan las demás y al marcar otra
  opción se desmarca ella. En una encuesta solo existe con `nose: true`. No se puede enviar sin marcar nada:
  para contestar «ninguna» se marca «no lo sé» (si está activa) o una opción como «Ninguno».
- **Encuestas:** el resultado es el **porcentaje de alumnos que marcaron cada opción**. Los porcentajes no
  suman 100 %, porque cada alumno puede marcar varias. Sin aciertos ni errores, y no cuentan en el conjunto.
- **`multiopcion`:** la puntuación va de 0 a 1 y es proporcional penalizando las incorrectas:
  (correctas marcadas − incorrectas marcadas) / total de correctas, con mínimo 0. Categorías:
  **acierto** (todas las correctas y ninguna incorrecta), **parcial** (puntuación entre 0 y 1),
  **error** (puntuación 0) y **no lo sé**. «Parcial» se muestra aparte, también en el resumen del conjunto,
  donde cada pregunta cuenta como una respuesta por alumno. La pantalla del docente marca todas las
  correctas con ✓ y muestra el porcentaje de marcas de cada opción.
- **Validación:** al menos 2 opciones; `correcta` en `multiopcion` es una lista no vacía, sin repetidos y
  dentro del rango (con un número suelto da error). `multiple` no se admite en `una_opcion` ni en `multiopcion`
  (da un error que remite a `tipo: multiopcion`); en `una_opcion`, `correcta` sigue siendo un solo número.
- Funciona con el Markdown y las imágenes de las opciones.

## Anonimato y seguridad

- El navegador del alumno genera un número aleatorio (`localStorage`) que solo sirve para contar un voto
  por pregunta. No se guarda IP ni nada identificable, y no aparece en ninguna pantalla.
  Solo en los temas con [identificación](#identificación-y-ranking-opcional) se guarda además el alias
  que elige el alumno, y se muestra en el ranking.
- En modo local, el panel del docente solo responde a conexiones desde el propio equipo del servidor
  (se puede añadir además una clave con `PULSO_CLAVE`). **Esa comprobación no protege detrás de un
  túnel**, porque el túnel conecta desde `localhost`: por eso el [modo remoto](#modo-remoto-túnel-de-cloudflare)
  exige clave y código de sala. No publiques el servidor con un túnel sin usar `--url-publica`.
- La respuesta correcta y la explicación no se envían a los alumnos hasta que se cierra la votación.

## Estilo

Tema oscuro con rejilla tenue, tipografía monoespaciada en títulos, esquinas rectas y ámbar como color de
acción, inspirado en <https://ziggity.dev/>. Usa solo fuentes del sistema, así que funciona sin internet.
Los colores están como variables CSS al principio de `pulso/static/estilos.css`.

## Estructura

```
pulso/acceso.py     modo remoto: código de sala, clave del docente, límites de intentos y QR
pulso/tipos.py      tipos de pregunta (una clase por tipo; hoy: una_opcion, multiopcion y encuesta)
pulso/cargador.py   lectura y validación del YAML (temas, tiempos, imágenes)
pulso/estado.py     estado de la sesión y fases (inicio → sala → [enunciado →] abierta → cerrada → resumen), temporizador y presencia
pulso/app.py        rutas FastAPI
pulso/informe.py    resumen final en Markdown (botón «Guardar resumen»)
pulso/static/       vistas de alumno y docente (JS plano, sin paso de build); markdown.js es el Markdown
pulso/recursos.py   localiza static/ también cuando se empaquete con PyInstaller
tests/              pytest (las pruebas del Markdown están en JavaScript: se ejecutan con Node si está instalado)
```

## Estado

Tipos: `una_opcion`, `multiopcion` y `encuesta` (esta, con una opción o con varias). Modo remoto con túnel de
Cloudflare, código de sala y QR. Preguntas rápidas. Pendiente: verdadero/falso, numérica, empaquetado.
