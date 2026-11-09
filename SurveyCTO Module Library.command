#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
VENV_DIR="$PROJECT_DIR/.venv"
LOG="${TMPDIR:-/tmp}/surveycto_module_library_launcher.log"

cd "$PROJECT_DIR" || exit 1
mkdir -p logs data/raw data/database data/exports

PYTHON_BIN=""
for CANDIDATE in python3.12 python3.11 python3.10 python3; do
  CANDIDATE_PATH=$(command -v "$CANDIDATE" 2>/dev/null || true)
  if [[ -n "$CANDIDATE_PATH" ]] && "$CANDIDATE_PATH" -c \
    'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
    PYTHON_BIN="$CANDIDATE_PATH"
    break
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "SurveyCTO Module Library needs Python 3.10 or newer."
  echo "Please ask the project maintainer to install a compatible Python version."
  read -r "?Press Enter to close..."
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Preparing the SurveyCTO Module Library for first use..."
  "$PYTHON_BIN" -m venv "$VENV_DIR" || {
    echo "Could not create the Python environment."
    read -r "?Press Enter to close..."
    exit 1
  }
fi

if [[ ! -f "$VENV_DIR/.library-installed" || pyproject.toml -nt "$VENV_DIR/.library-installed" ]]; then
  echo "Checking the application setup..."
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
  "$VENV_DIR/bin/python" -m pip install --quiet -e . >"$LOG" 2>&1 || {
    cat "$LOG"
    echo
    echo "Setup failed. Check your internet connection and try again."
    read -r "?Press Enter to close..."
    exit 1
  }
  touch "$VENV_DIR/.library-installed"
fi

CHOICE=$(/usr/bin/osascript <<'APPLESCRIPT'
choose from list {"Open library", "Update library from SurveyCTO", "Update and open library", "Change SurveyCTO login"} with title "SurveyCTO Module Library" with prompt "What would you like to do?" default items {"Update and open library"}
if result is false then return "Cancel"
return item 1 of result
APPLESCRIPT
)

case "$CHOICE" in
  "Open library")
    "$VENV_DIR/bin/surveycto-library" open
    ;;
  "Update library from SurveyCTO")
    "$VENV_DIR/bin/surveycto-library" update
    ;;
  "Update and open library")
    "$VENV_DIR/bin/surveycto-library" update && "$VENV_DIR/bin/surveycto-library" open
    ;;
  "Change SurveyCTO login")
    "$VENV_DIR/bin/surveycto-library" credentials --popup
    ;;
  *)
    exit 0
    ;;
esac

STATUS=$?
if [[ $STATUS -ne 0 ]]; then
  echo
  echo "The operation did not finish successfully. See the message above and logs/ for details."
  read -r "?Press Enter to close..."
fi
exit $STATUS
