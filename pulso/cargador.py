"""Carga y validación de los ficheros de preguntas (YAML).

Formato de cada fichero .yaml dentro de la carpeta de preguntas:

    temas:
      redes:
        titulo: "Redes básicas"
        preguntas:
          - texto: "..."
            opciones: [...]
            correcta: 2        # la primera opción es la 1

Las imágenes se referencian por ruta relativa a <carpeta de preguntas>/media/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from .tipos import TIPOS, PreguntaBase


class ErrorBanco(Exception):
    """Problema en los ficheros de preguntas (mensaje legible para el docente)."""


@dataclass
class Tema:
    id: str
    titulo: str
    tiempo: int = 0  # segundos por defecto de sus preguntas; 0 = sin límite
    identificacion: bool = False  # los alumnos eligen un alias y hay ranking
    preguntas: list[PreguntaBase] = field(default_factory=list)

    def tiempo_de(self, pregunta: PreguntaBase) -> int:
        """Tiempo de la pregunta, o el del tema si ella no define ninguno."""
        return self.tiempo if pregunta.tiempo is None else pregunta.tiempo


def _formatea(e: ValidationError) -> str:
    lineas = []
    for err in e.errors():
        donde = ".".join(str(p) for p in err["loc"] if p != "__root__")
        msg = err["msg"].removeprefix("Value error, ")
        lineas.append(f"    - {donde}: {msg}" if donde else f"    - {msg}")
    return "\n".join(lineas)


def _pregunta(raw: object, tema: str, n: int, fichero: Path) -> PreguntaBase:
    ctx = f"{fichero.name}, tema '{tema}', pregunta {n}"
    if not isinstance(raw, dict):
        raise ErrorBanco(f"{ctx}: debe ser un bloque con 'texto', 'opciones'...")
    datos = dict(raw)
    datos["id"] = str(datos.get("id", f"{tema}-{n:02d}"))
    tipo = datos.get("tipo", "una_opcion")
    cls = TIPOS.get(tipo)
    if cls is None:
        raise ErrorBanco(f"{ctx}: tipo '{tipo}' desconocido (tipos: {', '.join(TIPOS)})")
    try:
        return cls.model_validate(datos)
    except ValidationError as e:
        raise ErrorBanco(f"{ctx}:\n{_formatea(e)}") from None


def _comprueba_imagenes(p: PreguntaBase, media: Path, ctx: str) -> None:
    base = media.resolve()
    for ruta in p.imagenes():
        destino = (media / ruta).resolve()
        if base not in destino.parents:
            raise ErrorBanco(f"{ctx}: la imagen '{ruta}' sale de la carpeta media/")
        if not destino.is_file():
            raise ErrorBanco(f"{ctx}: no existe la imagen '{ruta}' (se busca en {media}/)")


def cargar(directorio: Path) -> dict[str, Tema]:
    directorio = Path(directorio)
    if not directorio.is_dir():
        raise ErrorBanco(f"No existe la carpeta de preguntas: {directorio}")
    ficheros = sorted([*directorio.glob("*.yaml"), *directorio.glob("*.yml")])
    if not ficheros:
        raise ErrorBanco(f"No hay ficheros .yaml en {directorio}")

    temas: dict[str, Tema] = {}
    for fichero in ficheros:
        try:
            doc = yaml.safe_load(fichero.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ErrorBanco(f"{fichero.name}: YAML no válido\n{e}") from None
        if not isinstance(doc, dict) or not isinstance(doc.get("temas"), dict):
            raise ErrorBanco(f"{fichero.name}: debe empezar con 'temas:'")

        for tid, cuerpo in doc["temas"].items():
            tid = str(tid)
            if tid in temas:
                raise ErrorBanco(f"{fichero.name}: el tema '{tid}' está repetido")
            if not isinstance(cuerpo, dict) or not cuerpo.get("preguntas"):
                raise ErrorBanco(f"{fichero.name}: el tema '{tid}' no tiene 'preguntas'")
            tiempo = cuerpo.get("tiempo", 0)
            if isinstance(tiempo, bool) or not isinstance(tiempo, int) or tiempo < 0:
                raise ErrorBanco(
                    f"{fichero.name}, tema '{tid}': 'tiempo' debe ser un número entero "
                    "de segundos (0 = sin límite)"
                )
            identificacion = cuerpo.get("identificacion", False)
            if not isinstance(identificacion, bool):
                raise ErrorBanco(
                    f"{fichero.name}, tema '{tid}': 'identificacion' debe ser true o false"
                )
            tema = Tema(id=tid, titulo=str(cuerpo.get("titulo", tid)), tiempo=tiempo,
                        identificacion=identificacion)
            ids: set[str] = set()
            for n, raw in enumerate(cuerpo["preguntas"], start=1):
                p = _pregunta(raw, tid, n, fichero)
                ctx = f"{fichero.name}, tema '{tid}', pregunta {n}"
                if p.id in ids:
                    raise ErrorBanco(f"{ctx}: el id '{p.id}' está repetido en el tema")
                ids.add(p.id)
                _comprueba_imagenes(p, directorio / "media", ctx)
                tema.preguntas.append(p)
            temas[tid] = tema
    return temas
