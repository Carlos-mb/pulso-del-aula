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

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class UnaOpcion(PreguntaBase):
    """Test de una única opción correcta. `correcta` cuenta desde 1."""

    tipo: Literal["una_opcion"] = "una_opcion"
    opciones: list[Opcion]
    correcta: int

    CATEGORIAS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("acierto", "Aciertos"),
        ("error", "Error"),
        ("nose", "No lo sé"),
    )

    @model_validator(mode="after")
    def _coherente(self) -> "UnaOpcion":
        if len(self.opciones) < 2:
            raise ValueError("hacen falta al menos 2 opciones")
        if not 1 <= self.correcta <= len(self.opciones):
            raise ValueError(
                f"'correcta' debe estar entre 1 y {len(self.opciones)} "
                "(la primera opción es la 1)"
            )
        return self

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
        }

    def validar_respuesta(self, r: Any) -> Any:
        if r == NOSE:
            return NOSE
        if isinstance(r, int) and not isinstance(r, bool) and 0 <= r < len(self.opciones):
            return r
        raise ValueError("respuesta no válida")

    def evaluar(self, r: Any) -> tuple[str, float]:
        """Devuelve (categoría, puntuación entre 0 y 1)."""
        if r == NOSE:
            return "nose", 0.0
        if r == self.correcta - 1:
            return "acierto", 1.0
        return "error", 0.0

    def resultados(self, respuestas: list[Any]) -> dict:
        n = len(respuestas)

        def pct(x: int) -> float:
            return round(100 * x / n, 1) if n else 0.0

        cats = Counter(self.evaluar(r)[0] for r in respuestas)
        por_opcion = Counter(r for r in respuestas if r != NOSE)
        return {
            "total": n,
            "categorias": [
                {"clave": k, "etiqueta": e, "n": cats[k], "pct": pct(cats[k])}
                for k, e in self.CATEGORIAS
            ],
            "opciones": [
                {"n": por_opcion[i], "pct": pct(por_opcion[i])}
                for i in range(len(self.opciones))
            ],
            "nose": {"n": cats["nose"], "pct": pct(cats["nose"])},
            "correcta": self.correcta - 1,
            "explicacion": self.explicacion,
        }


TIPOS: dict[str, type[PreguntaBase]] = {
    "una_opcion": UnaOpcion,
}
