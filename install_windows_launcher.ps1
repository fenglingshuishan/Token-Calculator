$ErrorActionPreference = "Stop"
$desktop = [Environment]::GetFolderPath("Desktop")
$source = "\\wsl.localhost\Ubuntu\home\hcj\dev\token-calculator\PromptWorkbench.cmd"
$cmdPath = Join-Path $desktop "PromptWorkbench.cmd"
Copy-Item -LiteralPath $source -Destination $cmdPath -Force
$stopSource = "\\wsl.localhost\Ubuntu\home\hcj\dev\token-calculator\StopPromptWorkbench.cmd"
$stopCmdPath = Join-Path $desktop "StopPromptWorkbench.cmd"
Copy-Item -LiteralPath $stopSource -Destination $stopCmdPath -Force

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktop "Prompt Workbench.lnk"))
$shortcut.TargetPath = $cmdPath
$shortcut.WorkingDirectory = $desktop
$shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,67"
$shortcut.Description = "Start Prompt Workbench in WSL2"
$shortcut.Save()

$stopShortcut = $shell.CreateShortcut((Join-Path $desktop "Stop Prompt Workbench.lnk"))
$stopShortcut.TargetPath = $stopCmdPath
$stopShortcut.WorkingDirectory = $desktop
$stopShortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,93"
$stopShortcut.Description = "Stop Prompt Workbench running in WSL2"
$stopShortcut.Save()

Write-Host "Windows desktop shortcuts created: Prompt Workbench.lnk and Stop Prompt Workbench.lnk"
