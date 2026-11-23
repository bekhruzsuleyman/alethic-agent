@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONPATH=src
echo Building standalone Alethic harness (no Python/PyTorch needed by users)...
set "SAVED_WEIGHTS="
if exist "dist\alethic-agent\model-sft3c.pt" (
  if not exist "runs_sft3c\model.pt" (
    set "SAVED_WEIGHTS=%TEMP%\alethic-saved-model-sft3c.pt"
    move /y "dist\alethic-agent\model-sft3c.pt" "%TEMP%\alethic-saved-model-sft3c.pt" >nul
  )
)
.venv\Scripts\python.exe -m pip install --quiet pyinstaller
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean alethic-agent.spec
if errorlevel 1 goto fail
rem PyInstaller drops a DLL that two packages share by name (sentencepiece needs its own copy), so copy every *.libs folder in
for /d %%D in (.venv\Lib\site-packages\*.libs) do (
  if not exist "dist\alethic-agent\_internal\%%~nxD" mkdir "dist\alethic-agent\_internal\%%~nxD"
  xcopy /y /q "%%D\*" "dist\alethic-agent\_internal\%%~nxD\" >nul
)
rem Other computers may not have the Microsoft Visual C++ runtime, so ship the DLLs next to torch (Microsoft allows this)
for %%F in (vcruntime140.dll vcruntime140_1.dll vcruntime140_threads.dll msvcp140.dll msvcp140_1.dll msvcp140_2.dll concrt140.dll) do (
  if exist "%SystemRoot%\System32\%%F" (
    copy /y "%SystemRoot%\System32\%%F" "dist\alethic-agent\_internal\" >nul
    copy /y "%SystemRoot%\System32\%%F" "dist\alethic-agent\_internal\torch\lib\" >nul 2>nul
  )
)
echo Checking that every library and embedded Python load...
dist\alethic-agent\alethic.exe --selftest
if errorlevel 1 goto fail
dist\alethic-agent\alethic.exe --run-python -c "import csv, json, unittest, sqlite3, statistics; print('embedded python ok')"
if errorlevel 1 goto fail
copy /y install.bat dist\alethic-agent\install.bat >nul
copy /y uninstall.bat dist\alethic-agent\uninstall.bat >nul
echo Making alethic-agent-windows.zip (harness bundle; setup installs weights too)...
if exist alethic-agent-windows.zip del alethic-agent-windows.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\alethic-agent' -DestinationPath 'alethic-agent-windows.zip' -CompressionLevel Fastest"
if errorlevel 1 goto fail
set "CSC=%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if exist "%CSC%" (
  echo Building GUI single-file installer dist\alethic-agent-setup.exe ...
  if exist dist\alethic-setup.exe del dist\alethic-setup.exe
  "%CSC%" /nologo /target:winexe /optimize+ /platform:x64 ^
    /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll ^
    /resource:alethic-agent-windows.zip,bundle.zip /out:dist\alethic-agent-setup.exe deploy\setup_installer.cs
  if errorlevel 1 goto fail
)
if defined SAVED_WEIGHTS (
  if exist "%SAVED_WEIGHTS%" move /y "%SAVED_WEIGHTS%" "dist\alethic-agent\model-sft3c.pt" >nul
) else if exist runs_sft3c\model.pt (
  echo Copying the SFT-3c weights next to the exe, so it does not download them again...
  copy /y runs_sft3c\model.pt dist\alethic-agent\model-sft3c.pt >nul
)
echo.
echo Done!
echo   Standalone setup installer (harness + model + PATH): dist\alethic-agent-setup.exe
echo   Portable zip (unzip + run install.bat):              alethic-agent-windows.zip
if "%~1"=="/quiet" exit /b 0
pause
exit /b 0
:fail
if defined SAVED_WEIGHTS (
  if exist "%SAVED_WEIGHTS%" move /y "%SAVED_WEIGHTS%" "dist\alethic-agent\model-sft3c.pt" >nul 2>nul
)
echo.
echo The build failed. Send me the text above.
if "%~1"=="/quiet" exit /b 1
pause
exit /b 1
