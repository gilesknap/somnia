"""Measure the player's vertical rhythm, instead of looking at it and guessing.

A render tells you a layout is wrong. It does not tell you by how much, and on
2026-08-07 it did not tell you at all: the page looked right and four of its six
gaps were out, with all the slack pooled above the conversation rather than
below it. The design brief gives exact numbers — 14/14/12 between the groups,
one flexible spacer taking the rest — so the honest check is arithmetic.

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
"""

import json
import pathlib
import re
import subprocess
import sys

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


def measure(src, height, root=20):
    src = pathlib.Path(src)
    scaled = src.with_name(f".measure-{src.name}")
    html = src.read_text().replace(
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
    src = sys.argv[1]
    # 867, not 780 — the same number the docstring is emphatic about. A default
    # of 780 hands the caller who omits the argument a viewport of about 693 and
    # six gaps measured against a phone nobody has.
    d = measure(src, int(sys.argv[2]) if len(sys.argv) > 2 else 867)
    print(f"root={d['root']}px  viewport={d['viewport']}  scrollH={d['scrollH']}")
    print(f"SCROLLS: {d['scrollH'] > d['viewport'] + 1}")
    # The player carries no conversation at all now — the whole thread is the
    # keyboard-up screen — so on it there is one gap where there used to be two,
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
            ("header -> conversation (top of it)", gap(d["header"], d["firstSaid"]), 12),
            (
                "conversation -> title  (the flexible one: should be LARGEST)",
                gap(d["lastSaid"], d["bookTitle"]),
                "max",
            ),
        ]
    rows += [
        ("title group -> chapter group", gap(d["sleep"], d["chapterTitle"]), 14),
        ("chapter group -> transport", gap(d["chapterStrip"], d["transport"]), 14),
        ("transport -> dock (the pill itself)", gap(d["transport"], d["pill"]), 12),
        (
            "dock -> bottom of screen",
            round(d["viewport"] - d["pill"]["bottom"], 1) if d.get("pill") else None,
            4,
        ),
    ]
    for name, got, want in rows:
        flag = ""
        if isinstance(want, int) and got is not None:
            flag = (
                "  OK"
                if abs(got - want) <= 3
                else f"  <-- want {want}, off by {round(got - want, 1)}"
            )
        print(f"{name:<62} {got}{flag}")
