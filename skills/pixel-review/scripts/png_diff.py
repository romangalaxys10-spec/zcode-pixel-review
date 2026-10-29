#!/usr/bin/env python3
"""png_diff.py: stdlib-only pixel diff of two PNG screenshots.

Decodes PNG with zlib+struct (no PIL): 8-bit grayscale, RGB, gray+alpha,
and RGBA. 16-bit and bit-depth < 8 are rejected explicitly. Aligns the two
images to their top-left common area, computes a diff percentage for the
whole image and per named region, and writes a highlighted diff PNG where
changed pixels are painted red.

Usage:
  python3 png_diff.py baseline.png current.png \
      --threshold 2.0 --grid 3x3 \
      --regions "header=0,0,100,15,nav=15,0,50,10,main=15,10,50,55" \
      --out diff.png --json report.json

Exit codes:
  0 = every region at or under --threshold percent,
  1 = at least one region above --threshold,
  2 = usage or decode error.

Region modes:
  default: --grid ROWSXCOLS equal-cell grid, cells named r1c1, r1c2, ...
  --regions "a,b,c" (no '='): rename the first N grid cells row-major.
  --regions "name=TOP,LEFT,W,H": percent boxes over the common area, one or
     several, comma-separated. Use these to mark intended vs unintended
     zones (header, main content, unchanged sidebar).
"""

import argparse
import json
import struct
import sys
import zlib


class PngError(Exception):
    pass


class Png:
    """Decode a 8-bit PNG into row-major (r, g, b) byte rows."""

    def __init__(self, path):
        self.path = path
        raw = open(path, "rb").read()
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise PngError("%s: not a PNG file" % path)
        pos = 8
        color_type, bit_depth, width, height = 0, 0, 0, 0
        idat = []
        while True:
            if len(raw) - pos < 8:
                raise PngError("%s: truncated chunk list" % path)
            (length,) = struct.unpack(">I", raw[pos:pos + 4])
            tag = raw[pos + 4:pos + 8]
            body = raw[pos + 8:pos + 8 + length]
            if len(body) < length:
                raise PngError("%s: truncated chunk %r" % (path, tag))
            if tag == b"IHDR":
                width, height, bit_depth, color_type = struct.unpack(
                    ">IIBB", body[:10])
                interlace = body[11]
            elif tag == b"IDAT":
                idat.append(body)
            elif tag == b"IEND":
                break
            pos += 12 + length
        else:
            raise PngError("%s: no IEND chunk" % path)

        if interlace:
            raise PngError("%s: interlaced (Adam7) PNG not supported; "
                           "re-capture the screenshot non-interlaced"
                           % path)

        self.width, self.height = width, height
        if bit_depth != 8:
            raise PngError("%s: bit depth %d unsupported "
                           "(8-bit only)" % (path, bit_depth))
        channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
        if channels is None:
            raise PngError("%s: unsupported PNG color type %d "
                           "(palette/16-bit PNGs not decoded)"
                           % (path, color_type))
        stride = width * channels
        expected = height * (1 + stride)
        d = zlib.decompressobj()
        data = d.decompress(b"".join(idat))
        if not d.eof:
            raise PngError("%s: IDAT stream not fully consumed" % path)
        if len(data) < expected:
            raise PngError("%s: decompressed %d bytes < expected %d"
                           % (path, len(data), expected))
        self.rows = self._unfilter(data[:expected], height, stride,
                                   channels, width)

    def _unfilter(self, data, height, stride, channels, width):
        out = []
        prev = bytearray(stride)
        off = 0
        for _row in range(height):
            ft = data[off]
            off += 1
            cur = bytearray(data[off:off + stride])
            off += stride
            if ft == 0:
                pass
            elif ft == 1:  # Sub
                for i in range(channels, stride):
                    cur[i] = (cur[i] + cur[i - channels]) & 0xFF
            elif ft == 2:  # Up
                for i in range(stride):
                    cur[i] = (cur[i] + prev[i]) & 0xFF
            elif ft == 3:  # Average
                for i in range(stride):
                    left = cur[i - channels] if i >= channels else 0
                    cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 0xFF
            elif ft == 4:  # Paeth
                for i in range(stride):
                    left = cur[i - channels] if i >= channels else 0
                    up = prev[i]
                    upleft = prev[i - channels] if i >= channels else 0
                    p = left + up - upleft
                    pa, pb, pc = abs(p - left), abs(p - up), abs(p - upleft)
                    if pa <= pb and pa <= pc:
                        pr = left
                    elif pb <= pc:
                        pr = up
                    else:
                        pr = upleft
                    cur[i] = (cur[i] + pr) & 0xFF
            else:
                raise PngError("invalid filter type %d" % ft)
            # convert to RGB: gray -> ggg, gray+alpha premultiplied onto white
            if channels == 1:
                row = bytearray()
                for x in range(width):
                    v = cur[x]
                    row += bytes((v, v, v))
            elif channels == 2:
                row = bytearray()
                for x in range(width):
                    g = cur[x * 2]
                    a = cur[x * 2 + 1]
                    if a >= 255:
                        row += bytes((g, g, g))
                    elif a <= 0:
                        row += bytes((255, 255, 255))
                    else:
                        m = g * a + 255 * (255 - a)
                        v = (m + 127) // 255
                        row += bytes((v, v, v))
            elif channels == 3:
                row = bytes(cur)
            else:
                row = bytearray()
                for x in range(width):
                    r = cur[x * 3]
                    g = cur[x * 3 + 1]
                    b = cur[x * 3 + 2]
                    a = cur[x * 3 + 3]
                    if a >= 255:
                        row += bytes((r, g, b))
                    elif a <= 0:
                        row += bytes((255, 255, 255))
                    else:
                        row += bytes((
                            (r * a + 255 * (255 - a) + 127) // 255,
                            (g * a + 255 * (255 - a) + 127) // 255,
                            (b * a + 255 * (255 - a) + 127) // 255,
                        ))
            out.append(bytes(row))
            prev = cur
        return out


def common_area(a, b):
    return min(a.width, b.width), min(a.height, b.height)


def region_cells(w, h, cols, rows, names=None):
    cw, ch = w // cols, h // rows
    regions = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            name = "r%d c%d" % (r + 1, c + 1)
            if names and idx < len(names):
                name = names[idx].strip()
            idx += 1
            x0 = c * cw
            y0 = r * ch
            x1 = w if c == cols - 1 else (c + 1) * cw
            y1 = h if r == rows - 1 else (r + 1) * ch
            regions.append((name, x0, y0, x1, y1))
    return regions


def region_boxes(w, h, spec):
    """Box specs are 'name=TOP,LEFT,W,H' (percent of the common area).

    Multiple boxes are separated by ';'; commas only appear inside a box.
    A spec with no ';' is treated as a single box.
    """
    parts = spec.split(";") if ";" in spec else [spec]
    regions = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise PngError("percent-box regions need 'name=TOP,LEFT,W,H'; "
                           "bare names are treated as grid cell renames")
        name, box = part.split("=", 1)
        vals = box.split(",")
        if len(vals) != 4:
            raise PngError("region box needs 4 values, boxes separated "
                           "by ';': %r" % part)
        t, l, bw, bh = (float(v) for v in vals)
        x0 = int(l / 100.0 * w)
        y0 = int(t / 100.0 * h)
        x1 = min(w, int((l + bw) / 100.0 * w))
        y1 = min(h, int((t + bh) / 100.0 * h))
        regions.append((name.strip(), x0, y0, x1, y1))
    return regions


def diff(a, b, regions, tol):
    w, h = common_area(a, b)
    changed = bytearray(w * h)
    regions_out = []
    total_diffed = 0
    for name, x0, y0, x1, y1 in regions:
        if x0 >= x1 or y0 >= y1:
            regions_out.append((name, 0.0, 0, 0))
            continue
        pixels, diffed = 0, 0
        for y in range(y0, y1):
            ra = a.rows[y]
            rb = b.rows[y]
            base = x0 * 3
            for x in range(x0, x1):
                pixels += 1
                i = base + (x - x0) * 3
                d = (abs(ra[i] - rb[i])
                     + abs(ra[i + 1] - rb[i + 1])
                     + abs(ra[i + 2] - rb[i + 2])) / 3.0
                if d > tol:
                    diffed += 1
                    changed[y * w + x] = 1
        total_diffed += diffed
        regions_out.append((name, 100.0 * diffed / pixels, pixels, diffed))
    whole = 100.0 * total_diffed / (w * h)
    return whole, regions_out, changed


def write_diff_png(out_path, a, w, h, changed, tol):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        base = y * w
        row = a.rows[y]
        for x in range(w):
            i = x * 3
            if changed[base + x]:
                raw += b"\xff\x20\x20"
            else:
                g, g2, g3 = row[i], row[i + 1], row[i + 2]
                v = (g * 77 + g2 * 150 + g3 * 29) // 256
                raw += bytes((v, v, v))
        del row

    def chunk(tag, body):
        c = struct.pack(">I", len(body)) + tag + body
        return c + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(out_path, "wb") as f:
        f.write(png)


def main():
    ap = argparse.ArgumentParser(
        description="Pixel-diff two PNG screenshots (stdlib only). "
                    "Exit 1 when a region's diff percent exceeds "
                    "--threshold."
    )
    ap.add_argument("baseline", help="before PNG")
    ap.add_argument("current", help="after PNG")
    ap.add_argument("--threshold", type=float, default=2.0,
                    help="max allowed diff percent per region (default 2.0)")
    ap.add_argument("--tolerance", type=int, default=16,
                    help="mean per-channel difference a pixel counts as "
                         "unchanged (0-255, default 16)")
    ap.add_argument("--grid", default="3x3",
                    help="region grid ROWSXCOLS (default 3x3, 1..5 each)")
    ap.add_argument("--regions", default="",
                    help="comma list of cell names (renames grid cells, "
                         "row-major) or percent boxes name=TOP,LEFT,W,H")
    ap.add_argument("--out", default="diff.png",
                    help="highlighted diff PNG to write (default diff.png)")
    ap.add_argument("--json", default="",
                    help="optional path for a JSON report")
    args = ap.parse_args()

    if not 0 <= args.tolerance <= 255:
        print("error: --tolerance must be 0-255", file=sys.stderr)
        return 2
    if "x" not in args.grid:
        print("error: --grid must be ROWSXCOLS", file=sys.stderr)
        return 2
    try:
        rows, cols = (int(t) for t in args.grid.lower().split("x"))
    except ValueError:
        print("error: --grid must be ROWSXCOLS", file=sys.stderr)
        return 2
    if not (1 <= rows <= 5 and 1 <= cols <= 5):
        print("error: --grid rows and cols must be 1..5", file=sys.stderr)
        return 2

    try:
        a = Png(args.baseline)
        b = Png(args.current)
    except (PngError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2

    w, h = common_area(a, b)
    if w == 0 or h == 0:
        print("error: images share no area (%dx%d vs %dx%d)"
              % (a.width, a.height, b.width, b.height), file=sys.stderr)
        return 2

    try:
        if "=" in args.regions:
            regions = region_boxes(w, h, args.regions)
        else:
            names = args.regions.split(",") if args.regions else None
            regions = region_cells(w, h, cols, rows, names)
    except PngError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2

    whole, region_stats, changed = diff(a, b, regions, args.tolerance)
    write_diff_png(args.out, a, w, h, changed, args.tolerance)

    report = {
        "baseline": args.baseline,
        "current": args.current,
        "baseline_size": [a.width, a.height],
        "current_size": [b.width, b.height],
        "common_area": [w, h],
        "threshold_percent": args.threshold,
        "tolerance": args.tolerance,
        "whole_image_diff_percent": round(whole, 4),
        "regions": [
            {"name": n, "diff_percent": round(p, 4), "pixels": px,
             "changed": ch, "pass": p <= args.threshold}
            for n, p, px, ch in region_stats
        ],
        "diff_image": args.out,
    }
    failing = [r["name"] for r in report["regions"] if not r["pass"]]
    report["pass"] = not failing
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    if failing:
        print("FAIL: region(s) over threshold: %s" % ", ".join(failing),
              file=sys.stderr)
        return 1
    print("PASS: all regions at or under %.2f%% diff" % args.threshold,
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
