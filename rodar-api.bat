@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

REM ============================================================================
REM  api-microdata - sobe a API do jeito profissional
REM
REM  Antes de subir, checa se ja existe instancia viva na porta. Se existe e e a
REM  nossa, apenas informa (nao sobe duas). Se existe e de outro programa, avisa e
REM  NAO mata - a porta 58244 e do oraculum legado e precisa ficar intacta.
REM
REM  Uso:  rodar-api.bat          ^|  parar-api.bat
REM ============================================================================

set "RAIZ=%~dp0"
set "APP=%RAIZ%app"
set "PY=%APP%\.venv\Scripts\python.exe"
set "PORTA=58245"
REM 0.0.0.0 = aceita conexao de fora da maquina. Trocar para 127.0.0.1 deixa
REM restrito ao localhost, o que so serve se o dgbcomex rodar na mesma maquina.
set "HOST=0.0.0.0"
set "URL=http://127.0.0.1:%PORTA%"
set "URL_EXTERNA="
set "LOG=%APP%\logs\api.log"
set "PIDFILE=%APP%\logs\api.pid"

echo.
echo  ==========================================================
echo   api-microdata  ^|  porta %PORTA%
echo  ==========================================================
echo.

REM --- 0. pre-requisitos -----------------------------------------------------
if not exist "%PY%" (
    echo  [ERRO] venv nao encontrado em %PY%
    echo         Rode: python -m venv .venv  e instale as dependencias.
    goto :falha
)

if not exist "%APP%\logs" mkdir "%APP%\logs" >nul 2>&1

REM --- 1. ja existe instancia na porta? --------------------------------------
REM cmd /c com powershell interno: pega o PID que segura a porta escutando.
set "OCUPADA="
set "PID_ATUAL="
for /f "tokens=*" %%p in ('powershell -NoProfile -Command ^
    "$c = Get-NetTCPConnection -LocalPort %PORTA% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { $c.OwningProcess }"') do (
    set "PID_ATUAL=%%p"
)

if defined PID_ATUAL (
    set "OCUPADA=1"
)

if not defined OCUPADA goto :sobe

REM --- 2. a instancia viva e a nossa? ----------------------------------------
set "SERVICO="
for /f "tokens=*" %%s in ('powershell -NoProfile -Command ^
    "try { $r = Invoke-RestMethod -Uri '%URL%/health' -TimeoutSec 8; $r.servico } catch { '' }"') do (
    set "SERVICO=%%s"
)

if /i "!SERVICO!"=="api-microdata" (
    echo  [OK] A API ja esta rodando.
    echo        PID    : !PID_ATUAL!
    echo        Health : %URL%/health
    echo.
    echo        Nada a fazer. Use parar-api.bat para derrubar.
    echo.
    exit /b 0
)

REM --- 3. porta ocupada por outro programa: NAO encosta ----------------------
set "PROG="
for /f "tokens=*" %%n in ('powershell -NoProfile -Command ^
    "try { (Get-Process -Id !PID_ATUAL! -ErrorAction Stop).ProcessName } catch { '' }"') do (
    set "PROG=%%n"
)

echo  [ATENCAO] A porta %PORTA% esta ocupada por outro processo e a API nao
echo            respondeu em /health.
echo.
echo            PID  : !PID_ATUAL!  (^!PROG!)
echo.
echo            NAO foi encerrado. Se for lixo, libere a porta com:
echo              netstat -ano ^| findstr :%PORTA%
echo              taskkill /PID !PID_ATUAL! /F
echo.
echo            Se for o oraculum legado (porta 58244), a API deste projeto
echo            deveria subir em outra porta - ajuste PORTA e MICRODATA_API_URL.
echo.
goto :falha

REM --- 4. sobe ---------------------------------------------------------------
:sobe
echo  [..] Nenhuma instancia na porta %PORTA%. Subindo...
echo.

cd /d "%APP%"
set "PYTHONPATH=."

echo       comando : uvicorn src.api.main:app --host %HOST% --port %PORTA%
echo       log     : %LOG%
echo.

powershell -NoProfile -Command ^
    "$p = Start-Process -FilePath '%PY%' -ArgumentList '-m','uvicorn','src.api.main:app','--host','%HOST%','--port','%PORTA%' -WorkingDirectory '%APP%' -RedirectStandardOutput '%LOG%' -RedirectStandardError '%LOG%.err' -WindowStyle Hidden -PassThru; Set-Content -Path '%PIDFILE%' -Value $p.Id"

REM --- 5. espera a health responder ------------------------------------------
echo  [..] Aguardando a health responder (ate 40s)...
set "PRONTO="
for /f "tokens=*" %%s in ('powershell -NoProfile -Command ^
    "$ok='0'; for ($i=0; $i -lt 40; $i++) { Start-Sleep -Seconds 1; try { $r = Invoke-RestMethod -Uri '%URL%/health' -TimeoutSec 4; if ($r.servico -eq 'api-microdata') { $ok='1'; break } } catch {} }; $ok"') do (
    set "PRONTO=%%s"
)

if not "!PRONTO!"=="1" (
    echo.
    echo  [ERRO] A API nao respondeu /health em 40s.
    echo         Veja o log:  %LOG%
    echo                     %LOG%.err
    goto :falha
)

set "DETALHE="
for /f "tokens=*" %%s in ('powershell -NoProfile -Command ^
    "try { $r = Invoke-RestMethod -Uri '%URL%/health' -TimeoutSec 8; $r.warehouse_local.ok; $r.neon.ok } catch { '' }"') do (
    if not defined DETALHE (set "DETALHE=%%s") else (set "DETALHE2=%%s")
)

REM IP da maquina na rede local: e por ele que outra maquina alcanca a API.
set "IP_LOCAL="
for /f "tokens=*" %%i in ('powershell -NoProfile -Command ^
    "(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress"') do (
    set "IP_LOCAL=%%i"
)
if defined IP_LOCAL set "URL_EXTERNA=http://!IP_LOCAL!:%PORTA%"

echo.
echo  ==========================================================
echo   API no ar
echo  ==========================================================
echo     bind            : %HOST%:%PORTA%  (aceita conexao de fora)
echo     local           : %URL%
echo     pela rede       : %URL_EXTERNA%
echo     IP desta maquina: !IP_LOCAL!
echo     warehouse local : !DETALHE!
echo     neon            : !DETALHE2!
echo     log             : %LOG%
echo.
echo     dgbcomex        : MICRODATA_API_URL deve apontar para %URL%
echo     derrubar        : parar-api.bat
echo.
echo  ^^^ Esta janela pode ser fechada; a API segue rodando em segundo plano.
echo.
exit /b 0

:falha
echo.
exit /b 1