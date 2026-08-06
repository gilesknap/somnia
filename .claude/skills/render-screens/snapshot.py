"""Turn the live page into a self-contained, static screen worth looking at.

The point is that this reads `src/somnia/web/index.html` and `style.css` every
time, so what gets rendered is the page as it is now and not a copy of it that
was true last week.

It fills the sample state by element **id**, from a script injected at load,
rather than by rewriting the markup. Ids are the stable part of this page; the
markup around them is the part being redesigned. A snapshot that keyed on exact
markup would quietly stop filling anything the first time a wrapper moved, and
the render would look plausible and be wrong — which is the one failure mode
that matters here, because the whole point of the picture is to be trusted.

Anything in FIXTURE that is not on the page is reported, not ignored: a name
printed under "not on the page" is either drift to fix here or a thing the
redesign removed.
"""

import argparse
import base64
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "somnia" / "web"

# One moment of one book, used by every screen so that any two renders can be
# put side by side. A long book title and a Roman-numeral chapter on purpose:
# both are the shapes that overflow.
FIXTURE = {
    "text": {
        "book-title": "The Wind in the Willows",
        "chapter-title": "IV. Mr Toad",
        "chapter-count": "chapter 4 of 37",
        "chapter-clock": "3:24 of 41:12",
        "clock": "1:12:08 of 9:41:33",
        "sleep": "sleep timer · off",
    },
    # The conversation, oldest first. The last line is the reader's, because
    # that is the state the page is in between asking and being answered.
    "transcript": [
        ("agent", "Where do you want to be?"),
        ("you", "the bit where they set off in the caravan"),
        ("agent", "Chapter two, about nine minutes in. Moving there now."),
        ("you", "and then where the horse bolts"),
    ],
    # Shown as if a book were playing: without this the page renders its
    # opening state, which is not the one anybody is designing.
    "unhide": ["player-bar"],
    "classes": {"playpause": ["playing"], "playpause-mini": ["playing"]},
}

FILL = """
<script>
  const FIXTURE = %s;
  const missing = [];
  const need = (id) => {
    const el = document.getElementById(id);
    if (!el) missing.push(id);
    return el;
  };

  for (const [id, text] of Object.entries(FIXTURE.text)) {
    const el = need(id);
    if (el) el.textContent = text;
  }

  for (const id of FIXTURE.unhide) {
    const el = need(id);
    if (el) el.hidden = false;
  }

  for (const [id, classes] of Object.entries(FIXTURE.classes)) {
    const el = document.getElementById(id);
    if (el) el.classList.add(...classes);
  }

  const transcript = need("transcript");
  if (transcript) {
    transcript.replaceChildren(
      ...FIXTURE.transcript.map(([who, what]) => {
        const p = document.createElement("p");
        p.className = "said " + who;
        p.textContent = what;
        return p;
      })
    );
  }

  // Rendered into the page rather than logged: a headless screenshot is the
  // only output, so a console warning nobody reads is the same as no warning.
  if (missing.length) {
    const flag = document.createElement("pre");
    flag.textContent = "not on the page: " + missing.join(", ");
    flag.style.cssText =
      "position:fixed;left:0;right:0;bottom:0;z-index:99;margin:0;padding:4px 6px;" +
      "font:12px/1.4 monospace;color:#1a1a1a;background:#c9a227;white-space:pre-wrap";
    document.body.append(flag);
  }
</script>
"""


def inline_fonts(css):
    """Fold the page's own woff2 files into the stylesheet as data URIs.

    The snapshot is written to /tmp, so a relative `url("newsreader-latin.woff2")`
    resolves next to the snapshot and finds nothing — and a render in the wrong
    serif is a render of the wrong page, because every size in style.css was
    measured against this one. This machine has neither Newsreader nor Georgia
    installed, so the miss is silent and looks plausible.
    """

    def swap(match):
        path = WEB / match.group(1)
        if not path.exists():
            sys.exit(f"snapshot: style.css asks for {match.group(1)} and it is not in {WEB}")
        data = base64.b64encode(path.read_bytes()).decode()
        return f'url("data:font/woff2;base64,{data}")'

    return re.sub(r'url\("([^"]+\.woff2)"\)', swap, css)


def build(out):
    html = (WEB / "index.html").read_text()
    css = inline_fonts((WEB / "style.css").read_text())

    for old, new in [
        ('<link rel="stylesheet" href="style.css" />', f"<style>\n{css}\n</style>"),
        ('<script src="app.js"></script>', ""),
    ]:
        if old not in html:
            sys.exit(f"snapshot: expected to find {old!r} in index.html and did not")
        html = html.replace(old, new)

    html = html.replace("</body>", FILL % json.dumps(FIXTURE) + "</body>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    print(build(ap.parse_args().out))
