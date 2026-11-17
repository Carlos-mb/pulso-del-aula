"""Localización de los recursos incluidos en el programa (static/).

Funciona tanto desde el código fuente como empaquetado con PyInstaller.
Los ficheros de preguntas NO pasan por aquí: viven fuera del programa.
"""
from __future__ import annotations

import sys
from pathlib import Path


def recurso(*partes: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "pulso"
    else:
        base = Path(__file__).parent
    return base.joinpath(*partes)
