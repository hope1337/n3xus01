$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    & python -m unittest discover -s tests -p 'test_device.py' -k WindowsLauncherTests -v
    if ($LASTEXITCODE -ne 0) { throw 'Native Windows argument transport failed' }
    & powershell.exe -NoProfile -File (Join-Path $repo 'device.ps1') doctor --json
    if ($LASTEXITCODE -ne 0) { throw 'Native Windows doctor failed' }
    & powershell.exe -NoProfile -File (Join-Path $repo 'device.ps1') demo --color never
    if ($LASTEXITCODE -ne 0) { throw 'Native Windows demo failed' }
    Write-Host 'PASS: native launcher, literal argv, JSON and terminal layout (no SSH/WSL)' -ForegroundColor Green
} finally { Pop-Location }
