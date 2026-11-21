"""Resumen final del test en Markdown, para guardarlo como documento de trabajo.

Solo texto: las imágenes no se incluyen (una opción que solo tiene imagen sale como «(imagen)»).
Los textos de preguntas y opciones ya están en Markdown y se copian tal cual.
"""
from __future__ import annotations

from datetime import datetime


def _pct(x: float) -> str:
    return f"{int(x + 0.5)} %"   # redondeo como en pantalla (Math.round)


def _categorias(cats: list[dict]) -> str:
    return " · ".join(f"{c['etiqueta']} {_pct(c['pct'])} ({c['n']})" for c in cats)


def _opcion(letra: str, o: dict, hay_respuestas: bool) -> str:
    texto = (o.get("texto") or "(imagen)").strip()
    datos = f"{_pct(o['pct'])} ({o['n']})" if hay_respuestas else "–"
    marca = " ✓ correcta" if o.get("correcta") else ""
    cabeza = f"- **{letra}** · {datos}{marca} · "
    if "\n" in texto:   # texto de varias líneas (p. ej. código): debajo, sangrado dentro del punto
        return cabeza.rstrip(" ·") + "\n\n" + "\n".join("  " + l if l else "" for l in texto.split("\n"))
    return cabeza + texto


def resumen_md(titulo: str, resumen: dict, fecha: datetime) -> str:
    """`resumen` es lo que devuelve `Sesion.resumen(con_ranking=True)`."""
    partes = [f"# Resumen: {titulo}", fecha.strftime("%d/%m/%Y %H:%M")]
    g = resumen["global"]
    if g["categorias"]:
        partes.append(f"**Global** ({g['total']} respuestas en preguntas con solución): "
                      + _categorias(g["categorias"]))
    if resumen.get("ranking"):
        partes.append("## Ranking final\n\n"
                      + "\n".join(f"- {f['alias']}: {f['puntos']} puntos" for f in resumen["ranking"]))
    for q in resumen["preguntas"]:
        encuesta = q["tipo"] == "encuesta"
        datos = f"{q['total']} respuesta{'' if q['total'] == 1 else 's'}"
        if encuesta:
            datos = "encuesta · " + datos
        elif q["total"]:
            datos += " · " + _categorias(q["categorias"])
        letras = iter("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        opciones = [_opcion("?" if o.get("nose") else next(letras), o, q["total"] > 0)
                    for o in q["opciones"]]
        partes.append(f"## Pregunta {q['indice'] + 1}\n\n{q['texto'].strip()}\n\n*{datos}*\n\n"
                      + "\n".join(opciones))
    return "\n\n".join(partes) + "\n"
