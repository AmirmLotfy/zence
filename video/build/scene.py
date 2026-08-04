"""Render a terminal scene to frames by animating it in the page and screencasting.

One Chrome, one page, JS drives the typing and the reveal, CDP captures frames at
a fixed cadence. The output text is the real ANSI capture; only the typing is
presentation.
"""

from __future__ import annotations

import base64
import html
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

import websocket

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "video" / "build"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9335
FPS = 25

FG = {30:"#5c6370",31:"#e06c75",32:"#98c379",33:"#e5c07b",34:"#61afef",35:"#c678dd",
      36:"#56b6c2",37:"#dcdfe4",90:"#7f848e",91:"#e06c75",92:"#98c379",93:"#e5c07b",
      94:"#61afef",95:"#c678dd",96:"#56b6c2",97:"#ffffff"}
SGR = re.compile(r"\x1b\[([0-9;]*)m")


def ansi_to_html(raw: str) -> str:
    out, depth, pos = [], 0, 0
    for m in SGR.finditer(raw):
        out.append(html.escape(raw[pos:m.start()])); pos = m.end()
        codes = [int(c) for c in (m.group(1) or "0").split(";") if c] or [0]
        if 0 in codes:
            out.append("</span>" * depth); depth = 0
            codes = [c for c in codes if c]
            if not codes: continue
        st = []
        for c in codes:
            if c == 1: st.append("font-weight:700")
            elif c == 2: st.append("opacity:.62")
            elif c == 4: st.append("text-decoration:underline")
            elif c in FG: st.append(f"color:{FG[c]}")
        if st:
            out.append(f'<span style="{";".join(st)}">'); depth += 1
    out.append(html.escape(raw[pos:])); out.append("</span>" * depth)
    return "".join(out)


TEMPLATE = """<!doctype html><meta charset=utf-8><style>
html,body{margin:0;background:#0f1115;width:1920px;height:1080px;overflow:hidden;
  font-family:ui-sans-serif,system-ui}
.win{position:absolute;left:96px;right:96px;top:74px;bottom:74px;border-radius:14px;
  overflow:hidden;border:1px solid #23262c;box-shadow:0 30px 90px rgba(0,0,0,.55)}
.bar{height:46px;background:#1c1f24;display:flex;align-items:center;padding:0 18px;gap:9px;
  border-bottom:1px solid #23262c}
.dot{width:13px;height:13px;border-radius:50%}
.t{margin-left:16px;color:#8b909a;font-size:15px}
pre{margin:0;padding:26px 32px;background:#14161a;color:#dcdfe4;height:100%;box-sizing:border-box;
  font:19px/1.62 "JetBrains Mono",ui-monospace,Menlo,monospace;white-space:pre-wrap;
  word-break:break-word}
#cur{display:inline-block;width:10px;height:20px;background:#98c379;vertical-align:-4px}
#out{opacity:0;transition:opacity .18s ease}
.cap{position:absolute;left:96px;right:96px;bottom:16px;color:#9aa0aa;font-size:19px;
  letter-spacing:.01em;opacity:0;transition:opacity .4s ease}
</style>
<div class=win>
  <div class=bar>
    <div class=dot style="background:#ec6a5e"></div>
    <div class=dot style="background:#f4bf4f"></div>
    <div class=dot style="background:#61c454"></div>
    <div class=t>__TITLE__</div>
  </div>
  <pre><span style="color:#98c379;opacity:.85">$</span> <span id=cmd></span><span id=cur></span>
<span id=out>__BODY__</span></pre>
</div>
<div class=cap id=cap>__CAPTION__</div>
<script>
const CMD = __CMD__, TYPE_MS = __TYPE_MS__, THINK_MS = __THINK_MS__;
const cmd = document.getElementById('cmd'), cur = document.getElementById('cur');
const out = document.getElementById('out'), cap = document.getElementById('cap');
window.__done = false;
let i = 0;
const tick = () => {
  if (i <= CMD.length) { cmd.textContent = CMD.slice(0, i++); setTimeout(tick, TYPE_MS); return; }
  cur.style.display = 'none';
  setTimeout(() => { out.style.opacity = 1; cap.style.opacity = 1;
                     setTimeout(() => { window.__done = true; }, __HOLD_MS__); }, THINK_MS);
};
setTimeout(tick, 350);
</script>"""


class Chrome:
    def __init__(self) -> None:
        subprocess.run(["pkill", "-f", f"remote-debugging-port={PORT}"], capture_output=True)
        time.sleep(1)
        self.proc = subprocess.Popen(
            [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
             f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
             "--window-size=1920,1080", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                t = next(x for x in json.load(
                    urllib.request.urlopen(f"http://localhost:{PORT}/json")) if x["type"] == "page")
                self.ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=120,
                                                      suppress_origin=True)
                self.n = 0
                self.send("Page.enable"); self.send("Runtime.enable")
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("chrome did not come up")

    def send(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                return m.get("result", {})

    def close(self) -> None:
        try: self.ws.close()
        except Exception: pass
        self.proc.terminate()


def record(chrome: Chrome, page_html: str, name: str, max_seconds: float = 40.0) -> int:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.png"):
        old.unlink()
    tmp = OUT / f"_{name}.html"
    tmp.write_text(page_html)

    chrome.send("Page.navigate", url=f"file://{tmp}")
    time.sleep(0.6)

    i, start, interval = 0, time.time(), 1.0 / FPS
    while time.time() - start < max_seconds:
        shot = chrome.send("Page.captureScreenshot", format="png")
        (d / f"{i:05d}.png").write_bytes(base64.b64decode(shot["data"]))
        i += 1
        done = chrome.send("Runtime.evaluate", expression="window.__done === true",
                           returnByValue=True).get("result", {}).get("value")
        if done:
            break
        elapsed = time.time() - start
        target = i * interval
        if target > elapsed:
            time.sleep(target - elapsed)
    print(f"  {name}: {i} frames ({i/FPS:.1f}s)")
    return i


def build(title: str, command: str, ansi: pathlib.Path, caption: str,
          hold_ms: int = 5200, type_ms: int = 22, think_ms: int = 900) -> str:
    return (TEMPLATE
            .replace("__TITLE__", html.escape(title))
            .replace("__BODY__", ansi_to_html(ansi.read_text(errors="replace")))
            .replace("__CAPTION__", html.escape(caption))
            .replace("__CMD__", json.dumps(command))
            .replace("__TYPE_MS__", str(type_ms))
            .replace("__THINK_MS__", str(think_ms))
            .replace("__HOLD_MS__", str(hold_ms)))


if __name__ == "__main__":
    SRC = pathlib.Path(sys.argv[1])
    JOIN = ('uv run zence evaluate --tool Write --file models/blend.sql \\\n'
            '  --content "SELECT l.email, p.phone\n'
            '             FROM northstar.marketing_leads l\n'
            '             JOIN bluepeak.patient_contacts p ON p.email = l.email" \\\n'
            '  -C examples/clients/northstar-analytics')

    SCENES = [
        ("s_deny", "zsh — northstar-analytics", JOIN, "deny.ansi",
         "Valid SQL. Real credentials. Blocked — because DataHub says that table is another client's.", 6400),
        ("s_cross", "zsh — bluepeak-data",
         JOIN.replace("northstar-analytics", "bluepeak-data"), "cross.ansi",
         "Same query, other workspace. The verdict flips — the query didn't change, the boundary did.", 6000),
        ("s_lineage", "zsh — northstar-analytics",
         'uv run zence evaluate --tool Write \\\n'
         '  --file models/marts/fct_revenue_daily.sql \\\n'
         "  --content \"CREATE OR REPLACE TABLE northstar.fct_revenue_daily AS\n"
         "             SELECT date_trunc('week', close_date) AS week,\n"
         "                    sum(amount) AS revenue\n"
         "             FROM northstar.crm_opportunities\n"
         "             GROUP BY 1\" \\\n"
         '  -C examples/clients/northstar-analytics', "lineage.ansi",
         "Two hops of real DataHub lineage found the dashboard. Zence asks, and names the owner.", 6400),
        ("s_allow", "zsh — northstar-analytics",
         'uv run zence evaluate --tool Write --file models/staging/stg_leads.sql \\\n'
         '  --content "SELECT id, email, created_at FROM northstar.marketing_leads" \\\n'
         '  -C examples/clients/northstar-analytics', "allow.ansi",
         "In-boundary work is allowed, and through the plugin it prints nothing at all.", 4600),
        ("s_verify", "zsh — live DataHub",
         "uv run zence demo verify", "verify.ansi",
         "Every entity, tag and lineage edge re-read from a live DataHub.", 4400),
    ]

    chrome = Chrome()
    try:
        for name, title, cmd, ansi, cap, hold in SCENES:
            record(chrome, build(title, cmd, SRC / ansi, cap, hold_ms=hold), name)
    finally:
        chrome.close()
