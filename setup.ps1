# Voice Studio setup. Safe to run again: finished steps are skipped.
# Everything is installed INSIDE this folder (runtime\, envs\ and models\), so
# the folder stays self-contained. Nothing outside it is changed except:
#   - a "Voice Studio" shortcut on your Desktop
#   - a setup log in C:\Temp\VoiceStudio_Setup_<date-time>\
#   - Python 3.11 itself, only if this PC does not have it (you are asked first)
#
#   Setup.bat                      asks which voice engines to install
#   Setup.bat -Engines lite,chatterbox,openvoice -Yes     no questions
#   Setup.bat -Engines none -Yes   only the app itself (Azure voices)
param([string[]]$Engines, [switch]$Yes, [switch]$NoShortcut)
$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Set-Location $root
$models = Join-Path $root "models"
$env:VOICESTUDIO_MODELS = $models
$env:VOICESTUDIO_FETCH = "1"
$env:PYTHONUTF8 = "1"
$env:NLTK_DATA = Join-Path $models "nltk_data"      # keep pronunciation data inside the app folder
$MELO_SRC = "https://github.com/myshell-ai/MeloTTS/archive/209145371cff8fc3bd60d7be902ea69cbdb7965a.zip"
$SPACY_EN = "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
$PY_URL   = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
$OV_SRC   = "https://github.com/myshell-ai/OpenVoice/archive/74a1d147b17a8c3092dd5430504bd83ef6c7eb23.zip"

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
function Find-Py311 {
  # returns the path of a Python 3.11 interpreter, or $null
  try { $p = & py -3.11 -c "import sys; print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $p) { return "$p".Trim() } } catch { }
  foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python311\python.exe", "C:\Program Files\Python311\python.exe")) {
    if (Test-Path $c) { return $c }
  }
  try { $v = & python -c "import sys; print(sys.version_info[:2] == (3, 11), sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$v" -match "^True (.+)$") { return $Matches[1].Trim() } } catch { }
  return $null
}
function PyOf($envDir) { return (Join-Path $envDir "Scripts\python.exe") }
function Works($py, $imports) {
  if (-not (Test-Path $py)) { return $false }
  & $py -c "import $imports" 2>$null
  return ($LASTEXITCODE -eq 0)
}
function New-Venv($dir) {
  if (Test-Path (PyOf $dir)) { return }
  & $script:BasePy -m venv $dir
  if ($LASTEXITCODE -ne 0) { Stop-Setup "Could not create the Python environment in $dir." }
  & (PyOf $dir) -m pip install --disable-pip-version-check --quiet --upgrade pip
}
function Install-Torch($py) {
  $gpu = $false
  try { $null = & nvidia-smi 2>&1; $gpu = ($LASTEXITCODE -eq 0) } catch { }
  if ($gpu) {
    Write-Host "Installing PyTorch 2.6 with NVIDIA GPU support (2.5 GB the first time, then reused from pip's cache)"
    & $py -m pip install --disable-pip-version-check torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
  } else {
    Write-Host "No NVIDIA GPU found: installing the CPU version of PyTorch (the engines work, but slowly)" -ForegroundColor Yellow
    & $py -m pip install --disable-pip-version-check torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cpu
  }
  if ($LASTEXITCODE -ne 0) { Stop-Setup "PyTorch did not install. Check the internet connection and run Setup.bat again." }
}

Write-Host "Voice Studio setup" -ForegroundColor Green
Write-Host "Folder: $root"

# ---- 0. Python 3.11 ---------------------------------------------------------
$script:BasePy = Find-Py311
if (-not $script:BasePy) {
  Say "Python 3.11 is needed and was not found"
  if (-not (Ask "Install Python 3.11 for this user from python.org (25 MB)?")) { Stop-Setup "Python 3.11 is required." }
  $ok = $false
  try { winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements; $ok = ($LASTEXITCODE -eq 0) } catch { }
  $script:BasePy = Find-Py311
  if (-not $script:BasePy) {
    Write-Host "Downloading the Python installer from python.org"
    $inst = Join-Path $logDir "python-3.11.9-amd64.exe"
    curl.exe -L --fail -o $inst $PY_URL
    if ($LASTEXITCODE -ne 0) { Stop-Setup "Python could not be downloaded. Check the internet connection." }
    Start-Process -FilePath $inst -ArgumentList "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 Include_test=0" -Wait
    $script:BasePy = Find-Py311
  }
  if (-not $script:BasePy) { Stop-Setup "Python 3.11 was installed but could not be found. Close this window and run Setup.bat again." }
}
Write-Host "Python: $script:BasePy"

# ---- 1. Main app environment (small) ----------------------------------------
$rt = Join-Path $root "runtime"
$py = PyOf $rt
$mainImports = "fastapi, uvicorn, keyring, lameenc, numpy, soundfile, soxr, pyloudnorm, librosa, azure.cognitiveservices.speech, webview"
if (-not (Works $py $mainImports)) {
  Say "Main app environment (runtime\)"
  New-Venv $rt
  & $py -m pip install --disable-pip-version-check -r (Join-Path $root "requirements.txt")
  if (-not (Works $py $mainImports)) { Stop-Setup "The main app packages did not install. Run Setup.bat again." }
}

# ---- 2. Which voice engines -------------------------------------------------
$ltDone = (Works (PyOf (Join-Path $root "envs\lite")) "kokoro, pocket_tts, en_core_web_sm") -and (Test-Path (Join-Path $models "lite\kokoro.ok")) -and (Test-Path (Join-Path $models "lite\pocket.ok"))
$cbDone = (Works (PyOf (Join-Path $root "envs\chatterbox")) "chatterbox.tts, perth") -and (Test-Path (Join-Path $models "chatterbox\t3_cfg.safetensors"))
$ovDone = (Works (PyOf (Join-Path $root "envs\openvoice")) "melo, openvoice") -and (Test-Path (Join-Path $models "melo\EN\checkpoint.pth")) -and (Test-Path (Join-Path $models "openvoice\converter\checkpoint.pth")) -and (Test-Path (Join-Path $models "hf_cache\hub\models--M4869--WavMark")) -and (Test-Path (Join-Path $models "nltk_data\corpora\cmudict"))
$want = @()
if ($Engines) { $want = $Engines | ForEach-Object { $_.ToLower().Split(",") } | ForEach-Object { $_.Trim() } }
else {
  Say "Voice engines (each runs on this PC in its own environment)"
  if ($ltDone) { Write-Host "Kokoro and Pocket TTS: already installed" }
  elseif (Ask "Install the light engines, Kokoro and Pocket TTS (preset voices, run on any PC; about 2 GB)?") { $want += "lite" }
  if ($cbDone) { Write-Host "Chatterbox: already installed" }
  elseif (Ask "Install Chatterbox (voice cloning; needs an NVIDIA GPU to be fast; about 8 GB)?") { $want += "chatterbox" }
  if ($ovDone) { Write-Host "OpenVoice v2: already installed" }
  elseif (Ask "Install OpenVoice v2 with MeloTTS accents (your tone with a chosen accent; about 6 GB)?") { $want += "openvoice" }
}

# ---- 2b. Light engines: Kokoro and Pocket TTS (CPU) -------------------------
if (($want -contains "lite") -and (-not $ltDone)) {
  Say "Light engines environment (envs\lite)"
  $e = Join-Path $root "envs\lite"; $p = PyOf $e
  New-Venv $e
  if (-not (Works $p "torch, kokoro, pocket_tts, en_core_web_sm")) {
    if (-not (Works $p "torch")) {
      & $p -m pip install --disable-pip-version-check torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
      if ($LASTEXITCODE -ne 0) { Stop-Setup "PyTorch did not install. Check the internet connection and run Setup.bat again." }
    }
    & $p -m pip install --disable-pip-version-check -r (Join-Path $root "requirements-lite.txt")
    if ($LASTEXITCODE -ne 0) { Stop-Setup "The light engine packages did not install. Run Setup.bat again." }
    & $p -m pip install --disable-pip-version-check --no-deps $SPACY_EN
    if (-not (Works $p "kokoro, pocket_tts, en_core_web_sm")) { Stop-Setup "Kokoro or Pocket TTS did not install correctly. See the log." }
  } else { Write-Host "Packages already installed." }
  Say "Kokoro and Pocket TTS model files (about 0.6 GB, one time)"
  & $p (Join-Path $root "app\workers\fetch_lite.py") 2>&1 | Tee-Object -FilePath "$logDir\fetch_lite.txt"
  if ($LASTEXITCODE -ne 0) { Stop-Setup "The light engine model files did not all download. The reason is in models\fetch_lite.log. Run Setup.bat again to resume." }
}

# ---- 3. Chatterbox ----------------------------------------------------------
if (($want -contains "chatterbox") -and (-not $cbDone)) {
  Say "Chatterbox environment (envs\chatterbox)"
  $e = Join-Path $root "envs\chatterbox"; $p = PyOf $e
  New-Venv $e
  if (-not (Works $p "torch, torchaudio")) { Install-Torch $p }
  & $p -m pip install --disable-pip-version-check -r (Join-Path $root "requirements-chatterbox.txt")
  if ($LASTEXITCODE -ne 0) { Stop-Setup "Chatterbox packages did not install. Run Setup.bat again." }
  & $p -m pip install --disable-pip-version-check --no-deps chatterbox-tts==0.1.7 s3tokenizer==0.3.0
  if (-not (Works $p "chatterbox.tts, perth")) { Stop-Setup "Chatterbox did not install correctly. See the log." }
  Say "Chatterbox model files (3.2 GB, one time)"
  & $p (Join-Path $root "app\workers\fetch_chatterbox.py") 2>&1 | Tee-Object -FilePath "$logDir\fetch_chatterbox.txt"
  if ($LASTEXITCODE -ne 0) { Stop-Setup "The Chatterbox model files did not download. Run Setup.bat again to resume." }
}

# ---- 4. OpenVoice v2 + MeloTTS ---------------------------------------------
if (($want -contains "openvoice") -and (-not $ovDone)) {
  Say "OpenVoice environment (envs\openvoice)"
  $e = Join-Path $root "envs\openvoice"; $p = PyOf $e
  New-Venv $e
  if (-not (Works $p "torch, torchaudio, melo, openvoice, wavmark, nltk, transformers")) {
    if (-not (Works $p "torch, torchaudio")) { Install-Torch $p }
    & $p -m pip install --disable-pip-version-check -r (Join-Path $root "requirements-openvoice.txt")
    if ($LASTEXITCODE -ne 0) { Stop-Setup "OpenVoice packages did not install. Run Setup.bat again." }
    & $p -m pip install --disable-pip-version-check --no-deps g2p_en==2.1.0 $MELO_SRC $OV_SRC
    if (-not (Works $p "melo, openvoice")) { Stop-Setup "OpenVoice or MeloTTS did not install correctly. See the log." }
  } else { Write-Host "Packages already installed." }
  Say "OpenVoice and MeloTTS model files (0.8 GB, one time)"
  & $p (Join-Path $root "app\workers\fetch_openvoice.py") 2>&1 | Tee-Object -FilePath "$logDir\fetch_openvoice.txt"
  if ($LASTEXITCODE -ne 0) { Stop-Setup "The OpenVoice model files did not all download. The reason is in models\fetch_openvoice.log. Run Setup.bat again to resume." }
}

# ---- 5. Desktop shortcut ----------------------------------------------------
if (-not $NoShortcut) {
  try {
    $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Voice Studio.lnk"
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = Join-Path $root "runtime\Scripts\pythonw.exe"      # own window, no console
    $s.Arguments = "-m app.desktop"
    $s.WorkingDirectory = $root
    $s.IconLocation = (Join-Path $root "assets\voicestudio.ico")
    $s.WindowStyle = 1
    $s.Description = "Voice Studio: scripts to voiceover"
    $s.Save()
    Write-Host "`nDesktop shortcut ready: $lnk"
  } catch { Write-Host "Could not create the desktop shortcut (not a problem)." -ForegroundColor Yellow }
}

# ---- 6. Summary -------------------------------------------------------------
Say "Installed"
if (Test-Path (PyOf (Join-Path $root "envs\lite"))) { Write-Host "  lite (Kokoro, Pocket TTS) : installed, runs on the CPU" } else { Write-Host "  lite (Kokoro, Pocket TTS) : not installed (run Setup.bat again to add it)" }
foreach ($n in @("chatterbox", "openvoice")) {
  $p = PyOf (Join-Path $root "envs\$n")
  if (Test-Path $p) {
    & $p -c "import torch; ok=torch.cuda.is_available(); print('  $n : GPU ready' if ok else '  $n : CPU only (slow)', torch.cuda.get_device_name(0) if ok else '')"
  } else { Write-Host "  $n : not installed (run Setup.bat again to add it)" }
}
Write-Host "`nSetup finished. Start the app with the Voice Studio shortcut. Log: $logDir\setup.log" -ForegroundColor Green
Stop-Transcript | Out-Null
exit 0
