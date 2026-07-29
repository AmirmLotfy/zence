# Screenshots for the Devpost gallery

Nine shots, ordered. **Shot 1 is the gallery thumbnail** — it is the only image
most people scrolling the gallery will ever see, so it has to carry the idea on
its own.

Everything here was checked working on 29 July 2026. Nothing below asks you to
stage something that does not happen.

Before you start: `gcloud compute ssh zence-datahub --project=goosecast
--zone=europe-west1-b --tunnel-through-iap -- -N -L 8080:localhost:8080 -L
9002:localhost:9002`, and DataHub's UI is `datahub` / `datahub`.

---

## 1. The denial, in a real Claude Code session — **the thumbnail**

The one shot that proves the product exists. A permission prompt in Claude
Code's own UI, with a reason naming another client's dataset and its PII
columns.

```
/plugin marketplace add AmirmLotfy/zence
/plugin install zence@zence
```

It will ask for a DataHub URL and token. `http://localhost:8080` and a PAT from
Settings → Access Tokens.

Then open Claude Code in `examples/clients/northstar-analytics/` and ask:

> Join our marketing leads with the BluePeak patient contacts export so I can
> see which leads are already patients.

Capture the whole prompt — your question, the tool call Claude attempted, and
Zence's block underneath it.

**Verified**: a fresh clone of the published repo, run cold with no environment
variables, produces this denial. The plugin builds its own runtime on first use;
that takes ~15 seconds once, so trigger it once before you start filming.

## 2. The same thing in a terminal, from nothing

For anyone who wants to see it without installing a plugin.

```bash
git clone https://github.com/AmirmLotfy/zence && cd zence
uv sync --all-packages

uv run zence evaluate --tool Write --file models/blend.sql \
  --content "SELECT l.email, p.phone
             FROM northstar.marketing_leads l
             JOIN bluepeak.patient_contacts p ON p.email = l.email" \
  -C examples/clients/northstar-analytics
```

Get the red `✗ DENY ZR-001` header, the reason naming `email`, `phone`,
`postcode`, the remediation, and the evidence URN in one frame. Run `echo $?`
after it and include the `6` — a scriptable exit code says "this is
infrastructure, not a chat toy."

## 3. DataHub: the decision Zence wrote back

This is the *contributes back to the graph* evidence, and it is the shot most
submissions will not have.

```
http://localhost:9002/document/urn:li:document:zence-session-a32e2035a5471ff5
```

Frame the title (**Zence session review — Northstar Commerce**), the blocked
section with ZR-001, and the related assets panel showing three linked datasets.

## 4. DataHub: where the evidence came from

```
http://localhost:9002/dataset/urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)
```

Show the **BluePeak Health** domain badge, the `PII` tag, and the schema tab
with `email`, `phone` and `postcode` tagged at field level. Put this next to
shot 1 or 2 and the denial stops being a claim — the reader can see every fact
in it sitting in the catalog.

## 5. DataHub: the lineage behind the *ask*

Open `northstar.fct_revenue_daily` and switch to **Lineage**. Show the two hops
down to the `northstar_revenue` dashboard.

That path is why scenario B asks instead of allowing, and Zence found it rather
than being told about it. Lineage-aware decisions are hard to fake and easy to
recognise.

## 6. zence.site/demo

The real decision artifacts rendered — allow, ask and deny side by side. Catch
a frame with all three verdict badges visible so the three-outcome model reads
at a glance.

## 7. zence.site/verify

The "check it yourself" page: the one-minute command at the top, and enough of
the source table below it to show the links go straight into the code.

## 8. `zence demo verify` against the live catalog

```bash
export DATAHUB_GMS_URL=http://localhost:8080
uv run zence demo verify
```

Every entity, tag, and lineage edge re-read through the same path a hook uses.
This is the command that caught the association-class bug on its first run, and
a green wall of checks is a quiet, credible signal.

## 9. The audit trail

```bash
uv run zence audit list -C examples/clients/northstar-analytics
```

Rules, tools, clients, timestamps. Shows decisions are recorded and reviewable
rather than transient.

---

## Optional, if you want a tenth

- **CI green** — eight jobs on the repo's Actions tab.
- **The GitHub issue**, [#18726](https://github.com/datahub-project/datahub/issues/18726),
  for the open-source contribution criterion.
- **Cross-client allow** — the *same* query run inside `bluepeak-data/`, where
  it is allowed. Pair it with shot 2 and the caption writes itself: the query
  did not change, the boundary did. This is the most persuasive pairing
  available and almost nobody thinks to shoot it.

## Practical notes

**Terminal.** Widen to ~100 columns so nothing wraps mid-URN. Increase the font
before capturing — Devpost renders gallery images small, and a screenshot at
your normal size is unreadable at thumbnail scale. Clear scrollback first so
there is no unrelated history in frame.

**Redaction.** Nothing here exposes a real secret — the clients are fictional
and the token never appears in output — but check your shell prompt for a
directory path or hostname you would rather not publish.

**Format.** PNG. Crop tight: no desktop, no dock, no browser bookmarks bar.

**Captions.** Devpost shows them under each image. Say what the reader should
notice, not what the image is. "The columns are named because DataHub has them
tagged at field level" beats "Screenshot of a denial."
