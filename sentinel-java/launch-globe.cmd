@echo off
setlocal
cd /d "%~dp0"

title Sentinel Phoenix - Narrated Globe

if not exist "pom.xml" (
    echo [ERROR] Place this launcher next to pom.xml.
    pause
    exit /b 1
)

echo [SENTINEL] Preparing the narrated globe...

call mvn compile dependency:build-classpath "-Dmdep.outputFile=target/globe-classpath.txt" "-DincludeScope=runtime"

if errorlevel 1 (
    echo [ERROR] Maven preparation failed.
    pause
    exit /b 1
)

echo [SENTINEL] Loading the complete dependency list...

powershell.exe -NoProfile -Command "$ErrorActionPreference = 'Stop'; $deps = [System.IO.File]::ReadAllText((Join-Path (Get-Location).Path 'target\globe-classpath.txt')).Trim(); if ($deps -notmatch 'sherpa-onnx-native-lib-win-x64') { throw 'The native Kokoro library is missing from the classpath.' }; $cp = (Join-Path (Get-Location).Path 'target\classes') + ';' + $deps; $java = 'C:\Program Files\Java\jdk-26.0.2.1\bin\java.exe'; if (-not (Test-Path $java)) { throw 'Java executable not found.' }; & $java '--enable-native-access=ALL-UNNAMED' '-cp' $cp 'GlobeLauncher'; exit $LASTEXITCODE"

if errorlevel 1 (
    echo [ERROR] The globe stopped with an error.
    pause
    exit /b 1
)

endlocal