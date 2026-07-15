$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build scripts\network_launcher.spec

$staging = Join-Path $root 'release\NetworkLauncher-windows-x64'
New-Item -ItemType Directory -Force $staging | Out-Null
Copy-Item 'dist\NetworkLauncher.exe' $staging -Force
Copy-Item 'START_HERE.md' (Join-Path $staging 'START_HERE.txt') -Force
Copy-Item 'README.md' (Join-Path $staging 'README.txt') -Force
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath (Join-Path $root 'release\NetworkLauncher-windows-x64.zip') -Force
Write-Host "Release archive: release\NetworkLauncher-windows-x64.zip"
