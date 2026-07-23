param(
    [string]$Root = "E:\AI\Dolphin-X1-405B",
    [string]$BindHost = "100.65.146.122",
    [int]$Port = 18780
)

$ErrorActionPreference = "Stop"
$part1 = Join-Path $Root "Dolphin-X1-Llama-3.1-405B.i1-IQ1_S.gguf.part1of2"
$part2 = Join-Path $Root "Dolphin-X1-Llama-3.1-405B.i1-IQ1_S.gguf.part2of2"
$model = Join-Path $Root "Dolphin-X1-Llama-3.1-405B.i1-IQ1_S.gguf"
$launcher = Join-Path $Root "start-dolphin-x1-server.ps1"

$expected = @{
    $part1 = @{ Length = 42949672960; Sha256 = "2387a10ceb3f236c5525985bafef1e6c8430ce3f7a32d980a413121941179e84" }
    $part2 = @{ Length = 42283853664; Sha256 = "a6d0cde87f086f20f48d5ad85860807cd8bc57c5fa2f7b534a6434a33ec6bd83" }
}
foreach ($path in $expected.Keys) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required exact-model shard is missing: $path"
    }
    if ((Get-Item -LiteralPath $path).Length -ne $expected[$path].Length) {
        throw "Exact-model shard has the wrong byte length: $path"
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected[$path].Sha256) {
        throw "Exact-model shard checksum mismatch: $path"
    }
}

if (-not (Test-Path -LiteralPath $model) -or (Get-Item -LiteralPath $model).Length -ne 85233526624) {
    $temporary = "$model.incomplete"
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    $output = [System.IO.File]::Open($temporary, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try {
        foreach ($sourcePath in @($part1, $part2)) {
            $input = [System.IO.File]::OpenRead($sourcePath)
            try { $input.CopyTo($output, 16MB) } finally { $input.Dispose() }
        }
        $output.Flush($true)
    } finally {
        $output.Dispose()
    }
    Move-Item -LiteralPath $temporary -Destination $model -Force
}

if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Server launcher is missing: $launcher"
}

$ruleName = "Nemotron Dolphin X1 405B (Tailscale only)"
try {
    Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction Stop
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP `
        -LocalAddress $BindHost -LocalPort $Port -RemoteAddress "100.64.0.0/10" `
        -Profile Any -ErrorAction Stop | Out-Null
} catch {
    & netsh advfirewall firewall delete rule name="$ruleName" | Out-Null
    & netsh advfirewall firewall add rule name="$ruleName" dir=in action=allow protocol=TCP `
        localport=$Port localip=$BindHost remoteip="100.64.0.0/10" profile=any enable=yes | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to configure the Tailscale-only firewall rule"
    }
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$launcher`" " +
    "-Root `"$Root`" -BindHost `"$BindHost`" -Port $Port"
)
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 2) `
    -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "Nemotron-Dolphin-X1-405B" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Exact dphn Dolphin X1 Llama 3.1 405B llama.cpp endpoint" -Force | Out-Null
Start-ScheduledTask -TaskName "Nemotron-Dolphin-X1-405B"
