#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Use the project Node version, including from a fresh desktop terminal.
if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
  set +u
  . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
  set -u
  nvm use --silent || { echo "Run nvm install in the project root first."; exit 1; }
fi
if command -v uv >/dev/null 2>&1; then
  margin_uv="$(command -v uv)"
elif [ -x .tools/uv ]; then
  margin_uv="./.tools/uv"
else
  echo 'Install uv from https://docs.astral.sh/uv/getting-started/installation/ first.'
  exit 1
fi
"$margin_uv" sync --locked
exec "$margin_uv" run --locked python -m scripts.dev
