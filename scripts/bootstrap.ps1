# LabIA: deja esta maquina lista y verificada. Uso: ./scripts/bootstrap.ps1 [-SinPull]
# Solo ASCII a proposito: PowerShell 5.1 lee los .ps1 sin BOM como ANSI.
# Lo corre tambien el CI en Windows, asi que si aqui falla, alli tambien.
param([switch]$SinPull)
$ErrorActionPreference = "Stop"

function Invoke-Paso([string]$Nombre, [scriptblock]$Bloque) {
    Write-Host "== $Nombre"
    $global:LASTEXITCODE = 0
    & $Bloque
    if ($LASTEXITCODE -ne 0) { throw "Fallo: $Nombre (codigo $LASTEXITCODE)" }
}

Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not $SinPull) { Invoke-Paso "git pull --ff-only" { git pull --ff-only } }
if (-not (Test-Path ".venv")) { Invoke-Paso "crear .venv" { python -m venv .venv } }
$py = if ($env:OS -eq "Windows_NT") { ".venv\Scripts\python.exe" } else { ".venv/bin/python" }
Invoke-Paso "instalar" { & $py -m pip install --quiet --disable-pip-version-check -e ".[dev]" }
Invoke-Paso "pytest" { & $py -m pytest -q }
Invoke-Paso "mypy --strict" { & $py -m mypy }
Invoke-Paso "reglas separan sus casos" { & $py -m verificador casos | Out-Null }
Invoke-Paso "manifiestos y pre-registro" { & $py -m estudios.manifiestos proyectos --corridas corridas }
$hash = (git rev-parse --short HEAD)
$maquina = if ($env:COMPUTERNAME) { $env:COMPUTERNAME } else { [System.Net.Dns]::GetHostName() }
Write-Host "OK $hash en $maquina"
