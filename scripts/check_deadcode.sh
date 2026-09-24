#!/usr/bin/env bash
set -euo pipefail

uv run vulture . --min-confidence 80 --exclude ".venv,**/.venv/*,**/__pycache__/*"
uv run ruff check . --select F401,F841
