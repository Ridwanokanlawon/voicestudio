# Voice Studio setup. Safe to run again: finished steps are skipped.
# Everything is installed INSIDE this folder (runtime\ and models\), so the
# folder stays self-contained. Nothing outside it is changed except:
#   - a "Voice Studio" shortcut on your Desktop
#   - a setup log in C:\Temp\VoiceStudio_Setup_<date-time>\
#   - Python 3.11 itself, only if this PC does not have it (you are asked first)
param([switch]$Yes, [switch]$NoShortcut)
$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Set-Location $root
$rt   = Join-Path $root "runtime"
$py   = Join-Path $rt "Scripts\python.exe"
$models = Join-Path $root "models"
$seed = Join-Path $env:USERPROFILE "Videos\What Could Go Wrong\_voice"   # an earlier install on this PC, if any
$ckptName = "wavtokenizer_large_speech_320_24k.ckpt"
$yamlName = "wavtokenizer_mediumdata_frame75_3s_nq1_code4096_dim512_kmeans200_attn.yaml"

$logDir = "C:\Temp\VoiceStudio_Setup_$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory -Force $logDir | Out-Null
Start-Transcript "$logDir\setup.log" | Out-Null

function Say($t, $c = "Cyan") { Write-Host "`n== $t" -ForegroundColor $c }
function Stop-Setup($msg) {
  Write-Host "`nSETUP STOPPED: $msg" -ForegroundColor Red
  Write-Host "Log: $logDir\setup.log"
  Stop-Transcript | Out-Null
  exit 1
}
function Ask($question) {
  if ($Yes) { return $true }
  $a = Read-Host "$question [Y/n]"
  return ($a -eq "" -or $a -match "^[Yy]")
}
function Has311 { try { $null = & py -3.11 --version 2>&1; return ($LASTEXITCODE -eq 0) } catch { return $false } }
function RuntimeWorks { if (-not (Test-Path $py)) { return $false }; & $py -c "import torch, torchaudio, transformers, outetts" 2>$null; return ($LASTEXITCODE -eq 0) }

Write-Host "Voice Studio setup" -ForegroundColor Green
Write-Host "Folder: $root"

# ---- 1. Python runtime (inside this folder) ---------------------------------
if (-not (RuntimeWorks)) {
  $seedVenv = Join-Path $seed ".venv"
  if ((-not (Test-Path $rt)) -and (Test-Path (Join-Path $seedVenv "Scripts\python.exe"))) {
    Say "Copying the Python environment that is already on this PC (no download, several GB, a few minutes)"
    robocopy $seedVenv $rt /E /MT:8 /NFL /NDL /NJH /NP /R:1 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { Write-Host "Copy had errors; will install fresh instead." -ForegroundColor Yellow }
  }
  if (-not (RuntimeWorks)) {
    if (-not (Has311)) {
      Say "Python 3.11 is needed and was not found"
      if (-not (Ask "Install Python 3.11 from the official source using winget?")) { Stop-Setup "Python 3.11 is required." }
      winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
      $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
      if (-not (Has311)) { Stop-Setup "Python was installed. Close this window and start Voice Studio again." }
    }
    if (-not (Test-Path $py)) {
      Say "Creating the Python environment in runtime\"
      & py -3.11 -m venv $rt
      if ($LASTEXITCODE -ne 0) { Stop-Setup "Could not create the Python environment." }
    }
    $gpu = $false
    try { $null = & nvidia-smi 2>&1; $gpu = ($LASTEXITCODE -eq 0) } catch { }
    if ($gpu) {
      Say "Installing PyTorch with NVIDIA GPU support (about 2.5 GB download)"
      & $py -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
    } else {
      Say "No NVIDIA GPU found: installing the CPU version of PyTorch (YarnGPT will work, but slowly)" "Yellow"
      & $py -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    }
    if ($LASTEXITCODE -ne 0) { Stop-Setup "PyTorch did not install. Check the internet connection and run Setup.bat again." }
  }
}

# ---- 2. Python packages -----------------------------------------------------
& $py -c "import fastapi, uvicorn, keyring, lameenc, transformers, outetts, uroman, inflect, soundfile, soxr, pyloudnorm, librosa, azure.cognitiveservices.speech" 2>$null
if ($LASTEXITCODE -ne 0) {
  Say "Python packages"
  Write-Host "These packages will be installed into this folder's runtime\ (not system-wide):"
  Write-Host "  New for Voice Studio : fastapi, uvicorn, keyring, lameenc (plus their small dependencies)"
  Write-Host "  Voice engines        : anything missing from requirements.txt"
  if (-not (Ask "Install them now?")) { Stop-Setup "Packages are required to run the app." }
  & $py -m pip install --disable-pip-version-check -r (Join-Path $root "requirements.txt")
  if ($LASTEXITCODE -ne 0) { Stop-Setup "Some packages did not install. Run Setup.bat again." }
}

# ---- 3. YarnGPT code --------------------------------------------------------
$vend = Join-Path $root "vendor\yarngpt"
if (-not (Test-Path (Join-Path $vend "audiotokenizer.py"))) {
  Say "Getting the YarnGPT code"
  New-Item -ItemType Directory -Force $vend | Out-Null
  $src = @((Join-Path $seed "yarngpt-main"), (Join-Path $seed "yarngpt")) | Where-Object { Test-Path (Join-Path $_ "audiotokenizer.py") } | Select-Object -First 1
  if (-not $src) {
    $zip = Join-Path $logDir "yarngpt.zip"
    curl.exe -L --fail -o $zip https://github.com/saheedniyi02/yarngpt/archive/refs/heads/main.zip
    Expand-Archive $zip -DestinationPath $logDir -Force
    $src = Join-Path $logDir "yarngpt-main"
  }
  Copy-Item (Join-Path $src "audiotokenizer.py"), (Join-Path $src "__init__.py"), (Join-Path $src "README.md") $vend -Force
  Copy-Item (Join-Path $src "default_speakers") $vend -Recurse -Force
  Copy-Item (Join-Path $src "default_speakers_local") $vend -Recurse -Force
}

# ---- 4. Model files ---------------------------------------------------------
New-Item -ItemType Directory -Force $models | Out-Null
$yaml = Join-Path $models $yamlName
$ckpt = Join-Path $models $ckptName
if (-not (Test-Path $yaml)) {
  if (Test-Path (Join-Path $seed "models\$yamlName")) { Copy-Item (Join-Path $seed "models\$yamlName") $yaml }
  else { Say "Downloading the audio config"; curl.exe -L --fail -o $yaml "https://huggingface.co/novateur/WavTokenizer-medium-speech-75token/resolve/main/$yamlName" }
}
if (-not (Test-Path $ckpt) -or (Get-Item $ckpt).Length -lt 1700000000) {
  if (Test-Path (Join-Path $seed "models\$ckptName")) {
    Say "Copying the audio model that is already on this PC (1.7 GB)"
    Copy-Item (Join-Path $seed "models\$ckptName") $ckpt -Force
  } else {
    Say "Downloading the audio model (1.7 GB, one time)"
    curl.exe -L --fail -C - -o $ckpt "https://huggingface.co/novateur/WavTokenizer-large-speech-75token/resolve/main/$ckptName"
    if ($LASTEXITCODE -ne 0) { Stop-Setup "The audio model did not download. Run Setup.bat again to resume." }
  }
}
Say "YarnGPT2 voice model"
& $py -m app.fetch_model
if ($LASTEXITCODE -ne 0) { Stop-Setup "The YarnGPT2 model is not in place. Check the internet connection and run Setup.bat again." }

# ---- 5. Desktop shortcut ----------------------------------------------------
if (-not $NoShortcut) {
  try {
    $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Voice Studio.lnk"
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = Join-Path $root "Voice Studio.bat"
    $s.WorkingDirectory = $root
    $s.IconLocation = (Join-Path $root "assets\voicestudio.ico")
    $s.WindowStyle = 7
    $s.Description = "Voice Studio: scripts to voiceover"
    $s.Save()
    Write-Host "`nDesktop shortcut ready: $lnk"
  } catch { Write-Host "Could not create the desktop shortcut (not a problem)." -ForegroundColor Yellow }
}

# ---- 6. Check ---------------------------------------------------------------
Say "Checking the graphics card"
& $py -c "import torch; ok=torch.cuda.is_available(); print('GPU ready:', ok, torch.cuda.get_device_name(0) if ok else '(YarnGPT will run on the CPU, slowly)')"
Write-Host "`nSetup finished. Log: $logDir\setup.log" -ForegroundColor Green
Stop-Transcript | Out-Null
exit 0
