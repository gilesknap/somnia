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

## Doing it

```bash
S=.claude/skills/render-screens
python3 $S/snapshot.py --out /tmp/somnia/page.html
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
- `1:12:08 of 9:41:33` and the sleep pill share one row and only just: at the
  sizes before the type scale landed they wrapped, and they still wrap if the
  sleep label grows past about eleven characters
- the header holds two things and a name, and they are not the same two on both
  screens: `library ›` and `somnia` on the player, with the right corner empty;
  `‹ controls`, `somnia` and `start over` on chat. The chat row fills most of
  the 320 and has no room for a fourth thing

Measure these off the PNG, not off `getBoundingClientRect` in an injected
script: instrumentation run inside a headless screenshot has reported a viewport
half again too wide here, while the picture itself was correct.

When width and height fight, **spend height**. Stacking beats cramming; that is
a standing preference, not a tie-break.
