param(
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

$AiEngineRoot = (
    Resolve-Path (
        Join-Path $PSScriptRoot ".."
    )
).Path

$PlatformRoot = (
    Resolve-Path (
        Join-Path $AiEngineRoot ".."
    )
).Path

$ComposeFile = Join-Path `
    $PlatformRoot `
    "docker\rtsp-test\compose.yml"

$Python = Join-Path `
    $AiEngineRoot `
    ".venv\Scripts\python.exe"

$TestFiles = @(
    (
        Join-Path `
            $AiEngineRoot `
            "tests\integration\test_real_rtsp_stream.py"
    )
    (
        Join-Path `
            $AiEngineRoot `
            "tests\integration\test_real_rtsp_reconnect.py"
    )
)

if (-not (Test-Path $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}

if (-not (Test-Path $Python)) {
    throw "Virtual-environment Python not found: $Python"
}

Push-Location $AiEngineRoot

try {
    Write-Host ""
    Write-Host "Building RTSP integration stack..."

    docker compose `
        -f $ComposeFile `
        up `
        -d `
        --build

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to start the RTSP integration stack"
    }

    Write-Host ""
    Write-Host "RTSP containers:"

    docker compose `
        -f $ComposeFile `
        ps

    $env:RUN_RTSP_INTEGRATION = "1"
    $env:RTSP_TEST_URI = (
        "rtsp://127.0.0.1:8554/synthetic"
    )

    Write-Host ""
    Write-Host "Running real RTSP integration test..."

    $env:RTSP_COMPOSE_FILE = $ComposeFile

    & $Python `
        -m pytest `
        @TestFiles `
        -v `
        -s

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "RTSP server logs:"

        docker compose `
            -f $ComposeFile `
            logs `
            --tail 100 `
            rtsp-server

        Write-Host ""
        Write-Host "Publisher logs:"

        docker compose `
            -f $ComposeFile `
            logs `
            --tail 100 `
            rtsp-publisher

        throw "RTSP integration test failed"
    }
}
finally {
    Remove-Item `
        Env:RUN_RTSP_INTEGRATION `
        -ErrorAction SilentlyContinue

    Remove-Item `
        Env:RTSP_TEST_URI `
        -ErrorAction SilentlyContinue

    Remove-Item `
        Env:RTSP_COMPOSE_FILE `
        -ErrorAction SilentlyContinue

    if (-not $KeepRunning) {
        Write-Host ""
        Write-Host "Stopping RTSP integration stack..."

        docker compose `
            -f $ComposeFile `
            down `
            --remove-orphans
    }
    else {
        Write-Host ""
        Write-Host "RTSP stack remains running:"
        Write-Host (
            "rtsp://127.0.0.1:8554/synthetic"
        )
    }

    Pop-Location
}