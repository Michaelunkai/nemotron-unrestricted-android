param(
    [string]$Root = "E:\AI\Dolphin-X1-405B",
    [string]$BindHost = "100.65.146.122",
    [int]$Port = 18780
)

$ErrorActionPreference = "Stop"
$model = Join-Path $Root "Dolphin-X1-Llama-3.1-405B.i1-IQ1_S.gguf"
$server = Join-Path $Root "llama\llama-server.exe"
$log = Join-Path $Root "llama-server.log"
$stdoutLog = Join-Path $Root "llama-server.stdout.log"
$stderrLog = Join-Path $Root "llama-server.stderr.log"

if (-not (Test-Path -LiteralPath $server -PathType Leaf)) {
    throw "Verified llama-server.exe is missing: $server"
}
if (-not (Test-Path -LiteralPath $model -PathType Leaf)) {
    throw "Merged Dolphin X1 405B GGUF is missing: $model"
}
if ((Get-Item -LiteralPath $model).Length -ne 85233526624) {
    throw "Merged Dolphin X1 405B GGUF has the wrong byte length"
}

$arguments = @(
    "--model", $model,
    "--alias", "dphn/Dolphin-X1-Llama-3.1-405B",
    "--host", $BindHost,
    "--port", "$Port",
    "--ctx-size", "4096",
    "--parallel", "1",
    "--threads", "8",
    "--threads-batch", "8",
    "--batch-size", "128",
    "--ubatch-size", "64",
    "--fit", "on",
    "--fit-target", "2048",
    "--fit-ctx", "4096",
    "--cache-type-k", "q4_0",
    "--cache-type-v", "q4_0",
    "--flash-attn", "on",
    "--jinja",
    "--metrics",
    "--no-webui"
)

"[$([DateTime]::UtcNow.ToString('o'))] Starting exact Dolphin X1 405B on $BindHost`:$Port" |
    Add-Content -LiteralPath $log -Encoding UTF8
$process = Start-Process -FilePath $server -ArgumentList $arguments -NoNewWindow `
    -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru -Wait
exit $process.ExitCode
