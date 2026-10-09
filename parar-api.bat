@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

REM ============================================================================
REM  api-microdata - derruba a API
REM
REM  Derruba so o que for da api-microdata na porta configurada. Se a porta estiver
REM  ocupada por outro programa, avisa e NAO encosta - a 58244 e do oraculum legado.
REM
REM  Uso:  parar-api.bat
REM ============================================================================

set "RAIZ=%~dp0"
set "APP=%RAIZ%app"
set "PIDFILE=%APP%\logs\api.pid"
set "PORTA=58245"
set "URL=http://127.0.0.1:%PORTA%"

echo.
echo  ==========================================================
echo   api-microdata  ^|  encerrando porta %PORTA%
echo  ==========================================================
echo.

set "PID="
for /f "tokens=*" %%p in ('powershell -NoProfile -Command ^
    "$c = Get-NetTCPConnection -LocalPort %PORTA% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { $c.OwningProcess }"') do (
    set "PID=%%p"
)

if not defined PID (
    echo  [OK] Nenhuma instancia escutando na porta %PORTA%.
    if exist "%PIDFILE%" del /q "%PIDFILE%"
    echo.
    exit /b 0
)

REM Confirma que e a nossa antes de matar.
set "SERVICO="
for /f "tokens=*" %%s in ('powershell -NoProfile -Command ^
    "try { $r = Invoke-RestMethod -Uri '%URL%/health' -TimeoutSec 8; $r.servico } catch { '' }"') do (
    set "SERVICO=%%s"
)

if /i not "!SERVICO!"=="api-microdata" (
    echo  [ATENCAO] A porta %PORTA% ^(PID !PID!^) nao e a api-microdata.
    echo            Nada foi encerrado.
    echo.
    exit /b 1
)

echo  [..] Encerrando PID !PID!...
powershell -NoProfile -Command "Stop-Process -Id !PID! -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 600"

REM Confirma que a porta liberou.
set "AINDA="
for /f "tokens=*" %%p in ('powershell -NoProfile -Command ^
    "$c = Get-NetTCPConnection -LocalPort %PORTA% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { $c.OwningProcess }"') do (
    set "AINDA=%%p"
)

if defined AINDA (
    echo  [ERRO] A porta %PORTA% continua presa pelo PID !AINDA!
    echo         Encerrar manualmente:  taskkill /PID !AINDA! /F
    goto :falha
)

if exist "%PIDFILE%" del /q "%PIDFILE%"
echo.
echo  [OK] API encerrada. Porta %PORTA% livre.
echo.
exit /b 0

:falha
echo.
exit /b 1