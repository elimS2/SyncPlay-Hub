@echo off
set "OUT=%~dp0..\certs\acme-dns-pending.txt"
> "%OUT%" echo DOMAIN=%CERTBOT_DOMAIN%
>> "%OUT%" echo TXT_NAME=_acme-challenge.%CERTBOT_DOMAIN%
>> "%OUT%" echo TXT_VALUE=%CERTBOT_VALIDATION%
>> "%OUT%" echo TXT_SUBDOMAIN=_acme-challenge.ph
rem Wait for DNS TXT to be added in adm.tools and propagate
timeout /t 120 /nobreak >nul
