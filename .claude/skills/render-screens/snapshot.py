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
        # The count alone. The word `chapter` above it is on the page as static
        # markup, because it never changes — and a book nobody counted takes it
        # away and says "chapter 4" here instead, which is a state worth
        # photographing by hand and not the one moment this fixture holds.
        "chapter-count": "4 of 37",
        "chapter-clock": "3:24 of 41:12",
        "clock": "1:12:08 of 9:41:33",
        # The places from the last question, counted under the position line. It
        # is the taller of that line's two states — a book nobody has asked
        # about carries no count, no dotted rule and no target — so it is the
        # one worth holding here: if this fits, both fit. It is also the state
        # the transcript below is in, which has just asked two questions.
        "places-found": "4 places found",
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
    "unhide": ["player-bar", "places-found"],
    # Which screen the page is on. app.js measures the keyboard and writes this
    # onto <body>, and the sheet reads it for everything that differs between
    # the player and the chat — so in a snapshot, which has no app.js, a body
    # with no class on it is a page on neither screen: no player arrangement, no
    # chat, and a height that changes nothing. The player is the default because
    # it is what the page boots on; `render.py --screen chat` swaps it.
    "body": ["player-screen"],
    # `openable` is drawPlaces' class and it carries the dotted rule and the
    # 44dp target, so without it the render would show the count under a line
    # that does not look pressable — which is a different screen from the one
    # the page draws when there are places.
    "classes": {
        "playpause": ["playing"],
        "places-open": ["openable"],
    },
    # Inline style, by id. The dim layer is the only thing that needs it, and it
    # needs it for a reason worth writing down: app.js does not run in a
    # snapshot, so the level the reader is actually looking through is set here
    # instead. Without it a future render is a photograph of a page 12% brighter
    # than the one on the phone — which is exactly the kind of plausible, wrong
    # picture this whole file exists to prevent. The value is style.css's own
    # default, restated; if the two ever drift the render is the one that lies.
    # `whole-played` is here for the same reason as `dim`, and it matters more:
    # drawPlayer sets the fill and drawPlayer does not run in a snapshot, so
    # without this every render photographs a book nobody has started — an
    # empty track with the knob parked at the gutter — whatever the clock above
    # it says. 12.4% is 1:12:08 of 9:41:33, so the line and the numbers beside
    # it are telling the same story.
    "styles": {"dim": {"opacity": "0.12"}, "whole-played": {"width": "12.4%"}},
}

# The two overlays, which are the half of this app app.js draws and a snapshot
# therefore cannot see at all. Without this every render of Books is a screen
# with a heading and no books under it, and Workshop is a search box over
# nothing — which is not the page, and is exactly the plausible-and-wrong
# picture this file exists to prevent.
#
# The row shapes are app.js's, class for class, and that duplication is the
# price of photographing a screen whose contents are built in JavaScript. What
# keeps it honest is that a class renamed in app.js draws an unstyled row here,
# which is loud in a render rather than quiet.
#
# The book in `reading now` is the fixture's own — same title, same chapter,
# same position as the player — so a render of Books and a render of the player
# are two views of one moment.
PANELS = {
    "books": {
        "unhide": ["queue", "reading-now", "reading-track", "shelf-label"],
        "text": {
            "reading-title": "The Wind in the Willows",
            "reading-meta": "chapter 4 of 37 · 1h12m in",
            "reading-resume": "pick it up at 1:12:08",
        },
        "styles": {"reading-fill": {"width": "12.4%"}, "dim-fill": {"width": "20%"}},
        # Three books, which is the shape of a real shelf on this box, and one
        # of them long enough to wrap. Titles only: Books gave the author up
        # when it took the player's type scale — see whoWrote in app.js.
        "shelf": [
            ["Black Beauty", "0:41:19 in", "pick it up"],
            ["The Adventures of Sherlock Holmes", "not started", "pick it up"],
            ["The Moonstone", "2:03:55 in · part rendered", "pick it up"],
        ],
    },
    "workshop": {
        "unhide": ["queue", "workshop", "queue-working", "queue-ended"],
        "text": {"queue-note": "", "queue-said": ""},
        "found": [
            ["Treasure Island", "Stevenson, Robert Louis, 1850-1894", "", "add this book"],
            ["Kidnapped", "Stevenson, Robert Louis, 1850-1894", "already here", None],
            ["The Black Arrow", "Stevenson, Robert Louis, 1850-1894", "part rendered", "finish this one"],
        ],
        "live": [
            ["Black Beauty — Sewell, Anna", "narrating", "chapter 4 of 39 · 1h12m read so far", "10.3%"],
            ["Treasure Island — Stevenson, Robert Louis", "queued", "1st in line", None],
        ],
        "gone": [
            ["The Moonstone — Collins, Wilkie", "stopped", "stopped part way — what was read still plays", None],
        ],
        # 30 is the shipped default, and the render has to show which of the
        # three is lit or the control photographs as three identical pills.
        "chosen": "jump-30",
    },
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

  document.body.classList.add(...FIXTURE.body);

  for (const [id, classes] of Object.entries(FIXTURE.classes)) {
    const el = document.getElementById(id);
    if (el) el.classList.add(...classes);
  }

  for (const [id, style] of Object.entries(FIXTURE.styles)) {
    const el = need(id);
    if (el) Object.assign(el.style, style);
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

  const PANEL = %s;
  if (PANEL) {
    for (const id of PANEL.unhide || []) {
      const el = need(id);
      if (el) el.hidden = false;
    }
    for (const [id, text] of Object.entries(PANEL.text || {})) {
      const el = need(id);
      if (el) el.textContent = text;
    }
    for (const [id, style] of Object.entries(PANEL.styles || {})) {
      const el = need(id);
      if (el) Object.assign(el.style, style);
    }
    if (PANEL.chosen) need(PANEL.chosen)?.classList.add("chosen");

    const put = (id, kids) => {
      const list = need(id);
      if (list) list.replaceChildren(...kids);
    };
    const p = (cls, text) => {
      const el = document.createElement("p");
      el.className = cls;
      el.textContent = text;
      return el;
    };
    const div = (cls, ...kids) => {
      const el = document.createElement("div");
      el.className = cls;
      el.append(...kids);
      return el;
    };
    const pill = (cls, text) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = cls;
      el.textContent = text;
      return el;
    };
    const bar = (trackCls, fillCls, width) => {
      const track = document.createElement("div");
      track.className = trackCls;
      const fill = document.createElement("div");
      fill.className = fillCls;
      fill.style.width = width;
      track.append(fill);
      return track;
    };

    put("shelf", (PANEL.shelf || []).map(([name, meta, press]) => {
      const li = document.createElement("li");
      li.className = "shelved";
      const text = div("shelved-text", p("shelved-name", name), p("shelved-meta", meta));
      const line = div("shelved-line", text);
      if (press) line.append(pill("shelved-open", press));
      li.append(line);
      return li;
    }));

    put("queue-results", (PANEL.found || []).map(([name, by, have, press]) => {
      const li = document.createElement("li");
      li.className = "found";
      const meta = p("found-meta", "");
      const who = document.createElement("span");
      who.className = "found-by";
      who.textContent = by;
      meta.append(who);
      if (have) {
        const mark = document.createElement("span");
        mark.className = "found-have";
        mark.textContent = have;
        meta.append(mark);
      }
      li.append(div("found-text", p("found-name", name), meta));
      if (press) {
        li.append(pill(press === "finish this one" ? "found-add again" : "found-add", press));
      }
      return li;
    }));

    const jobRow = (gone) => ([name, stage, state, width]) => {
      const li = document.createElement("li");
      li.className = gone ? "job gone" : "job";
      const head = div("job-line", p("job-name", name), p("job-stage" + (gone ? "" : " now"), stage));
      li.append(head, p("job-state", state));
      if (width) li.append(bar("job-track", "job-fill", width));
      if (!gone) li.append(pill("job-stop", "stop reading this"));
      return li;
    };
    put("queue-live", (PANEL.live || []).map(jobRow(false)));
    put("queue-gone", (PANEL.gone || []).map(jobRow(true)));
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
            sys.exit(
                f"snapshot: style.css asks for {match.group(1)} and it is not in {WEB}"
            )
        data = base64.b64encode(path.read_bytes()).decode()
        return f'url("data:font/woff2;base64,{data}")'

    return re.sub(r'url\("([^"]+\.woff2)"\)', swap, css)


def build(out, panel=None):
    html = (WEB / "index.html").read_text()
    css = inline_fonts((WEB / "style.css").read_text())

    for old, new in [
        ('<link rel="stylesheet" href="style.css" />', f"<style>\n{css}\n</style>"),
        ('<script src="app.js"></script>', ""),
    ]:
        if old not in html:
            sys.exit(f"snapshot: expected to find {old!r} in index.html and did not")
        html = html.replace(old, new)

    filled = FILL % (json.dumps(FIXTURE), json.dumps(PANELS.get(panel)))
    html = html.replace("</body>", filled + "</body>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument(
        "--panel",
        choices=sorted(PANELS),
        help="raise an overlay over the page and fill its lists: books, or workshop over it",
    )
    args = ap.parse_args()
    if args.panel and args.panel not in PANELS:
        sys.exit(f"snapshot: no fixture for panel {args.panel}")
    print(build(args.out, args.panel))
