#!/usr/bin/env bash
# Generate all vocabulary — runs A/B/C in parallel per language.
# Run: bash seed_all.sh

set -e
cd "$(dirname "$0")"

python3 generate.py seed spanish
echo ""
python3 generate.py seed english
echo ""
echo "🎉 All done!"
