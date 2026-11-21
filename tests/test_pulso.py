from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pulso.__main__ import main
from pulso.acceso import normaliza_codigo, qr_svg
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
    # El tema «redes» pide alias: se pone uno si hace falta (en los demás temas no hace nada).
    alumno.post("/api/alias", json={"token": token, "alias": "alumno-" + token[:6]})
    return alumno.post("/api/responder", json={"token": token, "respuesta": valor})


def estado(c, **params):
    return c.get("/api/estado", params=params).json()


def inicia(docente, tema):
    """Elige el tema y empieza el test (sale de la sala de espera)."""
    assert docente.post(f"/api/docente/tema/{tema}").status_code == 200
    assert docente.post("/api/docente/empezar").status_code == 200


def test_flujo_completo(cliente):
    docente, alumno = cliente
    assert estado(alumno)["fase"] == "inicio" and "tema" not in estado(alumno)
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
    assert e["tiempo"] == {"total": 30, "restante": 30.0, "pausado": False}

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


def test_pausar_congela_el_tiempo_y_reanudar_continua(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")              # 30 s
    reloj.t += 10
    assert docente.post("/api/docente/pausar").status_code == 200
    reloj.t += 1000                                       # en pausa no se agota
    e = estado(alumno)
    assert e["fase"] == "abierta"
    assert e["tiempo"] == {"total": 30, "restante": 20.0, "pausado": True}
    assert responde(alumno, TOKEN_A, 1).status_code == 200   # se puede votar en pausa

    assert docente.post("/api/docente/pausar").status_code == 200   # reanuda
    assert estado(alumno)["tiempo"] == {"total": 30, "restante": 20.0, "pausado": False}
    reloj.t += 21
    e = estado(alumno)
    assert e["fase"] == "cerrada" and e["motivo_cierre"] == "tiempo"


def test_en_pausa_sigue_cerrando_cuando_votan_todos(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")
    estado(alumno, token=TOKEN_A)                         # conectado
    docente.post("/api/docente/pausar")
    responde(alumno, TOKEN_A, 1)
    e = estado(alumno, token=TOKEN_A)
    assert e["fase"] == "cerrada" and e["motivo_cierre"] == "todos"


def test_pausar_sin_tiempo_o_cerrada_es_un_error(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "imagenes")           # sin límite
    assert docente.post("/api/docente/pausar").status_code == 409
    docente.post("/api/docente/cerrar")
    assert docente.post("/api/docente/pausar").status_code == 409


def test_reabrir_tras_pausar_empieza_sin_pausa(cliente, reloj):
    docente, alumno = cliente
    inicia(docente, "redes")
    reloj.t += 10
    docente.post("/api/docente/pausar")
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/abrir")
    assert estado(alumno)["tiempo"] == {"total": 30, "restante": 30.0, "pausado": False}


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

    sesion = docente.app.state.sesion
    sesion.respuestas = {"redes-01": {TOKEN_A: 1}, "redes-02": {TOKEN_B: 0}}
    reloj.t += 3600                      # por mucho que pase el tiempo, no se abre sola
    assert estado(alumno)["fase"] == "sala"
    assert docente.post("/api/docente/cerrar").status_code == 200       # no-op
    assert docente.post("/api/docente/abrir").status_code == 409
    assert docente.post("/api/docente/reiniciar").status_code == 409

    assert docente.post("/api/docente/empezar").status_code == 200
    e = estado(alumno)
    assert e["fase"] == "abierta" and e["tiempo"]["restante"] == 30.0   # el tiempo cuenta desde aquí
    assert sesion.respuestas == {}
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
    conecta(alumno, TOKEN_A, TOKEN_B)
    conecta(alumno, TOKEN_A)             # el mismo navegador no cuenta dos veces
    estado(alumno)                       # sin token (p. ej. la pantalla del docente): no cuenta
    estado(alumno, token="corto")        # token no válido: se ignora
    assert conectados() == 2

    reloj.t += 6
    estado(alumno, token=TOKEN_A)        # A sigue consultando; B ya no
    reloj.t += 6
    assert conectados() == 1             # B lleva 12 s sin aparecer
    conecta(alumno, TOKEN_C)
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
    """Conecta a los alumnos (con alias, por si el tema lo pide, como «redes»)."""
    for t in tokens:
        alumno.post("/api/alias", json={"token": t, "alias": "alumno-" + t[:6]})
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


def test_la_encuesta_pasa_sola_a_la_siguiente_cuando_han_respondido_todos(mixto):
    docente, alumno = mixto
    estado(alumno, token=TOKEN_A)                    # conectado
    responde(alumno, TOKEN_A, 0)                     # vota el único conectado
    e = docente.get("/api/docente/estado").json()
    assert e["fase"] == "abierta" and e["indice"] == 1       # ya está en la pregunta siguiente (el test)
    assert e["pregunta"]["tipo"] == "una_opcion" and e["n_respuestas"] == 0
    # la respuesta de la encuesta no se pierde: sale en el resumen
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    enc = estado(alumno)["resumen"]["preguntas"][0]
    assert [o["n"] for o in enc["opciones"]] == [1, 0, 0, 0]


def test_las_preguntas_de_test_siguen_cerrandose_sin_avanzar(mixto):
    docente, alumno = mixto
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")           # pregunta 2: test
    estado(alumno, token=TOKEN_A)
    responde(alumno, TOKEN_A, 1)
    e = docente.get("/api/docente/estado").json()
    assert e["fase"] == "cerrada" and e["indice"] == 1 and e["motivo_cierre"] == "todos"


def test_la_ultima_encuesta_pasa_al_resumen(mixto):
    docente, alumno = mixto
    for _ in range(2):
        docente.post("/api/docente/cerrar")
        docente.post("/api/docente/siguiente")       # llegamos a la última pregunta: una encuesta
    estado(alumno, token=TOKEN_A)
    responde(alumno, TOKEN_A, "nose")
    e = docente.get("/api/docente/estado").json()
    assert e["fase"] == "resumen"
    assert [o["n"] for o in e["resumen"]["preguntas"][2]["opciones"]] == [0, 0, 1]


def test_la_encuesta_no_avanza_si_se_cierra_por_tiempo_o_a_mano(tmp_path, reloj):
    d = escribe(tmp_path, """
temas:
  t:
    preguntas:
      - {tipo: encuesta, texto: "a", opciones: [x, y], tiempo: 10}
      - {tipo: encuesta, texto: "b", opciones: [x, y]}
      - {texto: "c", opciones: [x, y], correcta: 1}
""")
    app = crear_app(cargar(d), d, 8000, reloj=reloj)
    with TestClient(app, client=("127.0.0.1", 5000)) as docente, \
         TestClient(app, client=("192.168.1.50", 5000)) as alumno:
        inicia(docente, "t")
        conecta(alumno, TOKEN_A, TOKEN_B)            # dos conectados: no votan todos
        responde(alumno, TOKEN_A, 0)
        reloj.t += 11                                # se agota el tiempo
        e = docente.get("/api/docente/estado").json()
        assert e["fase"] == "cerrada" and e["indice"] == 0 and e["motivo_cierre"] == "tiempo"
        docente.post("/api/docente/siguiente")       # encuesta b
        responde(alumno, TOKEN_A, 1)
        docente.post("/api/docente/cerrar")          # el docente la cierra a mano
        e = docente.get("/api/docente/estado").json()
        assert e["fase"] == "cerrada" and e["indice"] == 1 and e["motivo_cierre"] == "docente"


def test_cerrar_justo_despues_de_que_respondan_todos_no_cierra_la_pregunta_nueva(mixto):
    """Una acción del docente no debe caer sobre la pregunta que se acaba de abrir sola."""
    docente, alumno = mixto
    estado(alumno, token=TOKEN_A)
    sesion = docente.app.state.sesion
    sesion.respuestas.setdefault(sesion.pregunta.id, {})[TOKEN_A] = 0   # responde, sin que nadie consulte aún
    docente.post("/api/docente/cerrar")              # pulsa «cerrar» antes del siguiente sondeo
    e = docente.get("/api/docente/estado").json()
    assert e["fase"] == "cerrada" and e["indice"] == 0      # cierra la encuesta, sin saltar a la siguiente


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
    assert [o["n"] for o in e1["opciones"]] == [0, 0, 0, 2]
    assert [o["texto"] for o in e1["opciones"]][-1] == "Lo uso con soltura"
    assert [o["n"] for o in e2["opciones"]] == [0, 0, 1] and e2["opciones"][-1]["nose"] is True   # sí, no, «no lo sé»
    assert [o["n"] for o in test["opciones"]] == [1, 1, 0]            # enlace, red, «no lo sé»
    assert [o["correcta"] for o in test["opciones"]] == [False, True, False]


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


# ---------- varias opciones: multiopción y encuestas con `multiple` ----------
MULTI = """
temas:
  m:
    titulo: "Multiopción"
    preguntas:
      - tipo: multiopcion
        texto: "¿Cuáles son IPv4 privadas?"
        opciones: ["10.0.0.5", "8.8.8.8", "192.168.1.20", "172.16.4.9"]
        correcta: [1, 3, 4]
      - tipo: encuesta
        multiple: true
        texto: "Estudios previos"
        opciones: ["Ninguno", "FP", "Universidad", "Trabajo"]
      - texto: "¿Capa de red?"
        opciones: ["Enlace", "Red"]
        correcta: 2
"""


@pytest.fixture
def multi(tmp_path, reloj):
    d = escribe(tmp_path, MULTI)
    app = crear_app(cargar(d), d, 8000, reloj=reloj)
    with TestClient(app, client=("127.0.0.1", 5000)) as docente, \
         TestClient(app, client=("192.168.1.50", 5000)) as alumno:
        inicia(docente, "m")
        yield docente, alumno


def test_carga_de_multiopcion_y_encuesta_multiple(tmp_path):
    t = cargar(escribe(tmp_path, MULTI))["m"]
    assert [p.tipo for p in t.preguntas] == ["multiopcion", "encuesta", "una_opcion"]
    assert [p.con_varias for p in t.preguntas] == [True, True, False]
    assert [p.puntua for p in t.preguntas] == [True, False, True]


@pytest.mark.parametrize("fragmento, mensaje", [
    ("tipo: multiopcion\n        opciones: [a, b]\n        correcta: 1", "debe ser una lista"),
    ("tipo: multiopcion\n        opciones: [a, b]\n        correcta: []", "al menos una"),
    ("tipo: multiopcion\n        opciones: [a, b]\n        correcta: [1, 1]", "repetidos"),
    ("tipo: multiopcion\n        opciones: [a, b]\n        correcta: [1, 3]", "entre 1 y 2"),
    ("tipo: multiopcion\n        opciones: [a, b]\n        correcta: [0]", "entre 1 y 2"),
    ("tipo: multiopcion\n        opciones: [a]\n        correcta: [1]", "al menos 2"),
    ("tipo: multiopcion\n        opciones: [a, b]", "correcta"),
    ("tipo: multiopcion\n        multiple: true\n        opciones: [a, b]\n        correcta: [1]", "sobra"),
    ("opciones: [a, b]\n        correcta: [1, 2]", "tipo: multiopcion"),
    ("opciones: [a, b]\n        correcta: 1\n        multiple: true", "tipo: multiopcion"),
    ("tipo: encuesta\n        opciones: [a, b]\n        multiple: quizá", "multiple"),
    ("tipo: encuesta\n        opciones: [a, b]\n        multiple: true\n        correcta: [1]", "no tiene respuesta correcta"),
])
def test_errores_de_varias_opciones(tmp_path, fragmento, mensaje):
    d = escribe(tmp_path, f"""
temas:
  t:
    preguntas:
      - texto: "?"
        {fragmento}
""")
    with pytest.raises(ErrorBanco, match=mensaje):
        cargar(d)


def test_puntuacion_proporcional_penalizando_incorrectas(tmp_path):
    p = cargar(escribe(tmp_path, MULTI))["m"].preguntas[0]   # correctas: índices 0, 2, 3
    assert p.evaluar([0, 2, 3]) == ("acierto", 1.0)
    assert p.evaluar([0, 2]) == ("parcial", pytest.approx(2 / 3))
    assert p.evaluar([0, 1, 2, 3]) == ("parcial", pytest.approx(2 / 3))      # 3 aciertos - 1 fallo
    assert p.evaluar([0, 1]) == ("error", 0.0)                               # 1 - 1 = 0
    assert p.evaluar([1]) == ("error", 0.0)                                  # nunca baja de 0
    assert p.evaluar([1, 0]) == ("error", 0.0)
    assert p.evaluar("nose") == ("nose", 0.0)


def test_resultados_de_multiopcion(tmp_path):
    p = cargar(escribe(tmp_path, MULTI))["m"].preguntas[0]
    r = p.resultados([[0, 2, 3], [0, 2], [1], "nose"])
    assert {c["clave"]: c["n"] for c in r["categorias"]} == {"acierto": 1, "parcial": 1, "error": 1, "nose": 1}
    assert [c["etiqueta"] for c in r["categorias"]] == ["Aciertos", "Parcial", "Error", "No lo sé"]
    assert [o["n"] for o in r["opciones"]] == [2, 1, 2, 1]
    assert [o["pct"] for o in r["opciones"]] == [50.0, 25.0, 50.0, 25.0]   # sobre 4 alumnos: suman más de 100
    assert r["nose"]["n"] == 1 and r["total"] == 4
    assert r["correctas"] == [0, 2, 3]


def test_validacion_de_respuestas_con_varias_opciones(multi):
    docente, alumno = multi
    conecta(alumno, TOKEN_A, TOKEN_B)          # B no vota: la pregunta sigue abierta
    pub = estado(alumno)["pregunta"]
    assert pub["multiple"] is True and pub["con_nose"] is True and "correcta" not in pub
    for mala in (1, [], [4], [-1], [1, 1], [True], ["a"], "otra", [0, "nose"], [0, 1, 2, 3, 0]):
        assert responde(alumno, TOKEN_A, mala).status_code in (400, 422), mala
    assert "mi_respuesta" not in estado(alumno, token=TOKEN_A)
    assert responde(alumno, TOKEN_A, [3, 0]).status_code == 200
    assert estado(alumno, token=TOKEN_A)["mi_respuesta"] == [0, 3]          # se guarda ordenada
    assert responde(alumno, TOKEN_A, "nose").status_code == 200              # «no lo sé» sustituye a las marcas
    assert estado(alumno, token=TOKEN_A)["mi_respuesta"] == "nose"
    assert responde(alumno, TOKEN_A, [1]).status_code == 200                 # y se puede volver a cambiar


def test_una_opcion_no_admite_listas(multi):
    docente, alumno = multi
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["pregunta"]["multiple"] is False
    assert responde(alumno, TOKEN_A, [1]).status_code == 400
    assert responde(alumno, TOKEN_A, 1).status_code == 200


def test_multiopcion_cerrada_da_categoria_y_marca_todas_las_correctas(multi):
    docente, alumno = multi
    responde(alumno, TOKEN_A, [0, 2, 3])
    responde(alumno, TOKEN_B, [0, 2])
    responde(alumno, TOKEN_C, [1])
    docente.post("/api/docente/cerrar")
    assert estado(alumno, token=TOKEN_A)["mi_categoria"] == "acierto"
    assert estado(alumno, token=TOKEN_B)["mi_categoria"] == "parcial"
    assert estado(alumno, token=TOKEN_C)["mi_categoria"] == "error"
    r = docente.get("/api/docente/estado").json()["resultados"]
    assert r["correctas"] == [0, 2, 3]
    assert [o["n"] for o in r["opciones"]] == [2, 1, 2, 1]


def test_multiopcion_se_cierra_cuando_todos_han_enviado(multi):
    docente, alumno = multi
    estado(alumno, token=TOKEN_A)
    estado(alumno, token=TOKEN_B)
    assert docente.get("/api/docente/estado").json()["fase"] == "abierta"
    responde(alumno, TOKEN_A, [0])
    assert docente.get("/api/docente/estado").json()["fase"] == "abierta"    # falta uno por enviar
    responde(alumno, TOKEN_B, [1])
    e = docente.get("/api/docente/estado").json()
    assert e["fase"] == "cerrada" and e["motivo_cierre"] == "todos"


def test_encuesta_multiple_porcentaje_de_alumnos_que_marcan_cada_opcion(multi):
    docente, alumno = multi
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["pregunta"]["multiple"] is True
    assert responde(alumno, TOKEN_A, [1, 2]).status_code == 200
    assert responde(alumno, TOKEN_B, [2]).status_code == 200
    assert responde(alumno, TOKEN_C, [0, 1, 2, 3]).status_code == 200
    assert responde(alumno, "d" * 16, [2, 3]).status_code == 200
    docente.post("/api/docente/cerrar")
    e = docente.get("/api/docente/estado").json()
    r = e["resultados"]
    assert r["total"] == 4 and r["categorias"] == [] and r["correctas"] == []
    assert [o["pct"] for o in r["opciones"]] == [25.0, 50.0, 100.0, 50.0]    # no suman 100 %
    assert "mi_categoria" not in estado(alumno, token=TOKEN_A)


def test_resumen_con_parcial_y_encuesta_multiple(multi):
    docente, alumno = multi
    responde(alumno, TOKEN_A, [0, 2, 3])                 # acierto
    responde(alumno, TOKEN_B, [0, 2])                    # parcial
    responde(alumno, TOKEN_C, [1])                       # error
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    responde(alumno, TOKEN_A, [0, 1])                    # encuesta múltiple
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    responde(alumno, TOKEN_A, 1)                         # una_opcion: acierto
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    r = estado(alumno)["resumen"]
    assert [c["clave"] for c in r["global"]["categorias"]] == ["acierto", "parcial", "error", "nose"]
    g = {c["clave"]: c["n"] for c in r["global"]["categorias"]}
    assert g == {"acierto": 2, "parcial": 1, "error": 1, "nose": 0} and r["global"]["total"] == 4
    multi_q, enc, _ = r["preguntas"]
    assert [c["clave"] for c in multi_q["categorias"]] == ["acierto", "parcial", "error", "nose"]
    assert [o["n"] for o in enc["opciones"]] == [1, 1, 0, 0]


def test_el_ejemplo_incluye_varias_opciones():
    temas = cargar(PREGUNTAS)
    assert [p.tipo for p in temas["multiopcion"].preguntas] == ["multiopcion", "multiopcion"]
    assert any(p.tipo == "encuesta" and p.con_varias for p in temas["experiencia"].preguntas)


# ---------- modo remoto (túnel de Cloudflare): código de sala y clave del docente ----------
URL_PUBLICA = "https://preguntas.ejemplo.online"
CLAVE = "clave-del-docente"
TOKEN_D = "d" * 16


@pytest.fixture
def remoto(reloj):
    """En modo remoto TODAS las peticiones llegan desde 127.0.0.1 (el túnel corre en el mismo equipo)."""
    app = crear_app(cargar(PREGUNTAS), PREGUNTAS, 8000, reloj=reloj, url_publica=URL_PUBLICA, clave=CLAVE)
    with TestClient(app, client=("127.0.0.1", 5000)) as docente, \
         TestClient(app, client=("127.0.0.1", 5001)) as alumno:
        yield docente, alumno, app.state.sesion


def entra(alumno, token, codigo):
    return alumno.post("/api/entrar", json={"token": token, "codigo": codigo})


def login(docente, clave=CLAVE, **cabeceras):
    return docente.post("/api/docente/entrar", json={"clave": clave}, headers=cabeceras)


def test_sin_codigo_el_alumno_no_ve_nada_ni_vota(remoto):
    docente, alumno, sesion = remoto
    login(docente)
    inicia(docente, "redes")
    r = alumno.get("/api/estado", params={"token": TOKEN_A})
    assert r.status_code == 401 and r.json() == {"detail": "codigo"}
    assert alumno.get("/api/estado").status_code == 401                 # ni siquiera sin token
    assert responde(alumno, TOKEN_A, 1).status_code == 401
    assert sesion.conectados() == 0                                     # no cuenta como conectado
    assert docente.get("/api/docente/estado").json()["n_respuestas"] == 0


def test_con_el_codigo_el_alumno_entra_y_participa(remoto):
    docente, alumno, sesion = remoto
    login(docente)
    inicia(docente, "redes")
    assert entra(alumno, TOKEN_A, sesion.codigo).status_code == 200
    assert estado(alumno, token=TOKEN_A)["fase"] == "abierta"
    assert responde(alumno, TOKEN_A, 1).status_code == 200
    assert sesion.conectados() == 1
    assert alumno.get("/api/estado", params={"token": TOKEN_B}).status_code == 401   # otro token, sin entrar


def test_codigo_incorrecto(remoto):
    docente, alumno, sesion = remoto
    r = entra(alumno, TOKEN_A, "XXXXXX")
    assert r.status_code == 403 and r.json()["detail"] == "Código incorrecto"
    assert alumno.get("/api/estado", params={"token": TOKEN_A}).status_code == 401
    assert alumno.post("/api/entrar", json={"token": "corto", "codigo": sesion.codigo}).status_code == 422


def test_el_codigo_admite_minusculas_espacios_y_guiones(remoto):
    docente, alumno, sesion = remoto
    c = sesion.codigo.lower()
    assert entra(alumno, TOKEN_A, f" {c[:3]}-{c[3:]} ").status_code == 200
    assert normaliza_codigo(" ab-c 2") == "ABC2"


def test_el_codigo_es_de_6_caracteres_sin_ambiguedades(remoto):
    _, _, sesion = remoto
    assert len(sesion.codigo) == 6 and not set(sesion.codigo) & set("01OIL")


def test_cierre_por_todos_ha_votado_solo_cuenta_a_los_admitidos(remoto):
    docente, alumno, sesion = remoto
    login(docente)
    inicia(docente, "redes")
    entra(alumno, TOKEN_A, sesion.codigo)
    estado(alumno, token=TOKEN_A)
    alumno.get("/api/estado", params={"token": TOKEN_C})                # intruso: 401, no es «conectado»
    responde(alumno, TOKEN_A, 1)                                        # el único admitido vota
    e = docente.get("/api/docente/estado").json()
    assert e["fase"] == "cerrada" and e["motivo_cierre"] == "todos"


def test_demasiados_codigos_erroneos_bloquea_las_entradas_nuevas(remoto, reloj):
    docente, alumno, sesion = remoto
    entra(alumno, TOKEN_B, sesion.codigo)                               # ya admitido
    for i in range(120):
        assert entra(alumno, TOKEN_A, "XXXXXX").status_code == 403
    assert entra(alumno, TOKEN_A, "XXXXXX").status_code == 429
    assert entra(alumno, TOKEN_A, sesion.codigo).status_code == 429     # ni con el código bueno
    assert alumno.get("/api/estado", params={"token": TOKEN_B}).status_code == 200   # el admitido sigue
    reloj.t += 61
    assert entra(alumno, TOKEN_A, sesion.codigo).status_code == 200


def test_la_misma_ip_no_penaliza_a_los_alumnos_que_aciertan(remoto):
    docente, alumno, sesion = remoto
    for i in range(30):                                                  # un aula entera tecleando
        assert entra(alumno, f"alumno{i:02d}" * 2, sesion.codigo).status_code == 200


def test_panel_del_docente_pide_clave_aunque_llegue_desde_localhost(remoto):
    docente, alumno, sesion = remoto
    assert docente.get("/docente").status_code == 200                    # la página no tiene secretos
    for ruta in ("/api/docente/estado", "/api/docente/qr.svg"):
        r = docente.get(ruta)
        assert r.status_code == 401 and r.json()["detail"] == "clave"
    assert docente.post("/api/docente/tema/redes").status_code == 401
    assert docente.post("/api/docente/cerrar").status_code == 401
    r = login(docente, "otra")
    assert r.status_code == 403 and r.json()["detail"] == "Clave incorrecta"
    assert docente.get("/api/docente/estado").status_code == 401
    r = login(docente)
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert docente.get("/api/docente/estado").status_code == 200
    assert docente.post("/api/docente/tema/redes").status_code == 200
    # el alumno (otra «sesión» de navegador) sigue sin acceso
    assert alumno.get("/api/docente/estado").status_code == 401


def test_la_cookie_del_docente_caduca(remoto, reloj):
    docente, _, _ = remoto
    login(docente)
    assert docente.get("/api/docente/estado").status_code == 200
    reloj.t += 13 * 3600
    assert docente.get("/api/docente/estado").status_code == 401


def test_la_cookie_es_secure_solo_si_llega_por_el_tunel(remoto):
    docente, alumno, _ = remoto
    assert "secure" not in login(docente).headers["set-cookie"].lower()          # http://localhost
    assert "secure" in login(alumno, **{"Cf-Connecting-Ip": "203.0.113.9"}).headers["set-cookie"].lower()


def test_limite_de_intentos_de_clave_por_origen(remoto):
    docente, alumno, _ = remoto
    for _ in range(10):
        assert login(alumno, "mala", **{"Cf-Connecting-Ip": "203.0.113.9"}).status_code == 403
    assert login(alumno, CLAVE, **{"Cf-Connecting-Ip": "203.0.113.9"}).status_code == 429    # bloqueado
    assert login(docente, "mala").status_code == 403                    # el docente en local tiene su propio cubo
    assert login(docente).status_code == 200
    assert login(alumno, CLAVE, **{"Cf-Connecting-Ip": "198.51.100.7"}).status_code == 200   # otro origen


def test_el_docente_ve_codigo_y_url_publica_y_el_qr_apunta_a_ellos(remoto):
    docente, _, sesion = remoto
    login(docente)
    e = docente.get("/api/docente/estado").json()
    assert e["codigo"] == sesion.codigo and e["url_alumnos"] == URL_PUBLICA + "/"
    r = docente.get("/api/docente/qr.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert r.text == qr_svg(f"{URL_PUBLICA}/?c={sesion.codigo}") and "<svg" in r.text


def test_cabeceras_de_seguridad(remoto):
    docente, _, _ = remoto
    r = docente.get("/docente")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"


def test_el_modo_local_no_pide_codigo_y_no_cambia(cliente):
    docente, alumno = cliente
    assert docente.get("/api/docente/estado").json()["codigo"] is None
    assert estado(alumno, token=TOKEN_A)["fase"] == "inicio"            # sin código, como siempre
    assert alumno.post("/api/entrar", json={"token": TOKEN_A, "codigo": ""}).status_code == 200
    assert docente.get("/api/docente/qr.svg").status_code == 404
    assert alumno.get("/api/docente/estado").status_code == 403         # solo desde el equipo, como siempre


def test_clave_opcional_en_modo_local(reloj):
    app = crear_app(cargar(PREGUNTAS), PREGUNTAS, 8000, reloj=reloj, clave="x")
    with TestClient(app, client=("127.0.0.1", 5000)) as docente, \
         TestClient(app, client=("192.168.1.50", 5000)) as otro:
        assert docente.get("/api/docente/estado").status_code == 401
        assert login(docente, "x").status_code == 200
        assert docente.get("/api/docente/estado").status_code == 200
        assert login(otro, "x").status_code == 403                      # además sigue siendo solo local


def test_modo_remoto_sin_clave_no_arranca(monkeypatch, capsys):
    with pytest.raises(ValueError, match="clave"):
        crear_app(cargar(PREGUNTAS), PREGUNTAS, 8000, url_publica=URL_PUBLICA)
    monkeypatch.delenv("PULSO_CLAVE", raising=False)
    assert main(["--preguntas", str(PREGUNTAS), "--url-publica", URL_PUBLICA]) == 1
    assert "necesita una clave" in capsys.readouterr().err


@pytest.mark.parametrize("url", ["preguntas.ejemplo.online", "ftp://x.online", "https://x.online/ruta", "https://x.online/?a=1", "https://"])
def test_url_publica_invalida(monkeypatch, capsys, url):
    monkeypatch.setenv("PULSO_CLAVE", "x")
    assert main(["--preguntas", str(PREGUNTAS), "--url-publica", url]) == 1
    assert "--url-publica" in capsys.readouterr().err


# ---------- páginas abiertas durante una actualización ----------
def test_el_estado_lleva_el_identificador_de_arranque(cliente, reloj):
    docente, alumno = cliente
    a = estado(alumno)["arranque"]
    assert a and docente.get("/api/docente/estado").json()["arranque"] == a
    inicia(docente, "redes")
    assert estado(alumno)["arranque"] == a                 # no cambia dentro de una misma ejecución
    docente.post("/api/docente/inicio")
    assert estado(alumno)["arranque"] == a
    otra = crear_app(cargar(PREGUNTAS), PREGUNTAS, 8000, reloj=reloj)
    with TestClient(otra, client=("192.168.1.50", 5000)) as otro_alumno:
        assert estado(otro_alumno)["arranque"] != a        # un servidor nuevo tiene otro



# ---------- identificación (alias) y ranking ----------
IDENT = """
temas:
  r:
    titulo: "Con ranking"
    modo_competicion: true
    preguntas:
      - texto: "¿Capa de red?"
        opciones: ["Enlace", "Red"]
        correcta: 2
      - tipo: multiopcion
        texto: "¿Privadas?"
        opciones: ["10.0.0.5", "8.8.8.8", "192.168.1.20", "172.16.4.9"]
        correcta: [1, 3, 4]
      - tipo: encuesta
        texto: "¿Te gusta?"
        opciones: ["Sí", "No"]
  s:
    titulo: "Sin ranking"
    preguntas:
      - texto: "¿Capa de red?"
        opciones: ["Enlace", "Red"]
        correcta: 2
"""
TOKENS = [chr(97 + i) * 16 for i in range(8)]   # a…h


@pytest.fixture
def ident(tmp_path, reloj):
    d = escribe(tmp_path, IDENT)
    app = crear_app(cargar(d), d, 8000, reloj=reloj)
    with TestClient(app, client=("127.0.0.1", 5000)) as docente, \
         TestClient(app, client=("192.168.1.50", 5000)) as alumno:
        yield docente, alumno


def alias(alumno, token, nombre):
    return alumno.post("/api/alias", json={"token": token, "alias": nombre})


def entran(alumno, n):
    for t, nombre in zip(TOKENS[:n], "Ana Beto Cris Dani Eva Fran Gus Hugo".split()):
        assert alias(alumno, t, nombre).status_code == 200


def ranking_docente(docente):
    v = docente.get("/api/docente/estado").json()
    return v.get("ranking") or v["resumen"].get("ranking")


def test_la_identificacion_es_una_opcion_del_tema(tmp_path):
    temas = cargar(PREGUNTAS)
    assert temas["redes"].identificacion and temas["multiopcion"].identificacion
    assert not temas["imagenes"].identificacion
    d = escribe(tmp_path, IDENT.replace("modo_competicion: true", "modo_competicion: 1"))
    with pytest.raises(ErrorBanco, match="modo_competicion"):
        cargar(d)


def test_sin_identificacion_no_hay_alias_ni_ranking(ident):
    docente, alumno = ident
    inicia(docente, "s")
    assert "identificacion" not in estado(alumno, token=TOKEN_A)
    assert alias(alumno, TOKEN_A, "Ana").status_code == 409
    assert responde(alumno, TOKEN_A, 1).status_code == 200
    docente.post("/api/docente/cerrar")
    assert "ranking" not in docente.get("/api/docente/estado").json()


def test_el_alumno_ve_que_debe_poner_alias_y_no_puede_responder_sin_el(ident):
    docente, alumno = ident
    docente.post("/api/docente/tema/r")
    v = estado(alumno, token=TOKEN_A)
    assert v["identificacion"] is True and "alias" not in v
    docente.post("/api/docente/empezar")
    sin_alias = alumno.post("/api/responder", json={"token": TOKEN_A, "respuesta": 1})
    assert sin_alias.status_code == 409
    assert alias(alumno, TOKEN_A, "Ana").status_code == 200
    assert estado(alumno, token=TOKEN_A)["alias"] == "Ana"
    assert responde(alumno, TOKEN_A, 1).status_code == 200


@pytest.mark.parametrize("nombre", ["", "   ", "x" * 21, "a\u0000b"])
def test_alias_no_valido(ident, nombre):
    docente, alumno = ident
    docente.post("/api/docente/tema/r")
    assert alias(alumno, TOKEN_A, nombre).status_code == 400


def test_no_se_admiten_alias_repetidos(ident):
    docente, alumno = ident
    docente.post("/api/docente/tema/r")
    assert alias(alumno, TOKEN_A, "Ana  López").status_code == 200
    r = alias(alumno, TOKEN_B, " ana lópez ")          # mayúsculas y espacios no distinguen
    assert r.status_code == 400 and "en uso" in r.json()["detail"]
    assert alias(alumno, TOKEN_B, "Beto").status_code == 200
    assert alias(alumno, TOKEN_A, "Ana  López").status_code == 200   # reenvío idéntico: sin error
    assert alias(alumno, TOKEN_A, "Otro").status_code == 409         # no se cambia de alias
    assert estado(alumno, token=TOKEN_A)["alias"] == "Ana López"


def test_el_alias_sobrevive_a_recargar_la_pagina(ident):
    docente, alumno = ident
    inicia(docente, "r")
    alias(alumno, TOKEN_A, "Ana")
    responde(alumno, TOKEN_A, 1)
    v = estado(alumno, token=TOKEN_A)        # misma persona, otra carga de página (mismo token)
    assert v["alias"] == "Ana" and v["mi_respuesta"] == 1


def test_puntos_100_y_bonus_por_orden_de_acierto(ident):
    docente, alumno = ident
    inicia(docente, "r")
    entran(alumno, 8)
    # A y B aciertan, C falla; D…H aciertan después: 10, 8, 5, 2, 1 y 0 de bonus
    orden = [(0, 1), (1, 1), (2, 0), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1)]
    for i, valor in orden:
        assert responde(alumno, TOKENS[i], valor).status_code == 200
    docente.post("/api/docente/cerrar")
    puntos = {f["alias"]: f["puntos"] for f in docente.app.state.sesion.ranking(0)}   # todos, no solo 5
    assert puntos == {"Ana": 110, "Beto": 108, "Cris": 0, "Dani": 105, "Eva": 102,
                      "Fran": 101, "Gus": 100, "Hugo": 100}


def test_el_ranking_entre_preguntas_son_los_5_primeros_ordenados_por_puntos(ident):
    docente, alumno = ident
    inicia(docente, "r")
    entran(alumno, 8)
    for i in range(8):
        responde(alumno, TOKENS[i], 1)
    docente.post("/api/docente/cerrar")
    r = docente.get("/api/docente/estado").json()["ranking"]
    assert [(f["alias"], f["puntos"]) for f in r] == [
        ("Ana", 110), ("Beto", 108), ("Cris", 105), ("Dani", 102), ("Eva", 101)]
    assert estado(alumno, token=TOKENS[0]).get("ranking") is None    # el alumno no lo recibe


def test_el_ranking_tiene_menos_de_5_si_hay_menos_participantes(ident):
    docente, alumno = ident
    inicia(docente, "r")
    entran(alumno, 2)
    responde(alumno, TOKENS[0], 0)           # falla
    docente.post("/api/docente/cerrar")
    r = docente.get("/api/docente/estado").json()["ranking"]
    assert [(f["alias"], f["puntos"]) for f in r] == [("Ana", 0), ("Beto", 0)]   # empate: alfabético


def test_cambiar_la_respuesta_cuenta_desde_que_se_reenvia(ident):
    docente, alumno = ident
    inicia(docente, "r")
    entran(alumno, 3)
    responde(alumno, TOKENS[0], 1)      # Ana acierta la primera…
    responde(alumno, TOKENS[1], 1)      # Beto
    responde(alumno, TOKENS[0], 1)      # …y la reenvía: pasa al final
    responde(alumno, TOKENS[2], 0)      # Cris falla y luego acierta
    responde(alumno, TOKENS[2], 1)
    docente.post("/api/docente/cerrar")
    puntos = {f["alias"]: f["puntos"] for f in ranking_docente(docente)}
    assert puntos == {"Beto": 110, "Ana": 108, "Cris": 105}


def test_acertar_y_luego_fallar_no_da_bonus(ident):
    docente, alumno = ident
    inicia(docente, "r")
    entran(alumno, 2)
    responde(alumno, TOKENS[0], 1)
    responde(alumno, TOKENS[0], 0)      # Ana cambia a una respuesta mala
    responde(alumno, TOKENS[1], 1)
    docente.post("/api/docente/cerrar")
    puntos = {f["alias"]: f["puntos"] for f in ranking_docente(docente)}
    assert puntos == {"Beto": 110, "Ana": 0}


def test_multiopcion_parcial_es_proporcional_y_sin_bonus(ident):
    docente, alumno = ident
    inicia(docente, "r")
    entran(alumno, 3)
    for t in TOKENS[:3]:
        responde(alumno, t, 1)
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")          # pregunta 2 (multiopción, correctas 1, 3 y 4)
    responde(alumno, TOKENS[0], [0, 1, 2, 3][:1] + [2])   # 2 de 3 correctas: parcial
    responde(alumno, TOKENS[1], [0, 2, 3])                # todas: acierto, primero
    responde(alumno, TOKENS[2], [0, 1, 2, 3])             # 3 correctas y 1 mala: (3-1)/3, parcial
    docente.post("/api/docente/cerrar")
    puntos = {f["alias"]: f["puntos"] for f in ranking_docente(docente)}
    # pregunta 1: 110, 108, 105; pregunta 2: Ana 67, Beto 100+10, Cris 67
    assert puntos == {"Ana": 110 + 67, "Beto": 108 + 110, "Cris": 105 + 67}


def test_las_encuestas_no_puntuan_ni_muestran_ranking(ident):
    docente, alumno = ident
    inicia(docente, "r")
    entran(alumno, 1)
    responde(alumno, TOKENS[0], 1)
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    responde(alumno, TOKENS[0], [0, 2, 3])
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")          # encuesta
    responde(alumno, TOKENS[0], 0)
    docente.post("/api/docente/cerrar")
    assert "ranking" not in docente.get("/api/docente/estado").json()
    docente.post("/api/docente/siguiente")          # resumen
    assert [(f["alias"], f["puntos"]) for f in ranking_docente(docente)] == [("Ana", 220)]


def test_el_ranking_acumula_hasta_la_pregunta_que_se_muestra(ident):
    docente, alumno = ident
    inicia(docente, "r")
    entran(alumno, 2)
    responde(alumno, TOKENS[0], 1)
    responde(alumno, TOKENS[1], 1)
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    responde(alumno, TOKENS[1], [0, 2, 3])
    docente.post("/api/docente/cerrar")
    assert [(f["alias"], f["puntos"]) for f in ranking_docente(docente)] == [("Beto", 218), ("Ana", 110)]
    docente.post("/api/docente/anterior")           # volver a la 1: solo cuenta hasta ella
    assert [(f["alias"], f["puntos"]) for f in ranking_docente(docente)] == [("Ana", 110), ("Beto", 108)]


def test_el_resumen_lleva_el_ranking_completo_solo_para_el_docente(ident):
    docente, alumno = ident
    inicia(docente, "r")
    entran(alumno, 7)
    for i in range(7):
        responde(alumno, TOKENS[i], 1)
    docente.post("/api/docente/cerrar")
    for _ in range(3):
        docente.post("/api/docente/siguiente")
        docente.post("/api/docente/cerrar")
    v = docente.get("/api/docente/estado").json()
    assert v["fase"] == "resumen" and len(v["resumen"]["ranking"]) == 7
    assert "ranking" not in estado(alumno, token=TOKENS[0])["resumen"]


def test_al_volver_a_los_temas_se_olvidan_los_alias(ident):
    docente, alumno = ident
    inicia(docente, "r")
    alias(alumno, TOKEN_A, "Ana")
    docente.post("/api/docente/inicio")
    docente.post("/api/docente/tema/r")
    assert "alias" not in estado(alumno, token=TOKEN_A)
    assert alias(alumno, TOKEN_B, "Ana").status_code == 200


def test_el_docente_ve_que_el_tema_tiene_ranking(ident):
    docente, _ = ident
    temas = {t["id"]: t["identificacion"] for t in docente.get("/api/docente/estado").json()["temas"]}
    assert temas == {"r": True, "s": False}


def test_alias_en_modo_remoto_exige_estar_admitido(tmp_path, reloj):
    d = escribe(tmp_path, IDENT)
    app = crear_app(cargar(d), d, 8000, reloj=reloj, url_publica=URL_PUBLICA, clave=CLAVE)
    with TestClient(app, client=("127.0.0.1", 5000)) as docente, \
         TestClient(app, client=("127.0.0.1", 5001)) as alumno:
        login(docente)
        docente.post("/api/docente/tema/r")
        assert alias(alumno, TOKEN_A, "Ana").status_code == 401
        entra(alumno, TOKEN_A, app.state.sesion.codigo)
        assert alias(alumno, TOKEN_A, "Ana").status_code == 200


def test_con_identificacion_solo_cuentan_como_conectados_los_que_tienen_alias(ident):
    docente, alumno = ident
    docente.post("/api/docente/tema/r")
    estado(alumno, token=TOKEN_A)
    estado(alumno, token=TOKEN_B)
    assert docente.get("/api/docente/estado").json()["conectados"] == 0   # aún sin alias
    alias(alumno, TOKEN_A, "Ana")
    assert docente.get("/api/docente/estado").json()["conectados"] == 1
    docente.post("/api/docente/empezar")
    responde(alumno, TOKEN_A, 1)        # B sigue sin alias: no retrasa el cierre por «todos han votado»
    assert estado(alumno, token=TOKEN_A)["fase"] == "cerrada"
    assert estado(alumno, token=TOKEN_A)["motivo_cierre"] == "todos"


def test_sin_identificacion_cuentan_todos_los_conectados(ident):
    docente, alumno = ident
    docente.post("/api/docente/tema/s")
    estado(alumno, token=TOKEN_A)
    estado(alumno, token=TOKEN_B)
    assert docente.get("/api/docente/estado").json()["conectados"] == 2


# ---------- preguntas rápidas ----------
RAPIDO = """
temas:
  rapido:
    titulo: "Rápido"
    rapido: true
    tiempo: 10
    preguntas:
      - {texto: "r1", opciones: [x, y], correcta: 1}
      - {texto: "n2", opciones: [x, y], correcta: 1, rapido: false, tiempo: 0}
      - {tipo: encuesta, texto: "e3", opciones: [x, y]}
      - {texto: "r4", opciones: [x, y], correcta: 2, tiempo: 5}
  normal:
    preguntas:
      - {texto: "n1", opciones: [x, y], correcta: 1}
      - {texto: "r2", opciones: [x, y], correcta: 1, rapido: true, tiempo: 8}
"""


@pytest.fixture
def rapido(tmp_path, reloj):
    d = escribe(tmp_path, RAPIDO)
    app = crear_app(cargar(d), d, 8000, reloj=reloj)
    with TestClient(app, client=("127.0.0.1", 5000)) as docente, \
         TestClient(app, client=("192.168.1.50", 5000)) as alumno:
        yield docente, alumno


def test_herencia_de_rapido(tmp_path):
    temas = cargar(escribe(tmp_path, RAPIDO))
    r, n = temas["rapido"], temas["normal"]
    assert [r.rapido_de(p) for p in r.preguntas] == [True, False, False, True]
    assert [n.rapido_de(p) for p in n.preguntas] == [False, True]
    assert [r.tiempo_de(p) for p in r.preguntas] == [10, 0, 10, 5]


@pytest.mark.parametrize("contenido, mensaje", [
    ("rapido: true\n    preguntas:\n      - {texto: a, opciones: [x, y], correcta: 1}", "rápida necesita tiempo"),
    ("rapido: true\n    tiempo: 10\n    preguntas:\n      - {texto: a, opciones: [x, y], correcta: 1, tiempo: 0}",
     "rápida necesita tiempo"),
    ("preguntas:\n      - {texto: a, opciones: [x, y], correcta: 1, rapido: true}", "rápida necesita tiempo"),
    ("tiempo: 10\n    preguntas:\n      - {tipo: encuesta, texto: a, opciones: [x, y], rapido: true}",
     "encuesta no puede ser rápida"),
    ("rapido: sí\n    preguntas:\n      - {texto: a, opciones: [x, y], correcta: 1}", "'rapido' debe ser true o false"),
    ("preguntas:\n      - {texto: a, opciones: [x, y], correcta: 1, rapido: quizá}", "rapido"),
])
def test_errores_de_rapido(tmp_path, contenido, mensaje):
    d = escribe(tmp_path, f"temas:\n  t:\n    {contenido}\n")
    with pytest.raises(ErrorBanco, match=mensaje):
        cargar(d)


def test_enunciado_sin_opciones_ni_tiempo_hasta_mostrar(rapido, reloj):
    docente, alumno = rapido
    inicia(docente, "rapido")
    e = estado(alumno, token=TOKEN_A)
    assert e["fase"] == "enunciado"
    assert e["pregunta"]["texto"] == "r1" and "opciones" not in e["pregunta"]
    assert "tiempo" not in e
    assert docente.get("/api/docente/estado").json()["duracion"] == 10
    assert responde(alumno, TOKEN_A, 0).status_code == 409
    reloj.t += 60                                   # el tiempo no corre en el enunciado
    assert estado(alumno)["fase"] == "enunciado"
    assert docente.post("/api/docente/mostrar").status_code == 200
    e = estado(alumno, token=TOKEN_A)
    assert e["fase"] == "abierta" and len(e["pregunta"]["opciones"]) == 2
    assert e["tiempo"]["restante"] == 10
    assert responde(alumno, TOKEN_A, 0).status_code == 200
    reloj.t += 10
    assert estado(alumno)["fase"] == "cerrada"


def test_mostrar_fuera_del_enunciado_es_un_error(rapido):
    docente, _ = rapido
    inicia(docente, "normal")
    assert estado(docente)["fase"] == "abierta"
    assert docente.post("/api/docente/mostrar").status_code == 409


def test_preguntas_normales_y_encuestas_en_tema_rapido(rapido):
    docente, alumno = rapido
    inicia(docente, "rapido")
    docente.post("/api/docente/mostrar")
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["fase"] == "abierta"      # rapido: false
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["fase"] == "abierta"      # encuesta: no hereda
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    e = estado(alumno)
    assert e["fase"] == "enunciado" and e["pregunta"]["texto"] == "r4"
    docente.post("/api/docente/mostrar")
    assert estado(alumno)["tiempo"]["restante"] == 5


def test_pregunta_rapida_en_tema_normal(rapido):
    docente, alumno = rapido
    inicia(docente, "normal")
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/siguiente")
    assert estado(alumno)["fase"] == "enunciado"


def test_reabrir_y_borrar_vuelven_al_enunciado(rapido):
    docente, alumno = rapido
    inicia(docente, "rapido")
    docente.post("/api/docente/mostrar")
    responde(alumno, TOKEN_A, 1)
    docente.post("/api/docente/cerrar")
    assert docente.post("/api/docente/abrir").status_code == 200
    e = estado(alumno, token=TOKEN_A)
    assert e["fase"] == "enunciado" and "mi_respuesta" not in e and e["n_respuestas"] == 1
    docente.post("/api/docente/mostrar")
    assert estado(alumno, token=TOKEN_A)["mi_respuesta"] == 1   # se conservan
    assert docente.post("/api/docente/reiniciar").status_code == 200
    e = estado(alumno)
    assert e["fase"] == "enunciado" and e["n_respuestas"] == 0
    assert docente.post("/api/docente/reiniciar").status_code == 200   # también desde el enunciado


def test_desde_el_enunciado_se_puede_cambiar_de_pregunta(rapido):
    docente, alumno = rapido
    inicia(docente, "rapido")
    assert docente.post("/api/docente/siguiente").status_code == 200
    assert estado(alumno)["pregunta"]["texto"] == "n2"
    docente.post("/api/docente/cerrar")
    docente.post("/api/docente/anterior")
    assert estado(alumno)["fase"] == "enunciado"   # no se había cerrado: vuelve a presentarse
