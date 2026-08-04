"""Assemble the Zence demo video from real captures."""

from __future__ import annotations

import html
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
B = ROOT / "video" / "build"
SRC = ROOT / "video" / "src"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FPS = 25
W, H = 1920, 1080

CARD_CSS = """
html,body{margin:0;width:1920px;height:1080px;background:#0f1115;overflow:hidden;
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#f2f0e9}
.wrap{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;
  padding:0 150px;box-sizing:border-box}
h1{font-size:78px;line-height:1.06;margin:0;letter-spacing:-.022em;font-weight:640}
h2{font-size:44px;line-height:1.22;margin:0;letter-spacing:-.012em;font-weight:560}
p{font-size:29px;line-height:1.5;color:#a8a49a;margin:26px 0 0;max-width:1400px}
.eyebrow{font:20px/1 "JetBrains Mono",ui-monospace,Menlo,monospace;letter-spacing:.18em;
  color:#86a967;text-transform:uppercase;margin-bottom:30px}
pre{font:26px/1.62 "JetBrains Mono",ui-monospace,Menlo,monospace;background:#14161a;
  border:1px solid #23262c;border-radius:12px;padding:30px 34px;margin:34px 0 0;color:#dcdfe4}
.c1{color:#7f848e}.c2{color:#e06c75}.c3{color:#98c379}
.foot{position:absolute;left:150px;right:150px;bottom:74px;display:flex;
  justify-content:space-between;color:#6b6862;font-size:23px}
"""


def card(name: str, body: str, seconds: float) -> pathlib.Path:
    doc = f"<!doctype html><meta charset=utf-8><style>{CARD_CSS}</style><div class=wrap>{body}</div>"
    (B / f"_{name}.html").write_text(doc)
    png = B / f"card_{name}.png"
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={W},{H}", f"--screenshot={png}",
                    "--virtual-time-budget=1200", f"file://{B / f'_{name}.html'}"],
                   check=True, capture_output=True)
    out = B / f"clip_{name}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", str(seconds),
                    "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "20", str(out)], check=True, capture_output=True)
    return out


def frames_clip(folder: str) -> pathlib.Path:
    out = B / f"clip_{folder}.mp4"
    # Chrome's screenshot comes back a few pixels short of the window height, and an
    # odd height cannot be encoded as yuv420p. Pad to frame on the same background
    # rather than scaling, so nothing is distorted.
    subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(B / folder / "%05d.png"),
                    "-vf", f"scale={W}:-2,pad={W}:{H}:0:({H}-ih)/2:0x0F1115,format=yuv420p",
                    "-c:v", "libx264", "-preset", "medium",
                    "-crf", "20", str(out)], check=True, capture_output=True)
    return out


def pan(png: pathlib.Path, name: str, seconds: float, top_pad: float = 0.0) -> pathlib.Path:
    """Scroll a tall page capture. Real content, moving at a readable pace."""
    out = B / f"clip_{name}.mp4"
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(png)],
                           capture_output=True, text=True, check=True).stdout.strip()
    sw, sh = (int(x) for x in probe.split(","))
    scaled_h = int(sh * (W / sw))
    travel = max(0, scaled_h - H)
    n = int(seconds * FPS)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(png),
        "-vf", (f"scale={W}:-1,crop={W}:{H}:0:'min({travel},max(0,(t-{top_pad})/"
                f"{max(0.001, seconds - top_pad - 0.6)}*{travel}))',fps={FPS},format=yuv420p"),
        "-frames:v", str(n), "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(out)
    ], check=True, capture_output=True)
    return out


def still(png: pathlib.Path, name: str, seconds: float, zoom: float = 1.05) -> pathlib.Path:
    """Hold a real screenshot, whole, with a slow push-in.

    The source shots are 3:2 and the frame is 16:9, so fit to height and pad the
    sides — cropping to fill would cut the very thing being shown. The zoom stays
    inside the padded frame so nothing leaves the edge.
    """
    out = B / f"clip_{name}.mp4"
    n = int(seconds * FPS)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(png),
        "-vf", (f"scale=-2:{H*2},pad={W*2}:{H*2}:({W*2}-iw)/2:0:0x0F1115,"
                f"zoompan=z='1+(on/{n})*{zoom - 1}':x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},format=yuv420p"),
        "-frames:v", str(n), "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(out)
    ], check=True, capture_output=True)
    return out
