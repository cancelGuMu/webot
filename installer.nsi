; webot Windows Installer
; Build: "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
; Output: dist/webot-setup.exe

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"

; ── Product Info ──────────────────────────────────────────────────────
!define PRODUCT_NAME "webot"
!define PRODUCT_DESC "微信 AI 群聊助手"
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "cancelGuMu"
!define PRODUCT_URL "https://github.com/cancelGuMu/webot"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\webot-setup.exe"
InstallDir "$LOCALAPPDATA\${PRODUCT_NAME}"
RequestExecutionLevel user
ShowInstDetails show
SetCompressor /SOLID lzma

; ── Interface Settings ─────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON "image\logo_assets\logo.ico"
!define MUI_UNICON "image\logo_assets\logo.ico"

; ── Pages ──────────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; ── Install Section ────────────────────────────────────────────────────
Section "Install"
  SetOutPath "$INSTDIR"

  ; Main executable
  File "dist\webot.exe"
  File ".env.example"

  ; Create data directory placeholder
  CreateDirectory "$INSTDIR\data"

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" \
    "$INSTDIR\webot.exe" "" "$INSTDIR\webot.exe" 0

  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\卸载 webot.lnk" \
    "$INSTDIR\uninstall.exe"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" \
    "$INSTDIR\webot.exe" "" "$INSTDIR\webot.exe" 0

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Registry for Add/Remove Programs
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "DisplayName" "${PRODUCT_NAME} - ${PRODUCT_DESC}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "DisplayIcon" "$INSTDIR\webot.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "URLInfoAbout" "${PRODUCT_URL}"

  ; Size estimation
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "EstimatedSize" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}" \
    "NoRepair" 1
SectionEnd

; ── Uninstall Section ──────────────────────────────────────────────────
Section "Uninstall"
  ; Remove installed files
  Delete "$INSTDIR\webot.exe"
  Delete "$INSTDIR\.env.example"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r "$INSTDIR\data"

  ; Remove shortcuts
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\卸载 webot.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

  ; Remove registry
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

  ; Remove install dir if empty (user data may remain)
  RMDir "$INSTDIR"
SectionEnd

; ── Version Info ───────────────────────────────────────────────────────
VIProductVersion "${PRODUCT_VERSION}.0"
VIAddVersionKey "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "FileDescription" "${PRODUCT_DESC}"
VIAddVersionKey "LegalCopyright" "MIT License"
VIAddVersionKey "CompanyName" "${PRODUCT_PUBLISHER}"
