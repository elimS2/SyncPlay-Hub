@echo off
call "%~dp0certbot_paths.bat"
if exist "%ACME_PENDING%" del "%ACME_PENDING%"
