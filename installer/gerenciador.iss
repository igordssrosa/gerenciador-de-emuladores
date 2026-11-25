; Instalador do Gerenciador de Emuladores (Inno Setup). Gerar: powershell -File build.ps1
; Instala só para o usuário atual (sem pedir senha de administrador).
#define AppName "Gerenciador de Emuladores"
#define AppVersion "1.0.1"   ; mantenha igual a app/version.py
#define AppExe "GerenciadorEmuladores.exe"

[Setup]
AppId={{7D6B6F0E-3C1A-4B0E-9A55-5C0DE0A1B2C3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=igordssrosa
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Instalar-GerenciadorEmuladores-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: checkedonce

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent

; Desinstalar remove só o programa. Jogos, emuladores e saves ficam em %LOCALAPPDATA%\GerenciadorEmuladores
; de propósito, para ninguém perder um save sem querer.
