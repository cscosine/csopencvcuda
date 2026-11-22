#!/usr/bin/env bash
# Owned by the project template (cs-project-template): change it there.
# Creates .venv, installs the project with its dev tools and csorchestrator, installs the pre-commit hooks.
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
  echo "Do not source this script. Run: ./setup.sh"
  return 1
fi

usage() {
  cat <<USAGE
Usage: ./setup.sh [--python=<interpreter>] [--csorchestrator=<tag|branch|path>]

  --python=<interpreter>        Python used to create .venv (default: python3 when it is 3.11 or newer, otherwise
                                  the newest of python3.14 ... python3.11 found)
  --csorchestrator=<spec>       csorchestrator to install (default: v0.1.0, the pinned version)
                                  a tag or branch of github.com/cscosine/csorchestrator, or
                                  the path of a local clone (installed editable, e.g. ../csorchestrator)
USAGE
}

PYTHON=""
CSORCHESTRATOR="v0.1.0"
for arg in "$@"; do
  case "${arg}" in
    --python=*) PYTHON="${arg#*=}" ;;
    --csorchestrator=*) CSORCHESTRATOR="${arg#*=}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: ${arg}"; usage; exit 1 ;;
  esac
done

recent_enough() { command -v "$1" >/dev/null 2>&1 && "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; }
if [[ -z "${PYTHON}" ]]; then
  for candidate in python3 python3.14 python3.13 python3.12 python3.11; do
    if recent_enough "${candidate}"; then PYTHON="${candidate}"; break; fi
  done
  PYTHON="${PYTHON:-python3}"
fi

echo "Using Python: ${PYTHON} ($("${PYTHON}" --version 2>&1))"

if ! "${PYTHON}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Error: Python 3.11 or newer is required."
  echo "Found:"
  "${PYTHON}" --version
  exit 1
fi

"${PYTHON}" -m venv .venv

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"

# uninstall first: switching between a tag, a branch and a local clone always takes effect
python -m pip uninstall --yes csorchestrator
if [[ -d "${CSORCHESTRATOR}" ]]; then
  echo "csorchestrator: local clone ${CSORCHESTRATOR} (editable)"
  python -m pip install -e "${CSORCHESTRATOR}"
else
  echo "csorchestrator: ${CSORCHESTRATOR} from github.com/cscosine/csorchestrator"
  python -m pip install "csorchestrator @ git+https://github.com/cscosine/csorchestrator.git@${CSORCHESTRATOR}"
fi

pre-commit install

echo "Setup complete."
echo ""
echo "Next: "
echo "  source .venv/bin/activate"
echo "  code ."
echo ""
echo "Or: "
echo "  ./open-code.sh"
