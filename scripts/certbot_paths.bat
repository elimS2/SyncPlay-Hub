@echo off
rem Shared certbot paths — reads CERTS_DIR from project .env, else D:\music\Youtube\certs
setlocal EnableDelayedExpansion
set "REPO_ROOT=%~dp0.."
set "CERTS_ROOT="
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "CERTS_DIR=" "%REPO_ROOT%\.env" 2^>nul`) do set "CERTS_ROOT=%%B"
if not defined CERTS_ROOT (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "ROOT_DIR=" "%REPO_ROOT%\.env" 2^>nul`) do set "CERTS_ROOT=%%B\certs"
)
if not defined CERTS_ROOT set "CERTS_ROOT=D:\music\Youtube\certs"
set "CFG=%CERTS_ROOT%\certbot\config"
set "WORK=%CERTS_ROOT%\certbot\work"
set "LOGS=%CERTS_ROOT%\certbot\logs"
set "OUT=%CERTS_ROOT%\certbot\last-run.log"
set "ACME_PENDING=%CERTS_ROOT%\acme-dns-pending.txt"
endlocal & (
  set "CERTS_ROOT=%CERTS_ROOT%"
  set "CFG=%CFG%"
  set "WORK=%WORK%"
  set "LOGS=%LOGS%"
  set "OUT=%OUT%"
  set "ACME_PENDING=%ACME_PENDING%"
  set "REPO_ROOT=%REPO_ROOT%"
)
