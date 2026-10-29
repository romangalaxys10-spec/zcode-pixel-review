---
description: Visual regression gate. Diff baseline vs current screenshots of a page and block done claims when unintended regions changed beyond threshold.
allowed-tools: Read, Bash, Write, Edit
argument-hint: [baseline.png] [current.png] [--regions spec]
---
Invoke the `pixel-review` skill with this input: **$ARGUMENTS**

Args, in order:
- baseline screenshot path,
- current screenshot path,
- optional `--regions "name=TOP,LEFT,W,H;name=TOP,LEFT,W,H"` percent boxes
  for the zones that must or must not move (boxes separated by `;`).

If args are empty:
- if a baseline for the page you just edited does not exist yet, stop and
  ask the user to capture one (or use the browser tool if it is active);
- capture or accept the current screenshot;
- run `png_diff.py`, review the red-highlighted diff image region by
  region, and report PASS or BLOCK in the skill's format.
