import type { Metadata } from "next";

import { Code, Section } from "@/components/primitives";

export const metadata: Metadata = {
  title: "Docs",
  description: "Install Zence, describe a boundary, and check that it works.",
  alternates: { canonical: "/docs/" },
};

// A lookup, not an interpolated class name. Tailwind extracts class names
// statically, so `text-${decision}` would produce nothing at all.
const DECISION_STYLE: Record<string, string> = {
  allow: "text-allow",
  ask: "text-ask",
  deny: "text-deny",
};

const RULES: [string, string, string][] = [
  ["ZR-001", "deny", "Cross-client asset carrying PII"],
  ["ZR-002", "ask", "Cross-client read of an unclassified asset"],
  ["ZR-003", "deny", "Write to another client's asset"],
  ["ZR-004", "ask", "Mutation in production"],
  ["ZR-005", "deny", "Destructive operation in production"],
  ["ZR-006", "ask", "Asset marked deprecated in DataHub"],
  ["ZR-007", "ask", "Sensitive asset with no owner recorded"],
  ["ZR-008", "ask", "Change reaching a critical downstream asset"],
  ["ZR-009", "allow", "In-boundary read in a permitted environment"],
  ["ZR-010", "allow", "In-boundary code generation, nothing sensitive"],
  ["ZR-011", "ask", "Unresolvable asset during a write"],
  ["ZR-014", "deny", "Edit to Zence or hook configuration"],
];

export default function DocsPage() {
  return (
    <>
      <section className="mx-auto max-w-5xl px-5 py-16 sm:py-20">
        <h1 className="max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
          Documentation
        </h1>
        <p className="mt-5 max-w-2xl text-pretty text-muted">
          The short version lives here. Reference material —{" "}
          <a className="underline underline-offset-4" href="https://github.com/AmirmLotfy/zence/blob/main/docs/POLICY_ENGINE.md">
            the policy engine
          </a>
          ,{" "}
          <a className="underline underline-offset-4" href="https://github.com/AmirmLotfy/zence/blob/main/docs/THREAT_MODEL.md">
            the threat model
          </a>
          ,{" "}
          <a className="underline underline-offset-4" href="https://github.com/AmirmLotfy/zence/blob/main/docs/DATAHUB_INTEGRATION.md">
            DataHub integration
          </a>{" "}
          — is in the repository, next to the code it describes.
        </p>
      </section>

      <Section id="requirements" eyebrow="Before you start" title="What you need">
        <div className="scroll-x rounded-lg border border-rule bg-surface">
          <table className="w-full text-sm">
            <caption className="sr-only">Requirements</caption>
            <tbody className="text-muted">
              {[
                ["Python", "3.11 or later, managed by uv"],
                ["uv", "The only hard prerequisite — the plugin's hook shim uses it"],
                ["Claude Code", "2.1.x"],
                ["DataHub", "OSS/Core. datahub docker quickstart needs ~8 GB RAM and 13 GB disk"],
                ["OS", "macOS or Linux"],
              ].map(([label, detail]) => (
                <tr key={label} className="border-b border-rule last:border-0">
                  <th scope="row" className="p-3 text-left font-medium text-fg">{label}</th>
                  <td className="p-3">{detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="install" eyebrow="Step 1" title="Install the plugin">
        <Code caption="You are prompted for your DataHub URL and token at enable time. The token goes to your system keychain, never to a file.">
{`/plugin marketplace add AmirmLotfy/zence
/plugin install zence@zence`}
        </Code>
      </Section>

      <Section id="boundary" eyebrow="Step 2" title="Describe the boundary">
        <Code caption="Run this in each client repository.">
{`zence init --client "Northstar Commerce" \\
           --domain "urn:li:domain:northstar-commerce"`}
        </Code>
        <p className="mt-5 max-w-2xl text-muted">
          This writes <code className="whitespace-nowrap font-mono text-sm">.zence/policy.yaml</code>{" "}
          in <strong className="text-fg">audit mode</strong>: every
          decision is evaluated and recorded, nothing is blocked. Watch it for a
          few days, then switch to <code className="whitespace-nowrap font-mono text-sm">enforce</code>.
          Blocking a team&rsquo;s work on day one is how a guardrail gets
          uninstalled.
        </p>
      </Section>

      <Section id="verify" eyebrow="Step 3" title="Check that it works">
        <Code caption="`evaluate` runs the real engine over a hypothetical call, so you can test a policy without provoking a violation. Its exit code carries the verdict — 0 allow, 6 deny, 7 ask — so CI can assert a rule still fires.">
{`zence doctor          # uv, workspace, token, catalog reachability
zence status          # which boundary this repository is bound to
zence inspect northstar.marketing_leads

zence evaluate --tool Write --file models/x.sql \\
  --content "SELECT email FROM bluepeak.patient_contacts"`}
        </Code>
      </Section>

      <Section
        id="rules"
        eyebrow="Reference"
        title="The twelve built-in rules"
        lede="Inherited automatically. A workspace rule sharing an id replaces the built-in one, so a single rule can be retuned without forking all of them."
      >
        <div className="scroll-x rounded-lg border border-rule bg-surface">
          <table className="w-full text-sm">
            <caption className="sr-only">Built-in policy rules</caption>
            <thead>
              <tr className="border-b border-rule text-left">
                <th scope="col" className="p-3 font-medium">Rule</th>
                <th scope="col" className="p-3 font-medium">Decision</th>
                <th scope="col" className="p-3 font-medium">Fires on</th>
              </tr>
            </thead>
            <tbody>
              {RULES.map(([id, decision, description]) => (
                <tr key={id} className="border-b border-rule last:border-0">
                  <th scope="row" className="p-3 text-left font-mono text-xs">{id}</th>
                  <td className={`p-3 ${DECISION_STYLE[decision]}`}>{decision}</td>
                  <td className="p-3 text-muted">{description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-sm text-muted">
          ZR-012 and ZR-013 are reserved for exception semantics — an active
          exception downgrading an ask, and an expired one having no effect. They
          live in the engine rather than the rule file, because putting a rule in
          a file that does not control the behaviour would be misleading.
        </p>
      </Section>

      <Section id="exceptions" eyebrow="Reference" title="Exceptions">
        <Code language="yaml" caption="Two constraints, both enforced at load time: the expiry is mandatory and must carry a timezone offset, and an exception may only target an ask rule. A deny cannot be waived in a policy file.">
{`exceptions:
  - rule_id: ZR-002
    scope:
      urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,shared.dim_date,PROD)"
    expires_at: "2026-12-31T23:59:59+02:00"
    approver: "you@example.com"
    reason: >-
      Shared date dimension. Lives in another domain for historical
      reasons and contains no client data.`}
        </Code>
      </Section>
    </>
  );
}
