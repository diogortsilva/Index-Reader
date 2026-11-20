#!/bin/bash
# Index-Reader launcher for macOS (also works on Linux): double-click to open the window.
# The first launch creates a private Python environment in the .venv folder
# and downloads openpyxl, the one library the tool needs. After that it runs offline.

cd "$(dirname "$0")" || exit 1

stop() {
    echo
    echo "$1"
    echo
    read -n 1 -s -r -p "Press any key to close this window."
    echo
    exit 1
}

if [ ! -x ".venv/bin/python" ]; then
    command -v python3 >/dev/null 2>&1 || stop "Python 3 was not found. Install it from python.org and try again."
    echo "First launch: setting up Index-Reader (needs the internet once)..."
    python3 -m venv .venv || stop "Could not create the Python environment (.venv)."
fi

if ! .venv/bin/python -c "import openpyxl" >/dev/null 2>&1; then
    echo "Installing openpyxl..."
    .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt \
        || stop "Could not install openpyxl. Check the internet connection and try again."
fi

if ! .venv/bin/python -c "import tkinter" >/dev/null 2>&1; then
    stop "This Python has no tkinter, which the window needs.
  Homebrew Python:  brew install python-tk   (then delete the .venv folder and launch again)
  Otherwise:        install Python from python.org, delete the .venv folder and launch again."
fi

echo "Index-Reader is running. Close its window (or press Ctrl+C here) to stop."
.venv/bin/python -m index_reader
status=$?
if [ $status -ne 0 ]; then
    stop "Index-Reader stopped with code $status."
fi
