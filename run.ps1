$ErrorActionPreference = 'Stop'
if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Bundled runtime requires Windows x64.' }
$AtlasRoot = $PSScriptRoot
$AtlasRuntime = Join-Path $AtlasRoot 'runtime/windows-x86_64'
$AtlasPython = Join-Path $AtlasRuntime 'python/python.exe'
if (-not (Test-Path $AtlasPython)) { throw 'Bundled Python missing; use the full distribution ZIP.' }
$env:PYTHONPATH = (Join-Path $AtlasRuntime 'site')
$env:PATH = (Join-Path $AtlasRuntime 'site/cmake/data/bin') + ';' + (Join-Path $AtlasRuntime 'site/ninja/data/bin') + ';' + (Join-Path $AtlasRuntime 'site/ninja') + ';' + $env:PATH
& $AtlasPython (Join-Path $AtlasRoot 'scripts/sdk_atlas.py') @args
exit $LASTEXITCODE
