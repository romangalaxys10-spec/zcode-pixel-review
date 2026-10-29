# Pixel Review

Visual regression gate that blocks "done" claims on agentic UI changes.

## Why

Agents edit UI code and report success without ever looking at the pixels.
A header move, a font shift, or a layout reflow can land "correctly" in the
code while breaking the screen. Pixel Review forces a before/after
screenshot pair through a diff gate: per-region diff percentages, a
red-highlighted diff image, and a verdict that says BLOCK when unintended
regions moved beyond the threshold.

## How it works

1. Baseline: capture the page before the UI code is edited (browser tool
   or user-supplied screenshot).
2. Edit: the agent changes the UI and names the intended regions.
3. Diff: `png_diff.py` (stdlib, no pip deps) decodes both PNGs, aligns
   sizes, computes whole-image and per-region diff percentages, and writes
   a highlighted diff PNG. Exit code 1 on over-threshold regions.
4. Gate: the agent reviews the diff image, runs a structural text check
   when DOM access is available, and reports PASS or BLOCK.

## Install

Option A: self-installable marketplace.

- Clone or download this repo.
- ZCode: Plugin Marketplace -> Add -> Add Plugin Marketplace.
- Paste the folder path to this repo.
- Install the `pixel-review` plugin from the list.

Option B: manual copy.

- Copy this folder into your workspace `plugins/` directory
  (e.g. `~/.zcode/workspace/<name>/plugins/pixel-review`).
- Restart the session so the skill loads.

## Try it

```
/pixel-review pixel-review/baseline-1280px.png pixel-review/current-1280px.png --regions "header=0,0,100,12;main=12,10,100,60"
```

Expected: a JSON report with per-region diff percentages, a
`diff.png` with changed pixels in red, and a PASS or BLOCK verdict
stating which region tripped the gate.

## Requirements

- Python 3 standard library only.
- 8-bit PNG screenshots (grayscale, RGB, or RGBA). 16-bit, paletted, and
  interlaced PNGs are rejected with a clear error; re-capture instead.
- Screenshots should be taken with fonts loaded and lazy content settled,
  or the diff measures layout noise instead of your change.

---

<p align="center">
  <a href="https://z.ai/subscribe?ic=R0K78RJKNW"><img alt="z.ai coding plans - 10% OFF coupon" src="https://img.shields.io/badge/z.ai%20coding%20plans-10%25%20OFF%20coupon-blueviolet" /></a>
  <a href="https://zcode.z.ai/invite/ALWM9JUA"><img alt="Try ZCode free" src="https://img.shields.io/badge/Try%20ZCode-free%20invite-0969da" /></a>
</p>

## License

MIT.
