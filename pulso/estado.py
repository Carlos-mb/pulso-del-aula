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

    def elegir_tema(self, tema_id: str) -> None:
        if tema_id not in self.temas:
            raise ValueError(f"tema desconocido: {tema_id}")
        self.inicio()
        self.tema = self.temas[tema_id]
        self.fase = "sala"

    def empezar(self) -> None:
        """Sale de la sala de espera y presenta la primera pregunta."""
        if self.fase != "sala":
            raise EstadoInvalido("El test ya ha empezado")
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

    def conectados(self) -> int:
        limite = self.reloj() - SEGUNDOS_PRESENCIA
        return sum(1 for v in self.vistos.values() if v >= limite)

    # ---------- acción del alumno ----------
    def responder(self, token: str, respuesta: Any) -> None:
        self.exige_admitido(token)
        self._tic()
        if self.fase != "abierta":
            raise EstadoInvalido("La votación no está abierta")
        valida = self.pregunta.validar_respuesta(respuesta)
        self.respuestas.setdefault(self.pregunta.id, {})[token] = valida
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
        limite = self.reloj() - SEGUNDOS_PRESENCIA
        conectados = [t for t, v in self.vistos.items() if v >= limite]
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
    def resumen(self) -> dict:
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
        return {"preguntas": filas,
                "global": {"total": total, "categorias": categorias}}

    def vista(self, token: str | None = None, docente: bool = False) -> dict:
        self._tic()
        v: dict[str, Any] = {"fase": self.fase, "arranque": self.arranque}
        if self.tema is not None:
            v["tema"] = {"id": self.tema.id, "titulo": self.tema.titulo}
            v["total"] = len(self.tema.preguntas)
            if self.fase == "resumen":
                v["resumen"] = self.resumen()
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
                if token is not None and token in resp:
                    v["mi_respuesta"] = resp[token]
                    if self.fase == "cerrada" and p.puntua:
                        v["mi_categoria"] = p.evaluar(resp[token])[0]
        if docente:
            v["temas"] = [
                {"id": t.id, "titulo": t.titulo, "n_preguntas": len(t.preguntas), "tiempo": t.tiempo}
                for t in self.temas.values()
            ]
            v["url_alumnos"] = self.url_alumnos
            v["codigo"] = self.codigo       # None en la red local
            v["conectados"] = self.conectados()
        return v
