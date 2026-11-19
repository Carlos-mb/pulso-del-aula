"""Estado de la sesión de clase (en memoria).

Fases:
    inicio  -> el docente aún no ha elegido tema
    sala    -> tema elegido; se espera a que se conecten los alumnos
    abierta -> pregunta presentada y votación abierta (se abre sola)
    cerrada -> votación cerrada; se muestran los resultados
    resumen -> test terminado; se muestra el resumen de todas las preguntas

Una votación se cierra sola en dos casos: cuando se agota el tiempo de la
pregunta (si lo tiene) y cuando han votado todos los alumnos conectados. En una
encuesta, además, al cerrarse porque han respondido todos se pasa sola a la
siguiente pregunta (o al resumen, si era la última): sus resultados se ven en el resumen.
Se comprueba al atender cada petición (los clientes consultan cada segundo),
así que no hace falta ningún hilo temporizador. Si el docente reabre una
pregunta, esta ya no se cierra por «todos han votado» (solo por tiempo o a mano).

Todos los métodos son síncronos y se llaman desde corrutinas sin `await`
intermedios, así que no hace falta bloqueo.
"""
from __future__ import annotations

import secrets
import time
from typing import Any, Callable

from .acceso import Bloqueado, CodigoIncorrecto, LimiteFallos, NoAdmitido, coincide, normaliza_codigo
from .cargador import Tema
from .tipos import PreguntaBase

# Un alumno cuenta como conectado si ha consultado el servidor hace menos de
# estos segundos (la página lo hace cada segundo).
SEGUNDOS_PRESENCIA = 10.0

# Modo remoto: máximo de alumnos admitidos, y de códigos erróneos por minuto entre todos
# (los alumnos del aula comparten IP, así que no se puede limitar por IP).
MAX_ADMITIDOS = 1000
FALLOS_CODIGO_POR_MINUTO = 120

# Puntuación (solo en los tests con identificación): 100 por pregunta acertada, o la parte
# proporcional si es de varias opciones, y un extra para los primeros en acertar del todo.
PUNTOS_ACIERTO = 100
BONUS_ORDEN = (10, 8, 5, 2, 1)
MAX_ALIAS = 20
TAM_RANKING = 5   # alumnos que se muestran entre pregunta y pregunta


class EstadoInvalido(Exception):
    """La acción no es posible en la fase actual."""


class Sesion:
    def __init__(
        self,
        temas: dict[str, Tema],
        url_alumnos: str = "",
        reloj: Callable[[], float] = time.monotonic,
        codigo: str | None = None,
    ) -> None:
        self.temas = temas
        self.url_alumnos = url_alumnos
        self.reloj = reloj
        # Identifica esta ejecución del servidor: si cambia, las páginas abiertas se recargan solas.
        self.arranque = secrets.token_hex(4)
        # Modo remoto: código de sala que hay que dar para participar. None = red local, sin código.
        self.codigo = codigo
        self.admitidos: set[str] = set()
        self.limite_codigo = LimiteFallos(FALLOS_CODIGO_POR_MINUTO, 60.0, reloj)
        # Presencia anónima: {token: instante de la última consulta}. Solo en memoria.
        self.vistos: dict[str, float] = {}
        self._ultima_poda = reloj()
        self.inicio()

    # ---------- acciones del docente ----------
    def inicio(self) -> None:
        self.tema: Tema | None = None
        self.indice = 0
        self.fase = "inicio"
        # {id_pregunta: {token: respuesta}}
        self.respuestas: dict[str, dict[str, Any]] = {}
        # preguntas ya cerradas -> motivo ("docente" | "tiempo" | "todos"); no se reabren al navegar
        self.cerradas: dict[str, str] = {}
        self.limite: float | None = None  # instante en que se agota el tiempo
        self.duracion = 0
        self.cierre_auto = True  # ¿se cierra al votar todos los conectados?
        # Alias de los alumnos (solo en los tests con identificación): {token: alias}
        self.alias: dict[str, str] = {}

    def elegir_tema(self, tema_id: str) -> None:
        if tema_id not in self.temas:
            raise ValueError(f"tema desconocido: {tema_id}")
        self.inicio()
        self.tema = self.temas[tema_id]
        self.fase = "sala"

    def empezar(self) -> None:
        """Borra las respuestas anteriores y presenta la primera pregunta."""
        if self.fase != "sala":
            raise EstadoInvalido("El test ya ha empezado")
        self.respuestas.clear()
        self._ir_a(0)

    def cerrar(self) -> None:
        self._tic(avanzar=False)
        if self.tema is None:
            raise EstadoInvalido("No hay tema elegido")
        if self.fase == "abierta":
            self._cerrar_pregunta("docente")
        # si ya estaba cerrada (p. ej. se agotó el tiempo justo ahora) no hay nada que hacer

    def abrir(self) -> None:
        """Reabre una pregunta cerrada, conservando sus respuestas y reiniciando su tiempo.

        Como los conectados ya habían votado, no se vuelve a cerrar por «todos han
        votado»: se cierra por tiempo o cuando lo decida el docente.
        """
        self._tic(avanzar=False)
        if self.fase != "cerrada":
            raise EstadoInvalido("Solo se puede reabrir una pregunta cerrada")
        self.cerradas.pop(self.pregunta.id, None)
        self._abrir_pregunta(cierre_auto=False)

    def reiniciar(self) -> None:
        """Borra las respuestas de la pregunta actual y la abre de nuevo."""
        self._tic(avanzar=False)
        if self.fase not in ("abierta", "cerrada"):
            raise EstadoInvalido("No hay una pregunta activa")
        self.respuestas.pop(self.pregunta.id, None)
        self.cerradas.pop(self.pregunta.id, None)
        self._abrir_pregunta()

    def siguiente(self) -> None:
        self._navegar(+1)

    def anterior(self) -> None:
        self._navegar(-1)

    # ---------- acceso de los alumnos (modo remoto) ----------
    def admitir(self, token: str, codigo: str) -> None:
        """Da por válido el token de un alumno si el código de sala es correcto.

        Se comprueba una vez por alumno; después basta el token. Con muchos fallos seguidos
        (de cualquiera) se rechaza todo intento nuevo, incluso con el código bueno, hasta
        que pase un minuto: los alumnos ya admitidos no se ven afectados.
        """
        if self.codigo is None or token in self.admitidos:
            return
        if not 8 <= len(token) <= 64:
            raise ValueError("token no válido")
        if self.limite_codigo.bloqueado():
            raise Bloqueado
        if not coincide(normaliza_codigo(codigo), self.codigo):
            self.limite_codigo.fallo()
            raise CodigoIncorrecto
        if len(self.admitidos) >= MAX_ADMITIDOS:
            raise EstadoInvalido("La sala está llena")
        self.admitidos.add(token)

    def exige_admitido(self, token: str | None) -> None:
        if self.codigo is not None and (token is None or token not in self.admitidos):
            raise NoAdmitido

    # ---------- identificación (alias) ----------
    @property
    def identificacion(self) -> bool:
        return self.tema is not None and self.tema.identificacion

    def poner_alias(self, token: str, alias: str) -> None:
        """Registra el alias del alumno. No se admiten repetidos (sin distinguir mayúsculas)."""
        self.exige_admitido(token)
        if not self.identificacion:
            raise EstadoInvalido("Este test no pide alias")
        limpio = " ".join(alias.split())
        if not limpio:
            raise ValueError("Escribe un alias")
        if len(limpio) > MAX_ALIAS:
            raise ValueError(f"El alias admite como máximo {MAX_ALIAS} caracteres")
        if not limpio.isprintable():
            raise ValueError("El alias tiene caracteres no válidos")
        clave = limpio.casefold()
        actual = self.alias.get(token)
        if actual is not None:
            if actual.casefold() == clave:   # reenvío del mismo formulario
                return
            raise EstadoInvalido("Ya tienes un alias")
        if any(a.casefold() == clave for a in self.alias.values()):
            raise ValueError("Ese alias ya está en uso: elige otro")
        if len(self.alias) >= MAX_ADMITIDOS:
            raise EstadoInvalido("La sala está llena")
        self.alias[token] = limpio

    def _puntos_pregunta(self, p: PreguntaBase) -> dict[str, int]:
        """Puntos de cada alumno en una pregunta (las encuestas no puntúan).

        100 por acierto, o la parte proporcional en las de varias opciones. Los cinco primeros
        en acertar del todo suman además 10, 8, 5, 2 y 1. El orden es el del último envío de cada
        alumno (`responder` coloca cada respuesta al final): quien cambia su respuesta pasa al final.
        """
        if not p.puntua:
            return {}
        puntos: dict[str, int] = {}
        aciertos = 0
        for token, r in self.respuestas.get(p.id, {}).items():
            categoria, nota = p.evaluar(r)
            pts = round(PUNTOS_ACIERTO * nota)
            if categoria == "acierto":
                if aciertos < len(BONUS_ORDEN):
                    pts += BONUS_ORDEN[aciertos]
                aciertos += 1
            puntos[token] = pts
        return puntos

    def ranking(self, hasta: int) -> list[dict]:
        """Puntos acumulados de todos los alumnos con alias hasta la pregunta `hasta` (incluida).

        De más a menos puntos. Sin posiciones, así que los empates no se resuelven: van juntos,
        por orden alfabético.
        """
        assert self.tema is not None
        total = {t: 0 for t in self.alias}
        for p in self.tema.preguntas[: hasta + 1]:
            for t, pts in self._puntos_pregunta(p).items():
                if t in total:
                    total[t] += pts
        filas = [{"alias": self.alias[t], "puntos": n} for t, n in total.items()]
        filas.sort(key=lambda f: (-f["puntos"], f["alias"].casefold()))
        return filas

    # ---------- presencia ----------
    def visto(self, token: str | None) -> None:
        """Anota que este navegador sigue conectado."""
        if not token or not 8 <= len(token) <= 64:
            return
        ahora = self.reloj()
        self.vistos[token] = ahora
        if ahora - self._ultima_poda > 30:  # descarta a quien se fue hace tiempo
            self._ultima_poda = ahora
            self.vistos = {t: v for t, v in self.vistos.items() if ahora - v < 60}

    def _tokens_conectados(self) -> list[str]:
        """Navegadores que han consultado hace poco. En un test con identificación, solo los que ya
        tienen alias: quien aún lo está escribiendo no cuenta ni retrasa el cierre de la votación."""
        limite = self.reloj() - SEGUNDOS_PRESENCIA
        return [t for t, v in self.vistos.items()
                if v >= limite and (not self.identificacion or t in self.alias)]

    def conectados(self) -> int:
        return len(self._tokens_conectados())

    # ---------- acción del alumno ----------
    def responder(self, token: str, respuesta: Any) -> None:
        self.exige_admitido(token)
        self._tic()
        if self.fase != "abierta":
            raise EstadoInvalido("La votación no está abierta")
        if self.identificacion and token not in self.alias:
            raise EstadoInvalido("Elige un alias antes de responder")
        valida = self.pregunta.validar_respuesta(respuesta)
        resp = self.respuestas.setdefault(self.pregunta.id, {})
        resp.pop(token, None)   # si la cambia, cuenta como enviada ahora (orden de llegada)
        resp[token] = valida
        self._tic()  # puede que este voto sea el último que faltaba

    # ---------- internos ----------
    @property
    def pregunta(self) -> PreguntaBase:
        assert self.tema is not None
        return self.tema.preguntas[self.indice]

    def _resp(self) -> dict[str, Any]:
        return self.respuestas.get(self.pregunta.id, {})

    def _abrir_pregunta(self, cierre_auto: bool = True) -> None:
        assert self.tema is not None
        self.fase = "abierta"
        self.cierre_auto = cierre_auto
        self.duracion = self.tema.tiempo_de(self.pregunta)
        self.limite = self.reloj() + self.duracion if self.duracion else None

    def _cerrar_pregunta(self, motivo: str) -> None:
        self.fase = "cerrada"
        self.cerradas[self.pregunta.id] = motivo
        self.limite = None

    def _todos_han_votado(self) -> bool:
        """Hay alumnos conectados y todos ellos han respondido a la pregunta actual."""
        conectados = self._tokens_conectados()
        resp = self._resp()
        return bool(conectados) and all(t in resp for t in conectados)

    def _tic(self, avanzar: bool = True) -> None:
        """Cierra la votación si se ha agotado el tiempo o si ya han votado todos.

        Si es una encuesta y han respondido todos, pasa además a la siguiente pregunta, salvo con
        `avanzar=False`. Las acciones del docente lo usan así: si pulsa «cerrar» o «siguiente» justo
        cuando acaban de responder todos, su pulsación no debe caer sobre la pregunta recién abierta.
        """
        if self.fase != "abierta":
            return
        if self.limite is not None and self.reloj() >= self.limite:
            self._cerrar_pregunta("tiempo")
        elif self.cierre_auto and self._todos_han_votado():
            self._cerrar_pregunta("todos")
            if avanzar and not self.pregunta.puntua:
                self._pasar_a_la_siguiente()

    def _pasar_a_la_siguiente(self) -> None:
        assert self.tema is not None
        if self.indice + 1 >= len(self.tema.preguntas):
            self.fase, self.limite = "resumen", None
        else:
            self._ir_a(self.indice + 1)

    def _ir_a(self, i: int) -> None:
        self.indice = i
        if self.pregunta.id in self.cerradas:
            self.fase, self.limite = "cerrada", None
        else:
            self._abrir_pregunta()

    def _navegar(self, paso: int) -> None:
        self._tic(avanzar=False)
        if self.tema is None:
            raise EstadoInvalido("No hay tema elegido")
        if self.fase == "abierta":
            raise EstadoInvalido("Cierra la votación antes de cambiar de pregunta")
        n = len(self.tema.preguntas)
        if self.fase == "sala":
            if paso > 0:
                self.empezar()
            return
        if self.fase == "resumen":
            if paso > 0:
                self.inicio()
            else:
                self._ir_a(n - 1)
            return
        i = self.indice + paso
        if i < 0:
            return
        if i >= n:
            self.fase, self.limite = "resumen", None
            return
        self._ir_a(i)

    # ---------- lo que se envía a los clientes ----------
    def resumen(self, con_ranking: bool = False) -> dict:
        """Aciertos/errores/no lo sé de cada pregunta y del conjunto, y el reparto de respuestas.

        Cada pregunta lleva sus opciones con el número y el porcentaje de respuestas de cada una.
        Las encuestas (sin respuesta correcta) no cuentan en el conjunto.
        """
        assert self.tema is not None
        filas = []
        globales: dict[str, dict] = {}
        total = 0
        for i, p in enumerate(self.tema.preguntas):
            r = p.resultados(list(self.respuestas.get(p.id, {}).values()))
            fila = {"indice": i, "texto": p.texto, "tipo": p.tipo, "total": r["total"],
                    "categorias": r["categorias"], "opciones": p.resumen_opciones(r)}
            if p.puntua:
                total += r["total"]
                for c in r["categorias"]:
                    g = globales.setdefault(c["clave"], {"clave": c["clave"], "etiqueta": c["etiqueta"], "n": 0})
                    g["n"] += c["n"]
            filas.append(fila)
        for g in globales.values():
            g["pct"] = round(100 * g["n"] / total, 1) if total else 0.0
        orden = {k: i for i, k in enumerate(("acierto", "parcial", "error", "nose"))}
        categorias = sorted(globales.values(), key=lambda g: orden.get(g["clave"], len(orden)))
        datos = {"preguntas": filas,
                 "global": {"total": total, "categorias": categorias}}
        if con_ranking and self.identificacion:
            datos["ranking"] = self.ranking(len(self.tema.preguntas) - 1)
        return datos

    def vista(self, token: str | None = None, docente: bool = False) -> dict:
        self._tic()
        v: dict[str, Any] = {"fase": self.fase, "arranque": self.arranque}
        if self.tema is not None:
            v["tema"] = {"id": self.tema.id, "titulo": self.tema.titulo}
            v["total"] = len(self.tema.preguntas)
            if self.identificacion:
                v["identificacion"] = True
                if token is not None and token in self.alias:
                    v["alias"] = self.alias[token]
            if self.fase == "resumen":
                v["resumen"] = self.resumen(con_ranking=docente)
            elif self.fase != "sala":
                p = self.pregunta
                resp = self._resp()
                v["indice"] = self.indice
                v["n_respuestas"] = len(resp)
                v["pregunta"] = p.publica()
                if self.fase == "abierta" and self.limite is not None:
                    v["tiempo"] = {
                        "total": self.duracion,
                        "restante": round(max(0.0, self.limite - self.reloj()), 2),
                    }
                if self.fase == "cerrada":
                    v["resultados"] = p.resultados(list(resp.values()))
                    v["motivo_cierre"] = self.cerradas.get(p.id, "docente")
                    if docente and self.identificacion and p.puntua:
                        v["ranking"] = self.ranking(self.indice)[:TAM_RANKING]
                if token is not None and token in resp:
                    v["mi_respuesta"] = resp[token]
                    if self.fase == "cerrada" and p.puntua:
                        v["mi_categoria"] = p.evaluar(resp[token])[0]
        if docente:
            v["temas"] = [
                {"id": t.id, "titulo": t.titulo, "n_preguntas": len(t.preguntas), "tiempo": t.tiempo,
                 "identificacion": t.identificacion}
                for t in self.temas.values()
            ]
            v["url_alumnos"] = self.url_alumnos
            v["codigo"] = self.codigo       # None en la red local
            v["conectados"] = self.conectados()
        return v
