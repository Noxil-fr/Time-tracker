; ── Time Tracker — Script Inno Setup ────────────────────────────────────────
; Génère un installeur Windows (droits admin requis, C:\Program Files\TimeTracker).
; Prérequis : Inno Setup 6  →  https://jrsoftware.org/isinfo.php

#define MyAppName      "Time Tracker"
#define MyAppVersion   "1.2"
#define MyAppPublisher "Antoine"
#define MyAppExeName   "TimeTracker.exe"
#define MyAppId        "FC2BFA72-5F24-4C4C-9F61-5933CB450A5E"

; ── Configuration générale ───────────────────────────────────────────────────
[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL=https://github.com/

; Installation dans C:\Program Files\TimeTracker — droits admin
DefaultDirName={commonpf}\TimeTracker
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin

; Icône & apparence
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

; Sortie
OutputDir=Output
OutputBaseFilename=TimeTracker_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes

; Ferme l'app si elle tourne avant d'installer (mise à jour silencieuse)
CloseApplications=yes

; Langue
[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

; ── Tâches optionnelles ──────────────────────────────────────────────────────
[Tasks]
Name: "desktopicon"; \
  Description: "Créer un raccourci sur le Bureau"; \
  GroupDescription: "Raccourcis :"; \
  Flags: unchecked

; ── Dossiers ─────────────────────────────────────────────────────────────────
[Dirs]
; data\ : droits en écriture pour l'utilisateur courant (app tourne sans admin)
Name: "{app}\data"; Permissions: users-modify

; ── Fichiers à installer ─────────────────────────────────────────────────────
[Files]
; Exécutable principal
Source: "..\dist\TimeTracker\{#MyAppExeName}"; \
  DestDir: "{app}"; Flags: ignoreversion

; Dépendances (_internal) — exclut les données personnelles
Source: "..\dist\TimeTracker\_internal\*"; \
  DestDir: "{app}\_internal"; \
  Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "data\games.json,data\auth.json,data\settings.json"

; Dossier data\ — games.json initial (uniquement si absent)
Source: "..\dist\TimeTracker\_internal\data\games.json"; \
  DestDir: "{app}\data"; \
  Flags: onlyifdoesntexist

; ── Icônes / raccourcis ───────────────────────────────────────────────────────
[Icons]
Name: "{group}\{#MyAppName}"; \
  Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\{#MyAppExeName}"

Name: "{group}\Désinstaller {#MyAppName}"; \
  Filename: "{uninstallexe}"

Name: "{autodesktop}\{#MyAppName}"; \
  Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon

; ── Démarrage automatique (registre) ─────────────────────────────────────────
[Registry]
Root: HKCU; \
  Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; \
  ValueName: "{#MyAppName}"; \
  ValueData: """{app}\{#MyAppExeName}"" --minimized"; \
  Flags: uninsdeletevalue

; ── Lancement après installation ─────────────────────────────────────────────
[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "Lancer {#MyAppName}"; \
  Flags: nowait postinstall

; ── Message de désinstallation ────────────────────────────────────────────────
[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    MsgBox(
      'Time Tracker a été désinstallé.' + #13#10 +
      'Vos données (jeux, historique) sont conservées dans :' + #13#10 +
      ExpandConstant('{app}\data'),
      mbInformation, MB_OK
    );
end;
