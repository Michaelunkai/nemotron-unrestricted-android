#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PACKAGE_FILE="$PROJECT_ROOT/toolchain/termux-packages.txt"
PYTHON_FILE="$PROJECT_ROOT/toolchain/python-requirements.txt"
packages=()

while IFS= read -r package; do
  case "$package" in ''|'#'*) continue ;; esac
  packages+=("$package")
done < "$PACKAGE_FILE"

pkg install -y "${packages[@]}"
python -m pip install --upgrade --requirement "$PYTHON_FILE"
"$PROJECT_ROOT/sync-capabilities.sh"

printf 'NEMOTRON_SECURITY_TOOLCHAIN_READY\n'
