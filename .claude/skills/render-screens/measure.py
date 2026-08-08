"""Measure the player's vertical rhythm, instead of looking at it and guessing.

A render tells you a layout is wrong. It does not tell you by how much, and on
2026-08-07 it did not tell you at all: the page looked right and four of its six
gaps were out, with all the slack pooled above the conversation rather than
below it. The design brief gives three weighted spacers with floors and ceilings —
2:1:1, 12/14/14 floors, 180/70/70 ceilings — so the honest check is
arithmetic.

Run it against a snapshot, not the live page:

    python3 snapshot.py --out /tmp/somnia/page.html
    python3 measure.py /tmp/somnia/page.html 867

**Pass 867, not 780.** Headless Chrome's `--dump-dom` opens a real window with
real chrome, unlike `--screenshot`, so the viewport comes up about 87px short;
867 lands `innerHeight` on the 780 the phone actually has. The script prints the
viewport it got — if that is not 780, the numbers under it are about a different
phone and the flexible gap will be wrong or negative.

SCROLLS must stay False. The brief makes "the player does not scroll at 360x780"
a hard rule, and it is the first thing any added row breaks.

    python3 measure.py /tmp/somnia/page.html 867 --text-scale 1.3

is the other phone, and the harder one: the reader's text scale as Chrome for
Android really applies it — every font size multiplied, every rem length left
where it is, root 16. The 20px root above grows the spacing along with the type,
so it can only ever report that a layout fits; this asks the question the three
spacers actually face. See render.py for why the two are different phones.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

from render import resolve_root, scale_text

PROBE = """
<script>
window.addEventListener('load', () => {
  const box = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {top: r.top, bottom: r.bottom, height: r.height};
  };
  // Only the turns that are actually on the screen. On the player the sheet
  // draws the newest turn and hides the rest, so querying them all put a
  // display:none element — a rect of all zeroes — at the top of the
  // conversation, and the first gap came out as -48 against a layout that was
  // right. A hidden turn is not where the reading starts.
  const said = [...document.querySelectorAll('#transcript .said')]
    .filter((el) => el.getClientRects().length > 0);
  const last = said.length ? said[said.length - 1].getBoundingClientRect() : null;
  const out = {
    root: parseFloat(getComputedStyle(document.documentElement).fontSize),
    header: box('header'),
    lastSaid: last ? {top: last.top, bottom: last.bottom} : null,
    firstSaid: said.length ? {top: said[0].getBoundingClientRect().top,
                              bottom: said[0].getBoundingClientRect().bottom} : null,
    pill: box('#question'),
    bookTitle: box('#book-title'),
    whereabouts: box('#whereabouts'),
    sleep: box('#sleep'),
    chapterTitle: box('#chapter-title'),
    chapterStrip: box('.chapter-strip'),
    nowPlaying: box('#now-playing'),
    transport: box('.transport'),
    composer: box('#composer'),
    viewport: window.innerHeight,
    scrollH: document.documentElement.scrollHeight,
  };
  document.title = 'MEASURED' + JSON.stringify(out);
});
</script>
</head>"""


def measure(src, height, root=20, text_scale=1.0):
    src = pathlib.Path(src)
    scaled = src.with_name(f".measure-{src.name}")
    html = scale_text(src.read_text(), text_scale).replace(
        "</head>", f"<style>html {{ font-size: {root}px; }}</style>{PROBE}"
    )
    scaled.write_text(html)
    try:
        dom = subprocess.run(
            [
                "google-chrome",
                "--headless",
                "--disable-gpu",
                "--dump-dom",
                f"--window-size=360,{height}",
                "--virtual-time-budget=2000",
                str(scaled),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    finally:
        scaled.unlink(missing_ok=True)
    m = re.search(r"MEASURED(\{.*?\})</title>", dom, re.S)
    if not m:
        sys.exit("probe did not run — no MEASURED payload in the DOM")
    return json.loads(m.group(1))


def gap(a, b):
    if not a or not b:
        return None
    return round(b["top"] - a["bottom"], 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    # 867, not 780 — the same number the docstring is emphatic about. A default
    # of 780 hands the caller who omits the argument a viewport of about 693 and
    # six gaps measured against a phone nobody has.
    ap.add_argument("height", nargs="?", type=int, default=867)
    ap.add_argument("--root", type=int, default=None)
    ap.add_argument(
        "--text-scale",
        type=float,
        default=1.0,
        help="the reader's Android/Chrome text scale: type x this, lengths as-is",
    )
    a = ap.parse_args()
    d = measure(a.src, a.height, resolve_root(a.root, a.text_scale), a.text_scale)
    scale = f"  text x{a.text_scale}" if a.text_scale != 1 else ""
    vp, sh = d["viewport"], d["scrollH"]
    print(f"root={d['root']}px{scale}  viewport={vp}  scrollH={sh}")
    print(f"SCROLLS: {d['scrollH'] > d['viewport'] + 1}")
    # The player carries no conversation at all now — the whole thread is on the
    # chat screen — so on it there is one gap where there used to be two,
    # and it runs from the header straight down to the book. Measured from
    # whatever is actually on the screen rather than from a hidden element,
    # because a `display: none` turn has a rect of all zeroes and reported -48
    # against a layout that was right.
    if d["firstSaid"] is None:
        rows = [
            (
                "header -> title  (the flexible one: should be LARGEST)",
                gap(d["header"], d["bookTitle"]),
                "max",
            ),
        ]
    else:
        rows = [
            (
                "header -> conversation (top of it)",
                gap(d["header"], d["firstSaid"]),
                12,
            ),
            (
                "conversation -> title  (the flexible one: should be LARGEST)",
                gap(d["lastSaid"], d["bookTitle"]),
                "max",
            ),
        ]
    rows += [
        # Spacers B and C are a range, not a number. The design gives them a
        # floor of 14 and a ceiling of 70 and shares the slack 2:1:1 with the
        # spacer above the title, so what they measure depends on how much room
        # the zoom level left over. A fixed 14 here would report a correct
        # screen as broken on every phone but the tightest.
        ("title group -> chapter group", gap(d["sleep"], d["chapterTitle"]), (14, 70)),
        (
            "chapter group -> transport",
            gap(d["chapterStrip"], d["transport"]),
            (14, 70),
        ),
        ("transport -> dock (the pill itself)", gap(d["transport"], d["pill"]), 12),
        (
            "dock -> bottom of screen",
            round(d["viewport"] - d["pill"]["bottom"], 1) if d.get("pill") else None,
            4,
        ),
    ]
    for name, got, want in rows:
        flag = ""
        if isinstance(want, tuple) and got is not None:
            lo, hi = want
            flag = (
                f"  OK (floor {lo}, ceiling {hi})"
                if lo - 1 <= got <= hi + 1
                else f"  <-- want {lo}..{hi}"
            )
        elif isinstance(want, int) and got is not None:
            flag = (
                "  OK"
                if abs(got - want) <= 3
                else f"  <-- want {want}, off by {round(got - want, 1)}"
            )
        print(f"{name:<62} {got}{flag}")
