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

## Two screens, not one

The keyboard shrinks the viewport rather than covering it — the page asks for
`interactive-widget=resizes-content` — so the page with a keyboard up is a
different layout, not a crop, and its height media queries have fired.

| | size | what it is |
|---|---|---|
| control | `360x780` | the page with no keyboard: the book, the chapter, the transport |
| chat | `360x470` | what the keyboard leaves: the conversation and the composer |

Render both. A change that tidies one can break the other, and the composer is
supposed to be identical across the flip.

## Doing it

```bash
S=.claude/skills/render-screens
python3 $S/snapshot.py --out /tmp/somnia/page.html
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/control.png
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/chat.png --height 470
```

Then **Read the PNGs.** Do not report on a layout you have not opened — the
whole value here is that the picture disagrees with you sometimes.

To try a change without touching the repo, copy the snapshot and edit its
inlined `<style>` block; it is self-contained and needs no server and no JS.

## What the snapshot does

`snapshot.py` reads `src/somnia/web/index.html` and `style.css` **every time**,
inlines the CSS, drops `app.js`, and fills one fixed moment of one book —
chapter 4 of 37, 3:24 into a 41:12 chapter, 1:12:08 into a 9:41:33 book. Same
data every render, so any two pictures can be put side by side.

It fills by element **id**, from a script injected at load, not by rewriting
markup. Ids are the stable part of this page; the markup around them is the part
being redesigned. Anything in `FIXTURE` that is not on the page is reported in a
yellow strip along the bottom of the render — that strip means either the
fixture has drifted and should be updated here, or something was removed on
purpose. It is never something to ignore.

Adding a readout to the page? Add its id to `FIXTURE` in `snapshot.py`, or it
photographs empty.

## Sizes worth knowing before you argue with a render

- transport buttons **4.5rem**; chapter skips and the microphone **3.5rem**
- the text column is **312px** — 360 less the 1.2rem margin each side
- `chapter 4 of 37` is about **150px**; `book 1:12:08 of 9:41:33` about **250px**
- the header — `somnia`, `books`, `clear` — measures **277px** of the 312

When width and height fight, **spend height**. Stacking beats cramming; that is
a standing preference, not a tie-break.
