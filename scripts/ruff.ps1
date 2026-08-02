$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$ruff = Join-Path $projectRoot '.venv\Scripts\ruff.exe'

if (-not (Test-Path $ruff)) {
    throw 'Ruff was not found. Create .venv and install: .\.venv\Scripts\python -m pip install -r requirements-dev.txt'
}

& $ruff format
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $ruff check --fix
exit $LASTEXITCODE
