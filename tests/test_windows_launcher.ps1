$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repository 'cluster.ps1'
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$tokens, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -ne 0) { throw ($parseErrors | Out-String) }
# Child PowerShell process with fake WSL. No installation, SSH or device access.
$taskTemp = Join-Path ([IO.Path]::GetTempPath()) ('personal-compute-launcher-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskTemp | Out-Null
$resolvedTaskTemp = [IO.Path]::GetFullPath($taskTemp)
$resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
if (-not $resolvedTaskTemp.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected temporary directory' }
try {
    $mockFile = Join-Path $taskTemp 'mock.ps1'
    $logFile = Join-Path $taskTemp 'arguments.json'
    $fixture = @'
param($Launcher, $Log)
function wsl.exe {
    if ($args[0] -eq '--list') { $global:LASTEXITCODE = 0; return 'Ubuntu-24.04' }
    if ($args -contains 'wslpath') { $global:LASTEXITCODE = 0; return '/mnt/c/path with spaces' }
    ConvertTo-Json -InputObject @($args) -Compress | Set-Content -LiteralPath $Log
    $global:LASTEXITCODE = 0
}
function Start-Process { throw 'Unexpected installation attempt in a prepared host test' }
& $Launcher run home --image 'sample:1' -- python -c 'print("literal $HOME; hello")'
'@
    [IO.File]::WriteAllText($mockFile, $fixture, [Text.UTF8Encoding]::new($false))
    & (Get-Process -Id $PID).Path -NoProfile -File $mockFile -Launcher $launcher -Log $logFile
    if ($LASTEXITCODE -ne 0) { throw 'Windows launcher routing test failed' }
    $forwarded = Get-Content -Raw -LiteralPath $logFile | ConvertFrom-Json
    if ($forwarded -notcontains 'CLUSTER_WINDOWS_SSH=/mnt/c/path with spaces') { throw 'SSH bridge path was not preserved' }
    if ($forwarded -notcontains '/mnt/c/path with spaces/cluster') { throw 'Repository path was split' }
    $encoded = @($forwarded | Where-Object { $_.StartsWith('CLUSTER_ARGUMENTS_BASE64=') })[0].Substring('CLUSTER_ARGUMENTS_BASE64='.Length)
    $decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded)) | ConvertFrom-Json
    if ($decoded -notcontains 'print("literal $HOME; hello")') { throw 'Command content was interpolated/split' }
    if ($decoded -notcontains '--') { throw 'Container argument delimiter was lost' }
    Write-Host 'PASS: PowerShell syntax and mocked WSL/SSH argument routing. No real WSL/device was used.'
} finally {
    # Fixed, resolved task-specific directory under the system temporary root.
    Remove-Item -LiteralPath $resolvedTaskTemp -Recurse -Force
}
