$ErrorActionPreference = "Stop"

$Python = if ($args.Count -gt 0) { $args[0] } else { "python" }

# Check Python version >= 3.11
& $Python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Python 3.11 or newer is required."
    & $Python --version
    exit 1
}

& $Python -m venv .venv

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
python -m pip install -e "../csorchestrator"


pre-commit install

Write-Host "Setup complete."
Write-Host ""
Write-Host "Next:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  code ."
Write-Host ""
Write-Host "Or: "
Write-Host ""
Write-Host ".\open-code.ps1"
