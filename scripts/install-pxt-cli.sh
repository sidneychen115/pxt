#!/usr/bin/env bash
# Install pxt-build (and pxt-rebuild alias) into ~/.local/bin.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${HOME}/.local/bin"
mkdir -p "$DEST"
install -m 755 "${ROOT}/scripts/pxt-build.sh" "${DEST}/pxt-build"
ln -sf pxt-build "${DEST}/pxt-rebuild"
printf 'Installed %s/pxt-build and %s/pxt-rebuild -> pxt-build\n' "$DEST" "$DEST"
