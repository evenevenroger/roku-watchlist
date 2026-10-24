$ErrorActionPreference = 'Stop'
$taskUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$scriptPath = Join-Path $PSScriptRoot 'ensure_server.py'
$action = New-ScheduledTaskAction -Execute 'C:\Python314\pythonw.exe' -Argument ('"' + $scriptPath + '"') -WorkingDirectory $PSScriptRoot
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
$checkTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Minha Watchlist - Servidor automatico' -Action $action -Trigger @($logonTrigger, $checkTrigger) -Settings $settings -Principal $principal -Description 'Inicia a Watchlist ao entrar no Windows e verifica a cada minuto se o servidor precisa ser religado.' | Out-Null
Start-ScheduledTask -TaskName 'Minha Watchlist - Servidor automatico'
Write-Output 'Inicio automatico configurado: ao entrar no Windows e verificacao a cada minuto.'
