#Requires -Version 5.1
<#
.SYNOPSIS
    Windows entry point for the useful_appcoll daily docket pipeline.
    Equivalent to run_docket.sh on macOS.

.DESCRIPTION
    Loads credentials from .env, activates the virtual environment, and runs
    the AppColl downloader and docket generator. Output is appended to
    logs/docket.log. Intended to be called by Windows Task Scheduler.
#>

$ErrorActionPreference = "Stop"

$ProjDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjDir

# Load credentials from .env
$EnvFile = Join-Path $ProjDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#\s][^=]*)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
        }
    }
}

# Activate virtual environment
$ActivateScript = Join-Path $ProjDir ".venv\Scripts\Activate.ps1"
. $ActivateScript

# Ensure project root is on the Python path so 'import config' works
$env:PYTHONPATH = $ProjDir

# Append all output to logs/docket.log
$LogDir = Join-Path $ProjDir "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$LogFile = Join-Path $LogDir "docket.log"
Start-Transcript -Path $LogFile -Append | Out-Null

Write-Output "--- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ---"

Write-Output "Downloading AppColl CSV..."
python scripts\appcoll_downloader.py
if ($LASTEXITCODE -ne 0) { Stop-Transcript; exit $LASTEXITCODE }

Write-Output "Generating docket report..."
python scripts\main.py
if ($LASTEXITCODE -ne 0) { Stop-Transcript; exit $LASTEXITCODE }

Write-Output "Done."
Stop-Transcript
