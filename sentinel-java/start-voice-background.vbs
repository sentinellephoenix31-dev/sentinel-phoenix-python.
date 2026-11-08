Option Explicit

Dim files, shell, root, scriptPath
Dim quote, command, result

Set files = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = files.GetParentFolderName(WScript.ScriptFullName)
scriptPath = root & "\start-sentinel-voice.ps1"
quote = Chr(34)

If Not files.FileExists(scriptPath) Then
    MsgBox "Missing start-sentinel-voice.ps1", vbExclamation, "Sentinel"
    WScript.Quit 1
End If

command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " _
    & quote & scriptPath & quote

result = shell.Run(command, 0, True)

If result <> 0 Then
    MsgBox "Sentinel could not start. Check data\voice-startup.log", _
        vbExclamation, "Sentinel"
End If

WScript.Quit result