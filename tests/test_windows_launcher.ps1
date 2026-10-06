$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$previousPath = $env:PATH
$env:PATH = $PSHOME + [IO.Path]::PathSeparator + $env:PATH
Push-Location $repo
try {
    & python -m unittest discover -s tests -p 'test_device.py' -k WindowsLauncherTests -v
    if ($LASTEXITCODE -ne 0) { throw 'Native Windows argument transport failed' }
    & powershell.exe -NoProfile -File (Join-Path $repo 'device.ps1') doctor --json
    if ($LASTEXITCODE -ne 0) { throw 'Native Windows doctor failed' }
    & powershell.exe -NoProfile -File (Join-Path $repo 'device.ps1') demo --color never
    if ($LASTEXITCODE -ne 0) { throw 'Native Windows demo failed' }
    & (Join-Path $repo 'device.ps1') demo --view dashboard --color never
    if ($LASTEXITCODE -ne 0) { throw 'Native Windows dashboard demo failed' }
    Write-Host 'PASS: native launcher, literal argv, JSON and terminal layout (no SSH/WSL)' -ForegroundColor Green
} finally { $env:PATH = $previousPath; Pop-Location }
