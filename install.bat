@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "SRC_DIR=%~dp0"
if "%SRC_DIR:~-1%"=="\" set "SRC_DIR=%SRC_DIR:~0,-1%"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\Alethic"
set "QUIET=0"
if /i "%~1"=="/quiet" set "QUIET=1"
if /i "%~1"=="--quiet" set "QUIET=1"
if /i "%~1"=="-q" set "QUIET=1"

if exist "%SRC_DIR%\alethic.exe" goto install_standalone
if exist "%SRC_DIR%\alethic-agent.exe" goto install_standalone
if exist "%SRC_DIR%\pyproject.toml" goto install_source

echo Error: Run this installer from the Alethic repository root or the extracted alethic-agent folder.
if "%QUIET%"=="0" pause
exit /b 1

:install_standalone
echo Installing standalone Alethic harness into "%INSTALL_DIR%" ...
if /i not "%SRC_DIR%"=="%INSTALL_DIR%" (
  if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
  robocopy "%SRC_DIR%" "%INSTALL_DIR%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NC /NS >nul
  if errorlevel 8 goto copy_fail
)
set "EXE_BIN=%INSTALL_DIR%\alethic.exe"
if exist "%EXE_BIN%" (
  if exist "%INSTALL_DIR%\alethic.cmd" del "%INSTALL_DIR%\alethic.cmd" >nul 2>nul
) else (
  set "EXE_BIN=%INSTALL_DIR%\alethic-agent.exe"
  (
    echo @echo off
    echo set "PYTHONUTF8=1"
    echo "%%~dp0alethic-agent.exe" %%*
  ) > "%INSTALL_DIR%\alethic.cmd"
)
call :copy_uninstall
call :add_to_path "%INSTALL_DIR%"
if errorlevel 1 goto path_fail
echo Checking standalone executable...
"%EXE_BIN%" --selftest
if errorlevel 1 goto test_fail
goto done

:install_source
set "PY=%SRC_DIR%\.venv\Scripts\python.exe"
if exist "%PY%" goto have_venv

set "SYS_PY="
py -3.12 -c "import sys" >nul 2>nul && set "SYS_PY=py -3.12"
if not defined SYS_PY (
  py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>nul && set "SYS_PY=py -3"
)
if not defined SYS_PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>nul && set "SYS_PY=python"
)
if not defined SYS_PY (
  echo Python 3.12+ was not found on PATH.
  echo Install Python 3.12+ from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo or use the standalone alethic-agent-windows.zip bundle which needs no Python.
  if "%QUIET%"=="0" pause
  exit /b 1
)
echo Creating virtual environment in "%SRC_DIR%\.venv" ...
%SYS_PY% -m venv "%SRC_DIR%\.venv"
if errorlevel 1 goto pip_fail

:have_venv
echo Installing Alethic package and CLI commands...
"%PY%" -c "import setuptools, torch, numpy, pyarrow, sentencepiece, regex, huggingface_hub, yaml, pytest" >nul 2>nul
if errorlevel 1 (
  "%PY%" -m pip install --upgrade pip setuptools
  if errorlevel 1 goto pip_fail
  "%PY%" -m pip install -e "%SRC_DIR%"
  if errorlevel 1 goto pip_fail
) else (
  "%PY%" -m pip install --no-build-isolation --no-deps -e "%SRC_DIR%"
  if errorlevel 1 goto pip_fail
)

if not exist "%SRC_DIR%\.venv\Scripts\alethic.exe" goto pip_fail
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
(
  echo @echo off
  echo set "PYTHONUTF8=1"
  echo "%SRC_DIR%\.venv\Scripts\alethic.exe" %%*
) > "%INSTALL_DIR%\alethic.cmd"
if exist "%SRC_DIR%\.venv\Scripts\alethic-cli.exe" (
  (
    echo @echo off
    echo set "PYTHONUTF8=1"
    echo "%SRC_DIR%\.venv\Scripts\alethic-cli.exe" %%*
  ) > "%INSTALL_DIR%\alethic-cli.cmd"
)
call :copy_uninstall
call :add_to_path "%INSTALL_DIR%"
if errorlevel 1 goto path_fail
echo Checking installed command...
"%INSTALL_DIR%\alethic.cmd" --selftest
if errorlevel 1 goto test_fail
goto done

:copy_uninstall
if exist "%SRC_DIR%\uninstall.bat" (
  if /i not "%SRC_DIR%"=="%INSTALL_DIR%" copy /y "%SRC_DIR%\uninstall.bat" "%INSTALL_DIR%\uninstall.bat" >nul
)
exit /b 0

:add_to_path
set "TARGET_PATH=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$dir = $env:TARGET_PATH;" ^
  "$cur = [Environment]::GetEnvironmentVariable('Path', 'User');" ^
  "$parts = @(); if ($cur) { $parts = $cur -split ';' | Where-Object { $_ -ne '' } };" ^
  "$norm = { param($p) $p.TrimEnd('\').ToLowerInvariant() };" ^
  "$want = & $norm $dir;" ^
  "if (-not ($parts | Where-Object { (& $norm $_) -eq $want })) {" ^
  "  $newPath = ($parts + $dir) -join ';';" ^
  "  [Environment]::SetEnvironmentVariable('Path', $newPath, 'User');" ^
  "  try { Add-Type -Namespace Win32 -Name Env -MemberDefinition '[DllImport(\"user32.dll\", SetLastError=true, CharSet=CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);' -ErrorAction SilentlyContinue; $r = [UIntPtr]::Zero; [Win32.Env]::SendMessageTimeout([IntPtr]0xffff, 0x001A, [UIntPtr]::Zero, 'Environment', 2, 2000, [ref]$r) | Out-Null } catch {};" ^
  "  Write-Host ('Added to User PATH: ' + $dir)" ^
  "} else { Write-Host ('Already on User PATH: ' + $dir) }"
exit /b %ERRORLEVEL%

:done
echo.
echo Alethic harness installed cleanly!
echo Open a NEW Command Prompt (cmd) or PowerShell window anywhere and run:
echo   alethic
echo.
echo Useful flags:
echo   alethic --help          Show all options
echo   alethic --folder .      Start directly in the current directory
echo   alethic --auto          Skip command confirmation prompts
echo.
if "%QUIET%"=="0" pause
exit /b 0

:copy_fail
echo Failed copying standalone files to "%INSTALL_DIR%".
if "%QUIET%"=="0" pause
exit /b 1

:pip_fail
echo Failed installing Python dependencies or entry points.
if "%QUIET%"=="0" pause
exit /b 1

:path_fail
echo Failed updating User PATH for "%INSTALL_DIR%".
if "%QUIET%"=="0" pause
exit /b 1

:test_fail
echo Installation finished, but self-test reported a failure above.
if "%QUIET%"=="0" pause
exit /b 1
