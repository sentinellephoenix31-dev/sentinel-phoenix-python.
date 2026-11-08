$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$logDirectory = Join-Path $projectRoot "data"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

$startupLog = Join-Path $logDirectory "voice-startup.log"

function Write-StartupLog {
    param([string]$Message)

    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $startupLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Quote-Argument {
    param([string]$Value)

    if ($Value.Contains('"')) {
        throw "An argument contains an unsupported quotation mark."
    }

    return '"' + $Value + '"'
}

function Test-LocalPort {
    param([int]$Port)

    $connection = New-Object System.Net.Sockets.TcpClient

    try {
        $pending = $connection.ConnectAsync("127.0.0.1", $Port)

        if (-not $pending.Wait(300)) {
            return $false
        }

        return $connection.Connected
    }
    catch {
        return $false
    }
    finally {
        $connection.Dispose()
    }
}

function Get-JavaProcesses {
    return @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -in @("java.exe", "javaw.exe")
            }
    )
}

$startupMutex = New-Object System.Threading.Mutex(
    $false,
    "Local\SentinelPhoenixVoiceStartup"
)

$ownsMutex = $false
$newRuntime = $null

try {
    try {
        $ownsMutex = $startupMutex.WaitOne(0)
    }
    catch [System.Threading.AbandonedMutexException] {
        $ownsMutex = $true
    }

    if (-not $ownsMutex) {
        Write-StartupLog "Another Sentinel startup is already in progress."
        exit 0
    }

    $javaPath = "C:\Program Files\Java\jdk-26.0.2.1\bin\java.exe"
    $serverPath = Join-Path $projectRoot "tools\whisper-server.exe"
    $modelPath = Join-Path $projectRoot "models\stt\ggml-base.bin"
    $classesPath = Join-Path $projectRoot "target\classes"
    $classpathFile = Join-Path $projectRoot "target\globe-classpath.txt"

    foreach ($requiredFile in @(
        $javaPath,
        $serverPath,
        $modelPath,
        $classpathFile,
        (Join-Path $classesPath "Main.class"),
        (Join-Path $classesPath "VoiceAssistant.class")
    )) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Required file missing: $requiredFile"
        }
    }

    $dependencies = [System.IO.File]::ReadAllText(
        $classpathFile
    ).Trim()

    if ($dependencies -notmatch "sherpa-onnx-native-lib-win-x64") {
        throw "The runtime classpath is missing the Kokoro Windows library."
    }

    $runtimeClasspath = $classesPath + ";" + $dependencies

    # --------------------------------------------------------
    # WHISPER
    # --------------------------------------------------------

    $servers = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -eq "whisper-server.exe" -and
                $_.CommandLine -match "\b8178\b"
            }
    )

    $serverProcess = $null

    if ($servers.Count -eq 0) {
        if (Test-LocalPort 8178) {
            throw "Port 8178 is occupied by another service."
        }

        Write-StartupLog "Starting Whisper Base with 6 threads."

        $serverArguments = @(
            "-m",
            (Quote-Argument $modelPath),
            "--host", "127.0.0.1",
            "--port", "8178",
            "-l", "auto",
            "-ng",
            "-t", "6"
        ) -join " "

        $serverProcess = Start-Process `
            -FilePath $serverPath `
            -ArgumentList $serverArguments `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDirectory "whisper-server.log") `
            -RedirectStandardError (Join-Path $logDirectory "whisper-server-error.log") `
            -PassThru
    }
    else {
        $expectedServers = @(
            $servers |
                Where-Object {
                    $_.ExecutablePath -eq $serverPath -and
                    $_.CommandLine -match "ggml-base\.bin"
                }
        )

        if ($servers.Count -ne 1 -or $expectedServers.Count -ne 1) {
            throw "A different Whisper server is using port 8178."
        }

        Write-StartupLog "Reusing the existing Whisper Base server."
    }

    $deadline = (Get-Date).AddSeconds(120)

    while (-not (Test-LocalPort 8178)) {
        if ($null -ne $serverProcess) {
            $serverProcess.Refresh()

            if ($serverProcess.HasExited) {
                throw "Whisper stopped. Check whisper-server-error.log."
            }
        }

        if ((Get-Date) -ge $deadline) {
            throw "Whisper startup timed out."
        }

        Start-Sleep -Milliseconds 300
    }

    Write-StartupLog "Whisper is available on 127.0.0.1:8178."

    # --------------------------------------------------------
    # HONEYPOT + DASHBOARD
    # --------------------------------------------------------

    $runtimes = @(
        Get-JavaProcesses |
            Where-Object {
                $_.CommandLine -match "\bMain\s+--services\b" -and
                $_.CommandLine.IndexOf(
                    $projectRoot,
                    [System.StringComparison]::OrdinalIgnoreCase
                ) -ge 0
            }
    )

    if ($runtimes.Count -gt 1) {
        throw "More than one Sentinel services process was found."
    }

    if ($runtimes.Count -eq 0) {
        # Only check the dashboard before startup.
        # Avoid creating a probe connection to the honeypot.
        if (Test-LocalPort 8080) {
            throw "Port 8080 is occupied. Stop the old Sentinel runtime or the conflicting service."
        }

        Write-StartupLog "Starting the honeypot and dashboard."

        $runtimeArguments = @(
            "--enable-native-access=ALL-UNNAMED",
            "-cp",
            (Quote-Argument $runtimeClasspath),
            "Main",
            "--services"
        ) -join " "

        $newRuntime = Start-Process `
            -FilePath $javaPath `
            -ArgumentList $runtimeArguments `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDirectory "services.log") `
            -RedirectStandardError (Join-Path $logDirectory "services-error.log") `
            -PassThru

        $deadline = (Get-Date).AddSeconds(60)
        $servicesReady = $false

        while ((Get-Date) -lt $deadline) {
            $newRuntime.Refresh()

            if ($newRuntime.HasExited) {
                throw "Sentinel services stopped. Check services.log and services-error.log."
            }

            # The dashboard starts only after HoneypotService.start returns.
            if (Test-LocalPort 8080) {
                $servicesReady = $true
                break
            }

            Start-Sleep -Milliseconds 300
        }

        if (-not $servicesReady) {
            throw "Sentinel services startup timed out."
        }
    }
    else {
        if (-not (Test-LocalPort 8080)) {
            throw "The services process exists but its dashboard is unavailable."
        }

        Write-StartupLog "Reusing the existing Sentinel services."
    }

    Write-StartupLog "Services available. Dashboard: http://127.0.0.1:8080/"

    # --------------------------------------------------------
    # VOICE ASSISTANT
    # --------------------------------------------------------

    $assistants = @(
        Get-JavaProcesses |
            Where-Object {
                $_.CommandLine -match "\bVoiceAssistant\b"
            }
    )

    if ($assistants.Count -gt 0) {
        Write-StartupLog "VoiceAssistant is already running. No duplicate started."
        exit 0
    }

    $voiceArguments = @(
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        (Quote-Argument $runtimeClasspath),
        "VoiceAssistant"
    ) -join " "

    Write-StartupLog "Starting VoiceAssistant."

    $assistantProcess = Start-Process `
        -FilePath $javaPath `
        -ArgumentList $voiceArguments `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDirectory "voice-background.log") `
        -RedirectStandardError (Join-Path $logDirectory "voice-background-error.log") `
        -PassThru

    Start-Sleep -Seconds 2
    $assistantProcess.Refresh()

    if ($assistantProcess.HasExited) {
        throw "VoiceAssistant stopped. Check voice-background-error.log."
    }

    Write-StartupLog "Startup completed. Wait for Heart before speaking."
}
catch {
    Write-StartupLog ("STARTUP ERROR: " + $_.Exception.Message)

    # Roll back only a services process started by this attempt.
    if ($null -ne $newRuntime) {
        $newRuntime.Refresh()

        if (-not $newRuntime.HasExited) {
            Stop-Process -Id $newRuntime.Id -ErrorAction SilentlyContinue
        }
    }

    exit 1
}
finally {
    if ($ownsMutex) {
        $startupMutex.ReleaseMutex()
    }

    $startupMutex.Dispose()
}