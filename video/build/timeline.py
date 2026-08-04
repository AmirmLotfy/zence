"""The Zence demo video, end to end."""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from assemble import B, SRC, card, frames_clip, pan, still  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHOTS = ROOT / "shots"

FOOT = ('<div class=foot><span>github.com/AmirmLotfy/zence</span>'
        '<span>Apache-2.0 &middot; zence.site</span></div>')

clips: list[pathlib.Path] = []

clips.append(card("title", """
  <div class=eyebrow>Build with DataHub &middot; The Agent Hackathon</div>
  <h1>Zence</h1>
  <p style="font-size:38px;color:#f2f0e9;margin-top:20px">
    Keep every client in bounds.</p>
  <p>A task-scoped policy firewall for Claude Code. It resolves the assets a tool call
     touches against DataHub, and refuses the ones that belong to a different client —
     before the call runs.</p>""" + FOOT, 7.0))

clips.append(card("problem", """
  <div class=eyebrow>The problem</div>
  <h2>Every individual step is valid.<br>The mistake is the combination.</h2>
  <pre><span class=c1>-- Perfectly valid SQL. Catastrophic in a consultancy.</span>
SELECT l.email, p.phone
FROM   northstar.marketing_leads  l   <span class=c3>-- the client you're working for</span>
JOIN   bluepeak.patient_contacts  p   <span class=c2>-- the one you're not</span>
  ON   l.email = p.email</pre>
  <p>It parses. Both tables exist. You have credentials for both — that is why you were
     hired. The only place it is wrong is the metadata.</p>""", 10.0))

clips.append(frames_clip("s_deny"))
clips.append(still(SHOTS / "05-datahub-pii-columns.png", "dh_pii", 8.5))
clips.append(frames_clip("s_cross"))
clips.append(frames_clip("s_lineage"))
clips.append(still(SHOTS / "06-datahub-lineage.png", "dh_lin", 7.5))
clips.append(frames_clip("s_allow"))

clips.append(card("writeback", """
  <div class=eyebrow>And it writes back</div>
  <h2>The catalog learns something<br>it did not know.</h2>
  <p>At session end Zence upserts one decision document into DataHub, linked to every asset
     the session touched. The id is derived from the workspace and session, so finalizing
     again updates that record instead of duplicating it.</p>""", 8.0))

clips.append(still(SHOTS / "04-datahub-decision-written-back.png", "dh_doc", 9.0))
clips.append(frames_clip("s_verify"))

clips.append(pan(SRC / "site-home.png", "site_home", 13.0, top_pad=1.4))
clips.append(pan(SRC / "site-demo.png", "site_demo", 10.0, top_pad=1.0))
clips.append(pan(SRC / "site-verify.png", "site_verify", 10.0, top_pad=1.0))

clips.append(card("close", """
  <div class=eyebrow>Open source &middot; Apache-2.0</div>
  <h2>Runs entirely on your machine.<br>No account, no hosted service.</h2>
  <pre>git clone https://github.com/AmirmLotfy/zence &amp;&amp; cd zence
uv sync --all-packages
uv run zence evaluate ... -C examples/clients/northstar-analytics
<span class=c2>&#10007; DENY  ZR-001  Cross-client PII access</span>          <span class=c1>exit 6</span></pre>
  <p>402 tests. Verified against a live DataHub. Every command above is on
     <b style="color:#f2f0e9">zence.site/verify</b>.</p>""" + FOOT, 10.0))

listing = B / "concat.txt"
listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))

out = ROOT / "video" / "zence-demo.mp4"
subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
               check=True, capture_output=True)
dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
size = out.stat().st_size / 1_000_000
print(f"\n  {out.relative_to(ROOT)}  {float(dur):.1f}s  {size:.1f} MB  ({len(clips)} clips)")
