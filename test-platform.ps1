$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Python = Join-Path $Root 'runtime/windows-x86_64/venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Run setup.ps1 first.' }
& $Python (Join-Path $Root 'scripts/test_platform.py')
exit $LASTEXITCODE
