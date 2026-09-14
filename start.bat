@echo off
REM ============================================================
REM  start.bat - TERMO LIVE
REM  1) verifica o Python
REM  2) cria o ambiente virtual se não existir
REM  3) instala as dependências
REM  4) inicia o backend
REM  5) abre o navegador em /live
REM  NOTA: não inicia o OBS automaticamente.
REM ============================================================
title TERMO LIVE
cd /d "%~dp0"

REM 1) Verificar Python
where python >nul 2>nul
if errorlevel 1 (
    echo [ERR] Python não encontrado. Instale o Python 3.11+ e tente novamente.
    pause
    exit /b 1
)

REM 2) Crear .venv si no existe
if not exist ".venv" (
    echo Criando ambiente virtual...
    python -m venv .venv
)

REM 3) Instalar dependencias
call .venv\Scripts\activate
echo Instalando dependências...
pip install -r requirements.txt

REM 4) Iniciar backend
echo Iniciando o TERMO LIVE...
start "TERMO LIVE backend" cmd /k "call .venv\Scripts\activate && python backend\main.py"

REM 5) Abrir navegador em /live
timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:8000/live
exit