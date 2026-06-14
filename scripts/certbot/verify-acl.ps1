# Verify certbot config files are readable (non-admin = Dropbox-like token).
$ErrorActionPreference = 'Continue'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$EnvFile = Join-Path $RepoRoot '.env'
$CertsRoot = 'D:\music\Youtube\certs'
if (Test-Path -LiteralPath $EnvFile) {
    Get-Content -LiteralPath $EnvFile | ForEach-Object {
        $line = $_.Trim().TrimStart([char]0xFEFF)
        if ($line -match '^\s*CERTS_DIR\s*=\s*(.+)\s*$') { $CertsRoot = $Matches[1].Trim() }
        elseif ($line -match '^\s*ROOT_DIR\s*=\s*(.+)\s*$' -and $CertsRoot -eq 'D:\music\Youtube\certs') {
            $CertsRoot = Join-Path $Matches[1].Trim() 'certs'
        }
    }
}

$ConfigDir = Join-Path $CertsRoot 'certbot\config'
if (-not (Test-Path -LiteralPath $ConfigDir)) {
    Write-Error "Config dir not found: $ConfigDir"
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if ($isAdmin) {
    Write-Warning 'Running elevated - use a normal shell for Dropbox-like check.'
}

$script:ok = 0
$script:bad = 0

Get-ChildItem -LiteralPath $ConfigDir -Recurse -Force -File | ForEach-Object {
    $filePath = $_.FullName
    try {
        $fs = [IO.File]::OpenRead($filePath)
        $fs.Dispose()
        Write-Host "OK   $filePath"
        $script:ok++
    }
    catch {
        Write-Host "BAD  $filePath"
        $script:bad++
    }
}

Write-Host ""
Write-Host "Summary: ok=$script:ok bad=$script:bad"
exit $(if ($script:bad -eq 0) { 0 } else { 1 })
