@echo off
rem Certbot deploy hook: copy renewed PEMs to certs/domains/<domain>/ for the app.
if "%CERTBOT_DOMAIN%"=="" exit /b 0
call "%~dp0certbot_paths.bat"
set "DEST=%CERTS_ROOT%\domains\%CERTBOT_DOMAIN%"
if not exist "%DEST%" mkdir "%DEST%"
if exist "%CERTBOT_FULLCHAIN_PATH%" copy /Y "%CERTBOT_FULLCHAIN_PATH%" "%DEST%\cert.pem" >nul
if exist "%CERTBOT_PRIVKEY_PATH%" copy /Y "%CERTBOT_PRIVKEY_PATH%" "%DEST%\key.pem" >nul
exit /b 0
