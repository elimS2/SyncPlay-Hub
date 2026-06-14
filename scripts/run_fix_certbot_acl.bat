@echo off
setlocal
set "ROOT=%~dp0.."
set "PS1=%ROOT%\scripts\certbot\fix-acl-elevated.ps1"
set "VERIFY=%ROOT%\scripts\certbot\verify-acl.ps1"

if not exist "%PS1%" (
  echo ERROR: not found: %PS1%
  exit /b 1
)

net session >nul 2>&1
if errorlevel 1 (
  echo ERROR: Run from an elevated console.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
set "RC=%ERRORLEVEL%"
if %RC% neq 0 exit /b %RC%
echo Done. Log: %TEMP%\youtube-certbot-fix-acl.log
echo Verify: powershell -NoProfile -ExecutionPolicy Bypass -File "%VERIFY%"
exit /b 0
