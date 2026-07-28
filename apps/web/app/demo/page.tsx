import type { Metadata } from "next";

import { SCENARIOS } from "../_data/scenarios";
import { Section, SyntheticNotice } from "@/components/primitives";
import { ScenarioTabs } from "@/components/replay";

export const metadata: Metadata = {
  title: "Demo",
  description:
    "Six real Zence decisions, recorded from actual runs against the synthetic demo catalog.",
};

export default function DemoPage() {
  return (
    <>
      <section className="mx-auto max-w-5xl px-5 py-16 sm:py-20">
        <h1 className="max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
          Six decisions, as they actually came out
        </h1>
        <p className="mt-5 max-w-2xl text-pretty text-muted">
          Each panel renders a JSON artifact produced by{" "}
          <code className="whitespace-nowrap font-mono text-sm">zence evaluate --json</code> and
          copied into this site by a build step. The verdicts, rule ids,
          evidence URNs and remediation text are the engine&rsquo;s own words.
        </p>
        <div className="mt-8">
          <SyntheticNotice />
        </div>
      </section>

      <Section id="scenarios">
        <ScenarioTabs scenarios={SCENARIOS} />
      </Section>

      <Section
        id="reproduce"
        eyebrow="Reproduce it"
        title="None of this requires taking our word for it"
        lede="Clone the repository, start DataHub, seed the synthetic catalog, and run the same commands. The artifacts you get should match the ones on this page."
      >
        <div className="scroll-x rounded-lg border border-rule bg-surface">
          <pre className="p-4 font-mono text-[13px] leading-relaxed">
{`git clone https://github.com/AmirmLotfy/zence && cd zence
uv sync --all-packages --extra datahub

datahub docker quickstart          # needs ~8 GB RAM
uv run zence demo seed
uv run zence demo verify           # exits non-zero on any gap

uv run zence evaluate --tool Write --file models/blend.sql \\
  --content "SELECT l.email, p.phone
             FROM northstar.marketing_leads l
             JOIN bluepeak.patient_contacts p ON p.email = l.email" \\
  -C examples/clients/northstar-analytics --json`}
          </pre>
        </div>
      </Section>
    </>
  );
}
