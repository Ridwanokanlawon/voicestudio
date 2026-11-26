# Voice Studio

Turns a written script into voiceover audio on your own PC, in your own voice.

## Start
Open **Voice Studio** from the Desktop or Start menu. It opens in its own window; closing the window (or pressing
**Quit**) stops it. Nothing runs in the background afterwards.

To add voice engines, press **Engines** at the top right, tick the ones you want and press **Download and install**.
Progress is shown in the app. Each engine is a one-time download.

If the window ever fails to open, `Voice Studio (browser mode).bat` runs the same app in a browser tab with a
console window, which is useful for troubleshooting. `Setup.bat` does the same job as the Engines screen from a
console.

## Voice engines
| Engine | Where it runs | What it does |
|---|---|---|
| Kokoro | This PC, CPU only | 13 preset American and British voices. Small and fast: loads in seconds, about 1.3 GB of memory, no graphics card needed. |
| Qwen3-TTS | This PC, NVIDIA graphics card with 8 GB | Large model (1.7B) with nine preset voices; Ryan and Aiden are the native English ones. A **Delivery** setting (clear narrator, warm, serious, lively). About 9 GB on disk and about 7 GB of free memory to load. Without a graphics card it works but is very slow. |
| Chatterbox | This PC | Clones the voice in a voice profile. Controls: Expressiveness and Pacing. |
| OpenVoice v2 | This PC | Speaks with a chosen English accent (American, British, Australian, Default, Indian), then applies the tone of a voice profile. |
| Azure AI Speech | Cloud, your own key | Leah, Asilia, Sonia, Ryan, Harry, Harper, Emma HD, Andrew HD, Abeo and Ezinne. |

Only one local engine is loaded at a time (8 GB graphics memory). Selecting another engine unloads the
previous one; the pill at the top right shows "Loading engine..." and then turns green.

## Presets, target length and the pronunciation list
- **Presets** (top of the Voice card): **Save preset** keeps the engine, voice, speaking rate, pause lengths, MP3
  choice, engine controls and target length under a name, for example "WCGW - Harry". Picking a preset sets
  everything at once, and the last preset used is selected again the next time the app starts.
- **Estimated length**: under the script, the app shows how long the take should be with the chosen voice. The
  estimate starts from a typical speaking speed and switches to each voice's measured speed after its first full
  take. Fill in **Target length** (for example `45` or `40-50`) and the app suggests the speaking rate that fits,
  with a button to set it. Harry, Harper, Emma HD and Andrew HD ignore the speaking rate; for those the app says
  so and tells you roughly how many words to cut or add instead.
- **Settings > Pronunciations**: a table of "written as" and "say as" (MFA = M F A). It is applied for every engine
  just before speaking. The script, the captions and the voice-safe check keep the written form, and the sentence
  editor shows "Said as: ..." under each sentence that was changed.
- **Settings > Voices**: untick a voice to hide it. A hidden voice cannot be used by the app or the command line.
  The choice is stored in `data\` on this PC, so a share zip shows every voice.

## Episodes, captions and the video folder
- **Captions**: every take also saves `<name>.srt` next to the WAV, one caption per sentence. Timings come from each
  sentence's own clip. Azure voices that report word timings also get `<name>.words.srt`, one caption per word. An
  Azure voice that comes back as one piece without timings has its sentence times placed on the pauses in the
  audio; the app says so, and those are worth a check.
- **Episode** box (under the script): filled in automatically from a `## EP22 | Title` file. With an episode code
  and a video folder set under **Settings > Folders**, the finished WAV is also copied there as
  `EP22_audio.wav`. A file that is already there is never replaced without asking: the app offers to keep both
  (`EP22_audio_v2.wav`), replace it, or leave the folder alone.
- **Generate all episodes**: shown for a file with several episodes when an engine that runs on this PC is
  selected. Episodes are made one after another; copies never replace an existing file (they are saved as `_v2`).
  Cloud voices stay one episode per click.

## Command line
`voicestudio-cli.bat` talks to the app that is already running (127.0.0.1 only) and prints JSON:

    voicestudio-cli status
    voicestudio-cli presets
    voicestudio-cli generate --preset "WCGW - Harry" --in script.txt --episode EP22
    voicestudio-cli generate --preset "WCGW - George" --in episodes.md --all-episodes

    voicestudio-cli hide-voices azure sonia leah
    voicestudio-cli set-folder "C:\Videos\Renders\_chunks"
    voicestudio-cli save-preset --name "WCGW - Harry" --engine azure --voice harry --target 40-50

`generate` prints the WAV, MP3 and caption paths, the duration, the estimate and where the copy went. The app does
the work, so its safety rules apply unchanged: one cloud request per run, no retries, 3 seconds between cloud
requests, voice-safe check first. If that check has warnings for a cloud voice, nothing is sent unless you add
`--accept-warnings`. `--all-episodes` works with local engines only. `--if-exists` chooses what happens when the
episode's file is already in the video folder: `version` (default, keep both), `skip` or `overwrite`.
Exit codes: 0 done, 1 failed, 2 app not running, 3 stopped by the voice-safe check.

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
- History, per-sentence clips, voice profiles, presets and settings: the app's `data\` folder. If Voice Studio is
  installed on this PC (`%LOCALAPPDATA%\VoiceStudio`), every copy of the app, a source folder included, uses the
  installed copy's `data\`, so there is one set of profiles, history and presets. Settings > Folders shows which
  copy is running and where its data is.
- Captions: `<name>.srt` next to each WAV.
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
for the current user (`%LOCALAPPDATA%\VoiceStudio`); the voice engines are then chosen and downloaded inside the app. It is not code-signed, so Windows
shows an "unknown publisher" notice on first run (More info, then Run anyway). Uninstalling removes the app,
environments and models but keeps `data\` (voice profiles and history).

## Share it with a friend
Double-click `Make Share Zip.bat`. The zip leaves out the Python environments, your voice profiles, history,
scripts and key. Your friend unzips it anywhere and double-clicks `Voice Studio.bat`; Setup asks which engines to
install (Windows 10 or 11, internet for setup, about 30 GB free for all four local engines; an NVIDIA GPU with 8 GB makes
the engines fast, without one they still work but slowly). Your friend records their own voice profile.

Moving this folder on your own PC: move it, then run `Setup.bat` once to refresh the Desktop shortcut.

## Updates
Settings > Updates. Updates come from the GitHub repository's Releases. Only the app's code is replaced; the old
files are copied to `data\backups\` first. With **Install updates automatically at start-up** ticked (the default), the app
checks when it starts, installs a newer release by itself and restarts; it never does this in the middle of a
session. Versions up to 0.5.0 could not download updates (GitHub rejected the request), so those need the installer
run once to reach 0.6.0 or later. Restart Voice Studio afterwards (run `Setup.bat` once only if the app
says packages changed). Starting a new version while an older copy is still running stops the older one first; if
the older one is in the middle of a generation it is left alone and you are told. To publish an update: change
`VERSION`, push, wait for the build, then publish the draft Release it creates.

## What changed in 0.6.0
- Qwen3-TTS engine (Engines screen, about 9 GB).
- Automatic updates at start-up, with a switch under Settings > General > Updates, and the app restarts itself.
- Fixed: in-app updates failed with "GitHub answered with error 415" in every earlier version.

## What changed in 0.5.0
- Pocket TTS removed (engine, downloads, setup, licences). The Engines screen offers to delete what it left on disk.
- Settings > Voices (hide voices), Settings > Pronunciations, Settings > Folders (video folder).
- Estimated length before generating, target length with a suggested speaking rate.
- Presets, with the last one remembered.
- Caption files (.srt) next to every WAV.
- Episode box and copy to the video folder, never replacing a file without asking.
- `voicestudio-cli` command line tool.
- Generate all episodes for engines that run on this PC.
- Fixes: a new version now replaces an older running copy instead of joining it; the "Cannot reach the server"
  line clears itself; one data folder for every copy on a PC; a "Free up memory" hint that names the biggest
  apps when an engine cannot load.

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
