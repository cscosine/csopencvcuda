#!/usr/bin/env bash
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
  echo "Do not source this script. Run: ./setup.sh"
  return 1
fi

PYTHON="${1:-python3}"

echo "Using Python: ${PYTHON}"

# Check Python version >= 3.11
if ! ${PYTHON} -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Error: Python 3.11 or newer is required."
  echo "Found:"
  ${PYTHON} --version
  exit 1
fi

${PYTHON} -m venv .venv

source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
python -m pip install -e "../csorchestrator"


pre-commit install

echo "Setup complete."
echo ""
echo "Next: "
echo "  source .venv/bin/activate"
echo "  code ."
echo ""
echo "Or: "
echo "  ./open-code.sh"
echo ""
echo "Or: "
echo "  source ./open-code.sh"
