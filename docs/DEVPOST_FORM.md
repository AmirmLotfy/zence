# Devpost form — copy-paste

Every number here was checked against the code on 29 July 2026. Nothing is
rounded up, and nothing is claimed that a judge cannot reproduce.

---

## Project name

```
Zence
```

## Elevator pitch

*(200 char limit — this is 168)*

```
Claude Code has no idea which client you're working for. DataHub does. Zence puts the catalog in the loop and blocks the cross-client query before the tool call runs — not after.
```

---

## About the project

### Inspiration

I do data work for more than one client from the same laptop. Two repos open,
two warehouses in my shell history, and an agent that will happily reach into
either one because from where it sits, both are just tables it has credentials
for.

The thing that stuck with me is that the dangerous query is never malformed.
It parses. The tables exist. You genuinely have access to both — that's why you
were hired. A linter is happy, the warehouse is happy, and the agent thinks it
just answered your question well:

```sql
SELECT l.email, p.phone
FROM   northstar.marketing_leads  l   -- the client you're working for
JOIN   bluepeak.patient_contacts  p   -- the one you're not
  ON   l.email = p.email
```

Nothing in that is wrong at the level of syntax, permissions, or intent. It's
only wrong at the level of *boundary* — those tables belong to different
clients, and one carries personal data at column level.

That is a question a catalog can answer instantly. Nothing in the loop was
asking it.

### What it does

Zence is a Claude Code plugin that sits in the hook path. Before a tool call
runs, it:

1. **Normalizes** the call into an action with an intent — read, write, mutate,
   destructive
2. **Extracts** the assets it touches — SQL through a real parser, dbt `ref()`
   and `source()`, shell commands, YAML ingestion recipes, DataHub MCP tool
   arguments, file paths
3. **Resolves** them against DataHub — domain, ownership, tags at dataset *and*
   column level, glossary terms, lifecycle, environment, two hops of downstream
   lineage
4. **Evaluates** deterministic policy against that evidence
5. **Returns one verdict** — allow, ask, or deny — with the rule that fired, the
   DataHub URNs behind it, and a safe alternative
6. **Writes the decision back** into DataHub as a durable document

A real denial looks like this. Every fact in it came from the catalog:

```
✗ DENY  ZR-001  Cross-client PII access

bluepeak.patient_contacts belongs to BluePeak Health, but this session is
bounded to Northstar Commerce. It carries urn:li:tag:PII, and columns email,
phone, postcode are classified at field level. Reading it here would move
another client's personal data into this workspace.

→ Use an asset inside Northstar Commerce. If you genuinely need to work on
  BluePeak Health, switch to that client's workspace so the correct boundary
  applies.

evidence  urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)
```

Three verdicts, not two, and the middle one is the interesting one. Cross-client
PII gets denied. A change to a shared model that feeds a critical dashboard gets
an **ask**, with the lineage path named. In-boundary work in a dev environment
is allowed **silently** — no prompt, no banner, nothing. A guardrail that
announces itself on safe work is one people uninstall in a week.

### How I built it

**DataHub is load-bearing on both the read and the write path, through two
different surfaces.**

The **MCP Server** is the surface Zence intercepts. Claude reads the catalog
through `mcp-server-datahub`, so a cross-client lookup shows up in the hook path
before that metadata ever reaches the model's context. The `PreToolUse` matcher
is `mcp__.*datahub.*__.*`, which covers both a user's own server and the one the
plugin bundles.

The **Python SDK** is what Zence reasons from. A hook can't borrow the agent's
MCP connection, and enforcement needs typed aspects — not prose shaped for a
model to read.

On the write side, at session end Zence upserts one decision document with a
deterministic id, `sha256(workspace::session)`, linked to every asset the
session touched, plus a `zence.last_review` structured property. Finalize ten
times, get one document. The idempotency is structural rather than a check that
can lose a race.

What Zence deliberately does **not** write: it never retags, reclassifies, or
reassigns ownership of a client's assets. Those are your team's calls. An agent
guardrail that quietly edits someone's catalog has become a different and much
worse product.

**The engine is deterministic and boring on purpose.** Twelve rules, ten
operators, policy as YAML data. No expression language, no `eval`, and no model
anywhere in the decision path. A model may help classify what a prompt is
*about*; it never decides what's allowed. That's what makes a denial arguable
rather than merely asserted — same inputs, same decision, every time, and you
can read the rule that produced it.

**Precision turned out to be a safety property.** An extractor that reports
table aliases and CTE names as real datasets produces a prompt on every action,
people learn to click approve without reading, and the guardrail becomes a
formality. The must-*not*-find tests outnumber the must-find ones.

The stack: Python 3.11, `acryl-datahub`, `mcp-server-datahub`, sqlglot for SQL,
Pydantic for schemas, SQLite for the audit trail, Typer and Rich for the CLI.
The site is a static Next.js export on Vercel that renders real JSON artifacts
from actual runs — CI fails the build if anyone edits one by hand.

### Challenges I ran into

Almost all the hard work was in the failure modes. Getting `allow` right is
easy. Getting *"I couldn't check, so I'm asking"* right — without being so noisy
that people stop reading — is where the time went.

**Three bugs sat on the same fault line: treating "I couldn't look it up" as "it
isn't there."**

- `_find_urn` caught a connection error and returned `None`, which the caller
  read as "not in the catalog." A DataHub outage was indistinguishable from a
  clean bill of health. That is precisely the failure this product exists to
  prevent, sitting in my own code.
- Rules fired against unresolved evidence. A failed lookup leaves `domain_urn`
  as `None`, which satisfies "not in allowed_domains" — so Zence produced a
  confident cross-client finding from *no evidence at all*, while the honest
  "couldn't reach DataHub" message never appeared.
- The SDK's default retry-with-backoff took **28 seconds** to give up on a dead
  endpoint, inside a hook that needs to answer in a couple of seconds. A DataHub
  outage would have looked like Claude Code hanging.

**The bug only a live catalog could find.** `Dataset.tags` doesn't return URN
strings. It returns `TagAssociationClass` objects, and `str()` on one gives you
`TagAssociationClass({'tag': 'urn:li:tag:PII', ...})` — which never equals
`urn:li:tag:PII`. So **ZR-001 could not fire against a real DataHub.** The
cross-client PII denial, the entire point of the project, did nothing outside of
tests. Every unit test agreed with the broken code, because a recorded fixture
stores plain strings.

`zence demo verify` caught it on the first run against the real instance — ten
problems, every one a missing tag. I'd written that command because seeding a
catalog is a batch of upserts that *mostly* succeeds, and "mostly" is how a demo
dies in front of an audience. It earned its place in about four minutes.

**And the worst one, found two weeks in.** The plugin builds its own virtualenv
on first run. It was installing the runtime *without* the optional DataHub SDK —
so a Zence installed from the marketplace had no SDK, every lookup failed, and
the fail-safe correctly turned every decision into `ask`.

It looked like it was working. Prompts appeared, the reasons were accurate,
nothing crashed. All 387 offline tests passed, because those tests are *supposed*
to run without the SDK. The only way to see it was to run the shim against a
live catalog and actually read the reason string. A contract test now asserts
the install line carries the extra, because I'd rather never find that twice.

**I also wrote my own ReDoS.** The secret-redaction pass I added to keep tokens
out of the audit log used unbounded quantifiers; 10 KB of adversarial input took
2.4 seconds. The thing protecting the logs became the way to hang the hook.

### Accomplishments that I'm proud of

Scenario A — the cross-client PII join — is **denied before execution**, with the
offending columns named, the DataHub URN as evidence, and an in-domain
alternative offered. Scenario B asks, and names the revenue dashboard it found
two lineage hops downstream. Scenario C allows, silently. All verified against a
live DataHub instance, not a mock.

**A judge needs nothing but `uv` to see it.** The demo workspace ships a catalog
recording captured from that live instance, so a fresh clone produces the real
denial — no Docker, no catalog, no account, no waiting. And a recording can
never impersonate a catalog: every decision it produces is stamped
`provider: fixture`, and a `DATAHUB_GMS_URL` in your environment always wins
over it. A workspace with neither still answers `ask`, because ignorance must
never quietly become permission.

Every claim on the website is a JSON artifact from a real run, and CI fails the
build if one is edited by hand.

402 tests. mypy strict. Eight CI jobs. Secret scanning across full history with
no allowlist — an allowlist is just a place a real secret can hide.

### What I learned

**Most of a guardrail's value is in what it does when it's broken.** Every
serious bug I hit was some flavour of the same mistake — a thing that couldn't be
checked being treated as a thing that was fine.

**Tests that pass without the dependency will happily pass without the
feature.** My offline suite was green while the shipped plugin couldn't read
DataHub at all. That's not an argument against offline tests; it's an argument
that "it works" has to be observed on the real path at least once.

**Verify the platform instead of remembering it.** `astral-sh/setup-uv` has no
moving `v9` tag. `claude plugin validate` silently skips `plugin.json` when a
marketplace manifest sits next to it. Tailwind v4 dropped the arbitrary-value
colour shorthand, so an entire palette rendered as nothing while the build
stayed green. Not one of those would have been caught by assuming.

**And say what you don't do.** The threat model opens with what Zence *isn't*.
It doesn't intercept a shell, it isn't a sandbox, and it doesn't replace
warehouse grants. Stating that plainly costs nothing and is the whole difference
between a tool you can trust and one you have to second-guess.

### What's next for Zence

- **Approval routing**, so an `ask` can reach the person who actually owns the
  asset instead of stopping at whoever is at the keyboard
- **More extractors.** Today it's SQL, dbt, shell, YAML recipes, MCP arguments
  and paths — and the README says exactly that rather than implying more
- **Proposals API write-back**, so Zence can suggest a classification it inferred
  rather than only recording its own decisions
- **A skill contributed upstream** to `datahub-project/datahub-skills` covering
  domain-boundary and PII-aware asset selection, which fell out of building this

---

## Built with

*(comma-separated, 22 tags)*

```
python, datahub, acryl-datahub, mcp, claude-code, anthropic, sqlglot, pydantic, sqlite, typer, rich, uv, pytest, mypy, ruff, nextjs, react, typescript, tailwindcss, vercel, github-actions, yaml
```

## Try it out links

```
https://github.com/AmirmLotfy/zence
https://zence.site
https://zence.site/verify
```

Order matters — the repo is the primary artifact, `/verify` is the page that
turns "trust me" into a command a judge can run in a minute.

---

## Challenge category

**Agents That Do Real Work.**

Its description is almost a spec for Zence: *"reads DataHub through the MCP
Server… to understand what's connected to what, takes action, and writes results
back."* That is the whole loop, and the write-back is the exact thing the
Use-of-DataHub criterion says the strongest submissions do.

*Metadata-Aware Code Generation & Development* asks for agents that **generate**
production data code and ships sample generated artifacts so judges can assess
output quality. Zence governs generated code; it doesn't generate it. Entering
there means being judged on output it doesn't produce.

## Notes on what to include, and what to leave out

**Include:**

- The AI-assistance disclosure. The rules explicitly permit AI coding
  assistants; being upfront costs nothing, and for a Claude Code plugin it reads
  as coherent rather than sheepish.
- That the demo clients are fictional. Pre-empts the obvious question, and a
  tool about not leaking client data shouldn't ship anyone's.
- The trust boundary — what Zence doesn't do. It reads as maturity, and every
  judge who has shipped something will recognise it.

**Leave out:**

- **Any live-catalog latency number.** The only instance reachable for
  measurement is behind an SSH tunnel that costs ~11s on first connect. Any
  figure would describe the tunnel. Warm decisions against the shipped recording
  are 0.20–0.28s on an M1, which is measured and safe to state if a number is
  wanted.
- **The demo VM.** It's a development convenience. Mentioning it only raises
  "what if it's off?" — and nothing a judge needs depends on it.
- **The other hackathon entry, and its upstream PR.** Different project. That PR
  is its contribution, not this one's, and claiming it here would be claiming
  one contribution twice.
- **Any open-source contribution for Zence.** None has been made. It's listed
  under What's Next, which is true, rather than under accomplishments, which
  would not be.

**One thing to fix in the form itself:** the story template Devpost pre-filled
still says *"What's next for Comgu"*. Change it to Zence before submitting.
