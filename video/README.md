# Demo video

`zence-demo.mp4` — 2:08, 1920×1080, 25fps, 7 MB. Under the hackathon's 3:00 limit.

Rebuild it:

```bash
python3 video/build/scene.py <dir-with-.ansi-captures>   # terminal scenes
python3 video/build/timeline.py                          # cards, pans, concat
```

## What is real

**All command output is real.** Every scene's text came from running that command
under a pty against a live DataHub instance, captured as raw ANSI and replayed —
nothing was retyped, edited, or mocked up. The verdicts, rule ids, reasons,
column names and URNs on screen are what the engine actually emitted.

**The DataHub screens are unedited browser captures** of a running instance.

**Presentation is authored**: the typing animation, the terminal window chrome,
the title cards, and the slow pans over the website. The typing is a rendering
of a command that was really run, not a recording of someone typing it.

So: an assembled film of real material, not a single continuous screen
recording. If a judge would rather see one take, the commands are all in
`docs/SCREENSHOTS.md` and every one reproduces.

## What is missing

The plugin denying inside Claude Code's own UI. That needs an authenticated
Claude Code session, which the build cannot drive. The plugin *is* verified
working there — loading it with `--plugin-dir` fires the SessionStart hook and
injects the boundary — but the screen recording of the permission prompt has to
be captured by hand.

## No audio

Silent, with on-screen captions. Add a voice-over if you want one; the cut
points are wide enough to talk over.
