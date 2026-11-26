# Voice Studio

Turns a written script into voiceover audio on your own PC, in your own voice.

## Start
Double-click **Voice Studio** on the Desktop (or `Voice Studio.bat` in this folder).
The first start runs Setup. To add or repair a voice engine later, run `Setup.bat`.

To stop it, press **Quit** in the app or close the small black window.

## Voice engines
| Engine | Where it runs | What it does |
|---|---|---|
| Kokoro | This PC, CPU only | 13 preset American and British voices. Small and fast: loads in seconds, about 1.3 GB of memory, no graphics card needed. |
| Pocket TTS | This PC, CPU only | 19 preset voices. About 1 GB of memory, no graphics card needed. |
| Chatterbox | This PC | Clones the voice in a voice profile. Controls: Expressiveness and Pacing. |
| OpenVoice v2 | This PC | Speaks with a chosen English accent (American, British, Australian, Default, Indian), then applies the tone of a voice profile. |
| Azure AI Speech | Cloud, your own key | Leah, Asilia, Sonia, Ryan, Harry, Harper, Emma HD, Andrew HD, Abeo and Ezinne. |

Only one local engine is loaded at a time (8 GB graphics memory). Selecting another engine unloads the
previous one; the pill at the top right shows "Loading engine..." and then turns green.

## Voice profiles
**Voice profiles** (top right) > **Create voice profile**: record the passage shown (about 20 seconds) or import
your own WAV or MP3. The app checks length (10 to 30 s), clipping and background noise before it lets you save,
and trims silence. Profiles are stored in `data\profiles\` on this PC only and are never put in a share zip.
Use them only for your own voice, or a voice you have written permission to use.

## A/B compare
Pick up to three engine and voice choices and press **Compare first two sentences** to hear them side by side.
Local engines load one after another. Only one cloud voice per comparison.

## Where things go
- Finished audio: `C:\Temp\VoiceStudio_<date-time>\` (48 kHz mono WAV at -16 LUFS, MP3 if ticked), with
  "AI-generated voice" in the file metadata. Regenerating a sentence saves a new file ending `_v2`, `_v3`.
- Logs: `C:\Temp\VoiceStudio_logs\` (`console.log`, `voicestudio.log`, one `worker_<engine>.log` per engine).
- History, per-sentence clips and voice profiles: `data\` in this folder.
- Azure key and region: Windows Credential Manager (entry "VoiceStudio"). Never in a file.

## Safety rules built in
- The app listens on 127.0.0.1 only and refuses requests from other sites.
- Azure: one request per click, no retries, at least 3 seconds between requests, and a voice-safe check before sending.
- No analytics or telemetry. The engines load their models from this folder with the network switched off.
  Network use is limited to Azure requests you start, the optional update check, and the
  **Download missing files** button (shown on an engine only when its model download did not finish).

## Installer
Every push to GitHub builds `VoiceStudio-Setup-<version>.exe` (see the repository's Actions tab) and tests the
app on a clean Windows machine. It also puts the installer on a draft Release named after `VERSION`; publish the
draft on GitHub (Releases, Edit, Publish) to make it downloadable and to switch on the in-app updater. The installer is small: it installs the app
for the current user, then downloads the engines ticked during installation. It is not code-signed, so Windows
shows an "unknown publisher" notice on first run (More info, then Run anyway). Uninstalling removes the app,
environments and models but keeps `data\` (voice profiles and history).

## Share it with a friend
Double-click `Make Share Zip.bat`. The zip leaves out the Python environments, your voice profiles, history,
scripts and key. Your friend unzips it anywhere and double-clicks `Voice Studio.bat`; Setup asks which engines to
install (Windows 10 or 11, internet for setup, about 20 GB free for both engines; an NVIDIA GPU with 8 GB makes
the engines fast, without one they still work but slowly). Your friend records their own voice profile.

Moving this folder on your own PC: move it, then run `Setup.bat` once to refresh the Desktop shortcut.

## Updates
Settings > Updates. Updates come from the GitHub repository's Releases. Only the app's code is replaced; the old
files are copied to `data\backups\` first. After an update, run `Setup.bat` once. To publish an update: change
`VERSION`, push, wait for the build, then publish the draft Release it creates.

## Add a new voice engine
1. Copy `app\engines\_template.py` to a new file in the same folder without the underscore.
2. Fill in the id, name, voices and `synth()`. For an engine whose packages clash with the others, subclass
   `WorkerEngine` instead and add a worker file under `app\workers\` plus its own environment under `envs\`
   (Chatterbox is the example to copy). Cloud engines set `kind = "cloud"` and write `synth_script()`.
3. Restart Voice Studio. The engine appears in the Engine list. Joining, export, history, the sentence editor
   and A/B compare work without further changes.
4. Add its licence to `LICENSES.md` before sharing the app.

## Licences
See `LICENSES.md`.

## Icon
Four options are in `assets\options\`. To switch, copy the chosen `icon_option_X.ico` over `assets\voicestudio.ico`
and `icon_option_X.png` over `assets\icon.png`, then run `Setup.bat` to refresh the shortcut.
