# Pulso del aula

Sondeo anónimo de conocimientos en clase. El docente proyecta una pregunta,
los alumnos responden desde el navegador de su equipo y se muestran los
porcentajes de **aciertos**, **error** y **no lo sé / quiero que se explique**.
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

```bat
git clone https://github.com/Carlos-mb/pulso-del-aula.git
cd pulso-del-aula
py -m venv .venv
.venv\Scripts\pip install -e .
```

Para actualizar más adelante: `git pull` dentro de la carpeta (no hay que reinstalar). Si el servidor
estaba en marcha, hay que pararlo y volver a arrancarlo para que cargue el código nuevo.

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

Opciones: `--preguntas CARPETA` (por defecto `./preguntas`), `--puerto N`, `--host H`.

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
   en la esquina superior derecha, también en la pantalla de los alumnos. Las siguientes preguntas
   también se abren solas al avanzar.
4. La votación se cierra, y se muestran los resultados, en el primero de estos casos:
   - **han votado todos los alumnos conectados** (aunque quede tiempo),
   - se agota el tiempo de la pregunta,
   - el docente la cierra.

   La pantalla indica el motivo (`cerrada: han votado todos`, `cerrada: tiempo agotado`) y, mientras se
   vota, muestra cuántas respuestas hay y cuántos conectados. El cierre por «todos han votado» necesita
   al menos un alumno conectado, y como cierra en el último voto, ese alumno ya no puede cambiar su respuesta.
   Un conectado que no vota mantiene abierta la votación hasta que responda, se agote el tiempo o
   pasen 10 s sin que su navegador consulte al servidor (entonces deja de contar).
5. Tras la última pregunta se muestra el **resumen**: aciertos, errores y «no lo sé» del conjunto
   y de cada pregunta.

**Conectados:** cuenta los navegadores que han consultado al servidor en los últimos 10 segundos
(cada página lo hace cada segundo), identificados solo por su token aleatorio y sin guardar nada más.
Si un alumno cierra la pestaña o pierde la conexión, deja de contar a los 10 s. Un mismo navegador
no cuenta dos veces.

### Controles del docente (una sola vista)

La barra de controles aparece al mover el ratón y se oculta sola a los 3 segundos.

| Tecla | Acción |
|---|---|
| `Espacio` / `Intro` | Sala → empezar el test · votación abierta → cerrarla · cerrada → siguiente pregunta · resumen → volver a los temas |
| `←` / `→` | Pregunta anterior / siguiente (con la votación cerrada) |
| `Esc` | Volver a la lista de temas |
| `1`–`9` | Elegir tema (pantalla inicial) |

- Volver a una pregunta ya cerrada conserva sus resultados y **no** la reabre.
- «Reabrir votación» conserva las respuestas y reinicia el tiempo. Esa pregunta ya no se cierra por
  «han votado todos» (los conectados ya habían votado): solo por tiempo o a mano.
- «Borrar respuestas» deja la pregunta a cero y la abre de nuevo.
- La pantalla se ajusta sola: si el contenido no cabe en la ventana, reduce el tamaño de letra.

## Preguntas

Cada `.yaml` de la carpeta `preguntas/` define uno o varios temas. Ver `preguntas/ejemplo.yaml`.

- **`correcta` cuenta desde 1** (la primera opción es la 1).
- **`tiempo`** (segundos para responder): en el tema es el valor por defecto de sus preguntas; en una
  pregunta lo sustituye (`tiempo: 0` = esa pregunta sin límite). Si no aparece en ninguno, sin límite.
- Las imágenes van en `preguntas/media/` y se referencian por ruta relativa, tanto en el enunciado
  (`imagen:`) como en las opciones.
- La opción «No lo sé / quiero que se explique» la añade el sistema.
- Al arrancar se valida todo y se muestran los errores con fichero, tema y pregunta.

## Anonimato y seguridad

- El navegador del alumno genera un número aleatorio (`localStorage`) que solo sirve para contar un voto
  por pregunta. No se guarda IP ni nada identificable, y no aparece en ninguna pantalla.
- El panel del docente solo responde a conexiones desde el propio equipo del servidor.
  **Si algún día se publica mediante un túnel (modo remoto), esta comprobación deja de proteger**,
  porque el túnel conecta desde `localhost`: habría que añadir una clave.
- La respuesta correcta y la explicación no se envían a los alumnos hasta que se cierra la votación.

## Estilo

Tema oscuro con rejilla tenue, tipografía monoespaciada en títulos, esquinas rectas y ámbar como color de
acción, inspirado en <https://ziggity.dev/>. Usa solo fuentes del sistema, así que funciona sin internet.
Los colores están como variables CSS al principio de `pulso/static/estilos.css`.

## Estructura

```
pulso/tipos.py      tipos de pregunta (una clase por tipo; hoy: una_opcion)
pulso/cargador.py   lectura y validación del YAML (temas, tiempos, imágenes)
pulso/estado.py     estado de la sesión y fases (inicio → sala → abierta → cerrada → resumen), temporizador y presencia
pulso/app.py        rutas FastAPI
pulso/static/       vistas de alumno y docente (JS plano, sin paso de build)
pulso/recursos.py   localiza static/ también cuando se empaquete con PyInstaller
tests/              pytest
```

## Estado

Solo tipo `una_opcion`. Pendiente: verdadero/falso, multiopción (puntuación proporcional penalizando
incorrectas), numérica, Markdown en enunciados, modo remoto, empaquetado.
