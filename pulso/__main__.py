"""Punto de entrada:  python -m pulso  [--preguntas CARPETA] [--puerto N]"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import uvicorn

from .app import crear_app
from .cargador import ErrorBanco, cargar


def url_publica_valida(texto: str) -> str | None:
    """Devuelve la URL sin la barra final, o None si no es una dirección web de la raíz de un dominio."""
    u = urlparse(texto)
    if u.scheme not in ("http", "https") or not u.netloc or u.path not in ("", "/") \
            or u.params or u.query or u.fragment:
        return None
    return texto.rstrip("/")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pulso", description="Pulso del aula")
    ap.add_argument("--preguntas", type=Path, default=Path("preguntas"),
                    help="carpeta con los .yaml de preguntas (por defecto ./preguntas)")
    ap.add_argument("--puerto", type=int, default=8000)
    ap.add_argument("--host", default=None,
                    help="interfaz donde escuchar (por defecto todas; en modo remoto, solo 127.0.0.1)")
    ap.add_argument("--url-publica", metavar="URL",
                    help="activa el modo remoto: dirección pública del túnel, p. ej. "
                         "https://preguntas.ifct0109.online. Los alumnos entran con un código "
                         "(o un QR) y el docente con una clave")
    ap.add_argument("--clave", default=os.environ.get("PULSO_CLAVE", ""),
                    help="clave del panel del docente (por defecto, la variable PULSO_CLAVE). "
                         "Obligatoria en modo remoto; en modo local, si se da, también se pide")
    args = ap.parse_args(argv)

    url_publica = None
    if args.url_publica is not None:
        url_publica = url_publica_valida(args.url_publica)
        if url_publica is None:
            print("Error: --url-publica debe ser una dirección como https://preguntas.ifct0109.online "
                  "(sin ruta)", file=sys.stderr)
            return 1
        if not args.clave:
            print("Error: el modo remoto necesita una clave para el docente. Defínela con la variable "
                  "de entorno PULSO_CLAVE (mejor, para que no quede en el historial) o con --clave.",
                  file=sys.stderr)
            return 1
    host = args.host or ("127.0.0.1" if url_publica else "0.0.0.0")

    try:
        temas = cargar(args.preguntas)
    except ErrorBanco as e:
        print(f"Error en las preguntas:\n{e}", file=sys.stderr)
        return 1

    app = crear_app(temas, args.preguntas, args.puerto, url_publica=url_publica, clave=args.clave)
    sesion = app.state.sesion
    n = sum(len(t.preguntas) for t in temas.values())
    print(f"Cargados {len(temas)} tema(s), {n} pregunta(s).")
    print(f"  Docente (en este equipo): http://localhost:{args.puerto}/docente"
          + ("  (pide la clave)" if args.clave else ""))
    print(f"  Alumnos:                  {sesion.url_alumnos}")
    if sesion.codigo:
        print(f"  Código de sala:           {sesion.codigo}   (cambia cada vez que se arranca)")
        print(f"  El túnel debe apuntar a:  http://localhost:{args.puerto}")
    uvicorn.run(app, host=host, port=args.puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
