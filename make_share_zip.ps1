# Makes a zip of Voice Studio that you can send to someone else.
# Never included: the Python environments, your voice profiles, history and
# settings (data\), your scripts (scripts\) and your Azure key (it lives in Windows Credential Manager,
# not in this folder).
$root = $PSScriptRoot
Set-Location $root
$ver = (Get-Content (Join-Path $root "VERSION") -Raw).Trim()
$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force $dist | Out-Null

Write-Host "Voice Studio $ver : make a zip to share`n" -ForegroundColor Green
Write-Host "  1  Small zip (a few MB). Your friend's PC downloads Python packages and"
Write-Host "     the voice models on first start (about 9 GB, needs internet once)."
Write-Host "  2  Zip with the voice models inside (about 4 GB). First start still"
Write-Host "     downloads the Python packages, but not the models."
$choice = Read-Host "`nChoose 1 or 2"
$skip = @("runtime", "envs", "data", "dist", "scripts", ".git")
if ($choice -eq "2") { $name = "VoiceStudio_${ver}_with-models.zip" }
else { $name = "VoiceStudio_${ver}.zip"; $skip += "models" }
$items = Get-ChildItem -Force -Name | Where-Object { $skip -notcontains $_ }
$zip = Join-Path $dist $name
if (Test-Path $zip) {
  $a = Read-Host "$name already exists in dist\. Replace it? [y/N]"
  if ($a -notmatch "^[Yy]") { Write-Host "Nothing changed."; exit 0 }
  Remove-Item $zip
}
# tar.exe ships with Windows 10 and 11 and has no 2 GB limit
& tar.exe -a -c -f $zip --exclude=__pycache__ @items
if ($LASTEXITCODE -ne 0) { Write-Host "Could not create the zip." -ForegroundColor Red; exit 1 }
Write-Host "`nDone: $zip  ($([math]::Round((Get-Item $zip).Length / 1MB, 1)) MB)" -ForegroundColor Green
Write-Host "Tell your friend: unzip anywhere, then double-click 'Voice Studio.bat'."
