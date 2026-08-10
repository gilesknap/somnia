// Whether there is room to draw the reading in, which is a different question
// from every other question about the size of the window and was answered for
// years by a rule that could not see the answer.
//
// Three facts, and the issue that started this got two of them right.
//
// `rem` in a MEDIA QUERY resolves against the browser's initial font size and
// never against `html { font-size }`. So `@media (max-height: 34rem)` was a hard
// 544 CSS px whatever the page set — rendered at 309x540 with the root forced
// down to 8px, with acres of room and type a third of its size, the reading was
// still hidden. The rule protecting the layout was blind to the layout.
//
// The page's root has been a fraction of the screen since #64 —
// `calc(var(--text-size) * min(100vw, 460px) / 18)` — so the query's rem and the
// page's rem are not even the same length any more. How much height the player
// wants is 32 of the page's, and only app.js can read those.
//
// And the thing the issue got wrong, which matters because it decides what a fix
// is allowed to be: 309x540 at the design's text size genuinely has no room. The
// page is 31.5 roots tall and the player wants 32, so drawing it anyway is the
// title landing on the clock. The fix is not to draw it. The fix is that `how
// big the words` decides it — one press down makes the page 35.0 roots tall and
// the reading comes back — and under the old query that press changed nothing at
// all.
//
// 32 rather than the 34 this file first shipped with, and the number came from
// pictures. 34 took the reading off 360x780 at `--text-size 1.2`: the design's
// own phone at the top of the reader's own control, on a page that renders
// entirely legible. style.css carries the sweep it was set from.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { boot, rootFor, VIEWPORT_HEIGHT, VIEWPORT_WIDTH } from "./harness.mjs";

// The phone in the issue: a Pixel 6 Pro at Android display size three notches
// above normal, which is the setting somebody who reads without glasses arrives
// at. Both numbers shrink with display size, and the height shrinks faster
// because the status bar and the gesture inset are fixed in dp and eat a
// constant share of a smaller total.
const REPORTED_WIDTH = 309;
const REPORTED_HEIGHT = 540;

// What a keyboard leaves of the design's own phone. Not a threshold and nothing
// here is tuned to it.
const WITH_KEYBOARD = 420;

// Whether the sheet has been told there is no room. It is a class on <body> and
// not a probe field on purpose: the class is the whole of what the stylesheet
// reads, so it is the whole of what a test about the stylesheet can look at.
function short(page) {
  return page.body.classes.has("short-page");
}

// -------------------------------------------------- the room, as the page has

test("the design's own phone has room for the reading", async (t) => {
  const page = await boot(t);
  // 360 across is a root of 20, and the player wants 640 of the 780 there are.
  assert.equal(short(page), false);
});

// The regression 34 shipped with, pinned so it cannot come back. `how big the
// words` at its maximum is `--text-size` 1.2, a root of 24 and a page 32.5 roots
// tall. At 34 the player wanted 816px of a 780px phone and the reader who turns
// the words up because they cannot see got a void where the book is — which is
// issue #65's own symptom, handed back to the reader it was reported by. At 32
// it wants 768 and there are 12px to spare.
test("the words turned all the way up keep the reading on the design's own phone", async (t) => {
  const page = await boot(t);
  page.click("text-up");
  page.click("text-up");
  assert.equal(page.probe().text, "1.2");
  assert.equal(short(page), false);
});

// And the bottom of the same control, which is where the room actually runs out
// on this phone. 360x640 is 32 roots exactly and sits just outside the rule; one
// press up is a root of 22 and 704px wanted of 640, which is a page with no room
// in it however the arithmetic is written.
test("the words turned up on a shorter phone take the reading away", async (t) => {
  const page = await boot(t);
  page.resize(640, 360);
  assert.equal(short(page), false);
  page.click("text-up");
  assert.equal(page.probe().text, "1.1");
  assert.equal(short(page), true);
});

// A desk window is measured too, and it comes out short, because the root stops
// growing at 460 across: 32 of them is a flat 818px and a laptop window has 720.
// The class is written all the same and means only that — it is the stylesheet
// that keeps the reading's own rule off a window wider than the page it was
// measured on, by asking `max-width: 460px` before it reads the class. Asserted
// so that a pass which decided a wide window should not be short would have to
// go and look at that gate on the way.
test("a wide window is short and is not thereby a page with the reading taken out", async (t) => {
  const page = await boot(t);
  page.resize(720, 1280);
  assert.equal(short(page), true);
});

// The issue, in one test. At 309x540 the reading really does have to go — the
// page is 31.5 roots and the player wants 32 — and the page has owned the remedy
// all along. Under the old query pressing it changed nothing, which is what the
// issue's own table shows: root forced to 13.85px, reading still hidden.
test("the words turned down give the reading back on a short phone", async (t) => {
  const page = await boot(t);
  page.resize(REPORTED_HEIGHT, REPORTED_WIDTH);
  assert.equal(short(page), true);
  page.click("text-down");
  assert.equal(page.probe().text, "0.9");
  assert.equal(short(page), false);
});

// -------------------------------------- a keyboard is not a page without room

// The bug #23 fixed, asked again about the other class. A keyboard shortens the
// visual viewport and moves no rem at all, so a page that judged its room by
// what was left of it would throw the reading away every time somebody started
// typing — and then be on the chat screen, where the reading is gone anyway, so
// nobody would notice until they stopped.
test("a keyboard is not a page with no room in it", async (t) => {
  const page = await boot(t);
  page.touch("to-chat");
  page.focus("question");
  page.resize(WITH_KEYBOARD);
  assert.equal(page.probe().screen, "chat");
  assert.equal(page.probe().keyboardUp, true);
  assert.equal(short(page), false);
});

// And the half of that which outlives the keyboard. `unobscured` is only taken
// while nothing has focus, so the 420 measured with a keyboard over the page is
// never what the page is judged by — before, during or after.
test("the height a page is judged by is the one with nothing over it", async (t) => {
  const page = await boot(t);
  page.touch("to-chat");
  page.focus("question");
  page.resize(WITH_KEYBOARD);
  assert.equal(short(page), false);
  page.blur("question");
  page.resize(VIEWPORT_HEIGHT);
  assert.equal(short(page), false);
  assert.equal(page.probe().screen, "player");
});

// The other side of the same coin, and the thing the old query conflated with a
// keyboard: a window somebody dragged short really is a page with no room in it,
// and the answer to that is losing the reading, not losing the book.
test("a window dragged short takes the reading and leaves the player where it is", async (t) => {
  const page = await boot(t);
  page.resize(500);
  assert.equal(short(page), true);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

// ------------------------------------------------------- the number was wrong

// 544 was a constant and what the player needs is not, so it was wrong in both
// directions. This rule fixes one of them and not the other, and which is which
// is worth pinning, because the reason is the limit of the whole model.
//
// A page 240 across has a root of 13.3 and wants 427px: 500px has that and to
// spare, and the old query hid the reading anyway for being under 544. That one
// the measurement gets right, and it is the direction the reader can feel —
// pressing `how big the words` down moves the root and moves this answer.
//
// The other one it does not reach. At 309 across the root is 17.2, and rendering
// a nine-hour book at 309x560 puts the title through the clock — but that page is
// 32.6 roots, over the 32 the player is given, so the reading stays and the
// overlap with it. It cannot be fixed by raising the number: the chrome the stack
// sits in is device pixels, so the same count of roots is a different stack at
// two text sizes, and the smallest number that catches 309x560 is above the 32.5
// roots that the design's own phone has with the words turned all the way up.
// Between hiding the book from the reader who turned the words up and letting a
// title touch a clock on a display-size phone, the reader keeps their book. The
// old query drew that page too, so nothing regresses; it is simply still wrong
// there, and the fix for it is clamping the title rather than emptying the page.
test("544 pixels was wrong in the direction the reader can feel", async (t) => {
  const page = await boot(t);
  page.resize(500, 240);
  assert.equal(short(page), false);
  // And the direction the roots model cannot separate, asserted so that a pass
  // which moves the number has to come and read the paragraph above.
  page.resize(560, REPORTED_WIDTH);
  assert.equal(short(page), false);
});

// ------------------------------------------------------------- and the sheet

const SHEET = readFileSync(
  fileURLToPath(new URL("../../src/somnia/web/style.css", import.meta.url)),
  "utf8",
);

// The sheet with its prose taken out and its whitespace flattened, so a rule can
// be looked for as the one string it is. screens.test.mjs does the same to the
// same file for the same reason; it is copied rather than shared because a test
// file that exported helpers would run its own suite twice on every import.
const RULES = SHEET.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\s+/g, " ");

// Every `@media` and the block that belongs to it, matched by counting braces
// rather than by a regexp, because a nested block would end the match early.
function mediaBlocks(sheet) {
  const blocks = [];
  for (let at = sheet.indexOf("@media"); at >= 0; at = sheet.indexOf("@media", at + 1)) {
    const open = sheet.indexOf("{", at);
    assert.ok(open >= 0, "an @media with no block");
    let depth = 0;
    for (let end = open; end < sheet.length; end++) {
      if (sheet[end] === "{") depth++;
      if (sheet[end] === "}") depth--;
      if (depth === 0) {
        blocks.push(sheet.slice(at, end + 1));
        break;
      }
    }
  }
  return blocks;
}

const condition = (block) => block.slice(0, block.indexOf("{"));

// The general guard, and the reason this file is worth having beyond the one
// bug. Nothing stops the next `max-height: 30rem` being written except somebody
// remembering what rem means in here, and nobody remembers: the sheet argued the
// wrong case for this in three separate comments for months. A question about
// size is asked in device pixels, or in shape, or it is asked in app.js.
test("no media query in the stylesheet asks a question in rem", async (t) => {
  for (const block of mediaBlocks(RULES)) {
    assert.ok(
      !condition(block).includes("rem"),
      `a media query is asking in rem, which is the browser's 16px and not the page's root: ${condition(block)}`,
    );
  }
});

// Where the reading is taken away, and where it is not. Exactly one rule hides
// it for want of room, it is keyed on the measurement, and the one media block
// allowed to mention it asks the size the measurement was taken at. None of it
// is a height standing in for the type.
test("the reading is taken away by a class and not by a height", async (t) => {
  assert.ok(
    RULES.includes("body.short-page #now-playing { display: none; }"),
    "the fit rule is not keyed on the measurement",
  );
  for (const block of mediaBlocks(RULES)) {
    if (!block.includes("#now-playing")) continue;
    const asks = condition(block);
    assert.ok(
      asks.includes("max-width: 460px") || asks.includes("max-height: 540px"),
      `a media query is deciding whether the reading is drawn: ${asks}`,
    );
  }
});

// And the two sizes it is held to, which are the difference between a phone with
// no room and a desk with room to spare. The root stops growing at 460 across, so
// past that 32 roots is a flat 818px and every browser window under that is
// measured short — on a page where the book's name and the chapter name have
// stopped wrapping, which is two of the lines the 32 was counting on them
// spending. A 1280x720 window keeps the whole reading, as it did before any of
// this. What judges a wide window instead is 540px, the reading's own measured
// height, so a letterbox still loses it.
test("the reading is only taken away from a page the size it was measured on", async (t) => {
  const [measured] = mediaBlocks(RULES).filter((block) =>
    block.includes("body.short-page #now-playing"),
  );
  assert.ok(measured, "the fit rule is not inside a query at all");
  const asks = condition(measured);
  assert.ok(
    asks.includes("max-width: 460px"),
    `the fit rule is asked of windows it was never measured on: ${asks}`,
  );
  assert.ok(
    asks.includes("max-height: 540px"),
    `a window dragged to a letterbox keeps a reading with no room: ${asks}`,
  );
});

// The whole of the landscape layout came out on the way through, and this is
// what says so. It was a two-column player for a phone on its side, gated on
// `(max-height: 34rem) and (min-width: 34rem)` — 544 CSS px on both halves — and
// the phone this issue was reported on is 540 across lying down, so it fell
// straight through the block that existed for it. Rebuilt on shape it reached
// that phone and photographed broken: the clock wrapped onto two lines, the
// sleep-timer pill was clipped off the left edge and `+30` off the right, on a
// grid drawn for 669px. It is a layout nobody arrives at on purpose and one
// nobody had looked at, so it is gone rather than half-repaired, and a phone on
// its side gets the same missing reading a short window gets.
test("there is no landscape layout to keep working", async (t) => {
  for (const block of mediaBlocks(RULES)) {
    assert.ok(
      !condition(block).includes("aspect-ratio"),
      `a media query is laying the player out by shape again: ${condition(block)}`,
    );
  }
  assert.ok(
    !RULES.includes("body.player-screen.short-page"),
    "a rule is still drawing the player differently on a page with no room",
  );
});

// The harness fakes `getComputedStyle` from this one declaration, because it is
// the yardstick the class under test is measured against and a fake that
// answered anything would be testing arithmetic against itself. So the copy has
// to be pinned to the original: change the sheet's root and this fails on the
// same run rather than three passes later.
test("the harness measures the root the sheet does", async (t) => {
  assert.ok(
    RULES.includes(
      "font-size: calc(var(--text-size) * min(100vw, 460px) / 18);",
    ),
    "the sheet's root has moved and the harness's copy of it has not",
  );
  // And the arithmetic itself, at the two places it behaves differently: under
  // the cap the root follows the width, over it the root stops.
  assert.equal(rootFor(VIEWPORT_WIDTH, 1), 20);
  assert.equal(rootFor(1200, 1), 460 / 18);
});
