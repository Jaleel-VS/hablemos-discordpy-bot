#!/usr/bin/env bash
set -euo pipefail

python -m vulture . --min-confidence 80 --exclude ".venv,**/.venv/*,**/__pycache__/*"
python -m ruff check . --select F401,F841
