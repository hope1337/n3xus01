$ErrorActionPreference = 'Stop'
$clusterArguments = @($args)
# PowerShell consumes a bare `--` when invoking a .ps1 script. Reconstruct the
# container delimiter from the known run options before forwarding to Python.
if ($clusterArguments.Count -gt 2 -and $clusterArguments[0] -eq 'run' -and $clusterArguments -notcontains '--') {
    $position = 2
    while ($position -lt $clusterArguments.Count) {
        if ($clusterArguments[$position] -eq '--image') { $position += 2; continue }
        if ($clusterArguments[$position] -eq '--gpu' -or $clusterArguments[$position] -like '--image=*') { $position++; continue }
        if ($clusterArguments[$position].StartsWith('--')) { break }
        $clusterArguments = @($clusterArguments[0..($position - 1)]) + @('--') + @($clusterArguments[$position..($clusterArguments.Count - 1)])
        break
    }
}
if ($clusterArguments.Count -eq 0 -or $clusterArguments[0] -in @('help', '--help', '-h')) {
    Write-Host 'Personal compute: setup -> add-device -> check -> ask your agent'
    Write-Host '.\cluster.ps1 setup'
    Write-Host '.\cluster.ps1 add-device [NAME] [--address TAILSCALE_IP] [--user SSH_USER] [--gpu]'
    Write-Host '.\cluster.ps1 check | status | check --static'
    Write-Host '.\cluster.ps1 run DEVICE --image IMAGE [--gpu] -- COMMAND ARGUMENTS...'
    Write-Host '.\cluster.ps1 jobs | logs JOB | wait JOB | delete-job JOB'
    Write-Host '.\cluster.ps1 kubectl get pods -A (advanced troubleshooting)'
    exit 0
}
$distribution = 'Ubuntu-24.04'
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw 'WSL unavailable. Enable WSL, restart, then rerun setup.' }
$installed = @(& wsl.exe --list --quiet 2>$null) -join "`n"
$installed = $installed.Replace([string][char]0, '')
if ($LASTEXITCODE -ne 0 -or $installed -notmatch '(?m)^\s*Ubuntu-24\.04\s*$') {
    if ($clusterArguments[0] -ne 'setup') { throw 'Run .\cluster.ps1 setup first.' }
    Write-Host '[cluster] Preparing Ubuntu-24.04. Windows may request administrator approval.'
    $process = Start-Process -FilePath 'wsl.exe' -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList @('--install', '-d', $distribution, '--no-launch')
    if ($process.ExitCode -ne 0) { throw 'WSL installation incomplete. Restart if requested, then rerun setup.' }
    $installed = (@(& wsl.exe --list --quiet 2>$null) -join "`n").Replace([string][char]0, '')
    if ($installed -notmatch '(?m)^\s*Ubuntu-24\.04\s*$') { throw 'Restart Windows to finish WSL installation, then rerun setup.' }
}
$sshCommand = Get-Command ssh.exe -ErrorAction Stop
$repoLinux = (& wsl.exe -d $distribution -u root --exec wslpath -u $PSScriptRoot | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $repoLinux.StartsWith('/')) { throw 'Could not resolve repository path in WSL.' }
$sshLinux = (& wsl.exe -d $distribution -u root --exec wslpath -u $sshCommand.Source | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $sshLinux.StartsWith('/')) { throw 'Could not locate Windows SSH inside WSL.' }
# JSON/base64 preserves container quotes and Unicode even in Windows PowerShell
# 5.1's legacy native argument handling. No shell string/eval or SSH key copy.
$encodedArguments = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $clusterArguments -Compress)))
& wsl.exe -d $distribution -u root --exec env "CLUSTER_WINDOWS_SSH=$sshLinux" "CLUSTER_ARGUMENTS_BASE64=$encodedArguments" bash "$repoLinux/cluster" $clusterArguments[0]
exit $LASTEXITCODE
