param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Default = ""
    )

    if (-not (Test-Path $Path)) {
        return $Default
    }

    $pattern = "^{0}=(.*)$" -f [regex]::Escape($Name)
    foreach ($line in Get-Content $Path) {
        if ($line -match $pattern) {
            return $Matches[1].Trim()
        }
    }

    return $Default
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"
$databaseUrl = Get-DotEnvValue -Path $envPath -Name "DATABASE_URL" -Default "sqlite:///./data/aisdr.db"
$username = Get-DotEnvValue -Path $envPath -Name "ADMIN_USERNAME" -Default "admin"
$password = Get-DotEnvValue -Path $envPath -Name "ADMIN_PASSWORD" -Default "change-me"

if (-not $databaseUrl.StartsWith("sqlite:///./")) {
    throw "start-demo.ps1 expects a local sqlite DATABASE_URL such as sqlite:///./data/aisdr.db."
}

$sourceDbRelative = $databaseUrl.Substring("sqlite:///./".Length).Replace("/", "\")
$sourceDb = Join-Path $repoRoot $sourceDbRelative
$demoDb = Join-Path $repoRoot "data\aisdr-demo.db"
$demoDataDir = Split-Path -Parent $demoDb

if (-not (Test-Path $sourceDb)) {
    throw "Source database not found at $sourceDb. Run the app once or create your local demo data first."
}

New-Item -ItemType Directory -Path $demoDataDir -Force | Out-Null
Copy-Item -Path $sourceDb -Destination $demoDb -Force

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    throw "Port $Port is already in use by PID $($listener.OwningProcess). Stop that process or choose another port."
}

$pythonCandidates = @(
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    (Join-Path $repoRoot "venv\Scripts\python.exe"),
    "python"
)
$python = $pythonCandidates | Where-Object { $_ -eq "python" -or (Test-Path $_) } | Select-Object -First 1

if (-not $python) {
    throw "Python was not found. Activate your virtual environment or install Python before running the demo."
}

$demoDbUrl = "sqlite:///./data/aisdr-demo.db"
$launchCommand = "set DATABASE_URL=$demoDbUrl&& `"$python`" -m uvicorn app.main:app --host 127.0.0.1 --port $Port"
$process = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $launchCommand -WorkingDirectory $repoRoot -PassThru

$demoUrl = "http://127.0.0.1:$Port/login"
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri $demoUrl -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
    }
}

if (-not $ready) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "AISDR did not respond on $demoUrl within 30 seconds."
}

Start-Process $demoUrl

Write-Host ""
Write-Host "AISDR demo is ready." -ForegroundColor Green
Write-Host "URL:      $demoUrl"
Write-Host "Username: $username"
Write-Host "Password: $password"
Write-Host ""
Write-Host "Demo order:"
Write-Host "1. Dashboard"
Write-Host "2. Settings"
Write-Host "3. Imports"
Write-Host "4. Contacts"
Write-Host "5. Contact detail"
Write-Host "6. Discovery"
Write-Host ""
Write-Host "This run uses a fresh snapshot at data\\aisdr-demo.db so your working database stays untouched."
