#!/usr/bin/env bash
# Copy decision artifacts into the website.
#
# The site renders real Zence output, not prose written to look like it. That
# only stays true if there is exactly one source: `examples/artifacts/decisions`,
# produced by `zence evaluate --json` against the demo catalog.
#
# Run before building the site. CI runs it and then checks `git diff --exit-code`,
# so an artifact edited by hand in the web tree fails the build rather than
# quietly becoming a mock-up.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${REPO_ROOT}/examples/artifacts/decisions"
DEST="${REPO_ROOT}/apps/web/app/_artifacts"

if [ ! -d "${SOURCE}" ]; then
    echo "error: no artifacts at ${SOURCE}" >&2
    echo "       generate them with \`zence evaluate --json\` first" >&2
    exit 1
fi

count=$(find "${SOURCE}" -name '*.json' | wc -l | tr -d ' ')
if [ "${count}" -eq 0 ]; then
    echo "error: ${SOURCE} contains no artifacts" >&2
    exit 1
fi

rm -rf "${DEST}"
mkdir -p "${DEST}"
cp "${SOURCE}"/*.json "${DEST}/"

echo "synced ${count} decision artifact(s) → apps/web/app/_artifacts"
