@echo off
setlocal
set "ROOT=%~dp0.."
set "CFG=%ROOT%\certs\certbot\config"
set "WORK=%ROOT%\certs\certbot\work"
set "LOGS=%ROOT%\certs\certbot\logs"
set "OUT=%ROOT%\certs\certbot\last-run.log"
mkdir "%CFG%" 2>nul
mkdir "%WORK%" 2>nul
mkdir "%LOGS%" 2>nul
certbot certonly --manual --preferred-challenges dns -d ph.elims.pp.ua ^
  --agree-tos --register-unsafely-without-email --non-interactive ^
  --manual-auth-hook "%ROOT%\scripts\certbot_dns_auth_hook.bat" ^
  --manual-cleanup-hook "%ROOT%\scripts\certbot_dns_cleanup_hook.bat" ^
  --config-dir "%CFG%" --work-dir "%WORK%" --logs-dir "%LOGS%" ^
  > "%OUT%" 2>&1
echo EXIT_CODE=%ERRORLEVEL%>> "%OUT%"
