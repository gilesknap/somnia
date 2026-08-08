---
name: render-screens
description: Photograph somnia's page at the phone it is actually read on, so a layout can be looked at instead of imagined. Use when changing index.html or style.css, when proposing or comparing UI, when asked to show a screen or mock one up, or before claiming a layout fits.
---

# Render the screens

A layout you have not looked at is a layout you are guessing about. This turns
the live page into a picture in two commands, at the measure it is actually read
at, so the guessing stops.

## The trap that costs a round of work

**somnia is not read at 412x892 with a 16px root.** It is read on a Pixel 6 Pro
with Android's text scaling turned up, because it is read in the dark without
glasses. The real measure is about **360x780 CSS px with a 20px root**.

Every line is roughly a third wider in practice than a stock render shows. In
August 2026 a whole round of mockups was drawn at the default and thrown away:
`book 1:12:08 of 9:41:33` and the sleep button would not share a row, and
`chapter 4 of 37` — about 150px — would not fit the 119px column it had been
given. Both looked fine at 412/16.

The tell that you have done it again: in a correct render, **"Where do you want
to be?" nearly fills its line.** If it sits at about half the width, you are
looking at the wrong phone.

## The 20px root is half a phone, and `--text-scale` is the other half

That root is a **model** of the reader's text scale, and it is the forgiving half
of one. Chrome for Android does not apply the scale as a root font size: it is a
**multiplier on computed font sizes**, put there by the text autosizer, with the
root left at 16. So on the phone the type lands at the size the design drew —
`1.35rem` is 21.6px x 1.25, the same 27dp a 20px root gives — and every **length**
stays 16-based. A `1rem` gutter is 16px there where the render says 20, and
gutters, gaps, radii, the transport slabs and the three spacer floors are all a
fifth tighter than any PNG this skill produces.

Which is why a render can only ever tell you a layout *fits*: it hands the page
spacing the phone does not have. To ask the question the spacers actually face:

```bash
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/big.png --text-scale 1.3
python3 $S/measure.py /tmp/somnia/page.html 867 --text-scale 1.3
```

`--text-scale` multiplies every rem font size and nothing else, and moves the
root to 16 on its own — passing it *and* `--root 20` counts the reader twice.
1.3 is the top of Android's own font-size slider; Chrome's text-scaling slider
goes to 2.0.

Measured 2026-08-08, at the commit that stopped the sheet pinning the scale: the
player does not scroll at any scale up to 2.0, because the three spacers give up
their slack first — B and C are on their 14px floor by 2.0 and the flexible gap
is down to 37. **1.5 is the last scale that still looks right.** At 2.0 the
header pills meet the wordmark, the sleep pill overflows its 320, and the book
title's second line is clipped mid-glyph by the two-line clamp.

None of which is the phone. This reproduces what Chrome-Android does to font
sizes; it does not reproduce Chrome-Android. "somnia is readable at the largest
setting" is still settled by picking the phone up.

## Two screens, not one — and the size no longer picks which

The keyboard shrinks the viewport rather than covering it — the page asks for
`interactive-widget=resizes-content` — so the page with a keyboard up is a
different layout and not a crop.

**Which screen it is on is a class on `<body>`, not a height.** app.js measures
the keyboard against the unobscured viewport and writes `player-screen` or
`chat-screen` (and `keyboard-up`, which is what the two overlays shrink for);
the sheet reads the class. A snapshot has no app.js, so `--screen` is how you
say it. `--height 470` on its own now photographs a short *player*, which is a
real state worth looking at and is not the chat screen.

| | size | say | what it is |
|---|---|---|---|
| player | `360x780` | — | the book, the chapter, the transport |
| chat | `360x470` | `--screen chat` | what the keyboard leaves: the conversation and the composer |
| short window | `360x470` | — | a window dragged short, or a big text scale: the reading gives way, the transport and the dock stay |
| panel typing | `360x470` | `--keyboard` | an overlay with its search box up over the player |

Render both of the first two. A change that tidies one can break the other, and
the composer is supposed to be identical across the flip.

## Two CSS traps this page has already sprung

Both cost a round of work, and neither is visible in a test suite — the page
renders, nothing throws, and the size is simply wrong on one of the two screens.

**A media query does not win on being the matching one.** The player size and
the chat size for `.said` were written at the **same specificity** in different
blocks, so **source order** decided the winner on both screens, and the rule for
the screen you were not looking at kept applying to the one you were.
Specificity is compared first; a media query only gates whether a block applies
at all and adds nothing to the weight of what is inside it.

The fix is to make the two rules beat each other **in one direction only, on
purpose**. The player size is `#transcript .said`; the chat size is
`body.chat-screen #transcript .said`, which carries a class on `<body>` as well
and so wins wherever it applies — by specificity rather than by being written
later. If you add a third size, give it a weight, not a position.

**Hiding siblings moves the browser's default margins onto whatever is left.**
The player draws only the newest turn, with
`#transcript .said:not(:last-child) { display: none }`. The browser's own
`p { margin: 1em 0 }` then landed on the one turn still showing, and because it
is in `em` it grew with the type — so the gap above the placement line drifted
every time the type scale changed. `margin-top: 0` is explicit for that reason.
Any rule that hides all but one of a set is worth re-measuring afterwards: the
survivor inherits edges it never had while it had neighbours.

`measure.py` reads only turns with a client rect, so a hidden turn is no longer
mistaken for the top of the conversation — it once reported `-48` against a
layout that was right.

## Doing it

The three overlays are `--panel books`, `--panel workshop` and `--panel places`.
Each fills its own lists, which app.js builds and a snapshot otherwise cannot
see — without the fixture those screens photograph as a heading over nothing,
which is a picture that looks fine and is not the page.

```bash
S=.claude/skills/render-screens
python3 $S/snapshot.py --out /tmp/somnia/page.html
python3 $S/snapshot.py --out /tmp/somnia/places.html --panel places
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/player.png
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/chat.png --screen chat --height 470
python3 $S/measure.py /tmp/somnia/page.html 867
```

## Looking is not measuring

`measure.py` prints each vertical gap on the player against the design brief's
rhythm table, and whether the page scrolls. Run it as well as looking, because
the two catch different things: in August 2026 a render was read as fine by eye
and the script found four of six gaps out, with every pixel of slack pooled
above the conversation instead of below it.

**Pass `867`, not `780`.** `--dump-dom` opens a real window with real chrome,
unlike `--screenshot`, so the viewport comes up ~87px short; 867 lands
`innerHeight` on 780. The script prints the viewport it got — if that is not
780, everything under it is about a different phone.

`SCROLLS: False` is a hard rule, not a preference, and it is the first thing a
newly added row breaks.

Then **Read the PNGs.** Do not report on a layout you have not opened — the
whole value here is that the picture disagrees with you sometimes.

To try a change without touching the repo, copy the snapshot and edit its
inlined `<style>` block; it is self-contained and needs no server and no JS.

## What the snapshot does

`snapshot.py` reads `src/somnia/web/index.html` and `style.css` **every time**,
inlines the CSS, folds the page's own `.woff2` files in as data URIs, drops
`app.js`, and fills one fixed moment of one book —
chapter 4 of 37, 3:24 into a 41:12 chapter, 1:12:08 into a 9:41:33 book. Same
data every render, so any two pictures can be put side by side.

The fonts matter as much as the CSS: the snapshot lands in `/tmp`, so a relative
`url("newsreader-latin.woff2")` would resolve beside the snapshot and find
nothing, and this machine has neither Newsreader nor Georgia installed. The
render would quietly fall back to a face none of the sizes in `style.css` were
measured against, and look entirely plausible.

It fills by element **id**, from a script injected at load, not by rewriting
markup. Ids are the stable part of this page; the markup around them is the part
being redesigned. Anything in `FIXTURE` that is not on the page is reported in a
yellow strip along the bottom of the render — that strip means either the
fixture has drifted and should be updated here, or something was removed on
purpose. It is never something to ignore.

Adding a readout to the page? Add its id to `FIXTURE` in `snapshot.py`, or it
photographs empty.

`FIXTURE["styles"]` sets inline style by id, and carries one thing: the dim
layer, at the 0.12 the page ships at. `app.js` does not run in a snapshot, so
without it every render would be a photograph of a page brighter than the one on
the phone — the reader looks at the whole page through that layer, both overlays
included.

## What the picture will not show you

CSS animations are frozen part-way through by this headless mode: an element
that rises and fades in over 240ms photographs at whatever opacity it had a
moment after it started, which looks like a bug in the page and is not. To judge
one, inject `animation: none` for it into the copied snapshot and render that.
Nothing that ships in `FIXTURE` animates, so this only bites when you unhide
something — the toast, for instance — by hand.

## Sizes worth knowing before you argue with a render

- transport buttons **5.5rem**; the chapter circles **3.2rem**; the microphone
  **5rem**; the header **2.4rem**
- the text column is **320px** — 360 less the 1rem gutter each side
- `1:12:08 of 9:41:33` and the sleep pill are **no longer on one row**. The
  position line, the count under it, the scrub line and the pill are four
  stacked full-width lines, so the pill has the whole 320 to itself and the old
  eleven-character ceiling on its label is gone with the row it was about. The
  fixture holds `sleep timer · 60 min left`, the widest of the six states, and
  it fits with room either side
- the header holds two things and a name, and they are not the same two on both
  screens: `books ›` and `somnia` on the player, with the right corner empty;
  `‹ controls`, `somnia` and `start over` on chat. The chat row fills most of
  the 320 and has no room for a fourth thing

Measure these off the PNG, not off `getBoundingClientRect` in an injected
script: instrumentation run inside a headless screenshot has reported a viewport
half again too wide here, while the picture itself was correct.

When width and height fight, **spend height**. Stacking beats cramming; that is
a standing preference, not a tie-break.
