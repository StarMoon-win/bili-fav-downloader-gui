; B站收藏夹下载器 —— Inno Setup 脚本
; 由 build.py 调用：ISCC /DMyAppVersion=x.y.z /DSourceDir=... /DOutputDir=... setup.iss
; 手动编译：ISCC.exe setup.iss

#define MyAppName "B站收藏夹下载器"
#define MyAppExeName "BiliFavDownloader.exe"
#define MyAppPublisher "StarMoon"
#define MyAppURL "https://github.com/StarMoon-win/bili-fav-downloader"

#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif
#ifndef MySourceDir
  #define MySourceDir "..\build\onedir\BiliFavDownloader"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
; AppId 一旦发布就不能改，否则新版本会被当成另一个软件（不能覆盖安装）
AppId={{9A7E3C41-5B62-4F8D-A1C3-7E2D4B6F8A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}

; 默认装到「当前用户」的 Programs 目录，不需要管理员权限；
; 用户可以在向导里改成任意路径，也可以选择「为所有用户安装」（需要管理员）
DefaultDirName={autopf}\BiliFavDownloader
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir={#OutputDir}
OutputBaseFilename=BiliFavDownloader-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
MinVersion=10.0

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 只清理安装目录里的运行残留；登录态在 %APPDATA%，由下面的代码询问后再删
Type: files; Name: "{app}\*.log"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\BiliFavDownloader');
    if DirExists(DataDir) then
    begin
      { 静默卸载不弹窗，也不删数据 —— 免得脚本化卸载把登录态误删 }
      if UninstallSilent then
        Exit;
      if MsgBox('是否同时删除登录信息（cookies）和配置？' + #13#10#13#10 +
                DataDir + #13#10#13#10 +
                '选择「否」会保留，下次安装还能直接用。',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
