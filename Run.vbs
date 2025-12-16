Set WshShell = CreateObject("WScript.Shell") 
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' 0 表示隐藏窗口启动
WshShell.Run chr(34) & strPath & "\Run.bat" & chr(34), 0
Set WshShell = Nothing