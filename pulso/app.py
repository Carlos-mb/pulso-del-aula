"""Aplicación web (FastAPI)."""
from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt, StrictStr

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


class Respuesta(BaseModel):
    token: str = Field(min_length=8, max_length=64)
    respuesta: StrictInt | StrictStr | list[StrictInt]


def crear_app(
    temas: dict[str, Tema],
    directorio_preguntas: Path,
    puerto: int,
    reloj: Callable[[], float] = time.monotonic,
) -> FastAPI:
    ip = ip_lan()
    sesion = Sesion(temas, url_alumnos=f"http://{ip}:{puerto}/", reloj=reloj)
    locales = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost", ip}

    def solo_local(request: Request) -> None:
        host = request.client.host if request.client else ""
        if host not in locales:
            raise HTTPException(
                403, "El panel del docente solo es accesible desde el equipo del servidor"
            )

    app = FastAPI(title="Pulso del aula", docs_url=None, redoc_url=None)
    app.state.sesion = sesion

    @app.middleware("http")
    async def sin_cache(request: Request, call_next):
        resp = await call_next(request)
        if not request.url.path.startswith("/media/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

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

    @app.get("/docente", include_in_schema=False, dependencies=[Depends(solo_local)])
    async def pagina_docente() -> FileResponse:
        return FileResponse(recurso("static", "docente.html"))

    # --- API de alumnos ---
    @app.get("/api/estado")
    async def estado(token: str | None = None) -> dict:
        sesion.visto(token)  # la propia consulta periódica indica que el alumno sigue conectado
        return sesion.vista(token)

    @app.post("/api/responder")
    async def responder(datos: Respuesta) -> dict:
        sesion.responder(datos.token, datos.respuesta)
        return {"ok": True}

    # --- API del docente (solo desde el propio equipo) ---
    docente = APIRouter(prefix="/api/docente", dependencies=[Depends(solo_local)])

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
