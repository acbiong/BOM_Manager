# Windows development entry point. No global PATH changes or background watchers.
[CmdletBinding()]
param(
    [ValidateSet('init', 'run', 'test', 'build', 'finish')]
    [string]$Action = 'init',
    [string]$PythonPath,
    [string]$MessageFile = '.tmp/change_message.txt'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$savedPath = $env:PATH
$savedUtf8 = $env:PYTHONUTF8
$savedPython = $env:BOM_PYTHON

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Executable $Arguments" }
}

Push-Location $projectRoot
try {
    $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $gitCommand) {
        foreach ($candidate in @(
            "$env:ProgramFiles\Git\cmd\git.exe",
            "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
        )) {
            if (Test-Path -LiteralPath $candidate) {
                $env:PATH = (Split-Path -Parent $candidate) + ';' + $env:PATH
                $gitCommand = Get-Command git.exe
                break
            }
        }
    }
    if (-not $gitCommand) { throw 'Install Git for Windows, then reopen the terminal.' }
    $env:PYTHONUTF8 = '1'
    if ($Action -eq 'init') {
        if (-not (Test-Path -LiteralPath $venvPython)) {
            if ($PythonPath) {
                Invoke-Checked $PythonPath @('-m', 'venv', '.venv')
            } elseif (Get-Command py.exe -ErrorAction SilentlyContinue) {
                Invoke-Checked 'py.exe' @('-3.12', '-m', 'venv', '.venv')
            } elseif (Test-Path -LiteralPath "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe") {
                Invoke-Checked "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" @('-m', 'venv', '.venv')
            } else {
                throw 'Install Python 3.12 x64 or pass -PythonPath to its python.exe.'
            }
        }
    }
    if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run tools\windows.ps1 init first.' }
    $env:PATH = (Split-Path -Parent $venvPython) + ';' + $env:PATH
    $env:BOM_PYTHON = $venvPython
    Invoke-Checked $venvPython @('-c', "import sys,struct; assert sys.version_info >= (3,12) and struct.calcsize('P')==8, 'Python 3.12+ x64 required'; print(sys.version)")
    foreach ($directory in @('.tmp', 'test_reports', 'package')) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    switch ($Action) {
        'init' {
            Invoke-Checked $venvPython @('-m', 'pip', 'install', '-r', 'requirements.txt')
            Invoke-Checked $venvPython @('-m', 'pip', 'check')
            Invoke-Checked $gitCommand.Source @('config', 'core.hooksPath', '.githooks')
            Invoke-Checked $venvPython @('tools/run_tests.py')
            Write-Host 'Ready: tools\windows.ps1 run | test | build | finish. No watcher started.'
        }
        'run' { Invoke-Checked $venvPython @('src/main.py') }
        'test' { Invoke-Checked $venvPython @('tools/run_tests.py') }
        'build' { Invoke-Checked $venvPython @('tools/build_windows.py') }
        'finish' {
            $gitRoot = Split-Path -Parent (Split-Path -Parent $gitCommand.Source)
            $bashPath = Join-Path $gitRoot 'bin\bash.exe'
            if (-not (Test-Path -LiteralPath $bashPath)) { throw 'Git Bash bin\bash.exe not found beside Git.' }
            if ((& $gitCommand.Source config --get core.hooksPath) -ne '.githooks') {
                throw 'Run tools\windows.ps1 init to enable the packaging hook first.'
            }
            Invoke-Checked $bashPath @('tools/finish_ai_change.sh', '--message-file', $MessageFile)
        }
    }
} finally {
    $env:PATH = $savedPath
    $env:PYTHONUTF8 = $savedUtf8
    $env:BOM_PYTHON = $savedPython
    Pop-Location
}
