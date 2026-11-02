# Start the local Neo4j container only when Docker and credentials are configured.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $env:YORIMIYU_NEO4J_PASSWORD) {
    Write-Host '[Neo4j] Not started: set YORIMIYU_NEO4J_PASSWORD to enable local graph service.'
    exit 0
}
if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    Write-Host '[Neo4j] Docker Desktop not installed; SQLite and chat remain available.'
    exit 0
}
try {
    & docker.exe info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine is not running' }
    & docker.exe compose -f (Join-Path $root 'docker-compose.neo4j.yml') up -d
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed' }
    Write-Host '[Neo4j] Local graph container started.'
} catch {
    Write-Host ('[Neo4j] Optional service unavailable: ' + $_.Exception.Message)
}
exit 0
