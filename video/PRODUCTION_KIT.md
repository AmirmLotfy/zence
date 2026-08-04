# Video production kit

Everything for assembling the final cut in Canva: shot list for the top and
tail, the voice-over script, the music prompt, and the YouTube copy.

---

## Read this before you set the speed

**A flat 2× will cost you the video's best moment.**

The denial reason is three lines of prose naming three columns and a URN. At 1×
it is on screen for about six seconds — enough to read. At 2× it is three, which
is enough to notice a red word and not enough to learn anything. Same for the
lineage ask and the write-back document.

Speed the parts where nothing is being read, keep the parts where something is:

| Segment | Source | Speed | Why |
|---|---|---|---|
| Typing before each command runs | all terminal clips | **3×** | Nobody needs to watch typing |
| The deny output | `s_deny` tail | **1×** | The reason names the columns. This is the film |
| DataHub PII columns | `dh_pii` | **1.5×** | Slow push-in already; it can take a little speed |
| The cross-boundary ask | `s_cross` tail | **1.25×** | Shorter text, still needs reading |
| The lineage ask | `s_lineage` tail | **1×** | Names the dashboard and the owner |
| DataHub lineage panel | `dh_lin` | **1.5×** | "Used by 1 dashboard" is the only line that matters |
| The allow | `s_allow` tail | **2×** | Two lines, and the point is that it is boring |
| Decision document | `dh_doc` | **1.5×** | Let the title and the Blocked heading land |
| `demo verify` | `s_verify` | **2×** | One green line |
| Website pans | `site_*` | **2×** | Motion reads fine fast |

Rough result: about **65–70 seconds** of demo. With a 25 s open and a 25 s close
you land near **2:00**, comfortably inside the 3:00 limit.

**Use `zence-demo-core.mp4`** (1:41) rather than `zence-demo.mp4` (2:08). The
core cut has my title, problem and closing cards stripped out, because you are
building better ones in Canva. Splitting it in Canva at the clip boundaries
above gives you the segments in the table.

---

## 1 · Opening and closing

### Licensing, first

The rules say the video **must not include third-party trademarks or copyrighted
material** without permission. Two consequences:

- Use Canva's own stock library. Your Pro licence covers it for this.
- Avoid any clip with a visible logo, brand, product UI or recognisable face on
  a badge. Server-room B-roll is full of vendor logos — check every frame.
- Do not add a screen recording of anyone else's product.

The DataHub and Claude Code names in the video are unavoidable and fine: you are
describing genuine integrations, which is nominative use, not branding.

### Opening — 0:00 to 0:25

Aim for calm and legible, not a tech-hype montage. The subject is a mistake
nobody notices, so the visual language should be *quiet*, not *urgent*.

**Shot 1 — 0:00–0:06 · the two-client reality**

- Canva search: `laptop desk night coding`, `developer working late`, `two
  monitors dark room`
- Pick: a static or slow-push shot, dim, screen glow, no face, no logos
- Over it: your title card. Wordmark `Zence`, then **Keep every client in
  bounds.** underneath
- Grade it dark to match the terminal footage (`#0F1115`)

**Shot 2 — 0:06–0:16 · the SQL**

Do not use stock here. Build it as a Canva text animation, monospace, on the
dark background:

```
SELECT l.email, p.phone
FROM   northstar.marketing_leads  l     ← the client you're working for
JOIN   bluepeak.patient_contacts  p     ← the one you're not
  ON   l.email = p.email
```

Reveal line by line. On the `JOIN` line, fade in a soft red underline. This is
the single most important graphic in the video — a stock clip cannot do it.

**Shot 3 — 0:16–0:25 · the boundary idea**

- Canva element search: `abstract network nodes line`, `data flow lines minimal`,
  `geometric grid lines dark`
- Pick: slow, thin-line, monochrome. **Avoid** particles, glowing orbs, neon
  circuit boards, spinning globes, blue "cyber" backgrounds and any hooded-figure
  cliché — they say *generic AI product* and undercut a governance tool
- Overlay: two labelled clusters, `Northstar Commerce` and `BluePeak Health`,
  with a line between them that a badge snaps onto. Colour the badge
  `#9B3B33` (the deny red used throughout the project)

Then cut straight to the terminal footage.

### Closing — after the demo, ~25 s

**Shot 4 — the three verdicts, as a graphic**

Build in Canva, no stock. Three rows appearing in turn, using the project's
palette:

| | | |
|---|---|---|
| `✓ ALLOW` | `#2F6F4E` | in-boundary work, silently |
| `? ASK` | `#B4761E` | lineage impact, or when it cannot see |
| `✗ DENY` | `#9B3B33` | another client's PII |

**Shot 5 — the proof line**

Plain text on the dark background, no stock:

> 402 tests · verified against a live DataHub · Apache-2.0

**Shot 6 — the card**

- `zence.site`
- `github.com/AmirmLotfy/zence`
- Small, bottom: *Built for Build with DataHub: The Agent Hackathon*
- Optional: one slow abstract line-motion clip behind it at low opacity

Hold four seconds. Do not fade to black on a logo sting; end on the URL.

---

## 2 · Voice-over

### Generation settings — Gemini 3.1 TTS

- **Voice:** male, mid-to-low register, unhurried. Prefer a natural conversational
  timbre over a "narrator" one
- **Style prompt:** *Read as a senior engineer explaining their own work to a
  colleague they respect. Calm, precise, quietly confident. Not a commercial. No
  upward inflection at the end of sentences. Let the technical terms land
  naturally — do not over-enunciate them.*
- **Pace:** slightly under conversational. The script is written with room
- **Generate section by section**, not as one block — you need to align each
  piece to picture, and one long take gives you no cut points
- `[beat]` markers are silence to leave in the edit, not text to read

### Script

Total ≈ 250 words, ≈ 105 seconds spoken with the beats.

---

**[OPEN — over shots 1–3]**

> If you do data work for more than one client, you already know this feeling.
> Two repositories open. Two warehouses in your shell history. And an agent that
> will happily reach into either one — because from where it sits, both are just
> tables you have credentials for.
>
> [beat]
>
> The dangerous query is never the malformed one. This parses. Both tables
> exist. You have access to both — that's why you were hired.
>
> [beat]
>
> The only place it's wrong is the metadata. Those tables belong to different
> clients, and one of them carries personal data.

**[DEMO — over the terminal footage]**

> Zence sits in Claude Code's hook path. Before a tool call runs, it resolves
> every asset that call touches against DataHub — and refuses the ones that are
> out of bounds.
>
> [beat]
>
> It names the columns because DataHub has them tagged at field level. Not
> because they look like personal data.
>
> [beat — over the cross-boundary scene]
>
> Same query, from the other client's workspace. The verdict flips. The query
> didn't change — the boundary did.
>
> [beat — over the lineage scene]
>
> Change a shared model and Zence walks two hops of real lineage, finds the
> dashboard downstream, and asks — naming the owner you should tell.
>
> [beat — over the allow]
>
> In-boundary work is allowed, silently. A guardrail that interrupts safe work
> is one people uninstall.
>
> [beat — over the write-back]
>
> Then it writes the session's decisions back into the catalog, linked to every
> asset touched. DataHub learns something it didn't know.

**[CLOSE — over shots 4–6]**

> The engine is deterministic. A model never decides what's allowed — which is
> why a denial is something you can argue with, instead of something you have to
> accept.
>
> [beat]
>
> Open source, Apache-2.0, and it runs entirely on your machine.
>
> Zence. Keep every client in bounds.

---

### Two notes on delivery

Let *"The query didn't change — the boundary did"* sit. It is the line that
explains the whole product, and it needs the pause more than the emphasis.

Do not push the closing tagline. Say it flat, like a fact. The read that sells
hardest is the read a judge trusts least.

---

## 3 · Background music — Lyria 3 Pro

Copy this as the prompt:

```
Minimal, restrained electronic underscore for a technical software demonstration.
Slow-evolving warm analog pad as the harmonic bed, with a sparse muted electric
piano or soft mallet motif placed high in the mix, several bars apart rather than
continuous. Subtle low sine pulse marking time, no drum kit, no percussion hits,
no risers, no impacts, no vocal samples, no melodic hook that competes for
attention.

Tempo around 80 BPM. Key: A minor, resolving warm rather than tense.

Structure: enters quietly and stays out of the way. A slight lift in harmonic
density about a third of the way through, a return to near-silence with only the
pad and the low pulse holding through the middle, then a final gentle bloom of
warmth in the last fifteen seconds that resolves cleanly rather than swelling.

Mood: composed, credible, unhurried. The feeling of someone who knows what they
are doing quietly showing you. Not cinematic, not corporate-inspirational, not
tense, not a product launch. Nothing that sounds like a countdown or a reveal.

Mix leaves the entire midrange open for a spoken male voice. No frequencies
competing with speech. Loop-friendly and seamless.

Duration: 2 minutes 15 seconds.
```

**Mixing:** sit it at **−22 to −26 dB** under the voice. If you notice it while
following the words, it is too loud. Fade in over the first two seconds; duck an
extra 3 dB under the opening SQL narration; let it come up alone for the final
three seconds after the last word.

---

## 4 · YouTube

### Title (86 characters)

```
Zence — Stopping Claude Code From Touching the Wrong Client's Data, Using DataHub
```

Alternatives if you prefer a different angle:

- `Zence: a policy firewall for Claude Code, powered by DataHub's metadata graph`
- `I gave Claude Code a data boundary it can't cross — built on DataHub`

### Description

```
Zence is a task-scoped context and policy firewall for Claude Code. Before a tool
call runs, it resolves the assets that call touches against DataHub's metadata
graph and refuses the ones belonging to a different client — with the evidence,
and a safe alternative.

Built solo for Build with DataHub: The Agent Hackathon.

▸ Live: https://zence.site
▸ Check it yourself: https://zence.site/verify
▸ Source (Apache-2.0): https://github.com/AmirmLotfy/zence

────────────────────────

THE PROBLEM

Run Claude Code across several clients from one laptop and nothing in the loop
knows which client is in scope. The dangerous query is never malformed — it
parses, both tables exist, and you have credentials for both, because that is
why you were hired. It is only wrong at the level of boundary, and that is a
question a catalog can answer.

WHAT YOU SEE IN THIS VIDEO

00:00  The problem, in four lines of valid SQL
00:25  A cross-client join denied before it runs
00:40  Where the evidence came from — column-level PII tags in DataHub
00:55  The same query from the other workspace, and the verdict flips
01:10  A shared model change, and two hops of real lineage
01:25  In-boundary work, allowed silently
01:35  The decision written back into DataHub
01:50  zence.site

HOW DATAHUB IS USED

Read: domain, ownership, dataset and column-level tags, glossary terms,
lifecycle, environment, and two hops of downstream lineage.

Write: at session end, one decision document upserted with a deterministic id
derived from the workspace and session, linked to every asset touched. Finalize
again and it updates that record rather than duplicating it.

The DataHub MCP Server is the surface Zence intercepts — catalog reads are
checked before the metadata reaches the model's context. The Python SDK is what
Zence reasons from, because a hook cannot borrow the agent's MCP connection.

Zence never retags, reclassifies or reassigns ownership of a client's assets.

WHAT IS REAL IN THIS VIDEO

Every command output on screen was captured from a real run against a live
DataHub instance — the verdicts, rule ids, reasons, column names and URNs are
what the engine actually emitted. The DataHub screens are unedited captures. The
typing animation and the titles are presentation.

The clients, datasets and people in the demo catalog are fictional. A tool about
not leaking client data should not ship anyone's.

BUILT WITH

Python 3.11 · acryl-datahub · mcp-server-datahub · sqlglot · Pydantic · SQLite ·
Typer · uv · Next.js · TypeScript · Tailwind · Vercel · GitHub Actions

402 tests. Verified against a live DataHub. Apache-2.0.

Developed with AI assistance (Claude Code) during the submission period.
```

### Tags

```
datahub, claude code, mcp, model context protocol, ai agents, data governance,
pii, data catalog, metadata, policy engine, ai coding assistant, data lineage,
agent guardrails, llm security, python, open source, devpost, hackathon,
data engineering, anthropic
```

### Thumbnail

Use gallery image `01-cross-client-deny.png`, cropped to 16:9 on the `✗ DENY
ZR-001` line, with two or three words of large text top-left — **Blocked before
it ran** — in the deny red. Do not add a face, an arrow, or a shocked expression.

### Settings

- **Public** — the rules require public visibility
- Category: Science & Technology
- Leave "Altered content" unchecked: this is real captured output, not synthetic
  media of a person or event. Do disclose the AI-assisted build in the
  description, which the text above already does
- Add the chapter timestamps above; they are what makes a judge able to skip to
  the deny
