# Voice Studio

Turns a written script into voiceover audio on your own PC.

## Start
Double-click **Voice Studio** on the Desktop (or `Voice Studio.bat` in this folder).
The first start runs Setup; after that it opens in your browser in a few seconds.
YarnGPT takes about a minute to warm up; the pill at the top right turns green when it is ready.

To stop it, press **Quit** in the app or close the small black window.

## Where things go
- Finished audio: `C:\Temp\VoiceStudio_<date-time>\` (48 kHz mono WAV at -16 LUFS, MP3 if ticked).
  Regenerating a sentence saves a new file ending `_v2`, `_v3`; nothing is overwritten.
- Error log: `C:\Temp\VoiceStudio_logs\voicestudio.log`, plus `errors.log` in the output folder of a failed run.
- History and per-sentence clips: `data\` in this folder.
- Azure key and region: Windows Credential Manager (entry "VoiceStudio"). Never in a file.

## Safety rules built in
- The app listens on 127.0.0.1 only and refuses requests from other sites.
- Azure: one request per click, no retries, at least 3 seconds between requests, and a voice-safe check before sending. Batch work happens only on local YarnGPT.
- No analytics or telemetry. Network use is limited to Azure requests you start and the optional update check.

## Share it with a friend
Double-click `Make Share Zip.bat`. It builds a zip in `dist\` without your runtime, history, scripts or key.
Your friend unzips it anywhere and double-clicks `Voice Studio.bat`; it sets itself up
(Windows 10 or 11, internet for the first start, about 8 GB free; an NVIDIA GPU makes YarnGPT fast, without one it still works but slowly).

Moving this folder on your own PC: move it, then run `Setup.bat` once to refresh the Desktop shortcut.

## Updates
Settings > Updates. Enter the GitHub repository (`owner/repository`), then **Check now**.
Updates come from that repository's Releases. Only the app's code is replaced; the old files are
copied to `data\backups\` first. To publish an update: change `VERSION`, push, and create a Release
whose tag is the version number (for example `v0.2.0`).

## Add a new voice engine
1. Copy `app\engines\_template.py` to a new file in the same folder without the underscore, for example `piper_engine.py`.
2. Fill in the id, name, voices and the `synth()` function (local) or `synth_script()` (cloud). It returns audio as a numpy array plus its sample rate.
3. Restart Voice Studio. The engine appears in the Engine list. Joining, 48 kHz export, loudness, history and the sentence editor work without further changes.

Set `kind = "cloud"` for anything that sends text to a service, and the cloud safety rules apply to it automatically.
New Python packages for an engine go in `requirements.txt`; run `Setup.bat` afterwards.

## Icon
Four options are in `assets\options\`. To switch, copy the chosen `icon_option_X.ico` over `assets\voicestudio.ico`
and `icon_option_X.png` over `assets\icon.png`, then run `Setup.bat` to refresh the shortcut.
