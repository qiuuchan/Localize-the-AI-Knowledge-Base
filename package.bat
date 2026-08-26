@echo off
REM ====================================================================
REM KB-AI package.bat -- builds KB-AI-M1-M3.zip
REM Tools: PowerShell Compress-Archive (Win 10+ built-in)
REM Run: double-click package.bat
REM Output: KB-AI-M1-M3.zip alongside the KB-AI source folder
REM
REM Layout tolerance (auto-detects both):
REM   workspace-root\package.bat         (preferred)
REM   workspace-root\KB-AI\package.bat   (zip goes to workspace-root\)
REM ====================================================================

chcp 65001 >nul
setlocal EnableExtensions

REM Resolve my own directory (the directory of THIS .bat file)
set "MY_DIR=%~dp0"
if "%MY_DIR:~-1%"=="\" set "MY_DIR=%MY_DIR:~0,-1%"

REM Try to locate KB-AI\:
REM   Case A: MY_DIR\KB-AI    (package.bat at workspace root)
REM   Case B: MY_DIR = KB-AI  (package.bat inside KB-AI\, source dir = parent)
if exist "%MY_DIR%\KB-AI\" goto KB_AI_CASE_A
if exist "%MY_DIR%\start.bat" goto KB_AI_CASE_B
echo [ERROR] Cannot locate KB-AI folder
echo         Current script dir: %MY_DIR%
echo         Tried: "%MY_DIR%\KB-AI\" or "%MY_DIR%\start.bat"
exit /b 1

:KB_AI_CASE_A
set "KBAI_DIR=%MY_DIR%\KB-AI"
set "OUT_DIR=%MY_DIR%"
goto KB_AI_FOUND

:KB_AI_CASE_B
set "KBAI_DIR=%MY_DIR%"
REM get parent of MY_DIR as OUT_DIR
for %%P in ("%MY_DIR%") do set "OUT_DIR=%%~dpP"
REM normalize trailing backslash
if "%OUT_DIR:~-1%"=="\" set "OUT_DIR=%OUT_DIR:~0,-1%"
goto KB_AI_FOUND

:KB_AI_FOUND

set "ZIP_NAME=KB-AI-M1-M3.zip"
set "ZIP_PATH=%OUT_DIR%\%ZIP_NAME%"

if exist "%ZIP_PATH%" del /F /Q "%ZIP_PATH%" >nul 2>&1

echo.
echo ============================================================
echo   KB-AI package.bat -- building KB-AI-M1-M3.zip
echo   source : %KBAI_DIR%
echo   target : %ZIP_PATH%
echo   exclude: data\, vectors\, cache\, logs\, tmp\
echo ============================================================
echo.

REM Write the PowerShell helper script to a temp file (ASCII-only).
set "TMP_PS=%TEMP%\kb-ai-package-%RANDOM%.ps1"
> "%TMP_PS%" echo $ErrorActionPreference = 'Stop'
>>"%TMP_PS%" echo $src = $env:KBAI_DIR
>>"%TMP_PS%" echo $zipPath = $env:ZIP_PATH
>>"%TMP_PS%" echo if (-not (Test-Path -LiteralPath $src)) { Write-Error "missing $src"; exit 2 }
>>"%TMP_PS%" echo $items = New-Object System.Collections.Generic.List[string]
>>"%TMP_PS%" echo foreach ($d in @('scripts','tests','docs','dify')) { $p = Join-Path $src $d; if (Test-Path -LiteralPath $p) { [void]$items.Add($p) } }
>>"%TMP_PS%" echo foreach ($f in @('start.bat','stop.bat','docker-compose.yml','QUICKSTART.md','docs\releases\RELEASE-M3.md','docs\releases\RELEASE-M3a.md','docs\releases\RELEASE-M3b.md','package.bat','.env.example','.gitignore')) { $p = Join-Path $src $f; if (Test-Path -LiteralPath $p) { [void]$items.Add($p) } }
>>"%TMP_PS%" echo Add-Type -AssemblyName System.IO.Compression.FileSystem
>>"%TMP_PS%" echo Compress-Archive -Path $items -DestinationPath $zipPath -CompressionLevel Optimal -Force
>>"%TMP_PS%" echo $z = Get-Item -LiteralPath $zipPath
>>"%TMP_PS%" echo $archive = [System.IO.Compression.ZipFile]::OpenRead($z.FullName)
>>"%TMP_PS%" echo $c = $archive.Entries.Count
>>"%TMP_PS%" echo $archive.Dispose()
>>"%TMP_PS%" echo $line = ('[package] packed {0} entries, size {1} bytes ({2:N1} KB)' -f $c, $z.Length, ($z.Length / 1024))
>>"%TMP_PS%" echo Write-Host $line

REM Pass KBAI_DIR + ZIP_PATH env vars to PowerShell child process.
set "KBAI_DIR=%KBAI_DIR%"
set "ZIP_PATH=%ZIP_PATH%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%TMP_PS%"

if errorlevel 1 (
    del /F /Q "%TMP_PS%" >nul 2>&1
    echo [ERROR] Compress-Archive failed
    exit /b 1
)

del /F /Q "%TMP_PS%" >nul 2>&1

echo.
echo ============================================================
echo   upgrade package ready: %ZIP_PATH%
echo   next: copy zip to USB SSD root, extract overwriting old files
echo ============================================================
echo.

endlocal
exit /b 0
