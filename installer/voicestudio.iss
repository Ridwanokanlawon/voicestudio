; Voice Studio installer (Inno Setup 6). Built by .github/workflows/build.yml:
;   ISCC.exe /DAppVersion=0.3.0 installer\voicestudio.iss
; The installer carries only the app itself (a few MB). It prepares the small
; app environment; voice engines are downloaded from the app's Engines screen.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C2B6C1E-5E1D-4B8E-9B5A-6F3D2A7E41C9}
AppName=Voice Studio
AppVersion={#AppVersion}
AppVerName=Voice Studio {#AppVersion}
DefaultDirName={localappdata}\VoiceStudio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=VoiceStudio-Setup-{#AppVersion}
SetupIconFile=..\assets\voicestudio.ico
UninstallDisplayIcon={app}\assets\voicestudio.ico
UninstallDisplayName=Voice Studio
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSES.md
UsePreviousAppDir=yes
CloseApplications=no

[Messages]
WelcomeLabel2=This installs Voice Studio [ver] in your user account.%n%nThe app itself is small. You choose the voice engines inside the app afterwards; each is a one-time download (2 to 8 GB, needs internet).
FinishedLabel=Voice Studio is installed. Start it from the Start menu or the Desktop shortcut.

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\app\*"; DestDir: "{app}\app"; Excludes: "__pycache__\*,*.pyc,test_*.py"; Flags: recursesubdirs ignoreversion
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: recursesubdirs ignoreversion
Source: "..\Voice Studio.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Voice Studio (browser mode).bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Setup.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\setup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Make Share Zip.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\make_share_zip.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-lite.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-chatterbox.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-openvoice.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\update.json"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{autoprograms}\Voice Studio"; Filename: "{app}\runtime\Scripts\pythonw.exe"; Parameters: "-m app.desktop"; WorkingDir: "{app}"; IconFilename: "{app}\assets\voicestudio.ico"
Name: "{autodesktop}\Voice Studio"; Filename: "{app}\runtime\Scripts\pythonw.exe"; Parameters: "-m app.desktop"; WorkingDir: "{app}"; IconFilename: "{app}\assets\voicestudio.ico"; Tasks: desktopicon

[Run]
; prepares the small app environment (no engines). Engines are chosen inside the app afterwards.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup.ps1"" -Yes -NoShortcut -Engines none"; WorkingDir: "{app}"; StatusMsg: "Preparing Voice Studio (downloads about 150 MB, a few minutes)..."; Flags: waituntilterminated runhidden
Filename: "{app}\runtime\Scripts\pythonw.exe"; Parameters: "-m app.desktop"; WorkingDir: "{app}"; Description: "Start Voice Studio now"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; things the app downloaded or generated. data\ (voice profiles, history) is kept on purpose.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\envs"
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\dist"
