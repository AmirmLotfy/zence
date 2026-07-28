import type { Metadata } from "next";

import { Card, Code, Section } from "@/components/primitives";

export const metadata: Metadata = {
  title: "Architecture",
  description: "How Zence is put together, and why each piece is where it is.",
};

export default function ArchitecturePage() {
  return (
    <>
      <section className="mx-auto max-w-5xl px-5 py-16 sm:py-20">
        <h1 className="max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
          Architecture
        </h1>
        <p className="mt-5 max-w-2xl text-pretty text-muted">
          A hook process, a deterministic engine, and two ways of reading the
          catalog. Everything runs on your machine; there is no Zence service.
        </p>
      </section>

      <Section id="flow" eyebrow="The path" title="What happens on a tool call">
        <Code caption="Claude Code invokes bin/zence-hook for each event. Warm calls take 0.6–0.8s against a 2.5s budget.">
{`Claude Code session in ~/clients/northstar-analytics/
  │
  ├─ SessionStart ──────► resolve boundary ──► inject context + session title
  ├─ UserPromptSubmit ──► classify intent (never decides on prose alone)
  ├─ PreToolUse ────────► normalize ─ extract ─ resolve ─ evaluate ─ decide
  │      matchers: mcp__.*datahub.*__.*  |  Bash  |  Write|Edit|NotebookEdit
  │                             │
  │                             ├─ LiveProvider ──► DataHub GMS (SDK, cached)
  │                             └─ decision ─────► local audit
  ├─ PostToolUse ───────► record outcome against the decision
  └─ Stop / SessionEnd ─► finalize ──► DataHub document (idempotent upsert)`}
        </Code>
      </Section>

      <Section
        id="decisions"
        eyebrow="Choices"
        title="Three decisions that shaped everything else"
      >
        <div className="space-y-4">
          <Card title="The MCP server is the interception surface; the SDK is the enforcement path">
            Claude reads the catalog through the DataHub MCP server, so that is
            where a cross-client lookup first becomes visible — and what the
            PreToolUse matcher keys on. Zence&rsquo;s own evidence lookups go
            through the Python SDK instead, because a hook cannot borrow the
            agent&rsquo;s MCP connection, and enforcement needs typed aspects
            rather than text shaped for a model to read.
          </Card>
          <Card title="Policy is data, not code">
            A rule is a set of field/predicate pairs ANDed together. There is no
            expression language and no eval, so a policy file cannot execute
            anything. Field paths are an allowlist: a typo is rejected at load
            time rather than silently evaluating to null — which, for a
            not_in predicate, would quietly invert the rule.
          </Card>
          <Card title="Fixtures are recorded, never written">
            The same interface serves a live DataHub and a recorded snapshot, and
            they are never silently interchanged: every piece of evidence carries
            which produced it, and that value reaches the decision and the audit
            record. A fixture is created only by capturing real responses.
          </Card>
        </div>
      </Section>

      <Section id="layout" eyebrow="Repository" title="Where things live">
        <Code>
{`packages/zence-core/     policy engine, providers, extraction, hooks
packages/zence-cli/      the zence command
bin/zence-hook           POSIX shim — bootstraps a venv, fails safe
hooks/hooks.json         hook wiring
.claude-plugin/          plugin + marketplace manifests
demo/catalog/            the synthetic two-client catalog
examples/clients/        two workspaces with opposite boundaries
examples/artifacts/      real decisions, rendered on this site`}
        </Code>
      </Section>
    </>
  );
}
