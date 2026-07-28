import type { Metadata } from "next";

import { Card, Code, Section } from "@/components/primitives";

export const metadata: Metadata = {
  title: "Open source",
  description: "Apache-2.0, built in the open for the DataHub Agent Hackathon.",
};

export default function OpenSourcePage() {
  return (
    <>
      <section className="mx-auto max-w-5xl px-5 py-16 sm:py-20">
        <h1 className="max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
          Open source
        </h1>
        <p className="mt-5 max-w-2xl text-pretty text-muted">
          Apache-2.0, developed in the open, and built for{" "}
          <a
            className="underline underline-offset-4"
            href="https://datahub.devpost.com/"
          >
            Build with DataHub: The Agent Hackathon
          </a>
          .
        </p>
      </section>

      <Section id="contributing" eyebrow="Contributing" title="The ground rules">
        <div className="grid gap-4 sm:grid-cols-2">
          <Card title="Never fake an integration">
            A fixture may stand in for DataHub in a test. It must never be
            presented as a live connection at runtime.
          </Card>
          <Card title="The engine stays deterministic">
            A model may help classify intent. It must never be the thing that
            decides allow, ask, or deny.
          </Card>
          <Card title="Fail safe, not open">
            Any new code path that can fail needs a documented decision for the
            failure case, and a test asserting it.
          </Card>
          <Card title="Extractors need false-positive tests">
            An extractor that over-reports causes approval fatigue, which is its
            own failure mode. Precision is a safety property here.
          </Card>
        </div>
      </Section>

      <Section id="run" eyebrow="Locally" title="Working on it">
        <Code caption="Most of the codebase runs without DataHub — unit and hook contract tests use recorded fixtures.">
{`git clone https://github.com/AmirmLotfy/zence && cd zence
uv sync --all-packages
uv run pytest -m "not integration and not e2e"
uv run ruff check . && uv run mypy`}
        </Code>
      </Section>

      <Section id="disclosure" eyebrow="Disclosure" title="How this was built">
        <p className="max-w-2xl text-muted">
          Zence was developed with AI assistance (Claude Code) during the
          hackathon submission period. No pre-existing project code was
          incorporated; third-party frameworks and libraries are declared in{" "}
          <code className="whitespace-nowrap font-mono text-sm">pyproject.toml</code> and{" "}
          <code className="whitespace-nowrap font-mono text-sm">package.json</code>. The fictional
          clients, datasets and people in the demo catalog are synthetic.
        </p>
      </Section>
    </>
  );
}
