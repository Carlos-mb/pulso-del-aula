from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pulso.app import crear_app
from pulso.cargador import ErrorBanco, cargar

PREGUNTAS = Path(__file__).parent.parent / "preguntas"
TOKEN_A, TOKEN_B, TOKEN_C = "a" * 16, "b" * 16, "c" * 16


def escribe(tmp_path: Path, contenido: str) -> Path:
    (tmp_path / "t.yaml").write_text(contenido, encoding="utf-8")
    return tmp_path


# ---------- carga de preguntas ----------
def test_carga_ejemplo():
    temas = cargar(PREGUNTAS)
    assert {"redes", "imagenes"} <= set(temas)
    assert temas["redes"].preguntas[0].id == "redes-01"


def test_tiempo_de_pregunta_y_de_tema():
    temas = cargar(PREGUNTAS)
    redes, imagenes = temas["redes"], temas["imagenes"]
    assert [redes.tiempo_de(p) for p in redes.preguntas] == [30, 45]       # tema / pregunta
    assert [imagenes.tiempo_de(p) for p in imagenes.preguntas] == [0, 15]  # sin tema -> 0 / pregunta


def test_pregunta_con_tiempo_cero_anula_el_del_tema(tmp_path):
    d = escribe(tmp_path, """
temas:
  t:
    tiempo: 20
    preguntas:
      - {texto: "a", opciones: [x, y], correcta: 1}
      - {texto: "b", opciones: [x, y], correcta: 1, tiempo: 0}
""")
    t = cargar(d)["t"]
    assert [t.tiempo_de(p) for p in t.preguntas] == [20, 0]


@pytest.mark.parametrize("fragmento, mensaje", [
    ("opciones: [a, b]\n        correcta: 3", "entre 1 y 2"),
    ("opciones: [a]\n        correcta: 1", "al menos 2"),
    ("opciones: [a, No]\n        correcta: 1", "entrecomíllalo"),
    ("opciones: [a, b]\n        correcta: 1\n        corecta: 2", "corecta"),
    ("opciones: [a, b]\n        correcta: 1\n        tiempo: -5", "tiempo"),
    ("opciones: [a, {imagen: no_existe.png}]\n        correcta: 1", "no existe la imagen"),
    ("opciones: [a, {imagen: ../x.png}]\n        correcta: 1", "sale de la carpeta"),
    ("tipo: raro\n        opciones: [a, b]\n        correcta: 1", "tipo 'raro'"),
])
def test_errores_de_carga(tmp_path, fragmento, mensaje):
    d = escribe(tmp_path, f"""
temas:
  t:
    preguntas:
      - texto: "?"
        {fragmento}
""")
    with pytest.raises(ErrorBanco, match=mensaje):
        cargar(d)


@pytest.mark.parametrize("valor", ["rápido", "-1", "true", "1.5"])
def test_tiempo_de_tema_invalido(tmp_path, valor):
    d = escribe(tmp_path, f"""
temas:
  t:
    tiempo: {valor}
    preguntas:
      - {{texto: "a", opciones: [x, y], correcta: 1}}
""")
    with pytest.raises(ErrorBanco, match="tiempo"):
        cargar(d)


# ---------- evaluación ----------
def test_evaluar_y_resultados():
    p = cargar(PREGUNTAS)["redes"].preguntas[0]  # correcta = 2 -> índice 1
    assert p.evaluar(1) == ("acierto", 1.0)
    assert p.evaluar(0) == ("error", 0.0)
    assert p.evaluar("nose") == ("nose", 0.0)
    r = p.resultados([1, 1, 0, "nose"])
    cat = {c["clave"]: c["n"] for c in r["categorias"]}
    assert cat == {"acierto": 2, "error": 1, "nose": 1}
    assert [c["etiqueta"] for c in r["categorias"]] == ["Aciertos", "Error", "No lo sé"]
    assert r["opciones"][1]["pct"] == 50.0
    assert r["correcta"] == 1


def test_resultados_sin_respuestas():
    p = cargar(PREGUNTAS)["redes"].preguntas[0]
    assert p.resultados([])["categorias"][0]["pct"] == 0.0


# ---------- API ----------
class Reloj:
    """Reloj controlable para probar el temporizador sin esperar."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def cliente(reloj):
    app = crear_app(cargar(PREGUNTAS), PREGUNTAS, 8000, reloj=reloj)
    with TestClient(app, client=("127.0.0.1", 5000)) as docente, \
         TestClient(app, client=("192.168.1.50", 5000)) as alumno:
        yield docente, alumno


def responde(alumno, token, valor):
    return alumno.post("/api/responder", json={"token": token, "respuesta": valor})


def estado(c, **params):
    return c.get("/api/estado", params=params).json()


def inicia(docente, tema):
    """Elige el tema y empieza el test (sale de la sala de espera)."""
    assert docente.post(f"/api/docente/tema/{tema}").status_code == 200
    assert docente.post("/api/docente/empezar").status_code == 200


def test_flujo_completo(cliente):
    docente, alumno = cliente
    assert estado(alumno) == {"fase": "inicio"}
    assert responde(alumno, TOKEN_A, 1).status_code == 409   # aún no hay pregunta

    assert docente.post("/api/docente/tema/redes").status_code == 200
    assert estado(alumno)["fase"] == "sala"
    assert responde(alumno, TOKEN_A, 1).status_code == 409   # en la sala aún no se vota
    assert docente.post("/api/docente/empezar").status_code == 200

    # la votación se abre sola al presentar la pregunta
    e = estado(alumno)          # (sin token: así nadie figura como conectado y no hay cierre automático)
    assert e["fase"] == "abierta"
    assert "correcta" not in str(e)          # la solución no viaja al alumno
    assert "explicacion" not in str(e)

    assert responde(alumno, TOKEN_A, 0).status_code == 200
    assert responde(alumno, TOKEN_A, 1).status_code == 200   # cambia de opinión: sigue contando 1
    assert responde(alumno, TOKEN_B, 0).status_code == 200
    assert responde(alumno, TOKEN_C, "nose").status_code == 200
    assert responde(alumno, TOKEN_C, 99).status_code == 400
    assert responde(alumno, TOKEN_C, True).status_code == 422   # un booleano no es una opción
    assert responde(alumno, TOKEN_C, "otra cosa").status_code == 400
    assert estado(alumno)["n_respuestas"] == 3

    docente.post("/api/docente/cerrar")
    e = estado(alumno, token=TOKEN_A)
    assert e["mi_categoria"] == "acierto"
    assert {c["clave"]: c["n"] for c in e["resultados"]["categorias"]} == \
        {"acierto": 1, "error": 1, "nose": 1}
    assert responde(alumno, TOKEN_A, 0).status_code == 409   # cerrada

    # siguiente pregunta: se abre sola; volver a la anterior conserva sus resultados
    docente.post("/api/docente/cerrar")  # (cierra la 1 de nuevo: no-op)
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["fase"] == "abierta"
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/anterior")
    e = estado(alumno)
    assert e["fase"] == "cerrada" and e["n_respuestas"] == 3

    # borrar respuestas: la pregunta se abre otra vez, vacía
    docente.post("/api/docente/reiniciar")
    e = docente.get("/api/docente/estado").json()
    assert e["fase"] == "abierta" and e["n_respuestas"] == 0


def test_reabrir_conserva_respuestas(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    responde(alumno, TOKEN_A, 1)
    docente.post("/api/docente/cerrar")
    assert docente.post("/api/docente/abrir").status_code == 200
    e = estado(alumno)
    assert e["fase"] == "abierta" and e["n_respuestas"] == 1


def test_no_se_cambia_de_pregunta_con_votacion_abierta(cliente):
    docente, _ = cliente
    inicia(docente, "redes")
    assert docente.post("/api/docente/siguiente").status_code == 409
    assert docente.post("/api/docente/anterior").status_code == 409


# ---------- tiempo ----------
def test_el_tiempo_se_agota_y_cierra_la_votacion(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")              # tema: 30 s
    e = estado(alumno)
    assert e["tiempo"] == {"total": 30, "restante": 30.0}

    reloj.t += 29
    assert estado(alumno)["tiempo"]["restante"] == 1.0
    assert responde(alumno, TOKEN_A, 1).status_code == 200

    reloj.t += 2                                          # se agota
    assert responde(alumno, TOKEN_B, 1).status_code == 409
    e = estado(alumno, token=TOKEN_A)
    assert e["fase"] == "cerrada" and "tiempo" not in e
    assert e["resultados"]["total"] == 1

    # el docente pulsa «cerrar» justo después de agotarse: no es un error
    assert docente.post("/api/docente/cerrar").status_code == 200


def test_tiempo_propio_de_la_pregunta(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")               # pregunta 2: 45 s
    assert estado(alumno)["tiempo"]["total"] == 45


def test_sin_tiempo_no_hay_cuenta_atras(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "imagenes")           # pregunta 1: sin límite
    reloj.t += 10_000
    e = estado(alumno)
    assert e["fase"] == "abierta" and "tiempo" not in e


def test_reabrir_reinicia_el_tiempo(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")
    reloj.t += 31
    assert estado(alumno)["fase"] == "cerrada"
    docente.post("/api/docente/abrir")
    assert estado(alumno)["tiempo"]["restante"] == 30.0


def test_volver_a_una_pregunta_cerrada_sin_respuestas_no_la_reabre(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")
    reloj.t += 31                                         # nadie respondió y se cerró sola
    docente.post("/api/docente/siguiente")
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/anterior")
    assert estado(alumno)["fase"] == "cerrada"


# ---------- resumen final ----------
def test_resumen_al_acabar_el_test(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    responde(alumno, TOKEN_A, 1)          # acierto
    responde(alumno, TOKEN_B, 0)          # error
    responde(alumno, TOKEN_C, "nose")     # no lo sé
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    responde(alumno, TOKEN_A, 1)          # pregunta 2 (correcta = 2): acierto
    responde(alumno, TOKEN_B, 1)          # acierto
    docente.post("/api/docente/cerrar")
    assert docente.post("/api/docente/siguiente").status_code == 200   # acaba el tema

    e = estado(alumno)
    assert e["fase"] == "resumen" and "pregunta" not in e
    r = e["resumen"]
    assert [q["total"] for q in r["preguntas"]] == [3, 2]
    g = {c["clave"]: (c["n"], c["pct"]) for c in r["global"]["categorias"]}
    assert r["global"]["total"] == 5
    assert g == {"acierto": (3, 60.0), "error": (1, 20.0), "nose": (1, 20.0)}
    assert r["preguntas"][0]["categorias"][0]["pct"] == 33.3

    # desde el resumen se puede volver a la última pregunta, o ir a los temas
    docente.post("/api/docente/anterior")
    e = estado(alumno)
    assert e["fase"] == "cerrada" and e["indice"] == 1
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["fase"] == "resumen"
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["fase"] == "inicio"


def test_resumen_con_preguntas_sin_respuestas(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    for _ in range(2):
        docente.post("/api/docente/cerrar")
        docente.post("/api/docente/siguiente")
    r = estado(alumno)["resumen"]
    assert r["global"]["total"] == 0
    assert all(c["pct"] == 0.0 for c in r["global"]["categorias"])


# ---------- seguridad y recursos ----------
def test_panel_docente_solo_en_local(cliente):
    docente, alumno = cliente
    assert docente.get("/docente").status_code == 200
    assert docente.get("/api/docente/estado").status_code == 200
    assert alumno.get("/docente").status_code == 403
    assert alumno.get("/api/docente/estado").status_code == 403
    assert alumno.post("/api/docente/tema/redes").status_code == 403
    assert alumno.post("/api/docente/cerrar").status_code == 403


def test_token_invalido(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    assert responde(alumno, "corto", 0).status_code == 422


def test_media_y_paginas(cliente):
    _, alumno = cliente
    assert alumno.get("/").status_code == 200
    assert alumno.get("/media/circulo.svg").status_code == 200
    assert alumno.get("/media/../ejemplo.yaml").status_code == 404
    assert alumno.get("/static/alumno.js").status_code == 200


# ---------- sala de espera y presencia ----------
def test_sala_de_espera_hasta_que_el_docente_empieza(cliente, reloj):
    docente, alumno = cliente
    docente.post("/api/docente/tema/redes")
    e = estado(alumno)
    assert e["fase"] == "sala"
    assert e["tema"]["titulo"] == "Redes básicas" and e["total"] == 2
    assert "pregunta" not in e and "tiempo" not in e

    reloj.t += 3600                      # por mucho que pase el tiempo, no se abre sola
    assert estado(alumno)["fase"] == "sala"
    assert docente.post("/api/docente/cerrar").status_code == 200       # no-op
    assert docente.post("/api/docente/abrir").status_code == 409
    assert docente.post("/api/docente/reiniciar").status_code == 409

    assert docente.post("/api/docente/empezar").status_code == 200
    e = estado(alumno)
    assert e["fase"] == "abierta" and e["tiempo"]["restante"] == 30.0   # el tiempo cuenta desde aquí
    assert docente.post("/api/docente/empezar").status_code == 409      # ya ha empezado


def test_flecha_derecha_en_la_sala_empieza_y_la_izquierda_no_hace_nada(cliente):
    docente, alumno = cliente
    docente.post("/api/docente/tema/redes")
    docente.post("/api/docente/anterior")
    assert estado(alumno)["fase"] == "sala"
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["fase"] == "abierta"


def test_conectados(cliente, reloj):
    docente, alumno = cliente
    conectados = lambda: docente.get("/api/docente/estado").json()["conectados"]

    assert conectados() == 0
    docente.post("/api/docente/tema/redes")
    estado(alumno, token=TOKEN_A)
    estado(alumno, token=TOKEN_B)
    estado(alumno, token=TOKEN_A)        # el mismo navegador no cuenta dos veces
    estado(alumno)                       # sin token (p. ej. la pantalla del docente): no cuenta
    estado(alumno, token="corto")        # token no válido: se ignora
    assert conectados() == 2

    reloj.t += 6
    estado(alumno, token=TOKEN_A)        # A sigue consultando; B ya no
    reloj.t += 6
    assert conectados() == 1             # B lleva 12 s sin aparecer
    estado(alumno, token=TOKEN_C)
    assert conectados() == 2


def test_la_presencia_sobrevive_al_cambio_de_tema(cliente):
    docente, alumno = cliente
    estado(alumno, token=TOKEN_A)
    docente.post("/api/docente/tema/redes")
    docente.post("/api/docente/inicio")
    docente.post("/api/docente/tema/imagenes")
    assert docente.get("/api/docente/estado").json()["conectados"] == 1


def test_el_alumno_no_ve_el_numero_de_conectados(cliente):
    docente, alumno = cliente
    estado(alumno, token=TOKEN_A)
    assert "conectados" not in estado(alumno, token=TOKEN_A)


# ---------- cierre automático cuando han votado todos los conectados ----------
def conecta(alumno, *tokens):
    for t in tokens:
        estado(alumno, token=t)


def test_se_cierra_cuando_votan_todos_los_conectados(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")                          # tema con 30 s
    conecta(alumno, TOKEN_A, TOKEN_B, TOKEN_C)

    assert responde(alumno, TOKEN_A, 1).status_code == 200
    assert responde(alumno, TOKEN_B, 0).status_code == 200
    e = estado(alumno)
    assert e["fase"] == "abierta" and e["tiempo"]["restante"] == 30.0   # falta C

    assert responde(alumno, TOKEN_C, "nose").status_code == 200         # vota el último
    e = estado(alumno, token=TOKEN_A)
    assert e["fase"] == "cerrada" and e["motivo_cierre"] == "todos"
    assert e["resultados"]["total"] == 3 and "tiempo" not in e
    assert responde(alumno, TOKEN_A, 0).status_code == 409              # ya no se puede cambiar


def test_un_conectado_que_no_vota_mantiene_abierta_la_votacion(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")
    conecta(alumno, TOKEN_A, TOKEN_B)
    responde(alumno, TOKEN_A, 1)
    for _ in range(5):                                # B sigue conectado pero no vota
        reloj.t += 5
        conecta(alumno, TOKEN_A, TOKEN_B)
        assert estado(alumno)["fase"] == "abierta"


def test_si_el_que_falta_se_desconecta_se_cierra(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")
    conecta(alumno, TOKEN_A, TOKEN_B)
    responde(alumno, TOKEN_A, 1)                      # falta B
    reloj.t += 6
    conecta(alumno, TOKEN_A)
    assert estado(alumno)["fase"] == "abierta"        # B se vio hace 6 s: aún cuenta
    reloj.t += 6
    conecta(alumno, TOKEN_A)                          # B lleva 12 s sin aparecer
    e = estado(alumno)
    assert e["fase"] == "cerrada" and e["motivo_cierre"] == "todos"


def test_sin_conectados_no_se_cierra_sola(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    responde(alumno, TOKEN_A, 1)                      # vota sin haber consultado nunca el estado
    assert estado(alumno)["fase"] == "abierta"


def test_un_voto_de_quien_no_esta_conectado_no_cierra(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    conecta(alumno, TOKEN_A)
    responde(alumno, TOKEN_B, 1)                      # B no figura como conectado
    assert estado(alumno)["fase"] == "abierta"        # A aún no ha votado


def test_cada_pregunta_espera_a_los_conectados_de_nuevo(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    conecta(alumno, TOKEN_A)
    responde(alumno, TOKEN_A, 1)
    assert estado(alumno)["fase"] == "cerrada"
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["fase"] == "abierta"        # pregunta 2: A aún no ha votado en ella
    responde(alumno, TOKEN_A, 1)
    assert estado(alumno)["fase"] == "cerrada"


def test_el_tiempo_sigue_cerrando_y_gana_el_primer_motivo(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")
    conecta(alumno, TOKEN_A, TOKEN_B)
    responde(alumno, TOKEN_A, 1)
    reloj.t += 31
    conecta(alumno, TOKEN_A, TOKEN_B)
    e = estado(alumno)
    assert e["fase"] == "cerrada" and e["motivo_cierre"] == "tiempo"


def test_cierre_manual_registra_el_motivo(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    conecta(alumno, TOKEN_A)
    docente.post("/api/docente/cerrar")
    assert estado(alumno)["motivo_cierre"] == "docente"
    docente.post("/api/docente/siguiente")
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/anterior")             # al volver se conserva el motivo
    assert estado(alumno)["motivo_cierre"] == "docente"


def test_reabrir_no_se_vuelve_a_cerrar_por_todos_han_votado(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")
    conecta(alumno, TOKEN_A)
    responde(alumno, TOKEN_A, 1)
    assert estado(alumno)["motivo_cierre"] == "todos"

    assert docente.post("/api/docente/abrir").status_code == 200
    conecta(alumno, TOKEN_A)
    e = estado(alumno)
    assert e["fase"] == "abierta" and e["tiempo"]["restante"] == 30.0   # sigue abierta aunque A ya votó
    reloj.t += 31
    assert estado(alumno)["motivo_cierre"] == "tiempo"                  # pero el tiempo sí la cierra


def test_borrar_respuestas_reactiva_el_cierre_automatico(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    conecta(alumno, TOKEN_A)
    responde(alumno, TOKEN_A, 1)
    docente.post("/api/docente/abrir")                # reabierta: sin cierre automático
    docente.post("/api/docente/reiniciar")            # empieza de cero
    assert estado(alumno)["fase"] == "abierta" and estado(alumno)["n_respuestas"] == 0
    responde(alumno, TOKEN_A, 0)
    assert estado(alumno)["motivo_cierre"] == "todos"


def test_el_docente_ve_conectados_durante_la_votacion(cliente):
    docente, alumno = cliente
    inicia(docente, "redes")
    conecta(alumno, TOKEN_A, TOKEN_B)
    e = docente.get("/api/docente/estado").json()
    assert e["fase"] == "abierta" and e["conectados"] == 2


# ---------- encuestas (preguntas sin respuesta correcta) ----------
MIXTO = """
temas:
  mixto:
    titulo: "Encuesta y test"
    preguntas:
      - tipo: encuesta
        texto: "La terminal de Linux"
        opciones: ["Nunca", "Lo he visto", "Lo he usado alguna vez", "Lo uso con soltura"]
      - texto: "¿Capa de red?"
        opciones: ["Enlace", "Red"]
        correcta: 2
      - tipo: encuesta
        texto: "¿Quieres más práctica?"
        nose: true
        opciones: ["Sí", "No"]
"""


@pytest.fixture
def mixto(tmp_path, reloj):
    d = escribe(tmp_path, MIXTO)
    app = crear_app(cargar(d), d, 8000, reloj=reloj)
    with TestClient(app, client=("127.0.0.1", 5000)) as docente, \
         TestClient(app, client=("192.168.1.50", 5000)) as alumno:
        inicia(docente, "mixto")
        yield docente, alumno


def test_carga_de_encuesta(tmp_path):
    t = cargar(escribe(tmp_path, MIXTO))["mixto"]
    assert [p.tipo for p in t.preguntas] == ["encuesta", "una_opcion", "encuesta"]
    assert [p.con_nose for p in t.preguntas] == [False, True, True]
    assert [p.puntua for p in t.preguntas] == [False, True, False]


@pytest.mark.parametrize("fragmento, mensaje", [
    ("opciones: [a, b]\n        correcta: 1", "no tiene respuesta correcta"),
    ("opciones: [a]", "al menos 2"),
    ("opciones: [a, b]\n        nose: quizá", "nose"),
    ("opciones: [a, b]\n        nosee: true", "nosee"),
])
def test_errores_de_encuesta(tmp_path, fragmento, mensaje):
    d = escribe(tmp_path, f"""
temas:
  t:
    preguntas:
      - tipo: encuesta
        texto: "?"
        {fragmento}
""")
    with pytest.raises(ErrorBanco, match=mensaje):
        cargar(d)


def test_resultados_de_encuesta_son_solo_el_reparto(tmp_path):
    p = cargar(escribe(tmp_path, MIXTO))["mixto"].preguntas[0]
    r = p.resultados([0, 0, 1, 3])
    assert [o["n"] for o in r["opciones"]] == [2, 1, 0, 1]
    assert [o["pct"] for o in r["opciones"]] == [50.0, 25.0, 0.0, 25.0]
    assert r["total"] == 4
    assert r["categorias"] == [] and r["correcta"] is None and r["nose"] is None
    assert p.resultados([])["opciones"][0]["pct"] == 0.0


def test_la_encuesta_no_ofrece_nose_por_defecto(mixto):
    docente, alumno = mixto
    assert estado(alumno)["pregunta"]["con_nose"] is False
    assert responde(alumno, TOKEN_A, "nose").status_code == 400      # no se admite
    assert responde(alumno, TOKEN_A, 9).status_code == 400
    assert "mi_respuesta" not in estado(alumno, token=TOKEN_A)
    assert responde(alumno, TOKEN_A, 2).status_code == 200


def test_la_encuesta_con_nose_activado_lo_admite(mixto):
    docente, alumno = mixto
    for _ in range(2):
        docente.post("/api/docente/cerrar")
        docente.post("/api/docente/siguiente")
    assert estado(alumno)["pregunta"]["con_nose"] is True
    assert responde(alumno, TOKEN_A, "nose").status_code == 200
    assert responde(alumno, TOKEN_B, 0).status_code == 200
    docente.post("/api/docente/cerrar")
    r = docente.get("/api/docente/estado").json()["resultados"]
    assert r["nose"]["n"] == 1 and r["opciones"][0]["n"] == 1 and r["total"] == 2


def test_encuesta_cerrada_no_da_solucion_ni_categoria(mixto):
    docente, alumno = mixto
    assert "correcta" not in estado(alumno)["pregunta"]
    responde(alumno, TOKEN_A, 1)
    docente.post("/api/docente/cerrar")
    e = estado(alumno, token=TOKEN_A)
    assert e["fase"] == "cerrada" and e["mi_respuesta"] == 1
    assert "mi_categoria" not in e                                    # ni acierto ni error
    r = docente.get("/api/docente/estado").json()["resultados"]
    assert r["categorias"] == [] and r["correcta"] is None
    assert [o["n"] for o in r["opciones"]] == [0, 1, 0, 0]


def test_la_encuesta_se_cierra_como_las_demas(mixto):
    docente, alumno = mixto
    estado(alumno, token=TOKEN_A)                    # conectado
    responde(alumno, TOKEN_A, 0)                     # vota el único conectado
    e = docente.get("/api/docente/estado").json()
    assert e["fase"] == "cerrada" and e["motivo_cierre"] == "todos"


def test_las_encuestas_no_cuentan_en_el_resumen_global(mixto):
    docente, alumno = mixto
    responde(alumno, TOKEN_A, 3)                     # encuesta 1
    responde(alumno, TOKEN_B, 3)
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    responde(alumno, TOKEN_A, 1)                     # test: acierto
    responde(alumno, TOKEN_B, 0)                     # test: error
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    responde(alumno, TOKEN_A, "nose")                # encuesta 2 con «no lo sé»
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")

    r = estado(alumno)["resumen"]
    assert r["global"]["total"] == 2                 # solo las dos respuestas del test
    g = {c["clave"]: (c["n"], c["pct"]) for c in r["global"]["categorias"]}
    assert g == {"acierto": (1, 50.0), "error": (1, 50.0), "nose": (0, 0.0)}

    e1, test, e2 = r["preguntas"]
    assert [e1["tipo"], test["tipo"], e2["tipo"]] == ["encuesta", "una_opcion", "encuesta"]
    assert e1["categorias"] == [] and e1["total"] == 2
    assert [o["n"] for o in e1["reparto"]] == [0, 0, 0, 2] and e1["con_nose"] is False
    assert "reparto" not in test
    assert [o["n"] for o in e2["reparto"]] == [0, 0, 1] and e2["con_nose"] is True   # sí, no, «no lo sé»


def test_resumen_con_solo_encuestas(tmp_path, reloj):
    d = escribe(tmp_path, """
temas:
  e:
    preguntas:
      - {tipo: encuesta, texto: "?", opciones: [a, b]}
""")
    app = crear_app(cargar(d), d, 8000, reloj=reloj)
    with TestClient(app, client=("127.0.0.1", 5000)) as docente:
        inicia(docente, "e")
        docente.post("/api/docente/cerrar")
        docente.post("/api/docente/siguiente")
        r = docente.get("/api/docente/estado").json()["resumen"]
    assert r["global"] == {"total": 0, "categorias": []}
