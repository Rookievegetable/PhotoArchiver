; PhotoArchiver Windows 安装器（ADR-031 方案 B，Phase P P-4）
; 编译：ISCC /DAppVersion=2.7.0 packaging\windows\installer.iss
; 离线模型包：ISCC /DAppVersion=2.7.0 /DPACK_MODELS=1 ...（需 models\ 就位）
; 产物：PhotoArchiver-{版本}-setup.exe（在线）/ PhotoArchiver-{版本}-offline-setup.exe（离线）

#define AppName "PhotoArchiver"
#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B57FC4C3-7F1C-4F98-8798-8BB252A4A03F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
; per-user（D-P2）：PrivilegesRequired=lowest 时 {autopf} 解析为
; %LOCALAPPDATA%\Programs\PhotoArchiver——免管理员，与数据目录锚定同域。
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=PhotoArchiver-{#AppVersion}-setup
#ifdef PACK_MODELS
OutputBaseFilename=PhotoArchiver-{#AppVersion}-offline-setup
#endif
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\PhotoArchiver.exe
; 升级（D-P5）：UsePreviousAppDir 覆盖安装，用户数据在 ADR-035 锚定的
; 用户目录（{app} 之外），卸载/升级天然保留。

; ChineseSimplified.isl 从 issrc 仓库 vendor 进来（choco 版 Inno 未随附）。
[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\build_dist\PhotoArchiver\*"; DestDir: "{app}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion
#ifdef PACK_MODELS
; 离线模型（构建期由 scripts/download_models.py 预置到 models\）——
; sha256 fail-closed 已在打包前完成校验；#ifdef 在编译期开关。
Source: "models\*"; DestDir: "{app}\models"; \
    Flags: recursesubdirs createallsubdirs ignoreversion
#endif

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\PhotoArchiver.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PhotoArchiver.exe"; \
    Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; \
    GroupDescription: "快捷方式："; Flags: unchecked

[Run]
Filename: "{app}\PhotoArchiver.exe"; Description: "启动 {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 用户数据（数据库/日志/偏好/模型）在 {app} 之外，卸载一律保留——
; 这里只清理 {app} 内的运行时产物（缩略图若被用户重定向到 {app} 下的场景）。
