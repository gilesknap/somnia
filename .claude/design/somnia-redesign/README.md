# UI refinement handoff: Somnia

## What this is

The app and server already work. This is **not** an implementation plan — it is a **diff** to apply to the
existing UI. Nothing here asks for new backend work, new data, or new capabilities.

`Somnia.dc.html` in this folder is a browser prototype of the refined screens: click through it, then port
the deltas below into the real app using its existing patterns. `android-frame.jsx` is only the device
bezel used to present the mock — discard it.

**Rules for whoever implements this**

- Do not rebuild working screens. Apply the listed changes and leave everything else alone.
- Where the prototype fakes something (agent replies, catalogue, ingest steps, playback tick), the real
  implementation already exists — wire the refined UI to it and ignore the fakes.
- Sizes below are **dp**, measured against the target device's real metric: **360×780 at a 20px root**
  (zoomed display). Do not re-derive them from rem; let the OS font scale ride on top.
- The **player must not scroll** at 360×780. If a size has to give, take it from spacing, not from tap
  targets — nothing tappable goes below 44dp.
- **Do not lay the player out with `justify-content: space-between`.** See "Player vertical rhythm" below —
  this is the single easiest thing to get wrong, and it is what went wrong on the first port.

---

## The design system (apply globally)

**Color** — one accent hue, no pure white, no pure black, no blue anywhere.

| Token | Value | Use |
| --- | --- | --- |
| bg | `#0b0a09` | app background |
| surface | `#16151b` | slabs, pills, inputs |
| surface-active | `#1d1c23` | pressed state |
| accent | `#c8873c` | progress, active states, agent voice, warnings |
| accent-surface | `#241a08` | play/pause slab fill |
| accent-tint | `rgba(200,135,60,.05–.12)` | amber washes |
| accent-line | `rgba(200,135,60,.35–.5)` | amber borders/rules |
| toast-bg | `#150f06` | toast background |
| text | `#e6dcc8` | primary |
| text (dimmed) | `rgba(230,220,200, .7 / .6 / .45 / .4 / .38 / .3 / .22)` | descending hierarchy — same cream, lower alpha |
| hairline | `rgba(230,220,200,.07–.16)` | dividers, borders, progress tracks |

**Type** — one serif family throughout (`Newsreader` 300/400 + italic; Georgia fallback). Scale in use:
34 page title · book title · transport numerals / 28 wake headline / 27 agent turn / 26 chapter title /
24 user turn · mark time / 23 dock placeholder / 22 chat input · chapter count · last-placement line /
21 position · sleep timer · close / 19 chapter position / 18 chapter label · secondary actions /
17 places count / 16.5–16 meta / 15.5 footnotes / 11 mono uppercase `.18em` section labels.
**Nothing below 15dp**, and on the player nothing below 18dp.

The player runs a size or two larger than the list screens on purpose: it is the screen you read with one
eye open. If a player value looks large next to a web app, it is correct — the first build came in too
small across the board.
Italic means exactly two things: the agent's placement line, and text not yet revealed/spoken.

**Spacing** — 20dp screen gutters; 34dp between sections; 20dp between chat turns; 12dp between sibling
controls; 16–18dp row padding.

**Radius** — 99 (pills/circles), 20 (transport slabs, close, wake choices), 18 (find slab), 14 (cards),
2–3 (progress fills).

**Motion** — fade 180–200ms ease-out for screen changes and reveals; 18–34dp rise + fade 220–300ms for
toasts and chat turns; 1.6s opacity pulse 0.35↔0.9 for "listening…"; 500ms width transition on progress.
No spring, no bounce, nothing over 300ms.

**Dim overlay (new, global)** — a full-screen black layer above all content, `pointer-events` off, opacity
from a user setting (default 0.12, range 0–0.6, 300ms transition). This lets the app go darker than the OS
minimum brightness. Implement as an overlay layer, not by touching screen brightness.

**Toast (new or restyled)** — bottom-anchored, 20dp side insets, 26dp from bottom, 1px
`rgba(200,135,60,.35)`, background `#150f06`, 14dp radius, 18dp `#c8873c`, rises 240ms, auto-dismisses at
2.8s. Copy pattern: "moved · playing", "shelved at 1:12:08", "fading out in 30 min",
"back to the beginning".

**Settings that need a home** — dim level, jump size (15/30/60s, drives the `−30`/`+30` labels), default
sleep timer. My suggestion is long-press on the control each one affects, rather than a settings screen;
your call.

---

## Screen 1 — Player

### Changes

1. **Add a scrub line.** Full width under the position readout: 2dp track `rgba(230,220,200,.13)`, amber
   fill, 8dp amber knob, inside a 44dp-tall tap area; tapping seeks proportionally. Deliberately a
   hairline — a status readout you *can* use, not an invitation to fiddle.
2. **Make the position line an entry point to Places.** `1:12:08 of 9:41:33` at 21dp
   `rgba(230,220,200,.45)` with a 1px dotted underline, followed by `7 places found` at 17dp
   `rgba(230,220,200,.3)`. Whole thing is one 44dp target → Places. **Still missing in the current build** —
   without the count and the dotted underline there is no route from the player into Places at all.
3. **Remove "start over" from the player entirely.** Seeking to the start is rare (a few taps of
   prev-chapter does it) and having a destructive action in the top-right corner of the screen you tap
   half-asleep is not worth it. That corner is now **empty on the player**. `start over` survives only on
   chat, where it means "clear the thread" — see Screen 3.
4. **Header row becomes action · label · quiet action.** 48dp tall, 14dp side padding.
   - Left: `library` as a visible affordance — 36dp pill, 15dp horizontal padding, 99 radius, 1px
     `rgba(230,220,200,.16)`, 16.5dp `rgba(230,220,200,.6)`, preceded by a 6dp right-pointing caret.
     Selected: border `rgba(200,135,60,.5)`, bg `rgba(200,135,60,.07)`, text `#c8873c`. In a 48dp target.
     (It was previously indistinguishable from the wordmark, so nobody found it.)
   - Center: wordmark `somnia`, 18dp, `letter-spacing:.3em`, `rgba(230,220,200,.4)`, **not tappable**.
     Absolutely centered — and because the letter-spacing adds a trailing gap the browser counts in the
     box, offset by **+.15em** so the glyph run is optically centred. (Layout-centring it looks wrong.)
   - Right: **empty on the player**; on chat, a matching 36dp `start over` pill (same pill spec as the left
     one) that clears the thread. Header is present on **every** screen.
5. **Replace the post-fade banner with the Wake screen** (below). Do not show a prompt inline on the
   player — it compresses everything under it.
6. **The slot above the title holds the last placement line**: italic 22dp `rgba(230,220,200,.42)`, e.g.
   *"— and then where the horse bolts"*.

### Player vertical rhythm (read this before laying the screen out)

The player is one column with **exactly one flexible gap**. Everything else is a fixed margin. Distributing
the leftover height evenly — `justify-content: space-between`, or a spacer between every group — is wrong:
it opens a canyon under the agent line and pushes the transport and dock apart, which is what happened on
the first port.

Column order, top to bottom, with the ONLY flexible element marked:

| # | Element | Spacing above |
| --- | --- | --- |
| 1 | Last placement line (italic 22dp) | 12dp below header |
| 2 | **Flexible spacer — `flex: 1`, `min-height: 16dp`** | absorbs *all* slack |
| 3 | Title group: book title → position line → scrub line → sleep pill | — |
| 4 | Chapter group: chapter title → chapter position → nav row | **18dp** |
| 5 | Transport grid | **18dp** |
| 6 | Dock: input pill + mic | **14dp** |
| — | bottom of screen | 4dp |

Every group except (2) is `flex: none`. Within the groups the internal spacing is tight and fixed:

- Title group: position line `margin-top: 2dp` (its 44dp tap area supplies the visual space); scrub line
  `margin-top: 2dp`; sleep pill `margin-top: 4dp`.
- Chapter group: chapter position `margin-top: 3dp`; nav row `margin-top: 10dp`.

Consequence to sanity-check on device: with the sleep timer off and a one-line placement line, the gap
between the placement line and the book title should be the **largest** gap on screen, and the gaps between
title group / chapter group / transport / dock should look near-identical (18/18/14). If the transport and
dock are drifting apart while the middle looks crowded, the slack is being shared instead of pooled.

### Target sizes (the player fits 360×780 exactly at these)

- Transport grid: `1fr 1.05fr 1fr`, 12dp gap, cells **96dp** tall, 20 radius.
  `−30`/`+30` on `#16151b` at 34dp `rgba(230,220,200,.75)`, active `#1d1c23`. Labels are single strings
  built from the jump-size setting. Centre slab: `#241a08`, 1px `rgba(200,135,60,.4)`, active `#2e2109`;
  pause = two 10×38 amber bars 8dp apart, play = 26dp amber triangle nudged 5dp right for optical centre.
- Dock: `the bit where…` pill flex:1, **76dp**, 99 radius, `#16151b`, 23dp `rgba(230,220,200,.4)` → Chat;
  plus a **76×76** mic circle → voice capture + Chat.
- Chapter circles **64×64**, 1px `rgba(230,220,200,.13)`, active border `rgba(200,135,60,.6)`. Between them,
  as **two stacked lines**: the word `chapter` at 18dp `rgba(230,220,200,.45)`, then `3 of 54` — **position
  and total, both** — at 22dp `rgba(230,220,200,.7)`. Rendering it as a single line reading `chapter 3`
  loses the total, which is the only place in the UI that says how much book is left in chapters.
- Sleep-timer pill: min **48dp**, 24dp horizontal padding, 99 radius, label 21dp. Off: 1px `rgba(230,220,200,.14)`,
  `rgba(230,220,200,.55)`. On: 1px `rgba(200,135,60,.45)`, `#c8873c`. Tap cycles
  off → 15 → 30 → 45 → end of chapter and toasts "fading out in 30 min". **Render the label as one string**
  ("sleep timer · off") — see the implementation note at the end.
- Book title 34dp, `letter-spacing:-.005em`.

---

## Screen 2 — Wake (new screen; replaces the drift banner)

Shown **instead of** the player, once, the first time the app opens after a sleep-timer fade. Header
hidden. Nothing else on screen. `space-between` column, 20dp gutters.

- Top: `good morning` (11dp mono, uppercase, `.18em`, `rgba(230,220,200,.3)`); then
  "The timer faded you out at 1:47." at 28dp `rgba(230,220,200,.88)`; then italic 22dp
  `rgba(230,220,200,.42)`: "You were probably gone before that."
- Bottom: three stacked full-width choices, 12dp gap, ordered by likely intent —
  1. **see where you might be** — 92dp, 20 radius, 1px `rgba(200,135,60,.45)`, bg `rgba(200,135,60,.06)`,
     22dp `#c8873c`, with `7 places found` beneath at 16dp `rgba(200,135,60,.6)` → Places.
  2. **tell me what you remember** — 80dp, `#16151b`, 21dp `rgba(230,220,200,.7)` → Chat.
  3. **keep it where it stopped · 1:12:08** — 72dp, borderless, 19dp `rgba(230,220,200,.38)` → Player.
- Any choice clears the flag for the session.

Requires one thing from the existing app: the sleep-timer fade must record its timestamp, and the launch
after a fade must know it happened. If the fade already logs a position, that's enough.

---

## Screen 3 — Chat / agent

A real Q&A surface, not just a placement prompt: it answers questions about the book ("remind me who Ginger
is") as well as "where was I". That is why it keeps a scrollback and stays a screen of its own rather than
collapsing into the player. The player's dock pill and mic are **portals** into it — the player itself shows
no replies.

### Changes

0. **Header on chat is symmetric**: `‹ controls` pill left, `start over` pill right (same 36dp pill spec).
   `start over` here means **clear the thread** back to "Where do you want to be?" — single tap, no confirm,
   since nothing is lost but questions. This is the only place `start over` exists.
1. **Remove play/pause from the dock.** It was crowding the input and forcing the text down. Dock is now:
   input pill flex:1, **80dp**, 99 radius, `#16151b`, 22dp serif, placeholder `the bit where…` at
   `rgba(230,220,200,.32)`; plus an **80×80** mic circle. Enter submits.
2. **The whole thread pane is a tap target that returns to the player.** Faster than hunting a button, and
   it works alongside the header pill (a tap and a scroll drag are distinguishable, so scrollback is
   unaffected). Keep the thread pinned to its newest turn on open and on every reply. Foot of thread carries a faint italic 15.5dp
   `rgba(230,220,200,.22)`: "tap anywhere here to go back to the controls".
3. **Route ambiguity to the Places page instead of showing candidate cards in the thread.** Chapter totals
   everywhere (player and Books) must come from **one** value — the prototype had them disagree (37 vs 54)
   and it is exactly the kind of thing that gets ported twice.
   - Confident (one good answer): agent replies in words ("Chapter two, about nine minutes in. Moving there
     now."), then ~900ms later seeks, returns to the player, plays, toasts "moved · playing".
   - Ambiguous: agent replies "I can't narrow that to one place. Three of your marks fit — I'll show you
     all of them.", then ~1100ms later opens **Places** with the fitting marks tagged.
4. Thread styling: 20dp gutters, 20dp between turns, each rising in over 260ms. Agent 27dp
   `rgba(230,220,200,.88)`; user turns 24dp `rgba(230,220,200,.5)` prefixed with an em dash —
   `— the bit where they set off in the caravan`. `listening…` at 21dp `#c8873c` with the 1.6s pulse.

The one thing the agent must return for this to work: for an ambiguous query, a set of **mark ids** plus a
short human reason per mark ("most likely · fits what you said"). If it currently returns prose only, the
tags simply don't render — the page still works.

---

## Screen 4 — Places you might be (new screen)

The disambiguation surface, and also reachable any time from the player's position line. Header shown, with
its left pill reading `‹ controls`.

- Title `Places you might be` 34dp — `Places that match` when answering a query. Subhead **19dp** `rgba(230,220,200,.4)`:
  default "Everywhere in this book that sounds like what you remembered. Text stays hidden until you ask for
  it."; after a query, "“…” sounds like any of these. Text stays hidden until you ask for it.". Do not quote a
  result count — the list is capped and windowed, so a count would misdescribe it.
- **Chronological, always.** Never sort by confidence — the ordering is what makes the spoiler rule legible.
- **"You are here" divider**, inserted before the mark containing the current position: 11dp mono,
  uppercase, `.18em`, `#c8873c` — `you are here · 1:12:08` — then a 1px `rgba(200,135,60,.35)` rule, then
  italic **17dp** `rgba(230,220,200,.3)`: "every match below this line you may not have heard yet".
- **Lead-rule fallback**: if no shown result falls at or before the current position, render that same rule
  **above the list** instead of between rows. The spoiler boundary must exist on every rendering of this
  screen — it is the reason the list is chronological.
- **Cap the list at 4 places, windowed around the current position.** More than four is not useful and each
  row is tall. Selection rule, in full: sort the results by position ascending; find `hereIdx`, the index of
  the last result at or before the current position; take `start = max(0, min(hereIdx - 1, count - 4))` and
  show `[start, start + 4)`. That keeps the result you are inside plus the one before it, then fills
  forward. **Do not take the top 4 by score or the newest 4** — either can leave every row ahead of the
  listener, which deletes the "you are here" divider and the entire spoiler rule with it.
- **Row** (20dp top / 22dp bottom padding, 1px bottom `rgba(230,220,200,.07)`). **Nothing sits side by side**:
  at 360dp wide, time + chapter + a `goto` pill on one line forces the chapter label to truncate
  ("Ch 2 · 02 The Hu…") and squeezes the snippet into a narrow column that clips mid-sentence. The row is a
  full-width stack instead, with **two independent targets**:
  - **Reveal** — the whole text stack, full width, one tap target. Optional amber fit tag (12dp mono
    uppercase, e.g. `most likely · fits what you said`), then:
    - time **30dp**, own line, `white-space: nowrap` (`#c8873c` if current, else `rgba(230,220,200,.85)`)
    - chapter **19dp** `rgba(230,220,200,.4)` on its own line — full width, so it never truncates
    - **match strength** **19dp** — `strong match` in `rgba(200,135,60,.8)`, `possible match` / `faint match`
      in `rgba(230,220,200,.38)`. Every row on this screen is a **semantic search hit**; there are no
      pause/fade/audio-stopped marks, so do not label rows by provenance
    - hidden, before your position: `tap to reveal`, italic 19dp `rgba(230,220,200,.3)`
    - hidden, **after** your position: `tap to reveal · may spoil`, italic 19dp `rgba(200,135,60,.5)`
    - revealed: the narration text, italic **22dp**, line-height 1.5, `rgba(230,220,200,.62)`, 200ms fade,
      **full width and not truncated** — show the whole sentence or do not show the mark
  - **`goto`** — on its own line beneath, right-aligned: 132dp min width, **64dp** tall, 99 radius, 1px
    `rgba(230,220,200,.16)`, 21dp `rgba(230,220,200,.6)`, active bg `rgba(200,135,60,.1)`. Current row
    reads `here` in amber. Separate from the reveal target **on purpose**: revealing must never move
    playback. (The word is "goto", not "jump" — "jump" reads like ±30s.)
- Foot note, 17dp: "tap a place to reveal what is said there · tap goto to move".
- **No bottom close button.** Leave via the header's `‹ controls` pill — the same gesture in the same place
  on every screen. End the scroller with ~28dp bottom padding so the last row is not against the frame.
- `goto` seeks, returns to the player, plays, clears the fit tags, toasts.

**What this screen needs from the app**: the semantic search results for the current book —
`{position, score, snippet}` — plus the current playback position. Nothing else. `score` maps to the three
strength labels; `snippet` is the narration text at that timestamp and must be shown in full or not at all.
Scoped to the current book.

**Cap and windowing**: show at most **4** results, and choose them **around the current position** (the hit
containing `pos`, plus its neighbours) — never simply the top 4 or the last 4. Taking the newest N can leave
every row ahead of the listener, which silently deletes the "you are here" rule and the entire spoiler
rule with it. If every shown result is still ahead of the current position, render the rule **above the
list** so the boundary always exists.

---

## Screen 5 — Books

Restructures your existing Books page. Header shown, left pill reading `‹ controls`. Section labels
throughout: 11dp mono, uppercase, `.18em`, `rgba(230,220,200,.3)`.

1. **Keep** the `Books` title at 34dp, and the input + `find` pairing.
2. **reading now** — title in `Title — Surname, Forename, dates` form at 25dp `rgba(230,220,200,.9)`; meta
   `chapter 4 of 54 · 1h12m listened` at 17.5dp `rgba(230,220,200,.42)`; 2dp progress hairline. Then two
   actions:
   - **`pick it up at 1:12:08`** — flex:1, 64dp, 99 radius, 1px `rgba(200,135,60,.45)`, bg
     `rgba(200,135,60,.06)`, `#c8873c`; reads `back to it · playing` when already playing. **This is new** —
     the page previously offered only the destructive action, so there was nothing to press to continue.
   - **`put it down`** — flex:none, 64dp, 22dp padding, **1px dashed** `rgba(230,220,200,.2)`,
     `rgba(230,220,200,.4)`. Dashed = recessive/undoable. Stops playback, shelves at the current time, and
     the block collapses to italic "nothing on the go — pick something below".
3. **on the shelf** — fills what was empty space: rows of title 22dp, the same meta line 16.5dp, 2dp
   progress hairline `rgba(200,135,60,.65)`; tap opens that book on the player. **No cover art anywhere** —
   covers are bright rectangles in a dark room, and four lines of text scan faster half-asleep.
4. **bring in something new · gutenberg** — input pill flex:1, 68dp, `#16151b`, 20dp serif, placeholder
   `a title, or an author`; `find` slab 96×68, 18 radius, `#16151b`. Filter live on **every typed word**
   (single-word matching made the page open nearly empty). Results: title 21dp, meta
   `Author · year · formats` 16dp, action pill 104×56 cycling `ingest` → `working` → `in library`, amber
   once queued.
5. **Queue panel** while anything is ingesting: 1px `rgba(230,220,200,.1)`, 14 radius, "the server is
   working", then per item title + right-aligned status (`queued`, `fetching text`, `narrating`, `ready`)
   over a 2dp progress hairline with a 500ms width transition. Wire to whatever progress your ingest job
   already emits.
6. **No bottom close button** — leave via the header's `‹ controls` pill. End the scroller with ~28dp
   bottom padding.

---

## Not designed — leave your existing UI alone

Server pairing, offline downloads, notification/lock-screen controls, failure states (unreachable server,
failed ingest, denied mic), per-book positions history, chapter/bookmark drawer. If you want any of these
restyled to match, that's a separate pass.

## Porting check (things missing or off in the first build)

Compare against the prototype before calling the player done:

0. **Type across the player is a size or two too small.** The revised scale is above; the biggest misses
   were book title (34, not 29), transport numerals (34, not 30), chapter title (26), position line (21),
   dock placeholder (23). There is spare vertical room on the player once the rhythm below is right — spend
   it on type, not on gaps.
1. **The chapter counter renders as one line, `chapter 3`.** It is two lines — `chapter` over `3 of 54` —
   and dropping the total loses the only "how much is left" signal on the screen.
2. **The scrub line is missing.** It belongs directly under the position readout, above the sleep pill —
   2dp track, amber fill, 8dp knob, in a 44dp tap area. Without it there is no visual sense of how far
   through the book you are, which is half the reason the position group exists.
3. **`7 places found` is missing** from the position line, and the position text has no dotted underline —
   so the route into Places is invisible from the player. Position line = dotted-underlined time + count,
   one 44dp target.
4. **Dock is undersized.** Input pill and mic circle are both **76dp**, not ~68. Same for the chapter
   circles: **64dp**.
5. **Header pill reads `books`; the rest of the UI calls that screen `Books`** — fine, but keep one word
   everywhere (the prototype says `library` in the pill; either is fine, pick one).
6. Optical centring of the wordmark: the `.3em` letter-spacing adds a trailing gap inside the text box, so
   a layout-centred wordmark sits visibly left. Offset by +.15em. (Yours looks correct — noting it so it
   survives future edits.)

Sanity check on device: "Black Beauty" at 34dp should span roughly two-thirds of the screen width, and the
`−30` numerals should read at about the same size as the book title — they are the two things you hit
without your glasses on.

## Two implementation notes from building the prototype

- Icons: the mic glyph, transport chevrons and the `library` caret are CSS-primitive placeholders. Use your
  real icon set at the same optical weight (hairline, ~1.5–2.5dp stroke, amber).
- Labels: build composed labels ("sleep timer · off", "−30", "or see all 7 places you might be") as single
  strings rather than concatenating text and a value inside a flex row — in the prototype's runtime that
  produced separate flex items with lost spaces and mismatched baselines. Harmless advice in most stacks,
  but it's why those strings look pre-assembled here.

## Files

- `Somnia.dc.html` — the refined prototype: player, wake, chat, places, books, all transitions above.
- `android-frame.jsx` — device bezel for presentation only. Not product.
