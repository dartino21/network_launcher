$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pip install -r requirements.txt pytest
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }

python -m pytest -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; release was not built' }

$version = python -c "import sys; sys.path.insert(0, 'src'); import network_launcher; print(network_launcher.__version__)"
if ($LASTEXITCODE -ne 0 -or -not $version) { throw 'Could not determine package version' }
$version = $version.Trim()

python -m PyInstaller --noconfirm --clean --distpath dist --workpath build scripts\network_launcher.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

$releaseName = "NetworkLauncher-v$version-windows-x64"
$staging = Join-Path $root "release\$releaseName"
if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
New-Item -ItemType Directory -Force $staging | Out-Null
Copy-Item 'dist\NetworkLauncher.exe' $staging -Force
Copy-Item 'START_HERE.md' (Join-Path $staging 'START_HERE.txt') -Force
Copy-Item 'README.md' (Join-Path $staging 'README.txt') -Force
$archive = Join-Path $root "release\$releaseName.zip"
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $archive -Force
Write-Host "Release archive: release\$releaseName.zip"
