# Hubfeed Agent — Update Script (Windows PowerShell)
# Run this on the HOST machine (not inside the container).
# It pulls the latest image and recreates the container.
# Persistent data in ./data and ./logs is preserved.

$ErrorActionPreference = "Stop"

$ComposeFile = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { "docker-compose.yml" }
$ServiceName = if ($env:SERVICE_NAME) { $env:SERVICE_NAME } else { "hubfeed-agent" }

Write-Host "=== Hubfeed Agent Updater ===" -ForegroundColor Cyan
Write-Host ""

# Check docker compose is available
$dcCommand = $null
try {
    docker compose version 2>&1 | Out-Null
    $dcCommand = "docker compose"
} catch {
    try {
        docker-compose version 2>&1 | Out-Null
        $dcCommand = "docker-compose"
    } catch {
        Write-Host "ERROR: docker compose is not installed." -ForegroundColor Red
        exit 1
    }
}

# Show current version (if container is running)
$current = "unknown"
try {
    $current = & docker compose -f $ComposeFile exec -T $ServiceName /py/bin/python -c "from src.__version__ import __version__; print(__version__)" 2>$null
    if (-not $current) { $current = "unknown" }
    $current = $current.Trim()
} catch {
    $current = "unknown"
}

Write-Host "Current version: $current"
Write-Host ""

Write-Host "Pulling latest image..."
& docker compose -f $ComposeFile pull
if ($LASTEXITCODE -ne 0) { Write-Host "Pull failed." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "Recreating container..."
& docker compose -f $ComposeFile up -d
if ($LASTEXITCODE -ne 0) { Write-Host "Container recreation failed." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "Waiting for agent to start..."
Start-Sleep -Seconds 5

# Show new version
$new = "unknown"
try {
    $new = & docker compose -f $ComposeFile exec -T $ServiceName /py/bin/python -c "from src.__version__ import __version__; print(__version__)" 2>$null
    if (-not $new) { $new = "unknown" }
    $new = $new.Trim()
} catch {
    $new = "unknown"
}

Write-Host "New version: $new"

if ($current -eq $new -and $current -ne "unknown") {
    Write-Host ""
    Write-Host "Already on the latest version." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "Update complete!" -ForegroundColor Green
}
