"""Punto de entrada:  python -m pulso  [--preguntas CARPETA] [--puerto N]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from .app import crear_app
from .cargador import ErrorBanco, cargar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pulso", description="Pulso del aula")
    ap.add_argument("--preguntas", type=Path, default=Path("preguntas"),
                    help="carpeta con los .yaml de preguntas (por defecto ./preguntas)")
    ap.add_argument("--puerto", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0",
                    help="interfaz donde escuchar (por defecto todas)")
    args = ap.parse_args(argv)

    try:
        temas = cargar(args.preguntas)
    except ErrorBanco as e:
        print(f"Error en las preguntas:\n{e}", file=sys.stderr)
        return 1

    app = crear_app(temas, args.preguntas, args.puerto)
    n = sum(len(t.preguntas) for t in temas.values())
    print(f"Cargados {len(temas)} tema(s), {n} pregunta(s).")
    print(f"  Docente (en este equipo): http://localhost:{args.puerto}/docente")
    print(f"  Alumnos:                  {app.state.sesion.url_alumnos}")
    uvicorn.run(app, host=args.host, port=args.puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
