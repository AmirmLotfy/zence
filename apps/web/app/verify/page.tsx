import type { Metadata } from "next";

import { Card, Code, Section } from "@/components/primitives";

export const metadata: Metadata = {
  title: "Verify",
  description:
    "Check every claim on this site yourself — no signup, no hosted service, nothing to trust.",
  alternates: { canonical: "/verify/" },
};

const REPO = "https://github.com/AmirmLotfy/zence";

function Row({
  label,
  href,
  children,
}: {
  label: string;
  href: string;
  children: React.ReactNode;
}) {
  return (
    <tr className="border-b border-rule last:border-0">
      <th scope="row" className="p-3 text-left align-top font-medium">
        <a className="underline underline-offset-4 hover:text-fg" href={href}>
          {label}
        </a>
      </th>
      <td className="p-3 align-top text-muted">{children}</td>
    </tr>
  );
}

export default function VerifyPage() {
  return (
    <>
      <section className="mx-auto max-w-5xl px-5 py-16 sm:py-20">
        <h1 className="max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
          Check it yourself
        </h1>
        <p className="mt-5 max-w-2xl text-pretty text-muted">
          There is no account to make, no service to sign up for, and nothing
          running that you have to trust. Everything below is a link into the
          repository or a command you can run in about a minute.
        </p>
      </section>

      <Section
        id="one-minute"
        eyebrow="One minute"
        title="See a real decision, with nothing installed but uv"
        lede="The demo workspace ships a recording captured from a live DataHub instance, so a fresh clone produces the real thing — no Docker, no catalog, no waiting."
      >
        <Code caption="Exit code 6 is a denial. 0 is allow, 7 is approval-required — so this is scriptable, and CI can assert a rule still fires.">
{`git clone ${REPO} && cd zence
uv sync --all-packages

uv run zence evaluate --tool Write --file models/blend.sql \\
  --content "SELECT l.email, p.phone
             FROM northstar.marketing_leads l
             JOIN bluepeak.patient_contacts p ON p.email = l.email" \\
  -C examples/clients/northstar-analytics`}
        </Code>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <Card title="What you should see">
            <code className="whitespace-nowrap font-mono text-xs">
              ✗ DENY ZR-001
            </code>{" "}
            naming <code className="font-mono text-xs">email</code>,{" "}
            <code className="font-mono text-xs">phone</code> and{" "}
            <code className="font-mono text-xs">postcode</code> as
            classified at column level, with the DataHub URN as evidence and an
            in-domain alternative offered.
          </Card>
          <Card title="Where that came from">
            A recording, captured by <code className="font-mono text-xs">zence
            demo record</code> from a live DataHub instance. Every decision it
            produces reports{" "}
            <code className="whitespace-nowrap font-mono text-xs">
              provider: fixture
            </code>{" "}
            — a recording can never pass itself off as a live read.
          </Card>
        </div>
      </Section>

      <Section
        id="ten-minutes"
        eyebrow="Ten minutes"
        title="Run it against your own DataHub"
        lede="Everything above, against a catalog you control. Setting DATAHUB_GMS_URL takes precedence over the recording."
      >
        <Code caption="`demo verify` re-reads every entity through the same provider a hook uses and exits non-zero on the first gap — it is how the tag-reading bug in this project was caught.">
{`datahub docker quickstart          # ~8 GB RAM, 13 GB disk
export DATAHUB_GMS_URL=http://localhost:8080

uv run zence demo seed
uv run zence demo verify
uv run pytest -m integration       # 15 tests against the live catalog`}
        </Code>
      </Section>

      <Section
        id="in-claude-code"
        eyebrow="The real thing"
        title="Install the plugin and try to break the boundary"
      >
        <Code caption="Then open Claude Code in examples/clients/northstar-analytics and ask it to join the Northstar leads with the BluePeak patient contacts.">
{`/plugin marketplace add AmirmLotfy/zence
/plugin install zence@zence`}
        </Code>
      </Section>

      <Section
        id="sources"
        eyebrow="Straight to the source"
        title="Every claim, and where it lives"
      >
        <div className="scroll-x rounded-lg border border-rule bg-surface">
          <table className="w-full text-sm">
            <caption className="sr-only">Links into the repository</caption>
            <tbody>
              <Row label="The decision engine" href={`${REPO}/blob/main/packages/zence-core/src/zence_core/policy/engine.py`}>
                Precedence, and why tamper is checked before everything else.
              </Row>
              <Row label="The fail-safe matrix" href={`${REPO}/blob/main/packages/zence-core/src/zence_core/policy/defaults.py`}>
                What happens when no rule matched — the part worth reading twice.
              </Row>
              <Row label="The twelve rules" href={`${REPO}/blob/main/packages/zence-core/src/zence_core/policy/builtin_rules.yaml`}>
                Policy as data. No expression language, no eval.
              </Row>
              <Row label="The DataHub provider" href={`${REPO}/blob/main/packages/zence-core/src/zence_core/providers/live.py`}>
                Including the association-object bug that only a live catalog revealed.
              </Row>
              <Row label="Hook wire format" href={`${REPO}/blob/main/tests/contract/test_hook_protocol.py`}>
                28 tests asserting the exact shape Claude Code acts on.
              </Row>
              <Row label="Adversarial tests" href={`${REPO}/blob/main/tests/security/test_hostile_input.py`}>
                Hostile policies, injected metadata, ReDoS, credential leakage.
              </Row>
              <Row label="Live DataHub tests" href={`${REPO}/blob/main/tests/integration/test_live_datahub.py`}>
                The four scenarios and idempotent write-back, against a real catalog.
              </Row>
              <Row label="Decision artifacts" href={`${REPO}/tree/main/examples/artifacts/decisions`}>
                The JSON rendered on the demo page. Not written by hand.
              </Row>
              <Row label="The demo catalog" href={`${REPO}/blob/main/demo/catalog/catalog.yaml`}>
                Two fictional clients, shaped so each rule has a realistic asset.
              </Row>
              <Row label="Clean-room verification" href={`${REPO}/blob/main/scripts/verify-clean-clone.sh`}>
                Clones the published repo and runs a reviewer&rsquo;s setup from nothing.
              </Row>
              <Row label="Threat model" href={`${REPO}/blob/main/docs/THREAT_MODEL.md`}>
                What Zence is not, and one accepted risk with its reasoning.
              </Row>
              <Row label="Build status" href={`${REPO}/blob/main/TASKS.md`}>
                What is verified, and against what.
              </Row>
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        id="honest"
        eyebrow="Worth knowing"
        title="Two things we would rather say than have you find"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Card title="There is no hosted catalog">
            Zence runs entirely on your machine, so there is no Zence server to
            be down and no demo instance to expire. That also means the
            live-DataHub path needs a catalog you start yourself — the recording
            exists precisely so that is optional rather than required.
          </Card>
          <Card title="The clients are fictional">
            Northstar Commerce and BluePeak Health do not exist. The decisions
            about them are real output from the engine; the companies, datasets
            and people are invented, because a tool about not leaking client
            data should not ship anyone&rsquo;s.
          </Card>
        </div>
      </Section>
    </>
  );
}
