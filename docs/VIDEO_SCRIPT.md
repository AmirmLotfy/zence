# Demo video — script and shot list

**Target 2:45.** Hard limit 3:00. Public on YouTube.

The whole video rests on one thing: the viewer has to believe the denial is
real. So every claim is shown as output on screen, in one continuous take per
scenario, with nothing cut mid-command.

---

## Before recording

```bash
# 1. Catalog up and verified — if this exits non-zero, stop and fix it
uv run zence demo seed && uv run zence demo verify

# 2. Clean history, so the audit trail on screen is from this run only
export ZENCE_DB_PATH=/tmp/zence-demo.db && rm -f /tmp/zence-demo.db*

# 3. Warm the hook runtime, so the first call is not the 7.7s cold start
uv run zence doctor
```

Terminal at ~16pt, light theme, window ≥1280×720. Two tabs: the Northstar
workspace, and DataHub at `localhost:9002` already logged in.

---

## 0:00 – 0:22 · The problem

**On screen:** a plain editor with the join, typed out.

```sql
SELECT l.email, p.phone
FROM   northstar.marketing_leads  l
JOIN   bluepeak.patient_contacts  p ON p.email = l.email
```

> "If you work across several clients, you have written a query like this. It
> parses. Both tables exist. You have credentials for both — that is why you
> were hired.
>
> Nothing here is an error, unless you know which client this repository belongs
> to. And your agent doesn't."

## 0:22 – 0:40 · What Zence is

**On screen:** Claude Code opening in `northstar-analytics/`, the Zence boundary
appearing in context.

> "Zence reads that from DataHub. This repository is bounded to Northstar
> Commerce, development and QA only. That boundary is now part of the session."

## 0:40 – 1:20 · Scenario A — denied

**On screen:** ask Claude for the join. Let the denial render in full. Hold on it.

> "So I ask for the join.
>
> Zence parsed the SQL, resolved both tables in DataHub, and stopped this before
> it ran. BluePeak Health, not Northstar. Tagged PII — and it names the columns,
> `email` and `phone`, because the tags are at field level. That is the DataHub
> URN it used.
>
> And it tells Claude what to use instead. A bare refusal just invites a retry."

*Pause a beat on the remediation line.*

## 1:20 – 1:50 · Scenario B — lineage

**On screen:** ask to change the revenue model's grain. Approval prompt appears.

> "This one is in bounds. Zence still pauses — because DataHub lineage says the
> executive revenue dashboard is two hops downstream.
>
> Not blocked. Asked. The change may well be right; somebody outside the data
> team should just know it is coming."

## 1:50 – 2:05 · Scenario C — silence

**On screen:** ask for a staging model over Northstar leads. It just works.

> "And the case that matters most: ordinary work. In domain, in DEV, nothing
> sensitive.
>
> Nothing happened. No prompt, no banner. A guardrail that interrupts safe work
> is a guardrail people uninstall."

## 2:05 – 2:35 · Write-back

**On screen:** `zence finalize`, then the document in the DataHub UI. Run
finalize **again**, refresh, show it is still one document.

> "At the end of the session, Zence writes the decisions back into DataHub — a
> document linked to the assets involved. The catalog now knows an agent was
> stopped from reaching this table, when, and why.
>
> Run it again — still one document. The id is derived from the workspace and
> session, so a repeat updates rather than duplicates."

## 2:35 – 2:45 · Close

**On screen:** `zence audit list`, then the repository.

> "Every decision is recorded locally too. Apache 2.0, and the site renders
> these same artifacts — not screenshots of them.
>
> Zence. Keep every client in bounds."

---

## Shot list

| # | Shot | Take |
|---|---|---|
| 1 | The join in an editor | static |
| 2 | Claude Code start, boundary in context | continuous |
| 3 | **Scenario A denial, full text** | continuous — do not cut |
| 4 | Scenario B approval prompt with the dashboard named | continuous |
| 5 | Scenario C — no output at all | continuous |
| 6 | `zence finalize` → DataHub document | continuous |
| 7 | `zence finalize` again → still one document | continuous |
| 8 | `zence audit list` | static |
| 9 | Repository, Apache-2.0 visible | static |

Shot 3 is the video. If only one thing is recorded carefully, make it that.
Shot 7 is the proof of idempotency — refresh visibly, so it is clearly a reload
and not a still frame.

## Rules for the recording

- **Never re-record a decision to make it look better.** If a scenario behaves
  differently on the day, the script changes, not the output.
- No sped-up footage over a command that produced a decision. If it takes a
  second, let it take a second.
- No captions asserting anything not visible on screen.
- Do not show the DataHub token, the `.env`, or any real hostname.

## Thumbnail

Warm off-white. Large near-black type: **"Keep every client in bounds."** Below
it, one line of the denial in mono, `DENY  ZR-001` in muted red. No faces, no
logos, no stock imagery, no arrows.

## Description

```
Zence is a task-scoped policy firewall for Claude Code. It resolves the assets a
tool call touches against DataHub and refuses the ones that belong to a
different client — before the call runs.

Built for Build with DataHub: The Agent Hackathon.

Repository: https://github.com/AmirmLotfy/zence  (Apache-2.0)
Site:       https://zence.site

00:00  The problem
00:22  The boundary
00:40  Denied — cross-client PII
01:20  Asked — lineage-aware approval
01:50  Allowed — and silent
02:05  Write-back to DataHub
02:35  Close

Northstar Commerce and BluePeak Health are fictional. Everything shown is real
Zence output against a synthetic catalog.
```
