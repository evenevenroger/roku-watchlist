' Liga o servidor Watchlist -> Roku sem abrir janela (usado no início automático do Windows).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
sh.Run """C:\Python314\pythonw.exe"" """ & dir & "\ensure_server.py""", 0, False
