#!/usr/bin/env bash
set -e

uso="Uso: $(basename "$0") [--venv <directorio-del-entorno-virtual>] [opciones de pulso...] [-- opciones de pulso...]"

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
herramienta="$raiz/.tools/uv"
archivo_env="$raiz/.env"

# El lanzador solo se queda con --venv y -h/--help; el resto se pasa a pulso tal cual.
# Tras «--» todo va a pulso (p. ej. «-- --help» muestra la ayuda de pulso).
venv=""
args_pulso=()
while [ $# -gt 0 ]; do
    case "$1" in
        --venv)
            if [ $# -lt 2 ] || [ -z "$2" ]; then
                echo "Error: falta el directorio después de --venv." >&2
                echo "$uso" >&2
                exit 1
            fi
            venv="$2"
            shift 2
            ;;
        -h|--help)
            echo "$uso"
            echo "Sin --venv, el directorio se lee de PULSO_VENV en $archivo_env (ver .env.example)."
            echo "Las demás opciones (--preguntas, --puerto, --host, --url-publica, --clave) se pasan a pulso."
            echo "Ayuda de pulso: $(basename "$0") -- --help"
            exit 0
            ;;
        --)
            shift
            args_pulso+=("$@")
            break
            ;;
        *)
            args_pulso+=("$1")
            shift
            ;;
    esac
done

# Lee PULSO_VENV de .env sin ejecutarlo: solo líneas «PULSO_VENV=valor»; gana la última.
leer_env() {
    local linea valor=""
    while IFS= read -r linea || [ -n "$linea" ]; do
        linea="${linea%$'\r'}"
        case "$linea" in
            PULSO_VENV=*) valor="${linea#PULSO_VENV=}" ;;
        esac
    done < "$archivo_env"
    case "$valor" in
        \"*\") valor="${valor#\"}"; valor="${valor%\"}" ;;
        \'*\') valor="${valor#\'}"; valor="${valor%\'}" ;;
    esac
    printf '%s' "$valor"
}

origen=""
if [ -n "$venv" ]; then
    base="$PWD"   # ruta relativa en --venv: desde donde se lanza
else
    if [ -f "$archivo_env" ]; then
        venv="$(leer_env)"
    fi
    if [ -z "$venv" ]; then
        echo "$uso" >&2
        echo "Falta el directorio del entorno virtual: indícalo con --venv o con PULSO_VENV en" >&2
        echo "$archivo_env (copia .env.example como .env y ajústalo)." >&2
        exit 1
    fi
    origen=" (indicado en .env)"
    base="$raiz"  # ruta relativa en .env: desde la carpeta del proyecto
    case "$venv" in
        "~") venv="$HOME" ;;
        "~/"*) venv="$HOME/${venv#\~/}" ;;
    esac
fi
# uv tomaría una ruta relativa desde la carpeta del proyecto; aquí se completa antes.
case "$venv" in
    /*) ;;
    *) venv="$base/$venv" ;;
esac

if [ -f "$venv/pyvenv.cfg" ]; then
    :   # entorno virtual existente: se reutiliza
elif [ -e "$venv" ]; then
    echo "Error: «$venv»$origen existe pero no es un entorno virtual; no se toca." >&2
    exit 1
else
    printf '¿Crear el entorno virtual en «%s»%s? [s/N] ' "$venv" "$origen" >&2
    respuesta=""
    read -r respuesta || true
    case "$respuesta" in
        s|S) ;;
        *)
            echo "No se ha creado nada." >&2
            exit 1
            ;;
    esac
fi

mkdir -p "$raiz/.tools"

if [ ! -x "$herramienta" ]; then
    echo "Preparando Pulso del aula por primera vez..."
    echo "Descargando uv dentro del proyecto..."

    if command -v curl >/dev/null 2>&1; then
        UV_INSTALL_DIR="$raiz/.tools" \
        UV_NO_MODIFY_PATH=1 \
            sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
    elif command -v wget >/dev/null 2>&1; then
        UV_INSTALL_DIR="$raiz/.tools" \
        UV_NO_MODIFY_PATH=1 \
            sh -c 'wget -qO- https://astral.sh/uv/install.sh | sh'
    else
        echo "Error: hace falta curl o wget para descargar uv."
        exit 1
    fi
fi

if [ ! -x "$herramienta" ]; then
    echo "Error: no se pudo preparar uv."
    exit 1
fi

export UV_PROJECT_ENVIRONMENT="$venv"
export UV_CACHE_DIR="$raiz/.uv-cache"
export UV_PYTHON_INSTALL_DIR="$raiz/.python"
export UV_NO_MODIFY_PATH=1

# Prepara el entorno la primera vez y reutiliza lo existente después.
"$herramienta" sync --project "$raiz"

echo "Ejecutando Pulso del aula..."
exec "$herramienta" run --project "$raiz" pulso "${args_pulso[@]}"
