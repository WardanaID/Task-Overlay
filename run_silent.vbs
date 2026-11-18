Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir

userProfile = WshShell.ExpandEnvironmentStrings("%USERPROFILE%")
pywPath = userProfile & "\AppData\Local\Programs\Python\Python312\pythonw.exe"

If fso.FileExists(pywPath) Then
    WshShell.Run """" & pywPath & """ """ & currentDir & "\main.py""", 0, False
Else
    WshShell.Run "pythonw main.py", 0, False
End If
