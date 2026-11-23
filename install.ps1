<#
.SYNOPSIS
    Install the Alethic harness so `alethic` can be invoked from cmd or PowerShell anywhere.
.DESCRIPTION
    Supports:
      1. Local standalone bundle (when `alethic-agent.exe` is beside this script)
      2. Local source checkout (when `pyproject.toml` is beside this script)
      3. Direct remote install from GitHub into an isolated venv in %LOCALAPPDATA%\Programs\Alethic
#>
[CmdletBinding()]
param(
    [string]$RepoUrl = "https://github.com/bekhruzsuleyman/alethic-300m.git",
    [switch]$SystemPython
)

$ErrorActionPreference = "Stop"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\Alethic"
$Here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }

function Add-UserPath {
    param([string]$Dir)
    $cur = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if ($cur) { $parts = $cur -split ";" | Where-Object { $_ -ne "" } }
    $want = $Dir.TrimEnd("\").ToLowerInvariant()
    if (-not ($parts | Where-Object { $_.TrimEnd("\").ToLowerInvariant() -eq $want })) {
        $newPath = ($parts + $Dir) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        try {
            $sig = '[DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);'
            $type = Add-Type -Namespace Win32 -Name EnvNotify -MemberDefinition $sig -PassThru -ErrorAction SilentlyContinue
            if ($type) {
                $r = [UIntPtr]::Zero
                [void]$type::SendMessageTimeout([IntPtr]0xffff, 0x001A, [UIntPtr]::Zero, "Environment", 2, 2000, [ref]$r)
            }
        } catch {}
        Write-Host "Added to User PATH: $Dir"
    } else {
        Write-Host "Already on User PATH: $Dir"
    }
}

function Find-Python312 {
    foreach ($cand in @(@("py", @("-3.12")), @("py", @("-3")), @("python", @()), @("python3", @()))) {
        $cmd = $cand[0]
        $pre = $cand[1]
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            & $cmd @pre -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return @{ Cmd = $cmd; Args = $pre }
            }
        }
    }
    throw "Python 3.12+ is required (not found on PATH). Install from https://www.python.org/downloads/ or use alethic-agent-windows.zip."
}

$exePrimary = Join-Path $Here "alethic.exe"
$exeLegacy = Join-Path $Here "alethic-agent.exe"
$exeLocal = if (Test-Path $exePrimary) { $exePrimary } else { $exeLegacy }
$pyprojLocal = Join-Path $Here "pyproject.toml"

if (Test-Path $exeLocal) {
    Write-Host "Installing standalone Alethic harness to $InstallDir ..."
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    if ($Here.TrimEnd("\") -ne $InstallDir.TrimEnd("\")) {
        Copy-Item -Path (Join-Path $Here "*") -Destination $InstallDir -Recurse -Force
    }
    $installedExe = Join-Path $InstallDir "alethic.exe"
    $legacyCmd = Join-Path $InstallDir "alethic.cmd"
    if (Test-Path $installedExe) {
        if (Test-Path $legacyCmd) { Remove-Item $legacyCmd -Force }
    } else {
        $installedExe = Join-Path $InstallDir "alethic-agent.exe"
        Set-Content -Path $legacyCmd -Encoding Ascii -Value "@echo off`r`nset `"PYTHONUTF8=1`"`r`n`"%~dp0alethic-agent.exe`" %*`r`n"
    }
    Add-UserPath $InstallDir
    & $installedExe --selftest
    if ($LASTEXITCODE -ne 0) { throw "Selftest failed" }
}
elseif (Test-Path $pyprojLocal) {
    & (Join-Path $Here "install.bat") /quiet
    if ($LASTEXITCODE -ne 0) { throw "install.bat failed with exit code $LASTEXITCODE" }
}
else {
    $py = Find-Python312
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    if ($SystemPython) {
        Write-Host "Installing Alethic into current Python environment from $RepoUrl ..."
        & $py.Cmd @($py.Args) -m pip install --upgrade "git+$RepoUrl"
        if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    } else {
        $venvDir = Join-Path $InstallDir "venv"
        $venvPy = Join-Path $venvDir "Scripts\python.exe"
        if (-not (Test-Path $venvPy)) {
            Write-Host "Creating isolated environment in $venvDir ..."
            & $py.Cmd @($py.Args) -m venv $venvDir
            if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
        }
        Write-Host "Installing Alethic from $RepoUrl ..."
        & $venvPy -m pip install --upgrade pip setuptools
        if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
        & $venvPy -m pip install --upgrade "git+$RepoUrl"
        if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
        $alethicExe = Join-Path $venvDir "Scripts\alethic.exe"
        Set-Content -Path (Join-Path $InstallDir "alethic.cmd") -Encoding Ascii -Value "@echo off`r`nset `"PYTHONUTF8=1`"`r`n`"$alethicExe`" %*`r`n"
        $cliExe = Join-Path $venvDir "Scripts\alethic-cli.exe"
        if (Test-Path $cliExe) {
            Set-Content -Path (Join-Path $InstallDir "alethic-cli.cmd") -Encoding Ascii -Value "@echo off`r`nset `"PYTHONUTF8=1`"`r`n`"$cliExe`" %*`r`n"
        }
        Add-UserPath $InstallDir
        & (Join-Path $InstallDir "alethic.cmd") --selftest
        if ($LASTEXITCODE -ne 0) { throw "Selftest failed" }
    }
}

Write-Host ""
Write-Host "Done! Open a NEW cmd or PowerShell window anywhere and run: alethic"
