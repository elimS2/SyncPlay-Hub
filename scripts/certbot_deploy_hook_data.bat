@echo off
rem Certbot deploy hook (lives in certbot\config\renewal-hooks\deploy\ on data drive).
if "%CERTBOT_DOMAIN%"=="" exit /b 0
for %%I in ("%~dp0..\..\..\..") do set "CERTS_ROOT=%%~fI"
set "DEST=%CERTS_ROOT%\domains\%CERTBOT_DOMAIN%"
if not exist "%DEST%" mkdir "%DEST%"
if exist "%CERTBOT_FULLCHAIN_PATH%" copy /Y "%CERTBOT_FULLCHAIN_PATH%" "%DEST%\cert.pem" >nul
if exist "%CERTBOT_PRIVKEY_PATH%" copy /Y "%CERTBOT_PRIVKEY_PATH%" "%DEST%\key.pem" >nul
exit /b 0
