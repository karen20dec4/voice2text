Set WshShell = CreateObject("WScript.Shell")
strScriptPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strScriptPath
Set Fso = CreateObject("Scripting.FileSystemObject")
If Fso.FileExists(strScriptPath & "\Voice2Text.exe") Then
    WshShell.Run """" & strScriptPath & "\Voice2Text.exe""", 0, False
    WScript.Quit
End If
strPython = strScriptPath & "\.venv\Scripts\pythonw.exe"
If Not Fso.FileExists(strPython) Then strPython = "pythonw.exe"
On Error Resume Next
WshShell.Run """" & strPython & """ """ & strScriptPath & "\Voice2Text.pyw""", 0, False
If Err.Number <> 0 Then
    MsgBox "Nu pot porni Voice2Text. Verifica instalarea Python si requirements.txt." & vbCrLf & Err.Description, 16, "Voice2Text"
End If
