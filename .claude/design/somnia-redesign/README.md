# UI refinement handoff: Somnia

## What this is

The app and server already work. This document is the **specification of the current design** — what each
screen *is*, in the present tense. It asks for no new backend work, no new data, no new capabilities.

**Read it as description, not as instructions.** Everything in the numbered screen sections describes how the
design stands now, whether or not the app already matches. If a paragraph describes something the app already
does, that is the document and the app agreeing — not a task. **The only place that says what is left to do is
`## Implementation status` near the end.** Start there, then read the screen sections for the detail of
whatever it lists.

That split is deliberate and was learned the hard way: this file used to be written as a diff, in imperatives
("add a scrub line", "remove play/pause"). Imperatives do not expire — once the work is done the sentence
still reads as an order, so each sync re-did work that was already finished. Descriptions stay true; only the
status list has to be maintained.

`Somnia.dc.html` in this folder is a browser prototype of the design. Click through it. Where it fakes
something (agent replies, catalogue, ingest steps, playback tick, and the font-scale sample) the real
implementation already exists or is out of the prototype's reach — take the layout and the copy, not the
fakes. `android-frame.jsx` is only the device bezel used to present the mock; discard it.

**Rules for whoever implements this**

- Do not rebuild working screens. Change only what `## Implementation status` lists, and leave the rest alone.
- Where the prototype fakes something (agent replies, catalogue, ingest steps, playback tick), the real
  implementation already exists — wire the refined UI to it and ignore the fakes.
- Sizes below are **dp**, measured against the target device's real metric: **360×780 at a 20px root**
  (zoomed display). Do not re-derive them from rem; let the OS font scale ride on top.
- The **player must not scroll**. The device is 360×780dp, but the app's own content column measures about
  **717dp** once the status bar and the gesture inset are taken off — that is the box to design into, and it
  is ~70dp taller than an early mock assumed, which is why the type could be raised. If a size has to give,
  take it from spacing, not from tap targets — nothing tappable goes below 44dp.
- **Read this as an over-50 screen.** The primary reader is 62, without glasses, in a dark room. Type on the
  player is sized for that, not for a normal phone app; the values below are minimums, not suggestions.
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
| failed | desaturated red, **at least as light as the accent** | something is broken and needs a human |
| text | `#e6dcc8` | primary |
| text (dimmed) | `rgba(230,220,200, .7 / .6 / .45 / .4 / .38 / .3 / .22)` | descending hierarchy — same cream, lower alpha |
| hairline | `rgba(230,220,200,.07–.16)` | dividers, borders, progress tracks |

**Failure has its own colour, and amber does not stretch to cover it.** Amber already means the sleep timer is
armed, the agent is speaking, the play slab, the progress fill and the current book's title. A sixth meaning
makes it mean nothing, so failure gets a desaturated red of its own. Three rules on it:

- **At least as luminous as the accent.** The obvious failure colours are darker than `#c8873c`, and a darker
  warm colour on near-black reads as *disabled* — which is what `opacity: .3` already means on a chapter
  button with nowhere to skip. Failure must not look recessive.
- **Waiting is not failing.** `the rest of this book hasn't been read yet` is a wait: the render has not caught
  up, nothing is wrong, and the book resumes on its own. That stays **amber**. Red is only for something that
  needs a person — `couldn't reach that book`, `that chapter didn't arrive`, a dead render. Colouring the wait
  red would put "something is wrong" on the most common and most benign event of the night.
- **The colour confirms; the words carry it.** Rod vision barely discriminates hue, so at the light levels
  this app is used in, amber and a dull red are adjacent. The status line's sentence is the signal.

Red is a defensible night hue for a reason worth recording: rods are least sensitive to long wavelengths, so a
desaturated red costs less dark adaptation than the amber does.

**Type** — one serif family throughout (`Newsreader` 300/400 + italic; Georgia fallback). Scale in use:
**Player** (largest, deliberately): 38 book title / 31 transport numerals / 29 chapter title / 22 dock
placeholder / 24 chapter count / 23 position · sleep timer / 21 chapter position / 19 chapter label /
18 places count.
**Places (a night screen — carries the player's weight)**: 34 title / 32 mark time / 24 revealed snippet /
22 goto / 21 subhead · chapter · reveal prompt / 19 dividers and footnotes.
**Other screens**: 34 page title / 28 wake headline / 25 agent turn / 22 chat input ·
revealed snippet · shelf title / 21 goto · secondary actions / 19 subhead · match strength · chapter /
17 footnotes / 16.5–16 meta / 11–12 mono uppercase `.18em` section labels.
**Nothing below 15dp**, and on the player nothing below 18dp.

The player runs a size or two larger than the list screens on purpose: it is the screen you read with one
eye open. If a player value looks large next to a web app, it is correct — the first build came in too
small across the board.
Italic means exactly one thing: **short prompts and asides** — "tap to reveal", "every match below this line
…", "set it here, where you can see it working". Never a block of narration. Italic serif at low light costs
real legibility over more than a few words, and the revealed snippets on Places are the longest thing
anybody reads on a night screen. They are **upright**; their quote marks already mark them as the book's
words rather than somnia's.

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

**Row versus button — when a list row is the target and when it needs a button.** Three screens do this
differently and it is one rule, not three decisions:

> A row is tappable as a whole when it has **exactly one** action. It needs an explicit button when it has
> **two**, or when the action is **not "open this"**.

- **Books shelf / reading now** — one action (play this book). The whole row is the press, no button.
- **Places** — two actions (reveal the text, go there). They must be separate targets: revealing must never
  move playback. The `goto` button is what keeps them apart.
- **Workshop results** — the row is not something you can open; it is a candidate, and the action spends
  server time turning it into audio and is not undoable in one press. That earns an explicit button.

Apply the rule to any new list rather than copying whichever screen was looked at last.

**Undo on `goto`.** `goto` is the last destructive press in the app: it discards the position, and the only
route back is another semantic search — the expensive thing this whole app exists to avoid. So the toast that
confirms it carries an **`undo`** for **6 seconds** (longer than the standard 2.8s), which restores the
previous position exactly. Toast copy becomes `moved to 1:20:20` — naming where it went, so the toast is
also a receipt — and `undo` sits at the right of it as a 48dp target, cream with a hairline underline rather
than amber, because it is a way back and not the subject of the sentence. Undoing says `back where you were`.
The same treatment is worth having on a mis-tapped shelf row, which is cheaper (positions are per book) but
not free.

**Sleep timer counts down.** The pill shows **remaining** time, live — `sleep timer · 24 min left`, dropping
to `· 45s left` under a minute — not the interval it was set to. "30 min" is ambiguous at 1am: total, or
left? Only remaining answers the question anybody is actually asking.

**Toast (new or restyled)** — bottom-anchored, 20dp side insets, 26dp from bottom, 1px
`rgba(200,135,60,.35)`, background `#150f06`, 14dp radius, 18dp `#c8873c`, rises 240ms, auto-dismisses at
2.8s. Copy pattern: "moved · playing", "shelved at 1:12:08", "fading out in 30 min",
"back to the beginning".

**Settings that need a home** — dim level, jump size (15/30/60s, drives the `−30`/`+30` labels), default
sleep timer. My suggestion is long-press on the control each one affects, rather than a settings screen;
your call.

---

## Screen 1 — Player

### Specification

1. **The scrub line is a readout only.** Full width under the position readout: 2dp track
   `rgba(230,220,200,.13)`, amber fill, 8dp amber knob, in a 22dp-tall band. **No tap target, no drag, no
   seek.** An earlier draft made it tappable; that was wrong. A mis-tap on a 2dp line in the dark destroys
   the exact thing this app exists to recover, and recovering it costs a semantic search. Every real
   navigation intent is already served by ±30, the chapter arrows, and Places. The line answers one
   question — how far through am I — and answers nothing else.
2. **The position line is the entry point to Places.** **Two centred lines, stacked** — never side by
   side:
   - `1:12:08 of 9:41:33` at 23dp `rgba(230,220,200,.45)`, `white-space: nowrap`, 1px dotted underline
     beneath it (2dp padding above the rule)
   - `4 places found` at 18dp `rgba(230,220,200,.3)`, 3dp below, also `nowrap`

   The whole stack is one 44dp target → Places. **Do not put the time and the count on one line**: at 360dp
   the pair leaves ~11dp of slack with a 9-hour book, so any book over ten hours (or a two-digit count)
   wraps the timestamp mid-string and splits the dotted underline across two lines.
3. **There is no "start over" on the player.** Seeking to the start is rare (a few taps of prev-chapter does
   it) and a destructive action in the top-right corner of the screen you tap half-asleep is not worth it.
   That corner holds `settings ›` (Screen 7). `start over` exists only on chat, where it means "clear the
   thread" — see Screen 3.
4. **The header row reads action · label · quiet action.** 48dp tall, 14dp side padding.
   - Left: `library` as a visible affordance — 36dp pill, 15dp horizontal padding, 99 radius, 1px
     `rgba(230,220,200,.16)`, 16.5dp `rgba(230,220,200,.6)`, preceded by a 6dp right-pointing caret.
     Selected: border `rgba(200,135,60,.5)`, bg `rgba(200,135,60,.07)`, text `#c8873c`. In a 48dp target.
     (It was previously indistinguishable from the wordmark, so nobody found it.)
   - Center: wordmark `somnia`, 18dp, `letter-spacing:.3em`, `rgba(230,220,200,.4)`, **not tappable** — and
     **only on the screens that have no title of their own**, which is the player and chat. Books, Places and
     Workshop each open with their own 30–34dp heading one line below the header, so the wordmark there is
     the one item on the row doing no job — and on Books, where the header carries two pills, three items at
     this type scale do not fit 344dp (101 + 85 + 114 = 300 with the wordmark overlapping the right pill).
     Same failure as the Places rows and the reading-now buttons: at this scale, two items per row.
     Absolutely centered — and because the letter-spacing adds a trailing gap the browser counts in the
     box, offset by **+.15em** so the glyph run is optically centred. (Layout-centring it looks wrong.)
   - Right: **empty on the player** — and it stays empty; on chat, a matching 36dp `start over` pill (same
     pill spec as the left one) that clears the thread and the agent's context; on Books, a `workshop ›`
     pill. Header is present on **every** screen.
5. **The post-fade prompt is the Wake screen** (Screen 2b), never a banner inline on the player — a banner
   there compresses everything under it.
6. **The status line.** The player carries one line that the design never described and should have: a single
   amber line, upright (not italic), ~21dp, one line reserved and two allowed, that says what somnia is doing
   about itself. It is the only amber text on the player, which is what sets it apart from a readout at a
   glance. It grows **upwards** into the space above rather than pushing the transport down — a control that
   has moved since the last glance is a control that gets missed.

   It is load-bearing at 2am, and these are its sentences: `the rest of this book hasn't been read yet` (the
   render frontier — the sound has stopped and the listener is waiting on a chapter, which otherwise looks
   exactly like a pause they made themselves), `that chapter didn't arrive`, `couldn't reach that book`,
   `something else took the sound`, `tap anywhere to carry on`, `listening…`, `goodnight`. The frontier one
   matters most: without it, a book that ran out of itself is indistinguishable from a book somebody paused.

   Include it in the vertical rhythm: it sits between the header and Spacer A, at `flex: none` with a
   reserved single-line height, so its appearance never moves anything below it.
7. **Nothing else sits above the book title.** No last placement line, no agent reply, no status text — the space
   between the header and the title is empty and belongs to the flexible spacer. Earlier drafts put the
   agent's most recent reply there; it was removed deliberately once chat became its own screen with a
   scrollback, because a single stale line is noise on the screen you look at half-asleep. If you are
   porting from an older copy of this doc, delete that element.

### Player conformance table — CHECK AGAINST THIS BEFORE SAYING THE SCREEN IS DONE

Every value is **dp on a 360dp-wide screen**. To verify, take a screenshot on the device and divide measured
pixels by the device pixel ratio (2.4 on this phone: an 864px-wide screenshot ÷ 2.4 = 360dp). Anything more
than ±2dp out is wrong — do not round to a nearby "nicer" number, and do not substitute a Material default.

| Element | Property | Value |
| --- | --- | --- |
| Header row | height | 48 |
| Header pill (left) | height / text | 36 / 16.5 |
| Header right (`start over`, chat only) | height / text | 36 / 16.5 |
| Empty band above title | — | whatever is left over; nothing renders here |
| Book title | font-size | **38** |
| Book title | line-height / max lines | 1.15 / 2 |
| Position line (`0:09:32 of 5:06:02`) | font-size / wrap | **23** / `nowrap`, own centred line |
| Places count (`4 places found`) | font-size / wrap | **18** / `nowrap`, centred line beneath |
| Position + count stack | min tap height | 44 |
| Scrub track / knob | height / diameter | 2 / 8 |
| Scrub band (not tappable) | height | 22 |
| Sleep-timer pill | height / text | 48 / **23** |
| Chapter title | font-size / line-height / max lines | **29** / 1.25 / 2 |
| Chapter position (`0:22 of 7:14`) | font-size | **21** |
| `chapter` label | font-size | **19** |
| `3 of 49` | font-size | **24** |
| Chapter prev/next circles | diameter | 64 |
| Transport slabs (all three) | height | **84** |
| Transport slabs | corner radius | 20 |
| Transport grid | columns / gap | `1fr 1.05fr 1fr` / 12 |
| `−30` / `+30` | font-size | **31** |
| Pause bars | each bar w×h, gap | 9×32, 7 |
| Play triangle | width | 22 (nudged 4 right) |
| Dock pill | height / text | **68** / **22** |
| Mic circle | diameter | **68** |
| Screen gutters | left/right padding | 20 |

**Gaps between groups**, top to bottom: flexible spacer (absorbs all slack) → title group → **14** → chapter
group → **14** → transport grid → **12** → dock → **4** to the bottom of the content area.

Two failure modes seen in real ports, both visible in a screenshot:

- **Transport slabs too tall** (108 instead of 84) — usually from letting the slab size itself around a large
  icon, or from a `1fr` row in a grid that distributes leftover height. Set the height explicitly.
- **Type quietly smaller than spec** (book title 34 instead of 38) — usually from a shared type scale or a
  `sp` value being re-derived at the 20dp root. Treat every number in this table as a literal dp, and let
  the OS font scale multiply it rather than replacing it.

### Player vertical rhythm (read this before laying the screen out)

The player is one column that **fills whatever height it is given at any system zoom level**. Do not pool
all the leftover height in one gap (an earlier draft did, and at looser zoom levels it opened a ~330dp void
under the header while everything else stayed welded to the bottom). Instead there are **three weighted
flexible spacers**, each with a floor and a ceiling, and the transport and dock stay pinned to the bottom by
fixed margins.

Column order, top to bottom:

| # | Element | Spacing / flex |
| --- | --- | --- |
| 1 | Header row | 48 tall |
| 2 | **Spacer A** | `flex: 2 1 0`, `min-height: 12`, `max-height: 180` |
| 3 | Title group: book title → position line → scrub line → sleep pill | `flex: none` |
| 4 | **Spacer B** | `flex: 1 1 0`, `min-height: 14`, `max-height: 70` |
| 5 | Chapter group: chapter title → chapter position → nav row | `flex: none` |
| 6 | **Spacer C** | `flex: 1 1 0`, `min-height: 14`, `max-height: 70` |
| 7 | Transport grid | `flex: none` |
| 8 | Dock: pill (a portal to chat) + mic | `flex: none`, **12** above |
| — | bottom of content area | 4 |

How it behaves:

- **Tightest zoom** (least dp available): all three spacers hit their floors and the layout collapses to the
  14/14/12 rhythm — still no scroll, because the floors are what the fixed content needs and no more.
- **Middle** (the common case): slack is shared **2 : 1 : 1**, so the largest breathing space is above the
  title, and the chapter group and transport each get half as much. The screen looks composed rather than
  bottom-heavy.
- **Loosest zoom** (most dp available): the ceilings stop Spacer A running away; any remaining slack
  distributes into B and C until they cap too, then sits at the bottom. The proportions stay recognisable at
  every zoom instead of one gap swallowing everything.

Do **not** use `justify-content: space-between` (equalises all gaps, ignores the 2:1:1 intent) and do **not**
use a single `flex: 1` spacer (pools all slack in one place). Nothing renders inside the spacers.

Consequence to sanity-check on device, at whatever zoom you use: the gap above the book title should be the
largest on screen but clearly finite — roughly twice the gap above the chapter group, which should itself
look about the same as the gap above the transport. If the top gap looks like half the screen, the ceilings
are missing.

### Target sizes (the player fits 360×780 exactly at these)

- Transport grid: `1fr 1.05fr 1fr`, 12dp gap, cells **84dp** tall, 20 radius. (These came down from 96 once
  the type went up — with 31dp numerals the slabs read as large without needing the height.)
  `−30`/`+30` on `#16151b` at 31dp `rgba(230,220,200,.75)`, active `#1d1c23`. Labels are single strings
  built from the jump-size setting. Centre slab: `#241a08`, 1px `rgba(200,135,60,.4)`, active `#2e2109`;
  pause = two 9×32 amber bars 7dp apart, play = 22dp amber triangle nudged 4dp right for optical centre.
- Dock: `the bit where…` pill flex:1, **68dp**, 99 radius, `#16151b`, 22dp `rgba(230,220,200,.4)` → Chat;
  plus a **68×68** mic circle → voice capture + Chat. The pill is a **portal**, not a live input — tapping it
  opens the chat screen and raises the keyboard there.
- Chapter name 29dp `rgba(230,220,200,.8)`, line-height 1.25, wrapping to a **maximum of two lines**
  (`-webkit-line-clamp: 2` + `overflow-wrap: break-word`) — never one truncated line, and never three, which
  would push the transport off-screen. Chapter position `3:24 of 41:12` 21dp.
- Chapter circles **64×64**, 1px `rgba(230,220,200,.13)`, active border `rgba(200,135,60,.6)`. Between them,
  as **two stacked lines**: the word `chapter` at 19dp `rgba(230,220,200,.45)`, then `3 of 54` — **position
  and total, both** — at 24dp `rgba(230,220,200,.7)`. Rendering it as a single line reading `chapter 3`
  loses the total, which is the only place in the UI that says how much book is left in chapters.
- Sleep-timer pill: min **48dp**, 24dp horizontal padding, 99 radius, label 23dp. Off: 1px `rgba(230,220,200,.14)`,
  `rgba(230,220,200,.55)`. On: 1px `rgba(200,135,60,.45)`, `#c8873c`. Tap cycles
  off → 15 → 30 → 45 → end of chapter and toasts "fading out in 30 min". **Render the label as one string**
  ("sleep timer · off") — see the implementation note at the end.
- Book title 38dp, `letter-spacing:-.005em`, line-height 1.15, clamped to **two lines** (same rule as the
  chapter name). Long titles are common in Gutenberg's catalogue, so both of the player's title lines wrap
  rather than truncate — but neither may take a third line.

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

### Specification

0. **The chat header is symmetric**: `‹ controls` pill left, `start over` pill right (same 36dp pill spec).
   `start over` here means **clear the thread** back to "Where do you want to be?" — single tap, no confirm,
   since nothing is lost but questions. This is the only place `start over` exists.
1. **The chat dock is the input pill and the mic, and nothing else** — no play/pause, no ±30. Transport
   controls belong on the player; repeated here they crowd the input, push the thread up, and shrink the type
   on the one screen that is nothing but text. It was crowding the input and forcing the text down. Dock is now:
   input pill flex:1, **80dp**, 99 radius, `#16151b`, 22dp serif, placeholder `the bit where…` at
   `rgba(230,220,200,.32)`; plus an **80×80** mic circle. Enter submits.
2. **The whole thread pane is a tap target that returns to the player.** Faster than hunting a button, and
   it works alongside the header pill (a tap and a scroll drag are distinguishable, so scrollback is
   unaffected). Keep the thread pinned to its newest turn on open and on every reply. Foot of thread carries a faint italic 15.5dp
   `rgba(230,220,200,.22)`: "tap anywhere here to go back to the controls".
3. **Route ambiguity to the Places page instead of showing candidate cards in the thread.**

   **Counts and totals must each come from ONE source.** Two have already gone wrong twice: the chapter
   total (the prototype once said 37 in one place and 54 in another) and the **places count** — the chat
   pill said "see all 7 places" while the player's line said "4 places found" and Places itself showed 4,
   because the cap and the label were computed separately. Derive every places count from the same capped
   value (`min(results, 4)`) and every chapter total from the same field. A literal number in a label is
   the bug.
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

- Title `Places you might be` 34dp — `Places that match` when answering a query. Subhead **21dp** `rgba(230,220,200,.45)`:
  default "Everywhere in this book that sounds like what you remembered. Text stays hidden until you ask for
  it."; after a query, "“…” sounds like any of these. Text stays hidden until you ask for it." That sentence
  is where the *set* is qualified — which is why no individual row needs to be. Do not quote a result count — the list is capped and windowed, so a count would misdescribe it.
- **Chronological, always.** Never sort by confidence — the ordering is what makes the spoiler rule legible.
- **"You are here" divider**, inserted before the mark containing the current position: **16dp** mono,
  uppercase, `.14em`, `#c8873c` — just `you are here`, **no timestamp** — then a 1px `rgba(200,135,60,.35)`
  rule, then italic **19dp** `rgba(230,220,200,.35)`: "every match below this line you may not have heard
  yet".

  It was 11dp with the time appended, which made the most safety-critical line on the screen the smallest.
  The time came off because it is already on screen twice — the player's position line, and the current row's
  own 32dp time immediately below this rule — and dropping it is what buys the size: the label is shorter, so
  a bigger label still leaves the rule long enough to read as a divider. Tracking comes in to `.14em` for the
  same reason.
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
  - **Reveal** — the whole text stack, full width, one tap target:
    - time **32dp**, own line, `white-space: nowrap` (`#c8873c` if current, else `rgba(230,220,200,.85)`)
    - chapter **21dp** `rgba(230,220,200,.45)` on its own line — full width, so it never truncates
    - hidden, before your position: `tap to reveal`, italic 21dp `rgba(230,220,200,.3)`
    - hidden, **after** your position: `tap to reveal · may spoil`, italic 21dp `rgba(200,135,60,.5)`
    - revealed: the narration text, **upright — not italic** — at **24dp**, line-height 1.5,
      `rgba(230,220,200,.72)`, 200ms fade, **full width and not truncated**: show the whole sentence or do
      not show the mark. This is the longest text on any night screen and the one somebody is actually
      reading; it was italic at 22dp/.62 and could not be read in a dark room.
  - **`goto`** — on its own line beneath, right-aligned: 132dp min width, **64dp** tall, 99 radius, 1px
    `rgba(230,220,200,.16)`, 22dp `rgba(230,220,200,.6)`, active bg `rgba(200,135,60,.1)`. Current row
    reads `here` in amber. Separate from the reveal target **on purpose**: revealing must never move
    playback. (The word is "goto", not "jump" — "jump" reads like ±30s.)
- Foot note, 19dp at `.3`: "tap a place to reveal what is said there · tap goto to move".
- **No bottom close button.** Leave via the header's `‹ controls` pill — the same gesture in the same place
  on every screen. End the scroller with ~28dp bottom padding so the last row is not against the frame.
- `goto` seeks, returns to the player, plays, clears the fit tags, toasts.

**What this screen needs from the app**: the semantic search results for the current book —
`{position, snippet}` — plus the current playback position. Nothing else. `snippet` is the narration text at
that timestamp and must be shown in full or not at all. Scoped to the current book.

**No match strength, and no per-row fit tag.** Both were specified and both are dropped: the backend has no
score to give, and a row that ranks itself invites the reader to trust the ranking instead of reading the
line. A row is a time, a chapter, and — when asked for — what is said there. Ordering stays chronological, so
nothing on the screen implies a ranking either.

**Cap and windowing**: show at most **4** results, and choose them **around the current position** (the hit
containing `pos`, plus its neighbours) — never simply the top 4 or the last 4. Taking the newest N can leave
every row ahead of the listener, which silently deletes the "you are here" rule and the entire spoiler
rule with it. If every shown result is still ahead of the current position, render the rule **above the
list** so the boundary always exists.

---

## Screen 5 — Books (night), and Screen 6 — Workshop (day)

**This replaces the single Library panel.** In real use that panel had grown to eight blocks — reading now,
the shelf, *ended in the last day*, search, results, the working queue, the server note, the last thing the
server said — and the reader could not read it in the dark. The blocks were each defensible; together they
had no answer to "what is this screen for".

The cut is **when you use it**, not what it is. That is what fixes the type problem: a night screen and a
daytime screen cannot share one scale, and only one of them can win.

Each screen gets one sentence. Anything that does not fit its sentence is on the wrong screen.

---

### Screen 5 — Books · *"what shall I listen to"*

Night. Reached from the player's left pill (which now reads `books ›`). Header shown, left pill
`‹ controls`. **Set at the player's type scale** — it is read in the same dark, at the same arm's length.

1. Title `Books` 34dp.
2. **reading now** (label becomes `playing now` while it is sounding) — section label 11dp mono, then the
   current book **as a tappable block, with no button on it**:
   - Title 29dp in **`#c8873c`** — amber is what marks it as the current book, and it is the only amber
     title in the app. The shelf below is ink.
   - Meta 21dp `rgba(230,220,200,.42)`: `chapter 4 of 54 · picks up at 1:12:08`, or `chapter 4 of 54 ·
     playing`. Use **`in`** rather than `listened` if you show elapsed time (`1h12m in`) — nothing stores
     how long anybody has listened, so `listened` would be a claim about a night nobody recorded. Where no
     chapter total exists, say `chapter 4` and stop rather than `4 of 0`.
   - 2dp progress hairline with an amber fill.
   - The whole block is one target (12dp top / 20dp bottom padding) → opens the book on the player.
   **There is no `pick it up` button, and no `put it down` either — the block has no controls at all.**
   `pick it up` was a 64dp amber pill sitting under a block that already described the book it would open. Every row on the shelf below opens its book by being tapped, so a
   button here made the current book the one entry in the list that worked differently — and it forced a
   second control onto the same row, which overflowed at this screen's type scale. Amber says which book is
   current; tapping it is the same gesture as every other row. The timestamp moved into the meta line, where
   it is a fact about the book rather than the label of a button.

   `put it down` went the same way. Shelving a book is not a thing anybody wants to do — what they want is
   to listen to something else, and tapping that something else on the shelf below already does it. A
   control whose only outcome is an empty `reading now` heading is a control that exists to undo itself.
   (Keep the empty state in the code — italic 23dp "nothing on the go — pick something below" — for a fresh
   install or a library whose current book was deleted. It is a state, not a destination.)
4. **on the shelf** — rows of title **26dp**, meta **19dp**, 2dp progress hairline, 20dp vertical padding;
   tap opens that book on the player. A book with no audio yet (still rendering, or a render that died) is a
   row with **no press**, marked the way search results mark a book already present — a press that was never
   available cannot be a press that did nothing. Omit the progress bar while a book is still arriving:
   `total_ms` is how much audio exists, so a bar drawn from it reaches the end at chapter 5 of 37 and then
   walks backwards. **No cover art** — bright rectangles in a dark room, and four lines of
   text scan faster half-asleep.
3. **how dark the room** — the dim control, **between `reading now` and the shelf**, above a hairline. Two
   64dp circles (`–` / `+`, 26dp glyphs, 0.06 steps, range 0–0.6) either side of a 2dp amber-filled track.
   The overlay updates live as it changes, which is the whole reason it is on a night screen: it can only be
   judged against the dark UI you are actually looking at, and a slider anywhere else is a slider set blind.

   **Above the shelf, not below it.** It was at the foot of the scroller, which on a twenty-book library put
   the only light control in the app behind twenty rows of scrolling — the same mistake as the Workshop row.
   Its place in the order is also an argument: `reading now` and `how dark the room` are both *the state of
   tonight*, and the shelf is a list of other nights.
5. **`workshop ›` in Books' own header**, right corner — the same 36dp pill spec as `‹ controls` opposite
   it, with the caret pointing forward. That corner is empty on Books (`start over` is chat-only), and this
   is what it is for.

   It was a row at the foot of the scroller, below the shelf. That was wrong for a reason that is not
   discoverability: it meant scrolling past every book to reach the one thing on the screen that is not about
   books. A header pill is reachable without scrolling, sits where every other cross-screen move in this app
   sits, and is still one screen further from the thumb than the player.

   **Not in the player's empty corner.** That was asked for and refused: Workshop is the daylight screen, and
   a mis-tap at 3am puts a full-brightness daytime palette in a dark-adapted eye — which costs a minute of
   night vision, the one thing this whole app is arranged around protecting. The corner stays empty.

**Not on this screen**: search, ingest, the render queue, the server note, jump size. All of it moved.

---

### Screen 6 — Workshop · *"get me a new book, and tell me it worked"*

Daytime, sitting up, lights on — so it may be **denser** than any other screen in the app, and must be
**brighter**. Reached only from Books; its left pill reads `‹ books`.

**Workshop uses a different ink scale from every other screen, and the dim overlay is switched off on it.**
This is the one place the night palette must not be reused. Every alpha in the main scale is calibrated for
a dark room and dilated pupils; carried into daylight on a phone at partial brightness, `.35` on `#0b0a09`
is not dim, it is invisible — and because the whole screen was drawn from the quiet end of the scale, there
was no hierarchy either: everything faint, nothing leading.

Implement it as a **token override scoped to the Workshop element** — redeclare the palette custom
properties on `#workshop` so everything inside inherits daylight values and nothing outside it can. That is
better than per-element day colours: the components keep one set of rules and the screen supplies the light.

Daytime ink, on the same `#0b0a09` ground:

| Role | Night value | **Workshop value** |
| --- | --- | --- |
| Primary text (titles, results, queue items, input) | `#e6dcc8` / .8 | **`#f4ece0`** (full) |
| Secondary (meta, subhead, counts, footnotes) | .3–.36 | **.5–.62** |
| Section labels | .3 | **.55** |
| Hairlines / dividers | .07 | **.12–.18** |
| Accent | `#c8873c` | **`#e8a45c`** (lifted; the night amber goes muddy in daylight) |
| Control surfaces | `#16151b` | **`#211f28`** (active `#2b2934`), with a `rgba(244,236,224,.14)` edge |
| Accent surface | `#241a08` | **`#3a2a15`** |
| Accent edge / tint | `.4` / `.07` | **`.75`** / **`.16`** |

The control edge is the one addition rather than a substitution: on near-black a filled slab is already a
control, and in daylight the fill alone stops saying so.

- **The dim overlay is 0 on this screen.** Dimming a daytime screen is actively wrong, and with the overlay
  at a user-chosen 0.4 the screen was unreadable no matter what the ink did.
- **Nothing below 16dp**, up from the 14 an earlier draft allowed. Denser than the night screens is right;
  small enough to squint at is not — the reader is the same 62-year-old either way. Every figure in the
  steps below already obeys this floor; if a number under 16 appears in this section, it is a stale edit,
  not an exception.

1. Title `Workshop` 30dp in full `#f4ece0`, with a **17dp** subhead at `.62`: "Daytime work — find a book,
   have it read, and see that it worked."
2. **project gutenberg** — input pill flex:1, 56dp, **18dp** serif in full ink, placeholder
   `a title, or an author` at `.5`; `find` slab 82×56, **18dp** full ink. Filter on **every typed word**.
   Results count **16dp** at `.55`. Result rows: title **18dp** full ink, meta `Author · year · formats`
   **16dp** at `.58`, action pill 92×48 with a **16dp** label, cycling `ingest` → `working` → `in library`,
   `#e8a45c` once queued.
3. **the server is working** — item title and status **17dp**, progress hairline at `.18`. The render queue
   sits directly beneath the results and on the same screen **on purpose**: you add a book and immediately want to know it is being made. Splitting ingest from its queue
   is how somebody adds the same book twice. Per item, title + right-aligned status (`queued`,
   `fetching text`, `narrating`, `ready`) over a 2dp hairline with a 500ms width transition. The existing
   *ended in the last day* list and the server note belong here too, under the same heading group.
4. **skip button size** — three segmented options (`15s` / `30s` / `60s`), 52dp tall with **18dp** labels,
   selected one `#e8a45c` with a `rgba(232,164,92,.16)` fill and a `.75` edge; the footnote beneath is
   **16dp** italic at `.5` and reads "how far the −/+ buttons move on the player." — it does not cross-refer
   to the dim control, for the reason below. Drives the player's `−30`/`+30` labels. Set once, maybe never — which
   is exactly why it is here and not at night.

Workshop holds **no settings**. Both controls are on Screen 7.

---

## Screen 7 — Settings · *"change how it behaves at night"*

**A night screen**, in the night palette, reached from the **player's top-right corner** — the corner that
had been empty since `start over` moved to chat. Left pill `‹ controls`. Its own 34dp `Settings` title, so
no wordmark.

1. **how dark the room** — two 64dp circles (`–` / `+`, 26dp glyphs, 0.06 steps, range 0–0.6) either side of a
   2dp amber-filled track. Note beneath, italic 19dp: "darker than the phone will go on its own. It changes
   as you press, so you can see it." The overlay updates **live** — that is what makes this control belong on
   a night screen at all.
2. **how far the skip buttons move** — three options (`15s` / `30s` / `60s`), **64dp** tall with 22dp labels,
   selected one amber with a `rgba(200,135,60,.07)` fill. Note beneath names the buttons it changes: "the
   −30 and +30 buttons either side of play."
3. **how big the words** — three options, 64dp tall, each label drawn **at its own scale** (19 / 21 / 23dp) so
   the control shows what it does: `phone's size` (1.0) / `a step larger` (1.15) / `largest` (1.3). Beneath
   them a **live sample** in a hairline box labelled `on the player`, showing the book title and position
   readout at the chosen scale — same principle as dim: a control you can see working. Note: "somnia only, on
   top of your phone's own text size — which somnia follows as well."

   **It is a multiplier, not a replacement.** Fix the pinned root first (see the implementation-status note)
   so the OS setting reaches the app, then apply this factor on top. Two reasons it is not simply "respect the
   OS and stop there": duplicating a system setting normally creates a second source of truth, but a
   multiplier explicitly composes with it rather than competing — and this app is read in conditions nothing
   else on the phone is read in, without glasses in the dark, so "1.0× for email, 1.4× for somnia" is a real
   need the system setting cannot express. Bound it at 1.3: OS 1.3 × app 1.3 is 1.7×, which is where the
   ladder below is doing the work.

### What gives as type grows

At OS scale × app scale the player will eventually not fit. "We might lose the layout" is not a reason to
ignore an accessibility setting; it is a reason to decide the order of sacrifice in advance and test against
it. On the player, in order:

1. The three spacers collapse to their floors (12 / 14 / 14). This already happens and covers most of it.
2. The word `chapter` goes. The count stays — it is the number anybody reads.
3. The chapter title drops from two lines to one.
4. The scrub line goes. It is a readout, not a control, and the position line above says the same thing in
   words.
5. Last resort: the whole chapter group goes — circles, label and count. Places and ±30 still cover
   navigation, and the transport is what must survive.

**Never sacrificed:** transport slab size, dock size, the book title, the position readout. Those four are the
screen. If they do not fit, the scale is out of range — clamp it rather than shrinking them.

### Why this exists, having twice been argued against

Earlier drafts refused a settings screen twice: first because two controls did not seem to justify one, then
because dim and jump size seemed to belong to different times of day — dim at night where it can be judged,
jump size in daylight as configuration. Both arguments were wrong, and the second was the load-bearing one:

- **Jump size is a night control.** You discover 30s is wrong for a particular narrator while lying there
  listening to them, not sitting up in daylight. Splitting it away from dim on a day/night axis put it on the
  wrong side of a line it does not cross.
- **A settings page is where the third control goes without an argument.** With no such page, a new control
  has to be argued onto whichever screen is nearest — which is exactly how the old Library panel grew to
  eight blocks. A place that scales is worth more than a screen saved.
- **It is the pattern people already know.** "Where are the settings?" is a question this app was making
  unanswerable on purpose, which is a poor trade for one fewer screen.

What survives from those arguments is the *palette*: this is a night screen, not a daylight one like
Workshop. It is used in the dark, and dim in particular can only be judged against a dark UI.

## Implementation status

**Synced against `gilesknap/somnia` `main`, 2026-08-08.** This is the only part of this document that says
what to *do*. Everything above describes the design as it stands; this says how much of it the app has.

### Outstanding

1. **The OS font scale never reaches the app.** Verified on device: Android's font-size setting changes
   nothing. The cause is the 20px root — a root set in **px** fixes what `1rem` means, so every rem-sized
   element stops tracking the user's setting. Express it relatively instead (`html { font-size: 125% }` keeps
   the same 20px baseline while staying relative to whatever the user chose). **Do this before 2**, then
   re-check the player at Android's largest setting against the degradation ladder in Screen 7.
2. **Settings (Screen 7)** — not built. A night screen on `settings ›` in the player's top-right corner,
   holding three controls: *how dark the room* (`#dim` is currently fixed at 0.12 for everyone), *how far the
   skip buttons move*, and *how big the words* (the multiplier from 1). Earlier drafts of this document argued
   against a settings screen twice and were wrong; the reasoning is recorded under Screen 7.
3. **Wake screen (Screen 2b)** — not built. The post-fade prompt: three ranked choices instead of the player,
   once, after a sleep-timer fade. Needs only that the fade records its timestamp and the next launch knows it
   happened.
4. **Undo on `goto`** — not built. A 6-second `undo` in the toast that restores the previous position.
   `goto` is the last destructive press in the app and the only route back is another semantic search.
5. **Places carries the list-screen type scale** — reported unreadable in use. It is a **night** screen and
   takes the player's weight (Screen 4 has the figures), and the revealed narration is **upright**, not
   italic.

### Confirmed in main

The three-spacer rhythm with its floors and ceilings; the player type scale (38 / 31 / 29 / 24 / 23 / 21 / 19
/ 18); 84dp transport slabs; 68dp dock and mic; the scrub line as a readout with no tap target; the stacked
position line with its dotted rule and places count; two-line clamps on both titles; the Books / Workshop
split; Workshop's daylight token override with the dim overlay off over it; `reading now` as a tappable block
with an amber title and no buttons on it; `‹ controls` as the single way out of every overlay; `start over` on
chat only, clearing the agent's context as well as the thread; the sleep timer counting down; no play/pause or
±30 on chat.

### Settled, and not to be reopened

- **Sleep-timer default** — dropped. It contradicted the six-hour expiry on a stored timer, which is the
  better behaviour: a timer is an intent about tonight, and persisting it would end a later night early.
- **`put it down`** — dropped. Shelving is not something anybody wants; listening to something else is, and
  tapping that something else on the shelf already does it.
- **`pick it up` button** — dropped. The `reading now` block is the press.
- **Match strength and per-row fit tags on Places** — dropped. No score exists to show, and a self-ranking
  row invites trusting the rank instead of reading the line.
- **The scrub line's tap target** — refused. A mis-tap on a 2dp line in the dark destroys the thing the app
  exists to recover.
- **The player's top-right corner** — it holds `settings ›` and nothing else. Never a destructive action, and
  never a route to the daylight screen.

### Where the app taught the design something

Recorded so these are not "fixed" back the other way: **chat is not a route** (the same element becomes the
chat screen when the keyboard rises, with Places and Library as overlays over a still-playing book);
**`1h12m in` rather than `listened`** (nothing stores listening time); **no-press rows** for books with no
audio yet, and no progress bar while a book is still arriving; **the palette override scoped to `#workshop`**
rather than per-element daylight colours; and **the `#status` line**, which this document had never described
until it was read out of the app — see Screen 1 item 6.

## Not designed — leave your existing UI alone

Server pairing, offline downloads, notification/lock-screen controls, failure states (unreachable server,
failed ingest, denied mic), per-book positions history, chapter/bookmark drawer. If you want any of these
restyled to match, that's a separate pass.

## Porting check (things missing or off in the first build)

Compare against the prototype before calling the player done:

0. **Type across the player is a size or two too small.** The revised scale is above; the biggest misses
   were book title (38), transport numerals (31), chapter title (29), position line (23), dock
   placeholder (22). There is spare vertical room on the player once the rhythm below is right — spend
   it on type, not on gaps.
1. **The chapter counter renders as one line, `chapter 3`.** It is two lines — `chapter` over `3 of 54` —
   and dropping the total loses the only "how much is left" signal on the screen.
2. **The scrub line is missing.** It belongs directly under the position readout, above the sleep pill —
   2dp track, amber fill, 8dp knob, in a 22dp band, **not interactive**. Without it there is no visual sense
   of how far through the book you are, which is half the reason the position group exists.
3. **`4 places found` is missing** from the position line, and the position text has no dotted underline —
   so the route into Places is invisible from the player. Position line = dotted-underlined time + count,
   one 44dp target.
4. **Dock sizing.** Input pill and mic circle are both **68dp**. Same for the chapter
   circles: **64dp**.
5. **Header pill reads `books`; the rest of the UI calls that screen `Books`** — fine, but keep one word
   everywhere (the prototype says `library` in the pill; either is fine, pick one).
6. Optical centring of the wordmark: the `.3em` letter-spacing adds a trailing gap inside the text box, so
   a layout-centred wordmark sits visibly left. Offset by +.15em. (Yours looks correct — noting it so it
   survives future edits.)

Sanity check on device: "Black Beauty" at 38dp should span roughly three-quarters of the screen width, and the
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
