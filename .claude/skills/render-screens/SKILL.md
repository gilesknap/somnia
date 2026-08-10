---
name: render-screens
description: Photograph somnia's page at the phone it is actually read on, so a layout can be looked at instead of imagined. Use when changing index.html or style.css, when proposing or comparing UI, when asked to show a screen or mock one up, or before claiming a layout fits.
---

# Render the screens

A layout you have not looked at is a layout you are guessing about. This turns
the live page into a picture in two commands, at the measure it is actually read
at, so the guessing stops.

## The trap that costs a round of work

**somnia is not read at 412x892.** It is read on a Pixel 6 Pro with the display
size turned up, because it is read in the dark without glasses. The real measure
is about **360x780 CSS px**.

Every line is roughly a third wider in practice than a stock render shows. In
August 2026 a whole round of mockups was drawn at the default and thrown away:
`book 1:12:08 of 9:41:33` and the sleep button would not share a row, and
`chapter 4 of 37` — about 150px — would not fit the 119px column it had been
given. Both looked fine at 412/16.

The tell that you have done it again: in a correct render, **"Where do you want
to be?" nearly fills its line.** If it sits at about half the width, you are
looking at the wrong phone.

## The size of the type: set the width, and stop there

**The root is not yours to choose any more.** `style.css` takes it from the
screen:

```css
html { font-size: calc(var(--text-size) * min(100vw, 460px) / 18); }
```

18 is the design itself — 360 CSS px across at a 20px root is a page **18 rem
wide** — so dividing the screen by 18 puts every dp where it was drawn on any
phone at any setting. `render.py` therefore injects **no root**: give it
`--width` and the page works out the root the phone would have had.

This replaced a root that was never set at all, which is worth knowing because
it explains a recurring complaint. Before PR #64 the page took the browser's
16px, so it matched the design only by accident of how the reader had tuned
their phone — 19.4rem across on Giles's, ~25.7rem for anyone untuned, against a
design drawn at 18. **"The type is a size or two too small" was that**, not the
type scale, and raising sizes to compensate would have been chasing it.

| flag | when |
|---|---|
| *(nothing)* | the phone. The page sizes itself from `--width` |
| `--text-size 0.8`…`1.2` | the reader's own control, `how big the words` on Settings. 1 ships |
| `--root 24` | forcing a what-if. Injects a fixed root and overrides the page |

`--root` and `--text-size` at once counts the reader twice. Prefer
`--text-size`: it is the control that exists.

## The three controls on the phone, and which ones reach a web page

Established on the device across several rounds, each of which cost one:

| control | reaches somnia? | how |
|---|---|---|
| Android **font size** | **no** | never arrives at all |
| Android **display size** | **yes** | changes CSS px density — the viewport gets narrower *and* shorter in CSS px |
| Chrome **page zoom** | **yes** | same mechanism |

Neither of the two that work is a *font* multiplier, which is why
`text-size-adjust` was never the cause of anything here — issue #51's diagnosis,
the design handoff's note and two rounds of my own were all wrong about that.
Giles reads at display size +1 with page zoom 133%, giving a **309 CSS px**
viewport.

Since PR #64 the root is a fraction of the screen, so **display size and page
zoom no longer change somnia's apparent size at all** — they cancel out. That is
deliberate, and `how big the words` on Settings is what replaces them.

`designsize.html` on nuc2 prints the viewport and the root that matches the
design at whatever the phone is currently set to. Use it rather than arithmetic.

## `rem` in a media query does not mean what it means everywhere else

**It resolves against the browser's initial font size, never against
`html { font-size }`.** So this, in `style.css`:

```css
@media (max-height: 34rem) { #now-playing { display: none } }
```

is a hard **544 CSS px**, whatever root the page has set.

Proved by rendering at 309x540 with the root forced to **8px** — acres of empty
room, type a third of its size, and the reading still hidden. The comment above
that query argued the opposite ("asking that in rem is what makes the answer
follow the OS text scale"); it was wrong, it was load-bearing, and it was
[issue #65](https://github.com/gilesknap/somnia/issues/65). Both the query and
the comment are gone — see below for what stands in their place.

The consequence in the wild: at display size +3 the player shows the header, the
transport and the composer with a void where the book is. That is this rule
firing, not a broken layout. And it will keep creeping closer, because **a
viewport gets proportionally shorter as display size grows** — the status bar
and gesture inset are fixed in *dp*, so they eat a constant number of CSS px out
of a shrinking total:

    width_css = W/S      height_css = H/S − C      (C constant)

If you need a height threshold that follows the type, measure it in app.js and
write a class, as #23 did for the keyboard. Do not reach for `rem`. As of #65
there is no `rem` left in any media query in `style.css`, and there is a test in
`tests/web/fitting.test.mjs` that fails if one comes back.

## `short-page` — whether there is room, and why a render can get it wrong

**app.js writes it, and a snapshot has no app.js.** The page compares the height
with nothing over it against **32 of its own roots** — `PLAYER_NEEDS_ROOTS` in
app.js — and puts `short-page` on `<body>`; `style.css` hides `#now-playing` on
that class and nothing else reads it.

That means **a short render without the class photographs a player the phone
would never draw**, with the whole reading in a window that has no room for it.
`render.py` therefore derives the class from the width, the height, `--root` and
`--text-size` rather than offering a flag, because a flag is a thing that gets
forgotten and the picture that forgets it looks fine. A keyboard render is judged
by the height with **nothing over it**, as app.js judges it: `--keyboard --height
470` is the design's phone with a panel over it and carries no `short-page` at
all.

Four consequences worth carrying around:

- `how big the words` on Settings now moves this, and it is the reader's only way
  out. At `309x540 --text-size 0.9` the page is 35.0 roots and the reading comes
  back where the design size has it hidden. Render both ends of that control when
  you touch the player's column.
- **32, not 34, and the number came from pictures.** 34 was arithmetic and it took
  the reading off `360x780 --text-size 1.2` — the design's own phone at the top of
  the reader's own control, on a page that renders entirely legible. Roots are an
  approximation: the header padding and safe-area inset are device pixels, so 32.5
  roots overlap at a root of 20 and are clean at a root of 24. Do not move this
  number without rendering `360x780 --text-size 1.2`, `360x640` and `309x540`.
- **The class is only half of it; the sheet asks a size as well.** The reading is
  taken away only under `max-width: 460px` — the width the 32 was measured at — or
  under `540px` of height, the reading's own measured height. A desk window is
  short by the arithmetic, since the root stops growing at 460 across and 32 of
  them is a flat 818px, and neither half touches it. Render at `1280x720` if you
  change either, and expect the ordinary upright player.
- `snapshot.py` composes the page without running app.js at all, so anything you
  read out of a snapshot is a page with none of these classes on it.

**There is no landscape layout any more.** A two-column player for a phone on its
side used to live under `(max-height: 34rem) and (min-width: 34rem)` — 544 CSS px
on both halves, so the display-+3 phone lying down at 540 across fell straight
through the block that existed for it. Rebuilt on shape during #65 it reached that
phone and photographed broken: the clock wrapped onto two lines, the sleep-timer
pill was clipped off the left edge and `+30` off the right, on a grid drawn for
669px. It is gone. A phone on its side, and any window dragged to a letterbox, now
gets the same page a short window gets — the header, the transport and the dock,
with the reading away. Do not add a `min-aspect-ratio` query back without a render
at `540x309`; there is a test that fails if one appears.

## Three screens, not one — and the size picks none of them

The keyboard shrinks the viewport rather than covering it — the page asks for
`interactive-widget=resizes-content` — so the page with a keyboard up is a
different layout and not a crop.

**Which screen it is on is a class on `<body>`, not a height.** app.js measures
the keyboard against the unobscured viewport and writes `player-screen`,
`chat-screen` or `wake-screen` (and `keyboard-up`, which is what the two overlays
shrink for); the sheet reads the class. A snapshot has no app.js, so `--screen`
is how you say it. `--height 470` on its own now photographs a short *player*,
which is a real state worth looking at and is not the chat screen.

| | size | say | what it is |
|---|---|---|---|
| player | `360x780` | — | the book, the chapter, the transport |
| chat | `360x470` | `--screen chat` | what the keyboard leaves: the conversation and the composer |
| wake | `360x780` | `--screen wake` | the morning after a sleep-timer fade: one sentence, three choices, no header |
| short window | `360x470` | — | a window dragged short, or a big text scale: the reading gives way, the transport and the dock stay |
| panel typing | `360x470` | `--keyboard` | an overlay with its search box up over the player |

Render the first two together. A change that tidies one can break the other, and
the composer is supposed to be identical across the flip.

**Wake is not measured and not pressed.** app.js reads the record the fade left
in `somnia-fade` and opens on it, so no window size and no keyboard can produce
it — which is why it needs saying to the renderer explicitly and why it cannot
appear by accident in the other two pictures. It is the one screen with **no
header**, and the one whose first choice is drawn only sometimes: `#wake-places`
appears when the last query left places for the open book, and the fixture
unhides it, so the picture you get is the taller of its two states. To see the
other one — which is most mornings — copy the snapshot and add
`#wake-places{display:none}`.

## Three CSS traps this page has already sprung

Each cost a round of work, and none is visible in a test suite — the page
renders, nothing throws, and it is simply wrong on a screen you were not looking
at. All three are the same shape: a rule that loses silently.

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

**An id in a group selector outranks the id of the thing itself.** Writing the
shared rule for a set of buttons as `#wake-choices button` gives it an id *and* a
type — (1,0,1) — which beats the plain `#wake-places` at (1,0,0). So the group's
`border: 0; background: none` won, and the morning's amber slab photographed as
bare text floating where a slab should be: right type, right position, not one
edge, fill or radius on the screen.

The page already had the right shape and it is worth copying rather than
rediscovering: `.transport button` is a class and a type, so `#playpause` beats
it and the centre slab can be the warm one. **Give the container a class, not an
id, whenever its children are ids that have to override it.**

This one is invisible to `measure.py` — every box was exactly where it belonged
and the gaps all passed. Only the picture showed it, which is the case for
opening the PNG rather than trusting the numbers.

`measure.py` reads only turns with a client rect, so a hidden turn is no longer
mistaken for the top of the conversation — it once reported `-48` against a
layout that was right.

## Doing it

The overlays are `--panel books`, `--panel workshop`, `--panel book` — one
book's own page, over Workshop — `--panel places` and `--panel settings`. Each
fills its own lists, which app.js builds and a snapshot otherwise cannot see —
without the fixture those screens photograph as a heading over nothing, which is
a picture that looks fine and is not the page.

```bash
S=.claude/skills/render-screens
python3 $S/snapshot.py --out /tmp/somnia/page.html
python3 $S/snapshot.py --out /tmp/somnia/places.html --panel places
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/player.png
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/chat.png --screen chat --height 470
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/wake.png --screen wake
python3 $S/measure.py /tmp/somnia/page.html 867
```

Changing anything about size? Do the ends of the reader's own range as well —
they are two more commands and they are where it breaks:

```bash
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/small.png --text-size 0.8
python3 $S/render.py /tmp/somnia/page.html --out /tmp/somnia/big.png   --text-size 1.2
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

## Measure the page with the book in it, never with placeholder text

`snapshot.py` fills the screens for exactly this reason, and a hand-rolled probe
that sets a couple of ids and leaves the rest empty is not the page — it is a
layout with all the long strings taken out, which is the layout that always
fits.

It cost a wrong fix on 2026-08-09. The landscape player was drawing the reading
as a row of single letters; a headless probe that set `#book-title` and
`#chapter-title` by hand said the repair worked at 669x309, and the PR shipped
with a table of measurements saying so. Rendering the *real* page with a
nine-hour book open showed `1:12:08 of 9:41:33` wrapping in a column 60px too
narrow, and the wrapped line pushing the sleep timer below the fold — the one
control that block exists to keep reachable. The probe had left `#whereabouts`
short, so the only element that mattered was the one it had not filled. (That
block has since been removed altogether — see above — but the lesson is about the
probe, not the layout, and it applies to every screen still here.)

The three strings that break a column here, and none of them is the title:

| string | why it is the widest thing on the screen |
|---|---|
| `1:12:08 of 9:41:33` | two clocks and a word, and it must not wrap |
| `sleep timer · 60 min left` | a pill, so it cannot ellipsize |
| `chapter 4 of 37` | ~150px, and it has been given a 119px column before |

So: render, then look, then measure — and if a number in a commit message came
from a probe rather than from `snapshot.py`, say which, because the two disagree
exactly where it matters.

**But `SCROLLS` is not the detector for type that is too big.** The column is
`flex: 1` all the way down, so the spacers give until there is nothing left and
then type lands on type — the book's title truncates to one line, the chapter
title clips through its own descenders, the header pills meet the wordmark. None
of that scrolls. Measured at 360 wide: clean to a root of 24, broken by 26, and
the page does not scroll until 30. **Four of the failures happen before the
number moves.** So run the script *and* open the picture.

Then **Read the PNGs.** Do not report on a layout you have not opened — the
whole value here is that the picture disagrees with you sometimes.

### `--dump-dom` and `--screenshot` do not agree about the window

Two separate quirks, both of which have cost time:

- `--dump-dom` opens a real window with real chrome, so the viewport is ~87px
  short — hence 867 above — and it **will not go below 500px wide** at all. Any
  width you pass under 500 is ignored.
- Headless lays out at **500 wide before honouring `--window-size`**, so anything
  derived from `100vw` — which is now the root — resolves at 500 first and
  settles afterwards. `window.innerWidth` read at `load` still says 500 while the
  picture is correctly 360.

The second one silently moved every chat render for a while: the scroll to the
bottom of the thread ran against the transient layout, so the picture depended on
what else was in `<head>`. `render.py` scrolls again on `resize` and on
`fonts.ready` for that reason. If you are comparing two chat renders byte for
byte and they disagree, suspect the scroll before you suspect the layout.

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
