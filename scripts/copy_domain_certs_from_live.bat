@echo off
rem Copy fullchain/privkey from certbot live\ to domains\ for the Flask app.
setlocal
if "%~1"=="" (
  echo Usage: %~nx0 domain.name
  exit /b 1
)
set "DOMAIN=%~1"
call "%~dp0certbot_paths.bat"
set "SRC=%CFG%\live\%DOMAIN%"
set "DEST=%CERTS_ROOT%\domains\%DOMAIN%"
if not exist "%SRC%\fullchain.pem" (
  echo ERROR: not found: %SRC%\fullchain.pem
  exit /b 1
)
if not exist "%SRC%\privkey.pem" (
  echo ERROR: not found: %SRC%\privkey.pem
  exit /b 1
)
if not exist "%DEST%" mkdir "%DEST%"
copy /Y "%SRC%\fullchain.pem" "%DEST%\cert.pem"
copy /Y "%SRC%\privkey.pem" "%DEST%\key.pem"
echo Copied certs to %DEST%
exit /b 0
