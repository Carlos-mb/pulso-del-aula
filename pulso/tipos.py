"""Tipos de pregunta.

Cada tipo es un modelo Pydantic que sabe:
  - validar su propia configuración (lo que se escribe en el YAML),
  - validar una respuesta,
  - evaluarla (categoría + puntuación),
  - agregar los resultados de toda la clase.

Para añadir un tipo nuevo: crear la clase y registrarla en TIPOS.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

NOSE = "nose"
ETIQUETA_NOSE = "No lo sé / quiero que se explique"


def url_media(ruta: str | None) -> str | None:
    return "/media/" + ruta.lstrip("/") if ruta else None


class Opcion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str | None = None
    imagen: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _desde_escalar(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError(
                "el texto de la opción se ha leído como verdadero/falso; "
                "entrecomíllalo (por ejemplo \"No\")"
            )
        if isinstance(v, (str, int, float)):
            return {"texto": str(v)}
        return v

    @model_validator(mode="after")
    def _con_contenido(self) -> "Opcion":
        if not self.texto and not self.imagen:
            raise ValueError("una opción necesita 'texto' o 'imagen'")
        return self

    def publica(self) -> dict:
        return {"texto": self.texto, "imagen": url_media(self.imagen)}


class PreguntaBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    texto: str
    imagen: str | None = None
    explicacion: str | None = None
    # Segundos para responder. None = usar el valor del tema; 0 = sin límite.
    tiempo: int | None = Field(default=None, ge=0)

    def imagenes(self) -> list[str]:
        return [self.imagen] if self.imagen else []


class PreguntaDeOpciones(PreguntaBase):
    """Base de las preguntas en que cada alumno elige una opción de una lista."""

    opciones: list[Opcion]

    # ¿Tiene respuesta correcta? Si no, no cuenta en los aciertos/errores del resumen.
    puntua: ClassVar[bool] = True

    @model_validator(mode="after")
    def _minimo_de_opciones(self) -> "PreguntaDeOpciones":
        if len(self.opciones) < 2:
            raise ValueError("hacen falta al menos 2 opciones")
        return self

    @property
    def con_nose(self) -> bool:
        """¿Se ofrece la opción «No lo sé / quiero que se explique»?"""
        return True

    def imagenes(self) -> list[str]:
        return super().imagenes() + [o.imagen for o in self.opciones if o.imagen]

    # --- lo que ve el alumno (nunca incluye la solución) ---
    def publica(self) -> dict:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "texto": self.texto,
            "imagen": url_media(self.imagen),
            "opciones": [o.publica() for o in self.opciones],
            "con_nose": self.con_nose,
        }

    def validar_respuesta(self, r: Any) -> Any:
        if r == NOSE and self.con_nose:
            return NOSE
        if isinstance(r, int) and not isinstance(r, bool) and 0 <= r < len(self.opciones):
            return r
        raise ValueError("respuesta no válida")

    def _reparto(self, respuestas: list[Any]) -> dict:
        """Número y porcentaje de respuestas de cada opción y de «no lo sé»."""
        n = len(respuestas)

        def pct(x: int) -> float:
            return round(100 * x / n, 1) if n else 0.0

        votos = Counter(respuestas)
        return {
            "total": n,
            "opciones": [
                {"n": votos[i], "pct": pct(votos[i])} for i in range(len(self.opciones))
            ],
            "nose": {"n": votos[NOSE], "pct": pct(votos[NOSE])} if self.con_nose else None,
            "explicacion": self.explicacion,
        }


class UnaOpcion(PreguntaDeOpciones):
    """Test de una única opción correcta. `correcta` cuenta desde 1."""

    tipo: Literal["una_opcion"] = "una_opcion"
    correcta: int

    CATEGORIAS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("acierto", "Aciertos"),
        ("error", "Error"),
        ("nose", "No lo sé"),
    )

    @model_validator(mode="after")
    def _coherente(self) -> "UnaOpcion":
        if not 1 <= self.correcta <= len(self.opciones):
            raise ValueError(
                f"'correcta' debe estar entre 1 y {len(self.opciones)} "
                "(la primera opción es la 1)"
            )
        return self

    def evaluar(self, r: Any) -> tuple[str, float]:
        """Devuelve (categoría, puntuación entre 0 y 1)."""
        if r == NOSE:
            return "nose", 0.0
        if r == self.correcta - 1:
            return "acierto", 1.0
        return "error", 0.0

    def resultados(self, respuestas: list[Any]) -> dict:
        r = self._reparto(respuestas)
        cats = Counter(self.evaluar(x)[0] for x in respuestas)
        n = r["total"]
        r["categorias"] = [
            {"clave": k, "etiqueta": e, "n": cats[k], "pct": round(100 * cats[k] / n, 1) if n else 0.0}
            for k, e in self.CATEGORIAS
        ]
        r["correcta"] = self.correcta - 1
        return r


class Encuesta(PreguntaDeOpciones):
    """Sondeo de opinión o de experiencia: una opción por alumno y ninguna correcta.

    No hay aciertos ni errores: los resultados son solo el reparto por opción, y la
    pregunta no cuenta en los porcentajes globales del resumen. La opción «No lo sé /
    quiero que se explique» no se añade salvo que se pida con `nose: true`.
    """

    tipo: Literal["encuesta"]
    nose: StrictBool = False

    puntua: ClassVar[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _sin_correcta(cls, v: Any) -> Any:
        if isinstance(v, dict) and "correcta" in v:
            raise ValueError("una encuesta no tiene respuesta correcta: quita 'correcta'")
        return v

    @property
    def con_nose(self) -> bool:
        return self.nose

    def evaluar(self, r: Any) -> tuple[str, float]:
        raise NotImplementedError("una encuesta no se evalúa")

    def resultados(self, respuestas: list[Any]) -> dict:
        r = self._reparto(respuestas)
        r["categorias"] = []
        r["correcta"] = None
        return r


TIPOS: dict[str, type[PreguntaBase]] = {
    "una_opcion": UnaOpcion,
    "encuesta": Encuesta,
}
