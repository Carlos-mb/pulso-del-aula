"""Acceso en modo remoto (túnel de Cloudflare): código de sala, clave del docente, QR.

En modo remoto todas las peticiones llegan al servidor desde 127.0.0.1 (porque `cloudflared` corre en
el mismo equipo), así que la IP no sirve para distinguir al docente de un alumno ni de un desconocido:

  - Los alumnos entran con un código de sala (`POST /api/entrar`), que se comprueba una sola vez por
    alumno. Como todos comparten la misma IP pública, los intentos fallidos se limitan en conjunto,
    no por IP.
  - El docente entra con una clave, que se guarda en una cookie.
"""
from __future__ import annotations

import hmac
import io
import secrets
import time
from collections import deque
from typing import Callable

# Sin 0, O, 1, I ni L, que se confunden al leer el código en una pantalla.
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LONGITUD_CODIGO = 6


class NoAdmitido(Exception):
    """El alumno aún no ha introducido el código de la sesión."""


class CodigoIncorrecto(Exception):
    """El código o la clave no son correctos."""


class Bloqueado(Exception):
    """Demasiados intentos fallidos seguidos."""


def codigo_nuevo(longitud: int = LONGITUD_CODIGO) -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(longitud))


def normaliza_codigo(codigo: str) -> str:
    """Admite minúsculas y espacios o guiones sueltos (`abc-234`)."""
    return "".join(c for c in codigo.upper() if c not in " -\t")


def coincide(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class LimiteFallos:
    """Máximo de fallos en una ventana de tiempo, por «cubo» (clave de agrupación)."""

    def __init__(self, maximo: int, ventana: float, reloj: Callable[[], float] = time.monotonic) -> None:
        self.maximo = maximo
        self.ventana = ventana
        self.reloj = reloj
        self._fallos: dict[str, deque[float]] = {}

    def _poda(self, cubo: str) -> deque[float]:
        limite = self.reloj() - self.ventana
        d = self._fallos.get(cubo)
        if d is None:
            return deque()
        while d and d[0] <= limite:
            d.popleft()
        if not d:
            del self._fallos[cubo]
        return d

    def bloqueado(self, cubo: str = "") -> bool:
        return len(self._poda(cubo)) >= self.maximo

    def fallo(self, cubo: str = "") -> None:
        self._poda(cubo)
        self._fallos.setdefault(cubo, deque()).append(self.reloj())

    def olvida(self, cubo: str = "") -> None:
        self._fallos.pop(cubo, None)


class AccesoDocente:
    """Clave del docente y sesiones abiertas con ella (cookie). Sin clave, no se pide nada."""

    HORAS = 12
    FALLOS_POR_MINUTO = 10

    def __init__(self, clave: str, reloj: Callable[[], float] = time.monotonic) -> None:
        self.clave = clave
        self.reloj = reloj
        self.sesiones: dict[str, float] = {}      # {cookie: instante en que caduca}
        self.limite = LimiteFallos(self.FALLOS_POR_MINUTO, 60.0, reloj)

    @property
    def requiere(self) -> bool:
        return bool(self.clave)

    def entrar(self, clave: str, cubo: str) -> str:
        """Devuelve la cookie de sesión, o lanza CodigoIncorrecto / Bloqueado."""
        if self.limite.bloqueado(cubo):
            raise Bloqueado
        if not coincide(clave, self.clave):
            self.limite.fallo(cubo)
            raise CodigoIncorrecto
        self.limite.olvida(cubo)
        ahora = self.reloj()
        self.sesiones = {t: c for t, c in self.sesiones.items() if c > ahora}
        token = secrets.token_urlsafe(32)
        self.sesiones[token] = ahora + self.HORAS * 3600
        return token

    def valido(self, token: str | None) -> bool:
        caduca = self.sesiones.get(token) if token else None
        return caduca is not None and caduca > self.reloj()


def qr_svg(url: str) -> str:
    """QR en negro sobre blanco (los lectores fallan con los invertidos del tema oscuro)."""
    import segno

    buf = io.BytesIO()
    segno.make(url, error="m").save(
        buf, kind="svg", scale=8, border=2, dark="#000", light="#fff", xmldecl=False, svgns=True
    )
    return buf.getvalue().decode("utf-8")
