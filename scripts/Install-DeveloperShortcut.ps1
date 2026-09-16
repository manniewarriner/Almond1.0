$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$iconPath = Join-Path $projectRoot "app\assets\almond.ico"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$shortcutPath = Join-Path $startMenu "Almond AI Developer Console.lnk"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Virtual environment missing: $pythonPath"
}
if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "Almond icon missing: $iconPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonPath
$shortcut.Arguments = "-m almond_ai.cli"
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "Almond Financial AI Development Console"
$shortcut.Save()

Write-Output "Created: $shortcutPath"
Write-Output "Open Start, search 'Almond AI Developer Console', then choose Pin to taskbar."
