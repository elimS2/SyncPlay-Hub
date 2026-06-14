@echo off
setlocal
call "%~dp0certbot_paths.bat"
set "ROOT=%REPO_ROOT%"
mkdir "%CFG%" 2>nul
mkdir "%WORK%" 2>nul
mkdir "%LOGS%" 2>nul
certbot certonly --manual --preferred-challenges dns -d ph.elims.pp.ua ^
  --agree-tos --register-unsafely-without-email --non-interactive ^
  --manual-auth-hook "%ROOT%\scripts\certbot_dns_auth_hook.bat" ^
  --manual-cleanup-hook "%ROOT%\scripts\certbot_dns_cleanup_hook.bat" ^
  --deploy-hook "%ROOT%\scripts\certbot_deploy_to_domains.bat" ^
  --config-dir "%CFG%" --work-dir "%WORK%" --logs-dir "%LOGS%" ^
  > "%OUT%" 2>&1
echo EXIT_CODE=%ERRORLEVEL%>> "%OUT%"
call "%ROOT%\scripts\copy_domain_certs_from_live.bat" ph.elims.pp.ua
