"use client";

import { useId, useState } from "react";

import type { Scenario } from "@/app/_data/scenarios";
import { Code, VerdictBadge } from "./primitives";

/**
 * A decision, unrolled into the steps that produced it.
 *
 * Not an animation. Each step shows a real field from the artifact, so a reader
 * can check the claim rather than take the picture's word for it — which is the
 * whole argument the product is making.
 */
function Step({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="relative pl-10">
      <span
        aria-hidden="true"
        className="absolute left-0 top-0.5 flex h-6 w-6 items-center justify-center rounded-full border border-rule bg-surface font-mono text-xs text-muted"
      >
        {n}
      </span>
      <h4 className="text-sm font-medium">{title}</h4>
      <div className="mt-2 text-sm text-muted">{children}</div>
    </li>
  );
}

function Urn({ value }: { value: string }) {
  return (
    <code className="break-all font-mono text-[12px] text-fg">
      {value}
    </code>
  );
}

export function DecisionReplay({ scenario }: { scenario: Scenario }) {
  const { decision, references, intents } = scenario.artifact;

  return (
    <div className="rounded-lg border border-rule bg-surface">
      <div className="border-b border-rule p-5">
        <VerdictBadge verdict={decision.verdict} ruleId={decision.rule_id} />
        <h3 className="mt-3 font-medium">{decision.rule_title}</h3>
      </div>

      <ol className="space-y-7 p-5">
        <Step n={1} title="What the developer asked for">
          <p className="italic">“{scenario.prompt}”</p>
        </Step>

        <Step n={2} title={`What Claude tried — ${scenario.attempt.tool}`}>
          <Code language="sql">{scenario.attempt.detail}</Code>
        </Step>

        <Step n={3} title="What Zence extracted">
          <ul className="space-y-1">
            {references.length === 0 ? (
              <li>No catalog assets referenced.</li>
            ) : (
              references.map((reference) => (
                <li key={reference.raw_text} className="flex flex-wrap gap-2">
                  <code className="font-mono text-[12px] text-fg">
                    {reference.raw_text}
                  </code>
                  <span className="text-xs opacity-70">
                    {reference.confidence} confidence · {reference.extractor}
                  </span>
                </li>
              ))
            )}
          </ul>
          <p className="mt-2 text-xs opacity-70">
            intent: {intents.join(", ") || "none"}
          </p>
        </Step>

        <Step n={4} title="What DataHub said">
          {decision.evidence_urns.length ? (
            <ul className="space-y-1">
              {decision.evidence_urns.map((urn) => (
                <li key={urn}>
                  <Urn value={urn} />
                </li>
              ))}
            </ul>
          ) : (
            <p>No asset resolved, so there was nothing to look up.</p>
          )}

          {decision.matched_tags.length ? (
            <p className="mt-2">
              Classified{" "}
              <strong className="font-medium text-fg">
                {decision.matched_tags.join(", ")}
              </strong>
              {decision.matched_columns.length ? (
                <>
                  {" "}
                  · columns{" "}
                  <strong className="font-medium text-fg">
                    {decision.matched_columns.join(", ")}
                  </strong>{" "}
                  tagged at field level
                </>
              ) : null}
            </p>
          ) : null}

          {decision.downstream_critical.length ? (
            <p className="mt-2">
              Lineage reaches{" "}
              <strong className="font-medium text-fg">
                {decision.downstream_critical.length}
              </strong>{" "}
              asset(s) this workspace marked critical:{" "}
              {decision.downstream_critical.map((urn) => (
                <Urn key={urn} value={urn} />
              ))}
            </p>
          ) : null}
        </Step>

        <Step n={5} title={`Decision — ${decision.rule_id}`}>
          <p className="text-fg">{decision.reason}</p>
          <p className="mt-2 text-xs opacity-70">
            policy v{decision.policy_version} · {decision.mode} mode · risk{" "}
            {decision.risk} · via {decision.source.replace(/_/g, " ")}
          </p>
        </Step>

        {decision.remediation ? (
          <Step n={6} title="What Claude is told to do instead">
            <p>{decision.remediation}</p>
            <p className="mt-2 text-xs opacity-70">
              The remediation is the point. A bare refusal invites a retry with a
              variation; naming the alternative turns it into a redirect.
            </p>
          </Step>
        ) : null}
      </ol>

      <p className="border-t border-rule px-5 py-3 font-mono text-xs text-muted">
        Rendered from {scenario.id}.json — real output of{" "}
        <span className="text-fg">zence evaluate --json</span>
      </p>
    </div>
  );
}

export function ScenarioTabs({ scenarios }: { scenarios: Scenario[] }) {
  const [active, setActive] = useState(0);
  const baseId = useId();

  return (
    <div>
      <div
        role="tablist"
        aria-label="Decision scenarios"
        className="flex flex-wrap gap-2"
      >
        {scenarios.map((scenario, index) => {
          const selected = index === active;
          return (
            <button
              key={scenario.id}
              role="tab"
              id={`${baseId}-tab-${index}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${index}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(index)}
              onKeyDown={(event) => {
                if (event.key === "ArrowRight") {
                  setActive((index + 1) % scenarios.length);
                } else if (event.key === "ArrowLeft") {
                  setActive((index - 1 + scenarios.length) % scenarios.length);
                }
              }}
              className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${
                selected
                  ? "border-fg bg-fg text-bg"
                  : "border-rule text-muted hover:text-fg"
              }`}
            >
              {scenario.label}
            </button>
          );
        })}
      </div>

      {scenarios.map((scenario, index) => (
        <div
          key={scenario.id}
          role="tabpanel"
          id={`${baseId}-panel-${index}`}
          aria-labelledby={`${baseId}-tab-${index}`}
          hidden={index !== active}
          className="mt-6"
        >
          <p className="mb-5 max-w-2xl text-pretty text-muted">
            {scenario.point}
          </p>
          <DecisionReplay scenario={scenario} />
        </div>
      ))}
    </div>
  );
}
