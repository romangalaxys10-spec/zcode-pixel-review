---
name: pixel-review
description: Use before and after any agent UI edit to gate the claim that the change is visually safe. Captures a baseline screenshot, re-captures after the edit, diffs them with a stdlib PNG script, and blocks done claims when diff exceeds threshold in regions the change was not supposed to touch.
---

# pixel-review

Visual regression gate for agentic UI changes.

## Inputs

- `url`: the page under test, reachable from a browser tool or viewable by the user.
- `change_summary`: what the agent just changed and which regions it was meant to touch.
- `viewports`: list of widths to gate, default 1280x900. Add a mobile width if the app is responsive.

## Workflow

### 1. Baseline (before the UI code is edited)

- If a browser tool is available, open the URL at each viewport and save
  `pixel-review/baseline-<w>px-<ts>.png`.
- If not, instruct the user:
  "Open the page at <w>px wide, take a full-page screenshot, and save it
  to pixel-review/baseline-<w>px-<ts>.png. I will use it as the gate."
- Do not edit UI code before at least one baseline exists for every
  viewport that must be gated.

### 2. Apply the UI edit

- The agent makes its change. Note the intended regions (e.g. "the pricing
  card only") and the regions that must stay put ("header, nav, footer").

### 3. Re-capture and diff

For each viewport:
```bash
python3 scripts/png_diff.py \
  pixel-review/baseline-1280px-<ts>.png \
  pixel-review/current-1280px-<ts>.png \
  --threshold 2.0 \
  --regions "header=0,0,100,12;nav=12,0,100,10;main=12,10,100,60;footer=75,0,100,25" \
  --out pixel-review/diff-1280px.png \
  --json pixel-review/report-1280px.json
```
Adjust the percent boxes to match the change: intended regions get their
real coordinates, unintended regions get theirs. `--regions` takes
`name=TOP,LEFT,W,H` percent boxes; several boxes are separated by `;`
(commas only appear inside a box). `--threshold` is the max allowed diff
percent per region. For a plain equal-cell grid instead, use `--grid 3x3`
(optionally `--regions a,b,c` to rename cells row-major).

### 4. Gate the done claim

- Exit code 1 means at least one region is over threshold. The agent MUST
  not claim the UI change is done until either the region is acceptable
  (it is in the intended zone) or the code is fixed.
- Structural check when available: if the page's rendered text or DOM can be
  captured (browser tool), diff the visible text list between baseline and
  current captures. Text that appeared, vanished, or changed outside the
  intended region is a fail even when pixels are under threshold.
- Always run the agent-side visual review: read `pixel-review/diff-*.png`
  (the red-highlighted image) and state, region by region, what moved.
  Pixel numbers alone do not say what the movement is.

### 5. Report format

```
pixel-review gate @ 1280px
  whole-image diff: 3.1%
  regions:
    header   0.2%  PASS
    nav      0.0%  PASS
    main     9.4%  FAIL (intended zone: OK / unintended zone: BLOCK)
    footer   0.1%  PASS
  structural text diff: 1 line changed in main, 0 elsewhere
  verdict: PASS / BLOCK
```
`BLOCK` means: fix the unintended change or widen the intended region in
the report with a reason, then re-run the gate.

## Honest limits

- The PNG decode is pure stdlib and handles 8-bit grayscale, RGB, gray+alpha,
  and RGBA with the common filters. 16-bit PNGs, paletted (color type 3)
  PNGs, and interlaced (Adam7) PNGs are not decoded and will error out;
  take screenshots at 8-bit.
- Pixel-perfect comparison of compressed or complex PNGs is approximate:
  anti-aliased edges, font subpixel rendering, and JPEG-style recompression
  in the screenshot pipeline produce noise the tolerance setting absorbs.
  Default `--tolerance 16` counts a pixel as unchanged when the mean
  per-channel difference is 16 or less.
- The diff image is the ground truth for what actually moved. The script's
  numbers tell you where, not why.
- A passing gate does not prove the UI is good. It proves the regions you
  boxed did not move more than expected.

## Guardrails

- Never declare the task done on the strength of "the diff was small".
  Small in the wrong region is still a fail.
- Keep the diff image and the JSON report next to the screenshot set so a
  later review can see what the gate saw.
- If the browser tool resizes or re-lays-out the page between captures
  (fonts not loaded, lazy content), re-capture before diffing; the diff
  would flag layout, not your change.
