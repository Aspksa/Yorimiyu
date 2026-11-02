# Download the official Windows embeddable Python only when no usable Python is found.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtime = Join-Path $root '.runtime'
$target = Join-Path $runtime 'python'
$version = '3.11.9'
$architecture = if ([Environment]::Is64BitOperatingSystem) { 'amd64' } else { 'win32' }
$url = "https://www.python.org/ftp/python/$version/python-$version-embed-$architecture.zip"
$archive = Join-Path $runtime 'python-download.zip'
$staging = Join-Path $runtime 'python-staging'
$log = Join-Path $runtime 'python-install.log'
function Log([string]$message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $message"
    Write-Host $line
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}
try {
    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
    Log 'Checking portable Python'
    $exe = Join-Path $target 'python.exe'
    if (Test-Path -LiteralPath $exe) {
        & $exe -c 'import sys,sqlite3,ssl;sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { Log 'Portable Python is ready'; exit 0 }
    }
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    Log "Downloading official Python $version from python.org ($architecture)"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing -MaximumRedirection 5
    Log 'Extracting Python'
    Expand-Archive -LiteralPath $archive -DestinationPath $staging -Force
    $candidate = Join-Path $staging 'python.exe'
    if (-not (Test-Path -LiteralPath $candidate)) { throw 'Downloaded archive has no python.exe' }
    & $candidate -c 'import sys,sqlite3,ssl;sys.exit(0 if sys.version_info >= (3,10) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Downloaded Python failed sqlite3/ssl validation' }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    Move-Item -LiteralPath $staging -Destination $target
    Log 'Portable Python installed successfully'
    exit 0
} catch {
    Log ("ERROR: " + $_.Exception.Message)
    exit 1
} finally {
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue }
}
