$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "api.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Listening = netstat -ano | Select-String "0.0.0.0:5000|127.0.0.1:5000"
if ($Listening) {
    "API already listening on port 5000 at $(Get-Date -Format s)" | Out-File -Append -Encoding UTF8 $LogFile
    exit 0
}

Set-Location $ProjectRoot
& $Python -m flask --app src.api.app run --host 0.0.0.0 --port 5000 *>> $LogFile
