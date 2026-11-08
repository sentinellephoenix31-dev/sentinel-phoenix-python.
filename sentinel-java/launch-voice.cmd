@echo off
setlocal
cd /d "%~dp0"

title Sentinel Phoenix - Voice Startup

echo [SENTINEL] Preparing compiled classes and dependencies...

call mvn compile dependency:build-classpath "-Dmdep.outputFile=target/globe-classpath.txt" "-DincludeScope=runtime"

if errorlevel 1 (
    echo [ERROR] Compilation failed.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-sentinel-voice.ps1"

if errorlevel 1 (
    echo [ERROR] Check data\voice-startup.log.
    pause
    exit /b 1
)

echo.
echo [SENTINEL] Background startup completed.
echo [SENTINEL] Wait for Heart, then say Hey Sentinel.

endlocal