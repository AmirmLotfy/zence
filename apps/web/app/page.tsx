import type { Metadata } from "next";
import Link from "next/link";

import { FEATURED } from "./_data/scenarios";
import { Card, Code, Section, SyntheticNotice, VerdictBadge } from "@/components/primitives";
import { ScenarioTabs } from "@/components/replay";

// Title and description come from the root layout; this exists to name the
// canonical URL. The deployment also answers on a *.vercel.app hostname, and
// two live copies of the same page should not compete with each other.
export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

export default function Home() {
  return (
    <>
      {/* Hero */}
      <section className="mx-auto max-w-5xl px-5 py-20 sm:py-28">
        <p className="font-mono text-xs uppercase tracking-widest text-muted">
          Open source · Apache-2.0
        </p>
        <h1 className="mt-5 max-w-3xl text-balance text-4xl font-semibold tracking-tight sm:text-6xl">
          Keep every client in bounds.
        </h1>
        <p className="mt-6 max-w-2xl text-pretty text-lg text-muted">
          Zence is a task-scoped policy firewall for Claude Code. It resolves the
          assets a tool call touches against DataHub, and refuses the ones that
          belong to a different client — before the call runs.
        </p>

        <div className="mt-9 flex flex-wrap gap-3">
          <Link
            href="/demo/"
            className="rounded-md bg-fg px-5 py-2.5 text-sm font-medium text-bg"
          >
            See a real decision
          </Link>
          <Link
            href="/verify/"
            className="rounded-md border border-rule px-5 py-2.5 text-sm font-medium hover:border-fg"
          >
            Check it yourself
          </Link>
          <a
            href="https://github.com/AmirmLotfy/zence"
            className="rounded-md border border-rule px-5 py-2.5 text-sm font-medium hover:border-fg"
          >
            View source
          </a>
        </div>

        <p className="mt-6 max-w-xl text-sm text-muted">
          Apache-2.0. Runs entirely on your machine — no account, no hosted
          service, nothing to sign up for.
        </p>
      </section>

      {/* The problem */}
      <Section
        id="problem"
        eyebrow="The problem"
        title="Every individual step is valid. The mistake is the combination."
        lede="Freelancers, agencies and consultancies run Claude Code across several clients from one machine. Claude Code has no concept of which client is in scope right now."
      >
        <div className="grid gap-8 lg:grid-cols-[1.1fr_1fr]">
          <Code
            language="sql"
            caption="Valid SQL. Both tables exist. The developer has credentials for both. Nothing here is an error — until you know which client the repository belongs to."
          >
{`SELECT l.email, p.phone
FROM   northstar.marketing_leads  l   -- Client A  (you are here)
JOIN   bluepeak.patient_contacts  p   -- Client B  (you are not)
  ON   l.email = p.email`}
          </Code>

          <div className="space-y-4 text-muted">
            <p>
              A linter sees well-formed SQL. The warehouse sees an authorised
              user. The agent sees a reasonable way to answer the question it was
              asked.
            </p>
            <p>
              The only place this is visibly wrong is in the metadata: those two
              tables sit in different domains, and one of them carries personal
              data at column level.
            </p>
            <p className="text-fg">
              That is a question a catalog can answer. Zence asks it, on every
              tool call, before the call runs.
            </p>
          </div>
        </div>
      </Section>

      {/* Real decisions */}
      <Section
        id="decisions"
        eyebrow="Real output"
        title="Three decisions, unrolled"
        lede="Every field below is real output from zence evaluate --json, copied into this page by a build step. Nothing is a mock-up."
      >
        <div className="space-y-6">
          <SyntheticNotice />
          <ScenarioTabs scenarios={FEATURED} />
          <p className="text-sm text-muted">
            <Link href="/demo/" className="underline underline-offset-4">
              Three more scenarios →
            </Link>
          </p>
        </div>
      </Section>

      {/* Three decisions */}
      <Section
        id="verdicts"
        eyebrow="How it answers"
        title="Three outcomes, not two"
        lede="A tool that can only allow or block forces a choice between being useful and being safe. Most real situations are the middle one."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-allow bg-allow-soft p-5">
            <VerdictBadge verdict="allow" />
            <p className="mt-3 text-sm text-muted">
              In domain, permitted environment, nothing sensitive. The hook
              returns an empty response and the developer sees nothing at all.
            </p>
          </div>
          <div className="rounded-lg border border-ask bg-ask-soft p-5">
            <VerdictBadge verdict="ask" />
            <p className="mt-3 text-sm text-muted">
              Production, deprecated, unowned, or something a critical dashboard
              depends on. You decide; both outcomes are recorded.
            </p>
          </div>
          <div className="rounded-lg border border-deny bg-deny-soft p-5">
            <VerdictBadge verdict="deny" />
            <p className="mt-3 text-sm text-muted">
              Cross-client PII, cross-client writes, destructive production
              operations. Blocked before execution, with the evidence.
            </p>
          </div>
        </div>

        <p className="mt-8 max-w-2xl text-muted">
          When Zence cannot reach DataHub, it does not fall back to allowing. An
          operation it cannot verify becomes an{" "}
          <span className="text-fg">ask</span>, and it says that the
          catalog was unreachable rather than implying the asset was clean.
        </p>
      </Section>

      {/* How it works */}
      <Section
        id="how"
        eyebrow="How it works"
        title="A hook, a catalog, and a deterministic engine"
        lede="Claude Code runs Zence before each tool call. Six steps, none of which involve asking a model whether something is allowed."
      >
        <ol className="grid gap-4 sm:grid-cols-2">
          {[
            ["Normalize", "The tool call becomes an action with an intent — read, write, mutate, destructive."],
            ["Extract", "SQL through a real parser, plus dbt, shell, YAML recipes and MCP arguments. CTEs and aliases are excluded; columns are attributed through aliases."],
            ["Resolve", "Each reference is looked up in DataHub: domain, owners, tags, glossary terms, lifecycle, schema, and two hops of downstream lineage."],
            ["Evaluate", "Rules are field/predicate pairs over that evidence. No expression language, no eval, no model in the decision path."],
            ["Decide", "Exactly one of allow, ask, deny — with the rule that fired, the evidence, and a remediation."],
            ["Record", "The decision is logged, and written back to DataHub as a durable document at session end."],
          ].map(([title, body], index) => (
            <li key={title} className="rounded-lg border border-rule bg-surface p-5">
              <p className="font-mono text-xs text-muted">
                {String(index + 1).padStart(2, "0")}
              </p>
              <h3 className="mt-1 font-medium">{title}</h3>
              <p className="mt-2 text-sm text-muted">{body}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* DataHub */}
      <Section
        id="datahub"
        eyebrow="DataHub"
        title="The catalog is the source of truth, on both the read and the write path"
        lede="Zence has no opinions of its own about your data. Everything it enforces is something DataHub already knows."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Card title="Read">
            Domain and ownership, dataset and column-level tags, glossary terms,
            lifecycle and deprecation status, schema fields, and two hops of
            downstream lineage — which is what makes a lineage-aware approval a
            real decision rather than a configured constant.
          </Card>
          <Card title="Write">
            At session end Zence upserts a decision document linked to the assets
            involved, plus a <code className="font-mono text-xs">zence.last_review</code>{" "}
            structured property. The document id is deterministic, so finalizing
            twice updates the record instead of duplicating it.
          </Card>
        </div>

        <p className="mt-8 max-w-2xl text-muted">
          The <strong className="text-fg">DataHub MCP Server</strong> is
          the surface Zence intercepts — it is how Claude reads the catalog, so it
          is where a cross-client lookup shows up first. Zence&rsquo;s own evidence
          lookups go through the DataHub Python SDK, because a hook must be
          deterministic and cannot borrow the agent&rsquo;s MCP connection.
        </p>
      </Section>

      {/* Install */}
      <Section
        id="install"
        eyebrow="Install"
        title="Two commands, then a policy file"
        lede="Zence needs uv, Claude Code, and a DataHub instance. Nothing else, and no hosted service."
      >
        <div className="space-y-6">
          <Code caption="Add the marketplace and install the plugin.">
{`/plugin marketplace add AmirmLotfy/zence
/plugin install zence@zence`}
          </Code>
          <Code caption="Then, in each client repository, describe its boundary. Starts in audit mode — nothing is blocked until you switch to enforce.">
{`zence init --client "Northstar Commerce" \\
           --domain "urn:li:domain:northstar-commerce"`}
          </Code>

          <p className="text-muted">
            Want to see a real decision before installing anything?{" "}
            <Link href="/verify/" className="underline underline-offset-4">
              One command, about a minute
            </Link>{" "}
            — the demo workspace ships a recording from a live DataHub instance,
            so a fresh clone produces the real output with no catalog running.
          </p>
        </div>
      </Section>

      {/* Boundary */}
      <Section
        id="boundary"
        eyebrow="What it is not"
        title="The honest limits"
        lede="Zence reduces accidental and agent-mediated mistakes inside the Claude Code workflow. That is a real thing to be, and it is not the same as being a sandbox."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Card title="Out of scope">
            Anything outside Claude Code. A user running the same query in a
            shell, a notebook, or a BI tool is not intercepted, and Zence does not
            pretend otherwise.
          </Card>
          <Card title="Not a substitute">
            Correct grants in your warehouse remain the first line of defence.
            Zence is the second one — the one that catches the mistake nobody
            meant to make.
          </Card>
        </div>

        <p className="mt-8">
          <Link href="/security/" className="underline underline-offset-4">
            The full threat model →
          </Link>
        </p>
      </Section>
    </>
  );
}
