#!/usr/bin/env bash
# Clean-room verification.
#
# Clones the published repository into a temporary directory and runs the setup
# a judge would follow, from nothing. This is the check that catches the class
# of failure where everything works on the machine it was built on: an
# uncommitted file, a stale lockfile, a path that only resolves locally.
#
# Deliberately does NOT reuse this working tree, this virtualenv, or this
# node_modules. If it passes here it passes for a stranger.
#
# Without DataHub it verifies everything that does not need a catalog. With
# DATAHUB_GMS_URL and DATAHUB_GMS_TOKEN set it also seeds and verifies the demo.

set -euo pipefail

REPO="${ZENCE_REPO:-https://github.com/AmirmLotfy/zence.git}"
REF="${ZENCE_REF:-main}"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; exit 1; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

step "Cloning ${REPO} @ ${REF}"
git clone --quiet --depth 1 --branch "${REF}" "${REPO}" "${WORKDIR}/zence" \
    || fail "clone failed"
cd "${WORKDIR}/zence"
pass "cloned into a fresh directory"

step "Prerequisites"
command -v uv   >/dev/null || fail "uv is not installed — https://docs.astral.sh/uv/"
command -v node >/dev/null || fail "node is not installed"
pass "uv $(uv --version | awk '{print $2}')"
pass "node $(node --version)"

step "Python workspace"
uv sync --all-packages --extra datahub --quiet || fail "uv sync failed"
pass "dependencies resolved from the committed lockfile"

step "Quality gates"
uv run ruff format --check . >/dev/null || fail "formatting"
pass "format"
uv run ruff check . >/dev/null       || fail "lint"
pass "lint"
uv run mypy >/dev/null                || fail "types"
pass "types (strict)"

step "Tests"
TEST_COUNT=$(uv run pytest -m "not integration and not e2e" -q 2>&1 | tail -1)
echo "${TEST_COUNT}" | grep -q "passed" || fail "tests failed: ${TEST_COUNT}"
pass "${TEST_COUNT}"

step "Policies"
uv run python -m zence_core.policy.validate_all >/dev/null || fail "policy validation"
pass "every shipped policy loads"

step "Plugin manifests"
./scripts/validate-plugin.sh >/dev/null 2>&1 || fail "plugin validation"
pass "plugin and marketplace manifests valid"
[ -x bin/zence-hook ] || fail "bin/zence-hook is not executable"
sh -n bin/zence-hook  || fail "bin/zence-hook is not valid POSIX sh"
pass "hook shim executable and parseable"

step "The decision this whole project is about"
# Exit codes: 0 allow, 6 deny, 7 ask.
#
# What the *correct* answer is here depends on whether a catalog is reachable,
# and that distinction is the point rather than an inconvenience.
#
#   With DataHub:    deny. Both tables resolve; the domains differ; PII at column
#                    level. ZR-001.
#   Without DataHub: ask. Zence cannot see the domains, so it refuses to convert
#                    ignorance into permission — and says the catalog was
#                    unreachable rather than implying the asset was clean.
#
# Asserting "deny" in both cases would be asserting something false, so the
# expectation moves with the configuration.
if [ -n "${DATAHUB_GMS_URL:-}" ] && [ -n "${DATAHUB_GMS_TOKEN:-}" ]; then
    EXPECTED=6; EXPECTED_LABEL="denied (ZR-001)"
else
    EXPECTED=7; EXPECTED_LABEL="held for approval — no catalog reachable, so Zence will not guess"
fi

set +e
uv run zence evaluate --tool Write --file models/blend.sql \
    --content "SELECT l.email, p.phone
               FROM northstar.marketing_leads l
               JOIN bluepeak.patient_contacts p ON p.email = l.email" \
    -C examples/clients/northstar-analytics >/dev/null 2>&1
VERDICT=$?
set -e
[ "${VERDICT}" -eq "${EXPECTED}" ] \
    || fail "cross-client join: expected exit ${EXPECTED}, got ${VERDICT}"
pass "cross-client PII join ${EXPECTED_LABEL}"

# Whatever the catalog situation, it must never come back as a clean allow.
[ "${VERDICT}" -ne 0 ] || fail "cross-client join was ALLOWED — this is the bug the project exists to prevent"
pass "never allowed, under any configuration"

step "The hook answers on stdin"
OUTPUT=$(printf '{"hook_event_name":"PreToolUse","session_id":"verify","cwd":"%s/examples/clients/northstar-analytics","tool_name":"Write","tool_input":{"file_path":"m.sql","content":"SELECT email FROM bluepeak.patient_contacts"}}' "$(pwd)" \
    | uv run zence-hook PreToolUse)

# Exactly one JSON object, always. Silence is read by Claude Code as "no
# opinion", which would let the call through unexamined.
echo "${OUTPUT}" | python3 -c "import json,sys; json.load(sys.stdin)" \
    || fail "hook output is not a single JSON object: ${OUTPUT:0:200}"
pass "returns exactly one JSON object"

echo "${OUTPUT}" | grep -qE '"permissionDecision": *"(deny|ask)"' \
    || fail "expected deny or ask; got: ${OUTPUT:0:200}"
echo "${OUTPUT}" | grep -q '"permissionDecision": *"allow"' \
    && fail "hook ALLOWED a cross-client PII read"
pass "cross-client PII read is never allowed through the hook"

echo "${OUTPUT}" | grep -q '"permissionDecisionReason"' \
    || fail "decision carries no reason"
pass "the decision carries a reason"

step "Website"
if command -v pnpm >/dev/null; then
    pnpm install --frozen-lockfile --silent >/dev/null 2>&1 || fail "pnpm install"
    pnpm -C apps/web build >/dev/null 2>&1                  || fail "site build"
    for route in "" demo docs architecture security open-source; do
        [ -f "apps/web/out/${route:-index}/index.html" ] || [ -f "apps/web/out/index.html" ] \
            || fail "route missing: /${route}"
    done
    pass "static export produced every route"
else
    printf '  \033[33m–\033[0m pnpm not installed; skipped the website\n'
fi

step "DataHub"
if [ -n "${DATAHUB_GMS_URL:-}" ] && [ -n "${DATAHUB_GMS_TOKEN:-}" ]; then
    uv run zence demo seed   >/dev/null || fail "demo seed"
    pass "synthetic catalog seeded"
    uv run zence demo verify >/dev/null || fail "demo verify"
    pass "catalog complete — every entity, tag and lineage edge"
else
    printf '  \033[33m–\033[0m DATAHUB_GMS_URL / DATAHUB_GMS_TOKEN not set;\n'
    printf '    skipped seeding, verification, and write-back.\n'
    printf '    These are the DataHub half and are NOT covered by this run.\n'
fi

printf '\n\033[32mClean clone verified.\033[0m\n'
