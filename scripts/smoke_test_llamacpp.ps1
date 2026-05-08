# Quick smoke test against the running llama-cpp-server.
# Run this from any PowerShell shell while the server is up on :8765.
#
# Usage:
#     pwsh scripts/smoke_test_llamacpp.ps1
#
# What it checks:
#   1. /v1/models — server is alive and reports the configured model
#   2. /v1/chat/completions with a TINY prompt — inference works at all
#   3. Roughly times the response — first-token-ish latency for a cold call

$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8765'
$auth = @{ Authorization = 'Bearer local-ultron' }

Write-Host '--- /v1/models ---' -ForegroundColor Cyan
$models = Invoke-RestMethod -Uri "$base/v1/models" -Headers $auth
$models | ConvertTo-Json -Depth 4
Write-Host ''

Write-Host '--- /v1/chat/completions (small prompt; cold first call may be slow) ---' -ForegroundColor Cyan
$body = @{
    model = 'qwen3.5-9b-local'
    messages = @(
        @{ role = 'system'; content = 'You are terse.' }
        @{ role = 'user'; content = 'Reply with exactly OPENCLAW-LLAMACPP-OK and nothing else.' }
    )
    max_tokens = 32
    temperature = 0
} | ConvertTo-Json -Compress

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$resp = Invoke-RestMethod -Uri "$base/v1/chat/completions" `
    -Method Post -ContentType 'application/json' `
    -Headers $auth -Body $body -TimeoutSec 300
$sw.Stop()

Write-Host ''
Write-Host "wall: $([Math]::Round($sw.Elapsed.TotalSeconds, 2))s"
Write-Host "completion:"
Write-Host $resp.choices[0].message.content
Write-Host ''
Write-Host "usage:"
$resp.usage | ConvertTo-Json -Compress
