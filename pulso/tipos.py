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

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

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
    # Pregunta rápida: primero solo el enunciado; las opciones (y el tiempo) cuando el docente
    # lo indique. None = usar el valor del tema (las encuestas no lo heredan).
    rapido: StrictBool | None = None

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

    @property
    def con_varias(self) -> bool:
        """¿Puede cada alumno marcar varias opciones?"""
        return False

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
            "multiple": self.con_varias,
        }

    def validar_respuesta(self, r: Any) -> Any:
        """Una opción (índice desde 0), o «nose». Con varias: lista de índices sin repetir."""
        if r == NOSE and self.con_nose:
            return NOSE
        n = len(self.opciones)
        if self.con_varias:
            if (isinstance(r, list) and 1 <= len(r) <= n
                    and all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n for i in r)
                    and len(set(r)) == len(r)):
                return sorted(r)
        elif isinstance(r, int) and not isinstance(r, bool) and 0 <= r < n:
            return r
        raise ValueError("respuesta no válida")

    def resumen_opciones(self, r: dict) -> list[dict]:
        """Opciones con su número y porcentaje de respuestas (para el resumen final).

        `r` es lo que devuelve `resultados()`. Si se pueden marcar varias opciones, los
        porcentajes no suman 100 %. «No lo sé» va al final, si se ofrece.
        """
        buenas = set(r["correctas"])
        filas = [
            {**o.publica(), **r["opciones"][i], "correcta": i in buenas}
            for i, o in enumerate(self.opciones)
        ]
        if r["nose"] is not None:
            filas.append({"texto": ETIQUETA_NOSE, "imagen": None, **r["nose"], "correcta": False, "nose": True})
        return filas

    def _reparto(self, respuestas: list[Any]) -> dict:
        """Número y porcentaje de respuestas de cada opción y de «no lo sé».

        El porcentaje es sobre el número de alumnos que respondieron; si se pueden marcar
        varias opciones, los porcentajes de las opciones no suman 100 %.
        """
        n = len(respuestas)

        def pct(x: int) -> float:
            return round(100 * x / n, 1) if n else 0.0

        votos: Counter = Counter()
        for x in respuestas:
            votos.update(x if isinstance(x, list) else [x])
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

    @model_validator(mode="before")
    @classmethod
    def _una_sola(cls, v: Any) -> Any:
        if isinstance(v, dict):
            if "multiple" in v:
                raise ValueError(
                    "'multiple' no se usa en preguntas con respuesta correcta: "
                    "para marcar varias opciones usa 'tipo: multiopcion'"
                )
            if isinstance(v.get("correcta"), list):
                raise ValueError(
                    "'correcta' debe ser un solo número; para varias correctas "
                    "usa 'tipo: multiopcion' con 'correcta: [1, 3]'"
                )
        return v

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
        r["correctas"] = [self.correcta - 1]
        return r


class MultiOpcion(PreguntaDeOpciones):
    """Test con varias opciones correctas: el alumno marca todas las que crea. `correcta` es una lista.

    Puntuación entre 0 y 1: (correctas marcadas - incorrectas marcadas) / total de correctas,
    con mínimo 0. Categorías: acierto (todas las correctas y ninguna incorrecta), parcial
    (puntuación entre 0 y 1, sin llegar a ninguno de los extremos), error y «no lo sé».
    """

    tipo: Literal["multiopcion"]
    correcta: list[StrictInt]

    CATEGORIAS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("acierto", "Aciertos"),
        ("parcial", "Parcial"),
        ("error", "Error"),
        ("nose", "No lo sé"),
    )

    @model_validator(mode="before")
    @classmethod
    def _lista(cls, v: Any) -> Any:
        if isinstance(v, dict):
            if "multiple" in v:
                raise ValueError(
                    "'multiple' sobra: el tipo 'multiopcion' ya permite marcar varias opciones"
                )
            if "correcta" in v and not isinstance(v["correcta"], list):
                raise ValueError(
                    "'correcta' debe ser una lista de números (por ejemplo 'correcta: [1, 3]'); "
                    "con una sola correcta usa el tipo 'una_opcion'"
                )
        return v

    @model_validator(mode="after")
    def _coherente(self) -> "MultiOpcion":
        n = len(self.opciones)
        if not self.correcta:
            raise ValueError("'correcta' necesita al menos una opción")
        if len(set(self.correcta)) != len(self.correcta):
            raise ValueError("'correcta' tiene números repetidos")
        if any(not 1 <= c <= n for c in self.correcta):
            raise ValueError(
                f"los números de 'correcta' deben estar entre 1 y {n} "
                "(la primera opción es la 1)"
            )
        return self

    @property
    def con_varias(self) -> bool:
        return True

    def puntuacion(self, marcadas: list[int]) -> float:
        buenas = {c - 1 for c in self.correcta}
        aciertos = len(buenas & set(marcadas))
        falladas = len(set(marcadas) - buenas)
        return max(0.0, (aciertos - falladas) / len(buenas))

    def evaluar(self, r: Any) -> tuple[str, float]:
        """Devuelve (categoría, puntuación entre 0 y 1)."""
        if r == NOSE:
            return "nose", 0.0
        p = self.puntuacion(r)
        if p >= 1.0:
            return "acierto", 1.0
        if p > 0.0:
            return "parcial", p
        return "error", 0.0

    def resultados(self, respuestas: list[Any]) -> dict:
        r = self._reparto(respuestas)
        cats = Counter(self.evaluar(x)[0] for x in respuestas)
        n = r["total"]
        r["categorias"] = [
            {"clave": k, "etiqueta": e, "n": cats[k], "pct": round(100 * cats[k] / n, 1) if n else 0.0}
            for k, e in self.CATEGORIAS
        ]
        r["correcta"] = None
        r["correctas"] = [c - 1 for c in self.correcta]
        return r


class Encuesta(PreguntaDeOpciones):
    """Sondeo de opinión o de experiencia: una opción por alumno y ninguna correcta.

    No hay aciertos ni errores: los resultados son solo el reparto por opción, y la
    pregunta no cuenta en los porcentajes globales del resumen. La opción «No lo sé /
    quiero que se explique» no se añade salvo que se pida con `nose: true`.
    """

    tipo: Literal["encuesta"]
    nose: StrictBool = False
    # Si es verdadero, cada alumno marca todas las opciones que correspondan.
    multiple: StrictBool = False

    puntua: ClassVar[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _sin_correcta(cls, v: Any) -> Any:
        if isinstance(v, dict) and "correcta" in v:
            raise ValueError("una encuesta no tiene respuesta correcta: quita 'correcta'")
        if isinstance(v, dict) and v.get("rapido") is True:
            raise ValueError("una encuesta no puede ser rápida: quita 'rapido: true'")
        return v

    @property
    def con_nose(self) -> bool:
        return self.nose

    @property
    def con_varias(self) -> bool:
        return self.multiple

    def evaluar(self, r: Any) -> tuple[str, float]:
        raise NotImplementedError("una encuesta no se evalúa")

    def resultados(self, respuestas: list[Any]) -> dict:
        r = self._reparto(respuestas)
        r["categorias"] = []
        r["correcta"] = None
        r["correctas"] = []
        r["multiple"] = self.multiple
        return r


TIPOS: dict[str, type[PreguntaBase]] = {
    "una_opcion": UnaOpcion,
    "multiopcion": MultiOpcion,
    "encuesta": Encuesta,
}
