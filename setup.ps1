$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$HostPython = (Get-Command python -ErrorAction Stop).Source
& $HostPython (Join-Path $Root 'scripts/setup_runtime.py') @args
exit $LASTEXITCODE
