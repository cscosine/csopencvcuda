# Owned by the project template (cs-project-template): change it there.
# Creates .venv, installs the project with its dev tools and csorchestrator, installs the pre-commit hooks.
# Usage: .\setup.ps1 [-Python <interpreter>] [-CsOrchestrator <tag|branch|path>]
param(
    # default: python when it is 3.11 or newer, otherwise the newest Python 3.14 ... 3.11 of the py launcher
    [string]$Python = "",
    # tag or branch of github.com/cscosine/csorchestrator, or the path of a local clone (installed editable)
    [string]$CsOrchestrator = "v0.1.0"
)
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    & $args[0] $args[1..($args.Count - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Failed: $args" }
}

function Test-RecentPython([string[]]$Command) {
    try {
        $exe, $rest = $Command
        & $exe @rest -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}
$PythonArgs = @()
if (-not $Python) {
    $Python = "python"
    if (-not (Test-RecentPython @("python"))) {
        foreach ($minor in 14, 13, 12, 11) {
            if (Test-RecentPython @("py", "-3.$minor")) { $Python = "py"; $PythonArgs = @("-3.$minor"); break }
        }
    }
}

Write-Host "Using Python: $Python $PythonArgs"

& $Python @PythonArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Python 3.11 or newer is required."
    Write-Host "Found:"
    & $Python @PythonArgs --version
    exit 1
}

Invoke-Checked $Python @PythonArgs -m venv .venv

.\.venv\Scripts\Activate.ps1

Invoke-Checked python -m pip install --upgrade pip setuptools wheel
Invoke-Checked python -m pip install -e ".[dev]"

# uninstall first: switching between a tag, a branch and a local clone always takes effect
Invoke-Checked python -m pip uninstall --yes csorchestrator
if (Test-Path -PathType Container $CsOrchestrator) {
    Write-Host "csorchestrator: local clone $CsOrchestrator (editable)"
    Invoke-Checked python -m pip install -e $CsOrchestrator
} else {
    Write-Host "csorchestrator: $CsOrchestrator from github.com/cscosine/csorchestrator"
    $Spec = "csorchestrator @ git+https://github.com/cscosine/csorchestrator.git@$CsOrchestrator"
    Invoke-Checked python -m pip install $Spec
}

Invoke-Checked pre-commit install

Write-Host "Setup complete."
Write-Host ""
Write-Host "Next:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  code ."
Write-Host ""
Write-Host "Or:"
Write-Host "  .\open-code.ps1"
