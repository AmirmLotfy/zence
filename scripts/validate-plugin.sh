#!/usr/bin/env bash
# Validate both Claude Code manifests.
#
# `claude plugin validate <dir>` checks the *marketplace* manifest when it finds
# one, and stops there. Because Zence ships as a marketplace-root plugin, both
# files live in the same `.claude-plugin/` directory — so a plain invocation
# silently leaves `plugin.json` unchecked, and a broken plugin manifest would
# reach users behind a green tick.
#
# So: validate the marketplace in place, then validate the plugin manifest from
# a copy that has no marketplace file next to it.

set -euo pipefail

CLI_VERSION="${CLAUDE_CODE_VERSION:-2.1.220}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI=(npx -y "@anthropic-ai/claude-code@${CLI_VERSION}" plugin validate)

echo "==> marketplace manifest"
"${CLI[@]}" "${REPO_ROOT}" --strict

echo
echo "==> plugin manifest (isolated, so it is not shadowed by the marketplace)"
STAGING="$(mktemp -d)"
trap 'rm -rf "${STAGING}"' EXIT

mkdir -p "${STAGING}/.claude-plugin"
cp "${REPO_ROOT}/.claude-plugin/plugin.json" "${STAGING}/.claude-plugin/"

# Components the manifest points at must come along, or validation of skill and
# hook frontmatter has nothing to read.
for component in hooks bin commands agents skills .mcp.json; do
    if [ -e "${REPO_ROOT}/${component}" ]; then
        cp -R "${REPO_ROOT}/${component}" "${STAGING}/"
    fi
done

"${CLI[@]}" "${STAGING}" --strict

echo
echo "==> both manifests valid"
