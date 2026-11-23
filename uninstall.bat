@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "HERE_DIR=%~dp0"
if "%HERE_DIR:~-1%"=="\" set "HERE_DIR=%HERE_DIR:~0,-1%"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\Alethic"
if exist "%HERE_DIR%\alethic.exe" set "INSTALL_DIR=%HERE_DIR%"
if exist "%HERE_DIR%\alethic-agent.exe" set "INSTALL_DIR=%HERE_DIR%"

set "DATA_DIR=%LOCALAPPDATA%\alethic-agent"
set "PURGE=0"
if /i "%~1"=="--purge" set "PURGE=1"
if /i "%~1"=="/purge" set "PURGE=1"

echo Removing "%INSTALL_DIR%" from User PATH...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$dir = $env:INSTALL_DIR;" ^
  "$cur = [Environment]::GetEnvironmentVariable('Path', 'User');" ^
  "if ($cur) {" ^
  "  $want = $dir.TrimEnd('\').ToLowerInvariant();" ^
  "  $kept = $cur -split ';' | Where-Object { $_ -ne '' -and $_.TrimEnd('\').ToLowerInvariant() -ne $want };" ^
  "  [Environment]::SetEnvironmentVariable('Path', ($kept -join ';'), 'User');" ^
  "  try { Add-Type -Namespace Win32 -Name Env -MemberDefinition '[DllImport(\"user32.dll\", SetLastError=true, CharSet=CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);' -ErrorAction SilentlyContinue; $r = [UIntPtr]::Zero; [Win32.Env]::SendMessageTimeout([IntPtr]0xffff, 0x001A, [UIntPtr]::Zero, 'Environment', 2, 2000, [ref]$r) | Out-Null } catch {};" ^
  "}"

reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Alethic" /f >nul 2>nul

if exist "%INSTALL_DIR%" (
  echo Removing "%INSTALL_DIR%" ...
  if /i "%CD%"=="%INSTALL_DIR%" cd /d "%TEMP%"
  rmdir /s /q "%INSTALL_DIR%" 2>nul
)

if "%PURGE%"=="1" (
  if exist "%DATA_DIR%" (
    echo Removing downloaded weights and user data in "%DATA_DIR%" ...
    rmdir /s /q "%DATA_DIR%" 2>nul
  )
) else (
  if exist "%DATA_DIR%" (
    echo Note: cached weights/work in "%DATA_DIR%" were kept ^(pass --purge to delete them too^).
  )
)

echo Uninstalled Alethic CLI from User PATH.
exit /b 0
