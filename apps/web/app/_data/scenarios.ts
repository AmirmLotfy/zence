import deprecatedAsk from "../_artifacts/deprecated-ask.json";
import mcpDeny from "../_artifacts/mcp-deny.json";
import scenarioADeny from "../_artifacts/scenario-a-deny.json";
import scenarioBAsk from "../_artifacts/scenario-b-ask.json";
import scenarioCAllow from "../_artifacts/scenario-c-allow.json";
import tamperDeny from "../_artifacts/tamper-deny.json";

import type { Verdict } from "@/components/primitives";

/**
 * The decision artifacts rendered on this site.
 *
 * `app/_artifacts/` is generated — `scripts/sync-artifacts.sh` clears and
 * repopulates it from `examples/artifacts/decisions`, which is itself the output
 * of `zence evaluate --json`. Nothing authored may live in there; this file is
 * the authored half, and it only supplies the surrounding narrative.
 *
 * Everything inside a `decision` object below is the engine's own words.
 */

export interface DecisionArtifact {
  decision: {
    verdict: Verdict;
    source: string;
    risk: string;
    rule_id: string;
    rule_title: string;
    policy_version: string;
    mode: string;
    reason: string;
    remediation: string | null;
    evidence_urns: string[];
    matched_tags: string[];
    matched_columns: string[];
    downstream_critical: string[];
    provider: string | null;
    degraded: boolean;
  };
  references: { raw_text: string; confidence: string; extractor: string }[];
  intents: string[];
}

export interface Scenario {
  id: string;
  label: string;
  /** What the developer asked Claude for, in their own words. */
  prompt: string;
  /** The tool call Claude attempted as a result. */
  attempt: { tool: string; detail: string };
  /** Why this scenario is worth showing. */
  point: string;
  artifact: DecisionArtifact;
}

const cast = (value: unknown) => value as DecisionArtifact;

export const SCENARIOS: Scenario[] = [
  {
    id: "cross-client-pii",
    label: "Cross-client PII",
    prompt:
      "Blend our Northstar leads with the BluePeak patient contact export so we can see overlap.",
    attempt: {
      tool: "Write",
      detail:
        "SELECT l.email, p.phone\nFROM   northstar.marketing_leads  l\nJOIN   bluepeak.patient_contacts p\n  ON   p.email = l.email",
    },
    point:
      "Every part of this is valid. The SQL parses, both tables exist, the developer has credentials for both. The mistake only exists at the level of boundary — and nothing else in the loop is tracking that.",
    artifact: cast(scenarioADeny),
  },
  {
    id: "critical-downstream",
    label: "Lineage-aware approval",
    prompt: "Change the revenue model to report gross instead of net.",
    attempt: {
      tool: "Edit",
      detail:
        "INSERT INTO northstar.fct_revenue_daily\nSELECT revenue_date, gross_revenue\nFROM   northstar.stg_orders",
    },
    point:
      "In bounds, and still worth a pause. DataHub lineage shows an executive dashboard two hops downstream, so this is a change someone outside the data team will notice. Zence asks rather than blocks — the change may well be correct.",
    artifact: cast(scenarioBAsk),
  },
  {
    id: "in-boundary",
    label: "Ordinary work",
    prompt: "Write a staging model over the last 30 days of leads.",
    attempt: {
      tool: "Write",
      detail:
        "SELECT lead_id, source_campaign\nFROM   northstar.marketing_leads\nWHERE  created_at >= DATEADD(day, -30, CURRENT_DATE())",
    },
    point:
      "The most important case. In domain, in DEV, nothing sensitive — so Zence returns an empty response and the developer sees nothing at all. A guardrail that announces itself on safe work is a guardrail that gets uninstalled.",
    artifact: cast(scenarioCAllow),
  },
  {
    id: "catalog-interception",
    label: "Catalog access",
    prompt: "Look up what's in the BluePeak patient contacts table.",
    attempt: {
      tool: "mcp__datahub__get_entities",
      detail:
        'urns: ["urn:li:dataset:(urn:li:dataPlatform:snowflake,\n        bluepeak.patient_contacts,PROD)"]',
    },
    point:
      "The DataHub MCP server is how Claude reads the catalog, which makes it the surface worth intercepting. Zence checks the call before it reaches the catalog rather than after the metadata is already in context.",
    artifact: cast(mcpDeny),
  },
  {
    id: "deprecated",
    label: "Deprecated asset",
    prompt: "Join against the legacy customer dimension.",
    attempt: {
      tool: "Write",
      detail: "SELECT customer_id FROM northstar.dim_customer_legacy",
    },
    point:
      "Nothing here is unsafe — it is simply about to waste a week. The asset is marked deprecated in DataHub, so Zence surfaces that before the work is built on top of it.",
    artifact: cast(deprecatedAsk),
  },
  {
    id: "tamper",
    label: "Editing the policy",
    prompt: "Just turn Zence off for this bit.",
    attempt: {
      tool: "Edit",
      detail: ".zence/policy.yaml\n\nmode: audit",
    },
    point:
      "Changing the boundary from inside the session it governs is refused, and the refusal is not waivable by an exception or by audit mode. Otherwise `mode: audit` would be a one-line way to disable the tool from within.",
    artifact: cast(tamperDeny),
  },
];

export const FEATURED = SCENARIOS.slice(0, 3);
