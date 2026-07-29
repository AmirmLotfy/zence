import type { Metadata } from "next";

import { Card, Section } from "@/components/primitives";

export const metadata: Metadata = {
  title: "Security",
  description:
    "What Zence protects against, what it explicitly does not, and how it behaves when it cannot see.",
  alternates: { canonical: "/security/" },
};

const THREATS: [string, string][] = [
  [
    "Prompt injection via catalog metadata",
    "A dataset description is data, not instructions. Metadata is rendered as quoted, length-bounded text with newlines collapsed, and policy decisions read typed fields only — never free text.",
  ],
  [
    "Untrusted MCP output",
    "Responses are schema-validated. An unexpected shape routes to ask rather than being parsed optimistically.",
  ],
  [
    "Token theft",
    "The DataHub token lives in the system keychain via the plugin's userConfig, is never written to a workspace file, never logged, and never printed by the CLI. A test asserts it.",
  ],
  [
    "Path traversal and symlinks",
    "Containment is checked after full resolution, so ../../etc/passwd and a file symlinked to .zence/policy.yaml are both caught. A path Zence cannot locate is treated as tampering.",
  ],
  [
    "Shell injection",
    "Commands are parsed with shlex and never executed. Zence reads them the way a linter does.",
  ],
  [
    "Disabling Zence from inside a session",
    "Edits to .zence/** and to Claude Code's hook configuration are denied, and that rule is triggered by a hardcoded flag rather than a policy condition — so it survives audit mode and cannot be waived by an exception.",
  ],
  [
    "Duplicate or replayed write-back",
    "The DataHub document id is derived deterministically, so finalizing twice updates one record rather than creating two.",
  ],
  [
    "Failing open on an outage",
    "The failure this project exists to prevent. A transport error is never reported as 'not in the catalog', and a rule that reads asset properties will not fire against evidence that failed to resolve.",
  ],
];

export default function SecurityPage() {
  return (
    <>
      <section className="mx-auto max-w-5xl px-5 py-16 sm:py-20">
        <h1 className="max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
          Security
        </h1>
        <p className="mt-5 max-w-2xl text-pretty text-muted">
          A security tool that overstates its boundary is worse than none,
          because people rely on the part that was never true.
        </p>
      </section>

      <Section
        id="boundary"
        eyebrow="Trust boundary"
        title="What Zence is, stated precisely"
      >
        <p className="max-w-2xl text-lg">
          Zence reduces <strong>accidental and agent-mediated mistakes inside
          the supported Claude Code workflow</strong>. It is not a kernel
          sandbox, not an endpoint security product, and not a substitute for
          warehouse permissions.
        </p>

        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          <Card title="Not intercepted">
            The same query run in a shell, a notebook, or a BI tool. Zence sits
            in Claude Code&rsquo;s hook path and nowhere else.
          </Card>
          <Card title="Not tamper-proof">
            Policy files live in the workspace. Zence refuses edits from inside a
            governed session and audits the attempt, but it does not defend
            against someone editing them out of band.
          </Card>
          <Card title="Not your first line">
            Correct grants in Snowflake or BigQuery remain the primary control.
            Zence catches what those cannot: a mistake made by someone who does
            have access.
          </Card>
        </div>
      </Section>

      <Section
        id="failsafe"
        eyebrow="When it cannot see"
        title="Ignorance never becomes permission"
        lede="If a lookup fails, if a reference will not resolve, if an asset sits outside the boundary and no rule happened to cover it — the answer is ask, not allow."
      >
        <div className="scroll-x rounded-lg border border-rule bg-surface">
          <table className="w-full text-sm">
            <caption className="sr-only">Fail-safe behaviour by situation</caption>
            <thead>
              <tr className="border-b border-rule text-left">
                <th scope="col" className="p-3 font-medium">Situation</th>
                <th scope="col" className="p-3 font-medium">Result</th>
              </tr>
            </thead>
            <tbody className="text-muted">
              {[
                ["Explicit high-risk violation", "deny"],
                ["DataHub unreachable during a data operation", "ask, and it says the catalog was unreachable"],
                ["DataHub unreachable, no assets referenced", "allow, flagged as degraded"],
                ["Asset named but unresolvable, during a write", "ask"],
                ["Resolved, outside the boundary, no rule matched", "ask"],
                ["The hook itself crashes or times out", "ask on data-touching tools; quiet on a local read"],
                ["Cross-client reference with a failed lookup", "ask, never allow"],
              ].map(([situation, result]) => (
                <tr key={situation} className="border-b border-rule last:border-0">
                  <th scope="row" className="p-3 text-left font-normal">{situation}</th>
                  <td className="p-3">{result}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-6 max-w-2xl text-muted">
          A crash is answered with <em>ask</em> only for tools that can touch
          data. Failing closed on everything would make a Zence bug
          indistinguishable from a policy violation, and train people to click
          through prompts — which is how a guardrail stops working.
        </p>
      </Section>

      <Section id="threats" eyebrow="Threat model" title="Specific threats">
        <dl className="space-y-5">
          {THREATS.map(([threat, mitigation]) => (
            <div key={threat} className="border-l-2 border-rule pl-5">
              <dt className="font-medium">{threat}</dt>
              <dd className="mt-1 text-sm text-muted">{mitigation}</dd>
            </div>
          ))}
        </dl>

        <p className="mt-10 text-sm text-muted">
          Report a vulnerability through{" "}
          <a
            className="underline underline-offset-4 hover:text-fg"
            href="https://github.com/AmirmLotfy/zence/security/advisories/new"
          >
            a private GitHub advisory
          </a>
          , not a public issue.
        </p>
      </Section>
    </>
  );
}
