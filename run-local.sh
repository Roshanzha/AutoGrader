#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if ! command -v gcc >/dev/null || [ ! -f /usr/include/stdio.h ] || ! command -v cppcheck >/dev/null || ! python3 -c 'import venv' 2>/dev/null; then
    echo 'Installing the Linux compiler and Python tools...'
    sudo apt-get update
    sudo apt-get install -y build-essential cppcheck python3-venv python3-pip
fi

if [ ! -x .venv-linux/bin/python ]; then
    python3 -m venv .venv-linux
fi
if ! cmp -s requirements.txt .venv-linux/installed-requirements.txt; then
    .venv-linux/bin/python -m pip install -r requirements.txt
    cp requirements.txt .venv-linux/installed-requirements.txt
fi

echo 'Starting AutoGrader. The server log shows the address and port (Ctrl+C to stop).'
exec .venv-linux/bin/python front_app.py "$@"
