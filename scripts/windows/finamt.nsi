Unicode true
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "x64.nsh"
!include "FileFunc.nsh"
!include "Sections.nsh"

!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\finamt"
Name "finamt"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\finamt"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
LicenseData "${LICENSE_FILE}"
Page license
Page components
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles
LoadLanguageFile "${NSISDIR}/Contrib/Language files/German.nlf"

Var ReleaseDir

Section "finamt (erforderlich)"
  SectionIn RO
  StrCpy $ReleaseDir "$INSTDIR\releases\${BUNDLE_ID}"
  SetOutPath "$ReleaseDir"
  File /r "${PAYLOAD_PATTERN}"

  DetailPrint "Python und die festgelegten Abhängigkeiten werden eingerichtet. Dazu ist Internetzugang nötig."
  System::Call 'Kernel32::SetEnvironmentVariableW(w "UV_PYTHON_INSTALL_DIR", w "$INSTDIR\python") i'
  System::Call 'Kernel32::SetEnvironmentVariableW(w "UV_PROJECT_ENVIRONMENT", w "$ReleaseDir\.venv") i'
  System::Call 'Kernel32::SetEnvironmentVariableW(w "UV_CACHE_DIR", w "$INSTDIR\setup-cache") i'
  nsExec::ExecToLog '"$ReleaseDir\uv.exe" --no-config --color never --no-progress sync --locked --no-dev --no-editable --extra windows-desktop --python 3.10 --managed-python --link-mode copy'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP|MB_OK "Die Einrichtung der Laufzeit ist fehlgeschlagen (Status $0). Prüfe die Installationsdetails und versuche es erneut." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}

  IfFileExists "$ReleaseDir\.venv\Scripts\pythonw.exe" +3
    SetErrorLevel 1
    Abort "Die lokale Python-Laufzeit fehlt."

  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortCut "$SMPROGRAMS\finamt.lnk" "$ReleaseDir\.venv\Scripts\pythonw.exe" '"$ReleaseDir\launch.pyw"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "finamt"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${FINAMT_VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "ReleaseDirectory" "$ReleaseDir"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section /o "Lokales KI-Modell herunterladen (ca. 2,5 GB)" LocalAI
  AddSize 2600000
  DetailPrint "Das lokale Modell Qwen3-4B-Instruct und seine CPU-Laufzeit werden heruntergeladen und geprüft."
  nsExec::ExecToLog '"$ReleaseDir\.venv\Scripts\python.exe" -m finamt.agents.model_assets "$INSTDIR\modell"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION|MB_OK "finamt wurde installiert. Das optionale KI-Modell ist noch nicht verfügbar. Siehe Installationsdetails. Du kannst die Modellauswahl beim erneuten Setup wieder aktivieren." /SD IDOK
  ${EndIf}
SectionEnd

Function .onInit
  SetShellVarContext current
  ${IfNot} ${IsNativeAMD64}
  ${OrIfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP|MB_OK "Diese Ausgabe benötigt Windows für x64." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/WITHAI" $1
  ${IfNot} ${Errors}
    !insertmacro SelectSection ${LocalAI}
  ${EndIf}
  ClearErrors
FunctionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$SMPROGRAMS\finamt.lnk"
  RMDir /r "$INSTDIR\releases"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\setup-cache"
  RMDir /r "$INSTDIR\modell"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
SectionEnd
