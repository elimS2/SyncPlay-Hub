#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Reset restrictive per-file ACLs on certbot config (run elevated).

  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\certbot\fix-acl-elevated.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\certbot\verify-acl.ps1
#>
param(
    [switch]$OnlyMissingElAccess
)

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
$LogFileLocal = Join-Path $env:TEMP 'youtube-certbot-fix-acl.log'
$LogFileProject = Join-Path $CertsRoot 'certbot\fix-acl.log'
$UserPrincipal = 'DESKTOP-4BOHCLK\eL'

try {
    $UserSid = (New-Object System.Security.Principal.NTAccount($UserPrincipal)).Translate(
        [System.Security.Principal.SecurityIdentifier]
    ).Value
}
catch {
    $UserSid = $null
}

$script:LogWriter = $null

function Initialize-Log {
    $script:LogWriter = [System.IO.StreamWriter]::new($LogFileLocal, $false, [System.Text.UTF8Encoding]::new($false))
    $script:LogWriter.AutoFlush = $true
}

function Close-Log {
    if ($script:LogWriter) {
        $script:LogWriter.Close()
        $script:LogWriter = $null
    }
    try {
        $logDir = Split-Path -Parent $LogFileProject
        if (-not (Test-Path -LiteralPath $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $LogFileLocal -Destination $LogFileProject -Force -ErrorAction Stop
    }
    catch {
        Write-Host "NOTE: could not copy log to $LogFileProject. Full log: $LogFileLocal"
    }
}

function Write-Log {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    if ($script:LogWriter) { $script:LogWriter.WriteLine($line) }
    Write-Host $line
}

function Test-ElHasFileAccess {
    param([string]$Path)
    $out = (& icacls.exe $Path 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { return $false }
    if ($out -match '(?i)DESKTOP-4BOHCLK\\eL:\([^)]*\)') { return $true }
    if ($UserSid -and $out -match ('(?i)' + [regex]::Escape($UserSid) + ':\([^)]*\)')) { return $true }
    return $false
}

function Reset-FileAcl {
    param([string]$Path)
    $takeown = & takeown.exe /F $Path 2>&1
    if ($LASTEXITCODE -ne 0) {
        $takeownA = & takeown.exe /F $Path /A 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "WARN takeown failed: $Path :: $takeown :: $takeownA"
        }
    }
    $steps = @(
        @{ Args = @($Path, '/reset'); Name = 'reset' },
        @{ Args = @($Path, '/inheritance:e'); Name = 'inheritance:e' },
        @{
            Args = @($Path, '/grant:r', "${UserPrincipal}:(F)", 'NT AUTHORITY\SYSTEM:(F)', 'BUILTIN\Administrators:(F)')
            Name = 'grant'
        }
    )
    foreach ($step in $steps) {
        $out = & icacls.exe @($step.Args) 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "WARN icacls /$($step.Name) failed ($LASTEXITCODE): $Path :: $out"
            return $false
        }
    }
    return $true
}

if (-not (Test-Path -LiteralPath $ConfigDir)) {
    Write-Error "Config dir not found: $ConfigDir"
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    Write-Error 'Run from an elevated PowerShell.'
    exit 1
}

Initialize-Log
try {
    Write-Log "=== fix-acl run $(Get-Date -Format o) ==="
    Write-Log "Config: $ConfigDir"
    Write-Log "User:   $UserPrincipal"

    $allFiles = @(Get-ChildItem -LiteralPath $ConfigDir -Recurse -Force -File)
    Write-Log "Files in config: $($allFiles.Count)"

    $targets = [System.Collections.Generic.List[string]]::new()
    foreach ($file in $allFiles) {
        $path = $file.FullName
        if ($OnlyMissingElAccess) {
            if (-not (Test-ElHasFileAccess -Path $path)) { $targets.Add($path) }
        }
        else {
            $targets.Add($path)
        }
    }

    Write-Log "Files to fix: $($targets.Count)"
    if ($targets.Count -eq 0) { exit 0 }

    $fixed = 0
    $failed = 0
    foreach ($path in $targets) {
        Write-Log "FIX  $path"
        if ((Reset-FileAcl -Path $path) -and (Test-ElHasFileAccess -Path $path)) {
            Write-Log "OK   $path"
            $fixed++
        }
        else {
            Write-Log "FAIL $path"
            $failed++
        }
    }

    Write-Log "Summary: ok=$fixed failed=$failed"
    exit $(if ($failed -gt 0) { 1 } else { 0 })
}
finally {
    Close-Log
}
