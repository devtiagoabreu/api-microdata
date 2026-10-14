@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

REM ============================================================================
REM  api-microdata - mostra o estado, derruba e sobe de novo
REM
REM  Uso:  reiniciar-api.bat           reinicia
REM        reiniciar-api.bat status    so mostra o estado e sai
REM
REM  Este e o comando do servidor depois de um `git pull`: o uvicorn nao recarrega
REM  sozinho, e sem derrubar a instancia ela continua servindo o codigo antigo. Foi
REM  exatamente assim que /contas-pagas-detalhe respondeu 404 na tela do BI mesmo
REM  com o arquivo do router no disco.
REM
REM  A confecao do final compara as rotas de detalhe com o /openapi.json da
REM  instancia que acabou de subir: e a prova de que o codigo novo esta no ar, e
REM  nao so no disco.
REM
REM  Se a porta 58245 estiver ocupada por outro programa, nada e encerrado: a
REM  porta 58244 e do oraculum legado e nunca pode ser tocada.
REM ============================================================================

set "RAIZ=%~dp0"
set "PORTA=58245"
set "URL=http://127.0.0.1:%PORTA%"

echo.
echo  ==========================================================
echo   api-microdata  ^|  porta %PORTA%
echo  ==========================================================
echo.
echo  [estado]
call :estado
echo.

if /i "%~1"=="status" (
    exit /b 0
)

echo  [1/3] Encerrando a instancia...
call "%RAIZ%parar-api.bat"
if errorlevel 1 goto :falha

echo  [2/3] Subindo de novo...
call "%RAIZ%rodar-api.bat"
if errorlevel 1 goto :falha

echo  [3/3] Conferindo o que subiu...
echo    rotas de detalhe na instancia:
call :rotas
echo.
call :estado
echo.
echo  [OK] API reiniciada.
echo.

if /i "%~1"=="rotas" exit /b 0
exit /b 0

REM ---------------------------------------------------------------------------
REM  :estado - quem segura a porta e se ela responde o que deve
REM ---------------------------------------------------------------------------
:estado
set "SERVICO="
set "PID="
for /f "tokens=*" %%s in ('powershell -NoProfile -Command ^
    "try { $r = Invoke-RestMethod -Uri '%URL%/health' -TimeoutSec 8; $r.servico } catch { '' }"') do (
    set "SERVICO=%%s"
)
for /f "tokens=*" %%p in ('powershell -NoProfile -Command ^
    "$c = Get-NetTCPConnection -LocalPort %PORTA% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { $c.OwningProcess }"') do (
    set "PID=%%p"
)
if defined PID (
    if /i "!SERVICO!"=="api-microdata" (
        echo    API no ar ^(PID !PID!^)
    ) else (
        echo    Porta %PORTA% presa pelo PID !PID!, mas NAO e a api-microdata.
    )
) else (
    echo    API fora do ar ^(nada escutando na %PORTA%^)
)
goto :eof

REM ---------------------------------------------------------------------------
REM  :rotas - o codigo novo esta no ar?
REM ---------------------------------------------------------------------------
:rotas
for /f "usebackq delims=" %%r in (`powershell -NoProfile -Command ^
    "try { $o = Invoke-RestMethod -Uri '%URL%/openapi.json' -TimeoutSec 15 } catch { $o = $null }; if (-not $o) { '  [ERRO] nao deu para ler o /openapi.json' } else { foreach ($r in @('/contas-pagas-detalhe','/custos-administrativos-detalhe','/custos-administrativos-anual-detalhe','/faturamento-detalhe')) { if ($o.paths.PSObject.Properties.Name -contains $r) { '  [OK]      ' + $r } else { '  [AUSENTE] ' + $r } } }"`) do (
    echo %%r
)
goto :eof

:falha
echo.
echo  [ERRO] A API nao foi reiniciada. Veja o log em app\logs\api.log
echo.
exit /b 1
