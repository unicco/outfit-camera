#!/bin/bash
set -euo pipefail

# Ensure API virtual environment is ready before coordinate-api.service starts.
# This script is invoked from systemd ExecStartPre and should remain lightweight.

PROJECT_ROOT="/home/pi/coordinate-recorder"
VENV_PATH="${PROJECT_ROOT}/venv"
PYTHON_BIN="${VENV_PATH}/bin/python"

failure() {
    local message="$1"
    echo "[coordinate-api] ${message}" | systemd-cat -t coordinate-api -p err
    echo "${message}" >&2
    exit 1
}

if [ ! -x "${PYTHON_BIN}" ]; then
    failure "Virtual environment missing at ${VENV_PATH}. Run 'sudo systemctl start coordinate-api-deploy.service'."
fi

# Attempt to import core dependencies; failure indicates deploy service must run.
if ! "${PYTHON_BIN}" - <<'PYCODE'
import importlib
required = ("fastapi", "uvicorn", "pydantic")
missing = []
for module in required:
    try:
        importlib.import_module(module)
    except ModuleNotFoundError:
        missing.append(module)

if missing:
    raise SystemExit("Missing modules: " + ", ".join(missing))
PYCODE
then
    failure "Required Python modules are missing. Run 'sudo systemctl start coordinate-api-deploy.service'."
fi

exit 0
