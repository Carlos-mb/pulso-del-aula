@echo off
setlocal

set "RAIZ=%~dp0"
set "RAIZ=%RAIZ:~0,-1%"
set "HERRAMIENTA=%RAIZ%\tools\uv.exe"
set "ARCHIVO_ENV=%RAIZ%\.env"
set "USO=Uso: %~nx0 [--venv DIRECTORIO-DEL-ENTORNO-VIRTUAL] [OPCIONES-DE-PULSO...] [-- OPCIONES-DE-PULSO...]"

rem El lanzador solo se queda con --venv y -h/--help; el resto se pasa a pulso tal cual.
rem Tras "--" todo va a pulso (p. ej. "-- --help" muestra la ayuda de pulso).
rem Se recorre con shift (no con for), para poder reenviar los argumentos con sus comillas.
set "VENV="
set "ARGS_PULSO="
set "AYUDA="
:argumentos
if "%~1"=="" goto fin_argumentos
if /i "%~1"=="--venv" (
    if "%~2"=="" (
        echo Error: falta el directorio despues de --venv. 1>&2
        echo %USO% 1>&2
        exit /b 1
    )
    set "VENV=%~2"
    shift
    shift
    goto argumentos
)
if /i "%~1"=="--help" set "AYUDA=1"
if /i "%~1"=="-h" set "AYUDA=1"
if defined AYUDA goto fin_argumentos
if "%~1"=="--" goto resto_a_pulso
set ARGS_PULSO=%ARGS_PULSO% %1
shift
goto argumentos
:resto_a_pulso
shift
if "%~1"=="" goto fin_argumentos
set ARGS_PULSO=%ARGS_PULSO% %1
goto resto_a_pulso
:fin_argumentos

if defined AYUDA (
    echo %USO%
    echo Sin --venv, el directorio se lee de PULSO_VENV en el archivo .env del proyecto ^(ver .env.example^).
    echo Las demas opciones ^(--preguntas, --puerto, --host, --url-publica, --clave^) se pasan a pulso.
    echo Ayuda de pulso: %~nx0 -- --help
    exit /b 0
)

rem Sin --venv, se lee PULSO_VENV de .env (solo líneas CLAVE=valor; # empieza un comentario).
set "ORIGEN="
if not defined VENV if exist "%ARCHIVO_ENV%" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ARCHIVO_ENV%") do (
        if /i "%%A"=="PULSO_VENV" set "VENV=%%~B"
    )
    set "ORIGEN= (indicado en .env)"
)
if not defined VENV (
    echo %USO% 1>&2
    echo Falta el directorio del entorno virtual: indicalo con --venv o con PULSO_VENV en 1>&2
    echo "%ARCHIVO_ENV%" ^(copia .env.example como .env y ajustalo^). 1>&2
    exit /b 1
)

rem En .env se admite ~ al principio (carpeta personal) y variables como %%USERPROFILE%%.
if defined ORIGEN if "%VENV:~0,1%"=="~" set "VENV=%USERPROFILE%%VENV:~1%"
if defined ORIGEN call set "VENV=%VENV%"

rem uv tomaría una ruta relativa desde la carpeta del proyecto; aquí se completa antes:
rem la de --venv, desde donde se lanza; la de .env, desde la carpeta del proyecto.
if defined ORIGEN pushd "%RAIZ%"
for %%I in ("%VENV%") do set "VENV=%%~fI"
if defined ORIGEN popd

rem Sin bloque: el texto de ORIGEN lleva paréntesis y cerraría el bloque antes de tiempo.
set "NO_ES_VENV="
if not exist "%VENV%\pyvenv.cfg" if exist "%VENV%" set "NO_ES_VENV=1"
if defined NO_ES_VENV echo Error: "%VENV%"%ORIGEN% existe pero no es un entorno virtual; no se toca. 1>&2
if defined NO_ES_VENV exit /b 1

set "CREAR="
set "RESPUESTA="
if not exist "%VENV%\pyvenv.cfg" set "CREAR=1"
if defined CREAR set /p "RESPUESTA=Crear el entorno virtual en %VENV%%ORIGEN%? [s/N] "
if defined CREAR if /i not "%RESPUESTA%"=="s" (
    echo No se ha creado nada. 1>&2
    exit /b 1
)

if not exist "%RAIZ%\tools" mkdir "%RAIZ%\tools"

if not exist "%HERRAMIENTA%" (
    echo Preparando Pulso del aula por primera vez...
    echo Descargando uv dentro del proyecto...

    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$env:UV_INSTALL_DIR='%RAIZ%\tools'; $env:UV_NO_MODIFY_PATH='1'; irm https://astral.sh/uv/install.ps1 | iex"

    if errorlevel 1 (
        echo Error: no se pudo descargar uv.
        exit /b 1
    )
)

if not exist "%HERRAMIENTA%" (
    echo Error: no se pudo preparar uv.
    exit /b 1
)

set "UV_PROJECT_ENVIRONMENT=%VENV%"
set "UV_CACHE_DIR=%RAIZ%\uv-cache"
set "UV_PYTHON_INSTALL_DIR=%RAIZ%\python"
set "UV_NO_MODIFY_PATH=1"

echo Preparando el entorno si hace falta...
"%HERRAMIENTA%" sync --project "%RAIZ%"
if errorlevel 1 exit /b 1

echo Ejecutando Pulso del aula...
"%HERRAMIENTA%" run --project "%RAIZ%" pulso %ARGS_PULSO%
exit /b %errorlevel%
