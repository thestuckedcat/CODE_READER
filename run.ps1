$ErrorActionPreference = 'Stop'
if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Bundled runtime requires Windows x64.' }
$AtlasRoot = $PSScriptRoot
$AtlasRuntime = Join-Path $AtlasRoot 'runtime/windows-x86_64'
$AtlasPython = Join-Path $AtlasRuntime 'venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $AtlasPython)) { $AtlasPython = Join-Path $AtlasRuntime 'python/python.exe' }
if (-not (Test-Path -LiteralPath $AtlasPython)) { throw 'Isolated runtime missing; run setup.ps1 first.' }
$env:PATH = (Split-Path -Parent $AtlasPython) + ';' + $env:PATH
$LegacySite = Join-Path $AtlasRuntime 'site'
if (Test-Path -LiteralPath $LegacySite) {
  $env:PYTHONPATH = $LegacySite
  $env:PATH = (Join-Path $LegacySite 'cmake/data/bin') + ';' + (Join-Path $LegacySite 'ninja/data/bin') + ';' + (Join-Path $LegacySite 'ninja') + ';' + $env:PATH
}
& $AtlasPython (Join-Path $AtlasRoot 'scripts/sdk_atlas.py') @args
exit $LASTEXITCODE
