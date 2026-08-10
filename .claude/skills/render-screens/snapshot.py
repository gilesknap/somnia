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
        # The widest the pill ever gets, for the reason the count above it is
        # held at its taller state: if this fits, every other state does. It
        # used to sit here at `off`, which is the narrowest of the six, and the
        # label has since become a countdown — `60 min left` is eight characters
        # more than the `45m` this row was last measured against, on a row that
        # was already described as only just fitting.
        "sleep": "sleep timer · 60 min left",
        # The morning, which app.js writes out of the record the fade left. The
        # time is the small hours because that is when the timer runs, and it is
        # the one-digit hour on purpose: it is the narrowest the headline ever
        # gets, so a render at this time cannot be read as proof that a wider one
        # fits. The position is the fixture's own, so the morning and the player
        # are two views of one book.
        "wake-said": "The timer faded you out at 1:47.",
        "wake-keep": "keep it where it stopped · 1:12:08",
        # The same count as the position line above, because it is the same list
        # said twice — drawPlaces writes one string into both, and a fixture that
        # held two different numbers here would photograph the bug this screen
        # was warned about rather than the page.
        "wake-found": "4 places found",
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
    # `wake-places` is the morning's first choice, which drawPlaces shows only on
    # the mornings there is a list to open. It is the taller of that screen's two
    # states, so it is the one worth holding — and it costs the other screens
    # nothing, because the whole of #wake is display:none unless <body> says the
    # page is on it.
    "unhide": ["player-bar", "places-found", "wake-places"],
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
        # `shelf-more` is up because the night it is drawn on is the night worth
        # looking at: the shelf stops at twenty books and this line is the only
        # thing that says so. Three rows and the line is not the twenty-book
        # case, and deliberately — twenty repeats of one row would photograph
        # the scroller rather than the thing being decided, which is how heavy
        # an italic aside is against the titles above it.
        "unhide": [
            "queue",
            "reading-now",
            "reading-track",
            "shelf-label",
            "shelf-more",
        ],
        "text": {
            "reading-title": "The Wind in the Willows",
            # The time is in this line now — it used to be the label of a pill
            # under the block, and the pill is gone. Nothing on `reading now`
            # is a button any more: the block is the press.
            "reading-meta": "chapter 4 of 37 · picks up at 1:12:08",
        },
        "styles": {"reading-fill": {"width": "12.4%"}, "dim-fill": {"width": "20%"}},
        # Three books, which is the shape of a real shelf on this box, and one
        # of them long enough to wrap. Titles only: Books gave the author up
        # when it took the player's type scale — see whoWrote in app.js.
        #
        # The third value is whether the row is a press at all, not what a
        # button on it says: a book with no audio yet is a plain div and every
        # other row is a button wrapping the whole of itself.
        "shelf": [
            ["Black Beauty", "0:41:19 in", True],
            ["The Adventures of Sherlock Holmes", "not started", True],
            ["The Moonstone", "2:03:55 in · part rendered", True],
        ],
    },
    # The list the whole spoiler rule is arranged around, and the one screen in
    # this app whose height is decided by its content rather than by its
    # controls. It was unphotographable until this fixture existed, which is
    # part of why its type sat two notches below what a night screen wants and
    # nobody saw: every render of Places was a heading over an empty <ol>.
    #
    # The shape is the one the server actually offers — four places at most,
    # the mark somewhere among them — and every state a row can be in is on it
    # at once, which is the only way one picture answers the question this
    # screen now raises: with the words hidden on every row, does an `ahead` row
    # still look different from a closed row it is safe to open?
    #
    # So: one closed row behind the mark, one revealed, two closed ahead. The
    # revealed one carries a long passage, because the length of a passage is
    # what this screen's height turns on and a list that fits with everything
    # covered and overflows the moment somebody reads one of them is a list that
    # fits only in the picture nobody took. It is no longer the opening state —
    # the list arrives with all four covered and much shorter than this — and
    # that is the point: this is the ceiling, not the greeting.
    "places": {
        "unhide": ["candidates"],
        "text": {"candidates-summary": "4 places between 0:58:14 and 2:11:40"},
        # `ahead` is the server's word for a place they have not reached. It no
        # longer decides whether the words are on the page — nothing is, until
        # the press — so what is left to it is which hint the row carries and
        # whether the chapter is named. `revealed` is the press having happened.
        "places": [
            [
                "0:58:14",
                "Ch 3 · The Wild Wood",
                "The Rat was sitting on the river bank, singing a little song.",
                False,
                False,
            ],
            [
                "1:09:02",
                "Ch 4 · Mr. Badger",
                "He had been having a long and comfortable dream, and it was "
                "only the cold that woke him at last, and the sound of the wind "
                "in the bare branches over his head.",
                False,
                True,
            ],
            ["1:24:51", "Ch 4", "", True, False],
            ["2:11:40", "Ch 6", "", True, False],
        ],
        # Where the rule goes: after the second row, which is the last one at or
        # before the position the rest of the fixture is set at. It is a place
        # like the rest now — a time, words behind a press, and the way back —
        # so the picture has to hold all three.
        "here": {
            "at": "1:12:08",
            "after": 2,
            "more": True,
            "back": True,
            "text": "and the tide had gone a long way out, further than he "
            "had ever seen it go.",
            "revealed": False,
        },
    },
    "workshop": {
        "unhide": ["queue", "workshop", "queue-working", "queue-ended"],
        "text": {"queue-note": "", "queue-said": ""},
        # The dim layer comes off while this screen is up — app.js does it in
        # drawDim, and drawDim does not run in a snapshot. Without this every
        # render of Workshop is the daylight screen photographed through 12% of
        # black, which is the one thing this screen is not.
        "styles": {"dim": {"opacity": "0"}},
        "found": [
            [
                "Treasure Island",
                "Stevenson, Robert Louis, 1850-1894",
                "",
                "add this book",
            ],
            ["Kidnapped", "Stevenson, Robert Louis, 1850-1894", "already here", None],
            [
                "The Black Arrow",
                "Stevenson, Robert Louis, 1850-1894",
                "part rendered",
                "finish this one",
            ],
        ],
        "live": [
            [
                "Black Beauty — Sewell, Anna",
                "narrating",
                "chapter 4 of 39 · 1h12m read so far",
                "10.3%",
            ],
            [
                "Treasure Island — Stevenson, Robert Louis",
                "queued",
                "1st in line",
                None,
            ],
        ],
        "gone": [
            [
                "The Moonstone — Collins, Wilkie",
                "stopped",
                "stopped part way — what was read still plays",
                None,
            ],
        ],
    },
    # Settings, the third night screen, and the one overlay with no list on it
    # at all: three controls and the sentences under them. It is raised over the
    # player rather than over Books — the pill that opens it is in the player's
    # own top-right corner — so nothing under it is unhidden here.
    #
    # The dim layer stays exactly where the fixture put it. This screen is read
    # through it like every other night screen, and a render with the layer off
    # would be a picture of the one thing the control cannot do.
    "settings": {
        "unhide": ["settings"],
        # A fifth of the way up the range, so the track is neither empty nor
        # full and can be seen to be a readout. The words' own size sits at its
        # middle step, which is where the page ships and is the only value that
        # shows the track has both directions to go in.
        "styles": {"dim-fill": {"width": "20%"}, "text-fill": {"width": "50%"}},
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
    const span = (cls, text) => {
      const el = document.createElement("span");
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
      const row = document.createElement(press ? "button" : "div");
      if (press) row.type = "button";
      row.className = "shelved-open";
      // Spans, as app.js builds them: a <button> takes phrasing content, and
      // the sheet gives each of these a block display back.
      row.append(span("shelved-name", name), span("shelved-meta", meta));
      li.append(row);
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
        const warm = press === "finish this one";
        li.append(pill(warm ? "found-add again" : "found-add", press));
      }
      return li;
    }));

    const jobRow = (gone) => ([name, stage, state, width]) => {
      const li = document.createElement("li");
      li.className = gone ? "job gone" : "job";
      const stageCls = "job-stage" + (gone ? "" : " now");
      const head = div("job-line", p("job-name", name), p(stageCls, stage));
      li.append(head, p("job-state", state));
      if (width) li.append(bar("job-track", "job-fill", width));
      if (!gone) li.append(pill("job-stop", "stop reading this"));
      return li;
    };
    put("queue-live", (PANEL.live || []).map(jobRow(false)));
    put("queue-gone", (PANEL.gone || []).map(jobRow(true)));

    // candidateRow and hereRow from app.js, class for class. Every reading is a
    // <button> now and every row starts covered; `revealed` is a press already
    // made, which is the only way words get onto this screen.
    if (PANEL.places) {
      const rows = [];
      PANEL.places.forEach(([when, where, text, ahead, revealed], i) => {
        const li = document.createElement("li");
        li.className = ahead ? "candidate ahead" : "candidate";
        if (revealed) li.classList.add("revealed");
        const show = document.createElement("button");
        show.type = "button";
        show.className = "candidate-show";
        show.append(p("candidate-when", when), p("candidate-where", where));
        const what = p("candidate-what", revealed ? text : "");
        if (!revealed) what.hidden = true;
        show.append(what);
        // Three sentences in two colours. Before the press it is an invitation
        // and, on a row they have not listened past, a warning — which is the
        // whole of what marks such a row out. After it, the way to undo it.
        const hint = p(
          "candidate-hint",
          revealed
            ? "tap to hide"
            : ahead
              ? "tap to reveal · may spoil"
              : "tap to reveal",
        );
        show.append(hint);
        li.append(show, pill("candidate-go", "goto"));
        rows.push(li);
        const here = PANEL.here;
        if (here && here.after === i + 1) {
          // A place like the others now: the rule with its name on it, then a
          // time at the size the list states times, the words one press away,
          // and the way back at the foot. Only the amber is its own.
          const rule = document.createElement("li");
          rule.className = "candidate here";
          rule.setAttribute("aria-current", "true");
          if (here.revealed) rule.classList.add("revealed");
          rule.append(p("section-label here-mark", "you are here"));
          const ask = document.createElement("button");
          ask.type = "button";
          ask.className = "candidate-show";
          ask.append(p("candidate-when here-when", here.at));
          const said = p("candidate-what", here.revealed ? here.text : "");
          if (!here.revealed) said.hidden = true;
          ask.append(said);
          // Absent until the words are in hand: this row's passage is the one
          // thing on the screen the page has to go and ask for.
          if (here.text) {
            const word = here.revealed ? "tap to hide" : "tap to reveal";
            ask.append(p("candidate-hint", word));
          }
          rule.append(ask);
          if (here.back) rule.append(pill("candidate-go here-go", "here"));
          // Last in the row, immediately above the first row it is true of.
          if (here.more) {
            rule.append(
              p("here-caveat", "anything below this line you may not have heard"),
            );
          }
          rows.push(rule);
        }
      });
      put("candidate-list", rows);
    }
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
        help="raise an overlay and fill its lists: books, or workshop over it",
    )
    args = ap.parse_args()
    if args.panel and args.panel not in PANELS:
        sys.exit(f"snapshot: no fixture for panel {args.panel}")
    print(build(args.out, args.panel))
