$ErrorActionPreference = 'Stop'
$deviceArguments = @($args | ForEach-Object { [string]$_ })
# .ps1 invocation may consume --; restore it before the program argv.
$actionPosition = -1
for ($i = 0; $i -lt $deviceArguments.Count; $i++) {
    if ($deviceArguments[$i] -eq '--json') { continue }
    if ($deviceArguments[$i] -eq '--color') { $i++; continue }
    if ($deviceArguments[$i] -match '^--color=') { continue }
    $actionPosition = $i
    break
}
if ($actionPosition -ge 0 -and $deviceArguments.Count -gt ($actionPosition + 3) -and $deviceArguments[$actionPosition] -in @('run', 'serve') -and $deviceArguments -notcontains '--') {
    $position = $actionPosition + 3
    while ($position -lt $deviceArguments.Count) {
        if ($deviceArguments[$position] -in @('--env', '--gpu', '--name', '--port', '--color', '--description', '--agent')) { $position += 2; continue }
        if ($deviceArguments[$position] -eq '--json' -or $deviceArguments[$position] -match '^--(env|gpu|name|port|color|description|agent)=') { $position++; continue }
        if ($deviceArguments[$position].StartsWith('--')) { break }
        $deviceArguments = @($deviceArguments[0..($position-1)]) + @('--') + @($deviceArguments[$position..($deviceArguments.Count-1)])
        break
    }
}
$python = if ($env:DEVICE_PYTHON_EXECUTABLE) { Get-Command -Name $env:DEVICE_PYTHON_EXECUTABLE -CommandType Application -ErrorAction SilentlyContinue } else { Get-Command python.exe -ErrorAction SilentlyContinue }
if (-not $python -or $python.Source -like '*WindowsApps*') {
    $python = Get-Command py.exe -ErrorAction SilentlyContinue
}
if (-not $python) { throw 'Install Python 3.10+ (or use your conda terminal). No WSL is required.' }
$previous = $env:DEVICE_ARGUMENTS_BASE64
try {
    # Preserve literal quotes/$/Unicode through Windows native argument rules.
    $env:DEVICE_ARGUMENTS_BASE64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $deviceArguments -Compress)))
    if ([IO.Path]::GetFileName($python.Source) -eq 'py.exe') {
        & $python.Source -3 (Join-Path $PSScriptRoot 'scripts/device_cli.py')
    } else {
        & $python.Source (Join-Path $PSScriptRoot 'scripts/device_cli.py')
    }
    $deviceExit = $LASTEXITCODE
    if ($deviceExit -eq 0 -and $actionPosition -ge 0 -and $deviceArguments[$actionPosition] -in @('setup', 'unregister')) {
        $deviceBin = Join-Path $env:LOCALAPPDATA 'PersonalDevice\bin'
        $pathEntries = @($env:PATH -split ';' | Where-Object { $_.TrimEnd('\') -ine $deviceBin.TrimEnd('\') })
        if ((Test-Path -LiteralPath (Join-Path $deviceBin 'device.ps1')) -and $deviceArguments -notcontains '--no-register') {
            $env:PATH = ($pathEntries + @($deviceBin)) -join ';'
        } elseif ($deviceArguments[$actionPosition] -eq 'unregister') {
            $userEntries = @([Environment]::GetEnvironmentVariable('Path', 'User') -split ';' | ForEach-Object { [Environment]::ExpandEnvironmentVariables($_).TrimEnd('\') })
            $env:PATH = if ($userEntries -icontains $deviceBin.TrimEnd('\')) { ($pathEntries + @($deviceBin)) -join ';' } else { $pathEntries -join ';' }
        }
    }
} finally {
    $env:DEVICE_ARGUMENTS_BASE64 = $previous
}
exit $deviceExit
