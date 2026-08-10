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
// wants is 34 of the page's, and only app.js can read those.
//
// And the thing the issue got wrong, which matters because it decides what a fix
// is allowed to be: 309x540 at the design's text size genuinely has no room. The
// page is 31.5 roots tall and the player wants 34, so drawing it anyway is the
// title landing on the clock. The fix is not to draw it. The fix is that `how
// big the words` decides it — one press down makes the page 39.3 roots tall and
// the reading comes back — and under the old query that press changed nothing at
// all.

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
  // 360 across is a root of 20, and the player wants 680 of the 780 there are.
  assert.equal(short(page), false);
});

// The case the old query could never see, and the one this change newly loses.
// Two presses up is `--text-size` at 1.2, which is a root of 24 and a page 32.5
// roots tall — and 32.5 is precisely the height style.css measures the book's
// title landing on the clock at. So the reading goes where it used to stay, and
// what it used to be is unreadable rather than missing.
test("the words turned all the way up take the reading off the design's own phone", async (t) => {
  const page = await boot(t);
  page.click("text-up");
  page.click("text-up");
  assert.equal(page.probe().text, "1.2");
  assert.equal(short(page), true);
});

// The issue, in one test. At 309x540 the reading really does have to go — the
// page is 31.5 roots and the player wants 34 — and the page has owned the remedy
// all along. Under the old query pressing it changed nothing, which is what the
// issue's own table shows: root forced to 13.85px, reading still hidden.
test("the words turned down give the reading back on a short phone", async (t) => {
  const page = await boot(t);
  page.resize(REPORTED_HEIGHT, REPORTED_WIDTH);
  assert.equal(short(page), true);
  page.click("text-down");
  page.click("text-down");
  assert.equal(page.probe().text, "0.8");
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

// Not conservative, not "errs on the side of hiding" — wrong in both directions,
// because 544 is a constant and what the player needs is not.
test("544 pixels was wrong in both directions", async (t) => {
  const page = await boot(t);
  // Above the old threshold, so the old query left the reading in. The root at
  // 309 across is 17.2 and the player wants 584, which 560 has not got: the
  // title lands on the clock and the old rule said nothing.
  page.resize(560, REPORTED_WIDTH);
  assert.equal(short(page), true);
  // Below the old threshold, so the old query took the reading away. The root at
  // 240 across is 13.3 and the player wants 453, which 500 has and to spare.
  page.resize(500, 240);
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
// it for want of room, it is keyed on the measurement, and the only media blocks
// allowed to mention it at all are the two that are about shape and about there
// being nothing left to arrange.
test("the reading is taken away by a class and not by a height", async (t) => {
  assert.ok(
    RULES.includes("body.short-page #now-playing { display: none; }"),
    "the fit rule is not keyed on the measurement",
  );
  for (const block of mediaBlocks(RULES)) {
    if (!block.includes("#now-playing")) continue;
    const asks = condition(block);
    assert.ok(
      asks.includes("min-aspect-ratio: 1/1") || asks.includes("max-height: 272px"),
      `a media query is deciding whether the reading is drawn: ${asks}`,
    );
  }
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

// The cascade, said out loud because it is the trap this block's own comment has
// been warning about for two passes. `body.short-page #now-playing` is (1,1,1)
// and the landscape rule is (1,2,1), so the landscape rule wins and the reading
// comes back beside the transport. The 272px rule has to beat that in turn, and
// a selector with one class cannot beat one with two however late it is written.
test("the last word on a page with nothing left to arrange still has the last word", async (t) => {
  const [floor] = mediaBlocks(RULES).filter((block) =>
    condition(block).includes("max-height: 272px"),
  );
  assert.ok(floor, "the 272px floor is not where it was");
  assert.ok(
    floor.includes("body.player-screen.short-page #now-playing { display: none; }"),
    "the floor rule has fewer classes than the landscape rule it must beat",
  );
  // Later in the file, which is the other half of winning a tie.
  assert.ok(
    RULES.indexOf("min-aspect-ratio: 1/1") <
      RULES.indexOf("max-height: 272px"),
    "the floor is written before the landscape block and no longer beats it",
  );
});

// Shape is a question a sheet can answer honestly. Room is not, so the landscape
// block asks the sheet for the first and app.js for the second. It used to ask
// `(max-height: 34rem) and (min-width: 34rem)`, whose width half was 544 CSS px
// — and a phone at display +3 lying down is 540 across, so the phone in the
// issue fell straight through this block to the reading being hidden entirely.
test("the landscape reading is asked for by shape", async (t) => {
  const landscape = mediaBlocks(RULES).filter((block) =>
    condition(block).includes("min-aspect-ratio: 1/1"),
  );
  assert.equal(landscape.length, 1, "the landscape block is not where it was");
  for (const rule of landscape[0].split("}")) {
    if (!rule.includes("body.player-screen")) continue;
    for (const selector of rule.split("{")[0].split(",")) {
      if (!selector.includes("body.player-screen")) continue;
      assert.ok(
        selector.includes("body.player-screen.short-page"),
        `a landscape selector lays out the player on a page with room in it: ${selector.trim()}`,
      );
    }
  }
});
