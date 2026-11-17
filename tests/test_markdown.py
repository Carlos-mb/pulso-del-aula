"""Ejecuta las pruebas del Markdown (JavaScript) con Node, si está instalado."""
import shutil
import subprocess
from pathlib import Path

import pytest

PRUEBA = Path(__file__).parent / "formato.test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_markdown_en_node():
    r = subprocess.run(["node", str(PRUEBA)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
