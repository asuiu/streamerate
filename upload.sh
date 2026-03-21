#!/bin/bash
set -euo pipefail
shopt -s nullglob

rm -f ./dist/*.whl ./dist/*.tar.gz
poetry build
poetry run twine upload --verbose dist/*
