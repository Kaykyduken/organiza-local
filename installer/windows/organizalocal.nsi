; =============================================================================
; OrganizaLocal — instalador para Windows (NSIS)
;
; Gera um Setup.exe com assistente em português que:
;   * traz o Python 3.12 oficial embutido (não precisa instalar o Python antes);
;   * instala para o usuário atual, sem pedir administrador
;     (%LOCALAPPDATA%\Programs\OrganizaLocal);
;   * cria a pasta de dados %APPDATA%\OrganizaLocal;
;   * cria atalhos no Menu Iniciar e (opcional) na Área de Trabalho;
;   * coloca (opcional) o serviço na pasta Inicializar, para organizar de hora em hora;
;   * adiciona o comando "organizalocal" ao PATH do usuário;
;   * registra o desinstalador em "Configurações > Aplicativos".
;
; Compilar: installer/windows/build.sh  (usa makensis no Linux ou no Windows)
; =============================================================================
Target amd64-unicode                             ; instalador 64 bits (o Python embutido é x64)
SetCompressor /SOLID lzma

!ifndef VERSION
  !define VERSION "1.0.0"
!endif
!define APPNAME   "OrganizaLocal"
!define PUBLISHER "Equipe OrganizaLocal - FATEC Itapetininga"
!define URL       "https://organiza-local.vercel.app"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\OrganizaLocal"

Name "${APPNAME} ${VERSION}"
OutFile "..\..\dist\OrganizaLocal-Setup-${VERSION}.exe"
RequestExecutionLevel user                       ; não precisa de administrador
InstallDir "$LOCALAPPDATA\Programs\OrganizaLocal"
InstallDirRegKey HKCU "Software\OrganizaLocal" "InstallDir"
BrandingText "OrganizaLocal ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APPNAME}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "Instalador do OrganizaLocal"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "LegalCopyright" "${PUBLISHER}"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "StrFunc.nsh"
${StrStr}
${UnStrRep}

; ----------------------------------------------------------------- aparência
!define MUI_ICON   "..\assets\organizalocal.ico"
!define MUI_UNICON "..\assets\organizalocal.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP   "..\assets\wizard.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "..\assets\wizard.bmp"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Bem-vindo ao OrganizaLocal ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "O OrganizaLocal organiza automaticamente, de hora em hora, os arquivos da sua pasta Downloads seguindo as regras que você criar, e faz backups com várias versões.$\r$\n$\r$\nTudo acontece no seu computador: nenhum arquivo é enviado para a internet.$\r$\n$\r$\nO Python já vem incluído — não é preciso instalar mais nada.$\r$\n$\r$\nClique em Avançar para continuar."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "Instalação concluída"
!define MUI_FINISHPAGE_TEXT "O OrganizaLocal foi instalado.$\r$\n$\r$\nAs regras de exemplo vêm DESATIVADAS: revise-as na aba Regras antes de ativar. Use Simular para ver o que seria movido.$\r$\n$\r$\nSe o navegador pedir acesso à rede local, clique em Permitir."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o OrganizaLocal agora"
!define MUI_FINISHPAGE_RUN_FUNCTION AbrirApp
!define MUI_FINISHPAGE_LINK "Site do projeto: ${URL}"
!define MUI_FINISHPAGE_LINK_LOCATION "${URL}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

; ----------------------------------------------------------------- seções
Section "OrganizaLocal (obrigatório)" SecApp
  SectionIn RO

  ; Se já houver uma versão aberta, pede para ela encerrar (evita arquivos em uso).
  ${If} ${FileExists} "$INSTDIR\organizalocal.cmd"
    DetailPrint "Encerrando a versão em execução..."
    nsExec::Exec '"$INSTDIR\organizalocal.cmd" stop'
    Pop $0
  ${EndIf}

  ; Python embutido (oficial, python.org)
  SetOutPath "$INSTDIR\python"
  File /r "build\python\*.*"

  ; Código do programa e interface local
  RMDir /r "$INSTDIR\app\organizalocal"
  RMDir /r "$INSTDIR\app\web"
  SetOutPath "$INSTDIR\app"
  File /r "build\app\*.*"

  SetOutPath "$INSTDIR"
  File "..\assets\organizalocal.ico"

  ; Comando de terminal: "organizalocal status", "organizalocal codigo"...
  FileOpen $0 "$INSTDIR\organizalocal.cmd" w
  FileWrite $0 '@echo off$\r$\ncd /d "%~dp0app" && "%~dp0python\python.exe" -m organizalocal %*$\r$\n'
  FileClose $0

  ; Pasta de dados do usuário (o programa completa as subpastas na 1ª execução)
  CreateDirectory "$APPDATA\OrganizaLocal"

  ; Atalho no Menu Iniciar (a pasta de trabalho do atalho é a pasta atual: app)
  SetOutPath "$INSTDIR\app"
  CreateShortcut "$SMPROGRAMS\OrganizaLocal.lnk" "$INSTDIR\python\pythonw.exe" "-m organizalocal open" "$INSTDIR\organizalocal.ico" 0 SW_SHOWNORMAL "" "Abrir o OrganizaLocal"
  ; Remove o atalho de início automático criado pelo instalar.ps1 antigo
  Delete "$SMSTARTUP\OrganizaLocal (servico).lnk"

  ; Desinstalador + registro em "Aplicativos instalados"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  WriteRegStr HKCU "Software\OrganizaLocal" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "${UNINSTKEY}" "URLInfoAbout" "${URL}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\organizalocal.ico"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Desinstalar.exe"'
  WriteRegStr HKCU "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\Desinstalar.exe" /S'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "EstimatedSize" 30000

  ; Adiciona a pasta ao PATH do usuário (variável de ambiente), se ainda não estiver lá.
  ReadRegStr $1 HKCU "Environment" "Path"
  ${StrStr} $2 "$1" "$INSTDIR"
  ${If} $2 == ""
    ${If} $1 == ""
      WriteRegExpandStr HKCU "Environment" "Path" "$INSTDIR"
    ${Else}
      WriteRegExpandStr HKCU "Environment" "Path" "$1;$INSTDIR"
    ${EndIf}
    SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=3000
  ${EndIf}
SectionEnd

Section "Atalho na Área de Trabalho" SecDesktop
  SetOutPath "$INSTDIR\app"
  CreateShortcut "$DESKTOP\OrganizaLocal.lnk" "$INSTDIR\python\pythonw.exe" "-m organizalocal open" "$INSTDIR\organizalocal.ico" 0 SW_SHOWNORMAL "" "Abrir o OrganizaLocal"
SectionEnd

Section "Iniciar com o Windows (organiza de hora em hora)" SecStartup
  SetOutPath "$INSTDIR\app"
  CreateShortcut "$SMSTARTUP\OrganizaLocal (servico).lnk" "$INSTDIR\python\pythonw.exe" "-m organizalocal serve --no-browser" "$INSTDIR\organizalocal.ico" 0 SW_SHOWMINIMIZED "" "Serviço do OrganizaLocal"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp}     "Programa, Python embutido, atalho no Menu Iniciar e comando 'organizalocal'."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Cria o atalho OrganizaLocal na Área de Trabalho."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartup} "Inicia o serviço junto com o Windows, para que a organização automática e os backups rodem sozinhos."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; Abre o site já conectado ao programa (inicia o serviço em segundo plano).
Function AbrirApp
  SetOutPath "$INSTDIR\app"
  Exec '"$INSTDIR\python\pythonw.exe" -m organizalocal open'
FunctionEnd

; ----------------------------------------------------------------- desinstalação
Section "Uninstall"
  DetailPrint "Encerrando o serviço..."
  nsExec::Exec '"$INSTDIR\organizalocal.cmd" stop'
  Pop $0
  Sleep 1000

  Delete "$DESKTOP\OrganizaLocal.lnk"
  Delete "$SMPROGRAMS\OrganizaLocal.lnk"
  Delete "$SMSTARTUP\OrganizaLocal (servico).lnk"

  SetOutPath "$TEMP"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\organizalocal.cmd"
  Delete "$INSTDIR\organizalocal.ico"
  Delete "$INSTDIR\Desinstalar.exe"
  RMDir "$INSTDIR"

  ; Remove a pasta do PATH do usuário
  ReadRegStr $1 HKCU "Environment" "Path"
  ${UnStrRep} $1 "$1" ";$INSTDIR" ""
  ${UnStrRep} $1 "$1" "$INSTDIR;" ""
  ${UnStrRep} $1 "$1" "$INSTDIR" ""
  WriteRegExpandStr HKCU "Environment" "Path" "$1"
  SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=3000

  DeleteRegKey HKCU "${UNINSTKEY}"
  DeleteRegKey HKCU "Software\OrganizaLocal"

  ; Os dados (regras, histórico, backups) só são apagados se o usuário confirmar.
  MessageBox MB_YESNO|MB_ICONQUESTION "Apagar também suas regras, histórico e backups?$\r$\n$\r$\n$APPDATA\OrganizaLocal$\r$\n$\r$\nEscolha Não para mantê-los (útil se for reinstalar)." /SD IDNO IDNO manter
    RMDir /r "$APPDATA\OrganizaLocal"
  manter:
SectionEnd
