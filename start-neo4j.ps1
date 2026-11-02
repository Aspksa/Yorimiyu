# Optional local Neo4j bootstrap. Never requires admin elevation without user consent.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtime = Join-Path $root '.runtime'
$secretFile = Join-Path $runtime 'neo4j-local.json'
$logFile = Join-Path $runtime 'neo4j-setup.log'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
function Log([string]$message) {
    Write-Host ('[Neo4j] ' + $message)
    Add-Content -LiteralPath $logFile -Encoding UTF8 -Value ((Get-Date -Format s) + ' ' + $message)
}
function DockerReady {
    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) { return $false }
    try {
        & docker.exe info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
try {
    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
        Log 'Docker Desktop is not installed.'
        if ($env:YORIMIYU_INSTALL_DOCKER -ne '1') {
            Log 'To install Docker Desktop, run setup-neo4j.bat and approve installation.'
            exit 0
        }
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            Log 'winget is unavailable. Install Docker Desktop manually.'
            exit 0
        }
        Log 'Installing Docker Desktop with winget (may request administrator approval).'
        & winget.exe install --id Docker.DockerDesktop --exact --source winget --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop installation failed' }
        Log 'Docker Desktop installed. Start Docker Desktop, enable WSL2 if prompted, and rerun Yorimiyu.'
        exit 0
    }
    if (-not (DockerReady)) {
        $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
        if (Test-Path -LiteralPath $desktop) {
            Log 'Starting Docker Desktop...'
            Start-Process -FilePath $desktop | Out-Null
            for ($i=0; $i -lt 30; $i++) {
                Start-Sleep -Seconds 2
                if (DockerReady) { break }
            }
        }
    }
    if (-not (DockerReady)) {
        Log 'Docker engine is not ready. Complete Docker Desktop / WSL2 first. Yorimiyu can still use SQLite.'
        exit 0
    }
    if (Test-Path -LiteralPath $secretFile) {
        $saved = Get-Content -LiteralPath $secretFile -Raw | ConvertFrom-Json
        $password = [string]$saved.password
    } else {
        $bytes = New-Object byte[] 36
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $password = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','A').Replace('/','B')
        $json = @{password=$password; user='neo4j'} | ConvertTo-Json -Compress
        [System.IO.File]::WriteAllText($secretFile,$json,[System.Text.Encoding]::UTF8)
        try { & icacls.exe $secretFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null } catch {}
        Log 'Created a local Neo4j credential file under .runtime (never commit this folder).'
    }
    if (-not $password) { throw 'Local Neo4j password is empty' }
    $env:YORIMIYU_NEO4J_PASSWORD = $password
    $env:YORIMIYU_NEO4J_USER = 'neo4j'
    Log 'Starting local Neo4j container...'
    & docker.exe compose -f (Join-Path $root 'docker-compose.neo4j.yml') up -d
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not start Neo4j' }
    Log 'Local Neo4j container started. The first download can take several minutes.'
} catch {
    Log ('Setup failed: ' + $_.Exception.Message)
}
exit 0
