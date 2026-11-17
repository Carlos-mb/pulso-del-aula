"""Aplicación web (FastAPI)."""
from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt, StrictStr

from .acceso import (AccesoDocente, Bloqueado, CodigoIncorrecto, NoAdmitido, codigo_nuevo,
                     qr_svg)
from .cargador import Tema
from .estado import EstadoInvalido, Sesion
from .recursos import recurso


def ip_lan() -> str:
    """IP del equipo en la red local (no envía ningún paquete)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


COOKIE_DOCENTE = "pulso_docente"


class Respuesta(BaseModel):
    token: str = Field(min_length=8, max_length=64)
    respuesta: StrictInt | StrictStr | list[StrictInt]


class Entrada(BaseModel):
    token: str = Field(min_length=8, max_length=64)
    codigo: str = Field(max_length=32)


class AliasEntrada(BaseModel):
    token: str = Field(min_length=8, max_length=64)
    alias: str = Field(max_length=200)


class Clave(BaseModel):
    clave: str = Field(max_length=200)


def crear_app(
    temas: dict[str, Tema],
    directorio_preguntas: Path,
    puerto: int,
    reloj: Callable[[], float] = time.monotonic,
    url_publica: str | None = None,
    clave: str | None = None,
) -> FastAPI:
    """`url_publica` activa el modo remoto (túnel): código de sala para los alumnos y clave
    obligatoria para el docente. Sin ella, red local: todo como siempre."""
    remoto = url_publica is not None
    if remoto and not clave:
        raise ValueError("el modo remoto necesita una clave para el panel del docente")
    ip = ip_lan()
    if remoto:
        base = url_publica.rstrip("/")
        sesion = Sesion(temas, url_alumnos=base + "/", reloj=reloj, codigo=codigo_nuevo())
    else:
        sesion = Sesion(temas, url_alumnos=f"http://{ip}:{puerto}/", reloj=reloj)
    acceso = AccesoDocente(clave or "", reloj)
    locales = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost", ip}

    def solo_local(request: Request) -> None:
        host = request.client.host if request.client else ""
        if host not in locales:
            raise HTTPException(
                403, "El panel del docente solo es accesible desde el equipo del servidor"
            )

    def pagina_docente_ok(request: Request) -> None:
        # En remoto el túnel hace que todo parezca local: la protección es la clave.
        if not remoto:
            solo_local(request)

    def autoriza_docente(request: Request) -> None:
        pagina_docente_ok(request)
        if acceso.requiere and not acceso.valido(request.cookies.get(COOKIE_DOCENTE)):
            raise HTTPException(401, "clave")

    def cubo(request: Request) -> str:
        """Quién intenta entrar: la IP real que indica Cloudflare, o «local» si no hay túnel."""
        return request.headers.get("cf-connecting-ip") or "local"

    app = FastAPI(title="Pulso del aula", docs_url=None, redoc_url=None)
    app.state.sesion = sesion

    @app.middleware("http")
    async def sin_cache(request: Request, call_next):
        resp = await call_next(request)
        if not request.url.path.startswith("/media/"):
            resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    @app.exception_handler(NoAdmitido)
    async def _no_admitido(_: Request, e: NoAdmitido) -> JSONResponse:
        return JSONResponse({"detail": "codigo"}, status_code=401)

    @app.exception_handler(CodigoIncorrecto)
    async def _codigo_incorrecto(_: Request, e: CodigoIncorrecto) -> JSONResponse:
        return JSONResponse({"detail": "Código incorrecto"}, status_code=403)

    @app.exception_handler(Bloqueado)
    async def _bloqueado(_: Request, e: Bloqueado) -> JSONResponse:
        return JSONResponse({"detail": "Demasiados intentos. Espera un minuto."}, status_code=429)

    @app.exception_handler(EstadoInvalido)
    async def _estado_invalido(_: Request, e: EstadoInvalido) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(ValueError)
    async def _valor_invalido(_: Request, e: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=400)

    # --- páginas ---
    @app.get("/", include_in_schema=False)
    async def pagina_alumno() -> FileResponse:
        return FileResponse(recurso("static", "alumno.html"))

    @app.get("/docente", include_in_schema=False, dependencies=[Depends(pagina_docente_ok)])
    async def pagina_docente() -> FileResponse:
        return FileResponse(recurso("static", "docente.html"))

    # --- API de alumnos ---
    @app.get("/api/estado")
    async def estado(token: str | None = None) -> dict:
        sesion.exige_admitido(token)
        sesion.visto(token)  # la propia consulta periódica indica que el alumno sigue conectado
        return sesion.vista(token)

    @app.post("/api/entrar")
    async def entrar(datos: Entrada) -> dict:
        sesion.admitir(datos.token, datos.codigo)
        return {"ok": True}

    @app.post("/api/alias")
    async def poner_alias(datos: AliasEntrada) -> dict:
        sesion.poner_alias(datos.token, datos.alias)
        return {"ok": True}

    @app.post("/api/responder")
    async def responder(datos: Respuesta) -> dict:
        sesion.responder(datos.token, datos.respuesta)
        return {"ok": True}

    # --- API del docente (solo desde el propio equipo) ---
    @app.post("/api/docente/entrar", dependencies=[Depends(pagina_docente_ok)])
    async def entrar_docente(datos: Clave, request: Request, respuesta: Response) -> dict:
        if acceso.requiere:
            try:
                token = acceso.entrar(datos.clave, cubo(request))
            except CodigoIncorrecto:
                raise HTTPException(403, "Clave incorrecta") from None
            # «Secure» solo si la petición llegó por el túnel (en http://localhost no se enviaría)
            https = remoto and url_publica.startswith("https://") and "cf-connecting-ip" in request.headers
            respuesta.set_cookie(COOKIE_DOCENTE, token, max_age=AccesoDocente.HORAS * 3600,
                                 httponly=True, samesite="strict", secure=https, path="/")
        return {"ok": True}

    docente = APIRouter(prefix="/api/docente", dependencies=[Depends(autoriza_docente)])

    @docente.get("/qr.svg")
    async def qr() -> Response:
        if sesion.codigo is None:
            raise HTTPException(404, "no hay código de sala (modo local)")
        return Response(qr_svg(f"{sesion.url_alumnos}?c={sesion.codigo}"), media_type="image/svg+xml")

    @docente.get("/estado")
    async def estado_docente() -> dict:
        return sesion.vista(docente=True)

    @docente.post("/tema/{tema_id}")
    async def elegir_tema(tema_id: str) -> dict:
        sesion.elegir_tema(tema_id)
        return {"ok": True}

    acciones: dict[str, Any] = {
        "empezar": sesion.empezar,
        "abrir": sesion.abrir,
        "cerrar": sesion.cerrar,
        "siguiente": sesion.siguiente,
        "anterior": sesion.anterior,
        "inicio": sesion.inicio,
        "reiniciar": sesion.reiniciar,
    }

    @docente.post("/{accion}")
    async def accion(accion: str) -> dict:
        if accion not in acciones:
            raise HTTPException(404, "acción desconocida")
        acciones[accion]()
        return {"ok": True}

    app.include_router(docente)

    app.mount("/static", StaticFiles(directory=recurso("static")), name="static")
    app.mount(
        "/media",
        StaticFiles(directory=directorio_preguntas / "media", check_dir=False),
        name="media",
    )
    return app
