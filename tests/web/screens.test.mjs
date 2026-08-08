// Which screen the page is on, and the one thing that decides it.
//
// The player and the chat are the same document — the conversation never leaves
// it, and the whole of "going to the chat screen" is a class on <body> that the
// stylesheet reads. Everything below is about how that class is arrived at,
// because it used to be arrived at wrongly: the sheet asked
// `@media (max-height: 34rem)`, took that to mean "is the keyboard up?", and got
// it wrong for every short window and permanently for anybody whose OS text
// scale put 34rem above the height of their phone. The player went, and nothing
// they could do to the phone brought it back.
//
// So the keyboard is measured now: what is left of the viewport, against what
// the viewport is when nothing is over it, and only while somebody is actually
// typing into something. Every test here is one of the two halves of that sum
// moving on its own.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { boot, VIEWPORT_HEIGHT } from "./harness.mjs";

// What is left of the phone with a keyboard over it: a little over half. The
// number is not a threshold and nothing here should be tuned to it — it is
// simply what an Android keyboard takes, and any height clearly under three
// quarters of the page would do as well.
const WITH_KEYBOARD = 420;

// How long the page waits before looking again, because a keyboard animates and
// the viewport it leaves does not arrive with the focus event that started it.
const SETTLING_MS = 250;

// A window somebody dragged short, and the height the old query collapsed the
// player at: 34rem at the browser's default 16px root. It is above what a
// keyboard leaves and below what the phone has, which is exactly why guessing
// between the two from height alone could not work.
const SHORT_WINDOW = 544;

// The keyboard arriving, as a phone does it: the box takes focus, and then the
// viewport comes up short. In that order, and never together — a page that
// decided on focus alone would take the player away from anybody with a
// physical keyboard, and there is a test below that says so.
function keyboardOver(page, id = "question") {
  page.focus(id);
  page.resize(WITH_KEYBOARD);
}

// What the sheet actually reads, as a sorted list, so that a page which set one
// class without clearing the other is a failure here rather than a screen drawn
// half in each.
function classes(page) {
  return [...page.body.classes].sort();
}

// ----------------------------------------------------------- the two screens

test("the page opens on the player", async (t) => {
  const page = await boot(t);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
  assert.deepEqual(classes(page), ["player-screen"]);
});

test("a keyboard over the composer is the chat screen", async (t) => {
  const page = await boot(t);
  keyboardOver(page);
  assert.equal(page.probe().screen, "chat");
  assert.equal(page.probe().keyboardUp, true);
  assert.deepEqual(classes(page), ["chat-screen", "keyboard-up"]);
});

test("the keyboard going away is the whole of the way back to the player", async (t) => {
  const page = await boot(t);
  keyboardOver(page);
  page.blur("question");
  page.resize(VIEWPORT_HEIGHT);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
  assert.deepEqual(classes(page), ["player-screen"]);
});

test("the keyboard coming up moves nothing on the page but the screen", async (t) => {
  const page = await boot(t);
  const before = page.probe();
  keyboardOver(page);
  const after = page.probe();
  assert.deepEqual(
    { ...after, screen: before.screen, keyboardUp: before.keyboardUp },
    before,
  );
});

// ------------------------------------------------- a window is not a keyboard

// The issue, in one line. A desktop window dragged shorter than 34rem used to
// take the book, the chapter, both clocks and the scrub line off the screen and
// leave the conversation in their place, and nothing about a window being
// resized says anybody is typing.
test("a window dragged short with nobody typing is still the player", async (t) => {
  const page = await boot(t);
  page.resize(SHORT_WINDOW);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

// The other half of the same issue, and the worse one, because it could not be
// undone: the old threshold was 34 times a root that is the OS text scale on
// purpose, so a reader who turned their text up far enough had a page where the
// threshold was above the height of the phone and the player was gone for good.
// There is no rem in here to turn up — what stands in for it is that no height
// at all can move the page to the other screen while nobody is typing. The
// reading still gives way on a window with no room for it; that is a rule about
// room, it leaves the transport and the dock where they are, and it is in the
// sheet.
test("no height on its own moves the page to the chat screen", async (t) => {
  const page = await boot(t);
  // 884 is 34rem at the root that made this permanent; 544 is 34rem at the
  // browser's default; 272 is a window with barely a transport's worth of room
  // left in it.
  for (const height of [884, VIEWPORT_HEIGHT, SHORT_WINDOW, 300, 272]) {
    page.resize(height);
    assert.equal(page.probe().screen, "player", `at ${height}px`);
    assert.equal(page.probe().keyboardUp, false, `at ${height}px`);
  }
});

test("a box focused on a screen nothing is over is not a keyboard", async (t) => {
  const page = await boot(t);
  // A physical keyboard, or a mouse click into the box on a desktop: focus, and
  // then nothing, because nothing has been put over the page.
  page.focus("question");
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

test("the address bar sliding in is not a keyboard", async (t) => {
  const page = await boot(t);
  page.focus("question");
  // Chrome's own chrome, coming and going as the page scrolls: 56px of a 780px
  // phone. It is a real shrink and it is not somebody's keyboard.
  page.resize(VIEWPORT_HEIGHT - 56);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

// -------------------------------------------------- what it measures against

test("a keyboard is measured against the window it comes up in", async (t) => {
  const page = await boot(t);
  // A page in a browser tab with something else taking the top of the screen,
  // or a desktop window that was never full height: 480px is all this one has
  // ever had, and 480 is therefore what a keyboard has to be measured against.
  page.resize(480);
  page.focus("question");
  // A sixth of the window, gone while somebody is typing in it. Against 480 that
  // is nobody's keyboard. Against the 780 this page was drawn for it is half the
  // screen, and a page still holding that number would have gone to the chat
  // screen here and taken the player with it.
  page.resize(400);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
  // And the real thing, in the same window: half of 480 is a keyboard by any
  // reading, so the two directions are both said here rather than in two tests
  // that could drift apart.
  page.resize(250);
  assert.equal(page.probe().screen, "chat");
  assert.equal(page.probe().keyboardUp, true);
});

test("the height a keyboard is measured against is never taken while one is up", async (t) => {
  const page = await boot(t);
  keyboardOver(page);
  // Every resize a keyboard fires while it is settling in, and one more for the
  // orientation of the phone changing under it. None of them may be mistaken
  // for the page's own height, or the keyboard becomes invisible and the way
  // back to the player with it.
  page.resize(WITH_KEYBOARD - 10);
  page.resize(WITH_KEYBOARD);
  assert.equal(page.probe().screen, "chat");
  page.blur("question");
  page.resize(VIEWPORT_HEIGHT);
  keyboardOver(page);
  assert.equal(page.probe().screen, "chat");
});

// Android's back button closes the keyboard and leaves the field focused, so
// there is no blur to hear. The measurement is what catches it: the page came
// back to its own height, and a page that had believed focus alone would have
// stayed on the chat screen with the book behind it and nothing saying how to
// get back.
test("a keyboard dismissed without the box losing focus is still the player", async (t) => {
  const page = await boot(t);
  keyboardOver(page);
  page.resize(VIEWPORT_HEIGHT);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

// --------------------------------------------------- and again, a beat later

// Focus and blur each measure twice: once on the event, and once a quarter
// second after it, because the keyboard is still moving when the event lands.
// Every other test here stops at the first measurement. The second one runs
// with the page already on a screen, so a change that made it decide
// differently would take somebody off the conversation a beat after the
// keyboard put them there, and nothing above would notice.
test("the measurement a beat later says the same as the first", async (t) => {
  const page = await boot(t);
  keyboardOver(page);
  assert.equal(page.wake(SETTLING_MS), true);
  assert.equal(page.probe().screen, "chat");
  assert.equal(page.probe().keyboardUp, true);
  // And on the way out, where the delayed pass is the first one to run in a
  // window the keyboard has actually given back.
  page.blur("question");
  page.resize(VIEWPORT_HEIGHT);
  assert.equal(page.wake(SETTLING_MS), true);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

// ---------------------------------------------- a keyboard over an overlay

// The books panel is searched with the same keyboard, and there is no chat
// behind it — there is a player. Both overlays shrink their rows for a keyboard
// and neither of them is a screen, which is the whole reason the page carries
// two facts here rather than one flag with two jobs.
test("the books panel's keyboard leaves the player behind it", async (t) => {
  const page = await boot(t);
  keyboardOver(page, "queue-query");
  assert.equal(page.probe().keyboardUp, true);
  assert.equal(page.probe().screen, "player");
  assert.deepEqual(classes(page), ["keyboard-up", "player-screen"]);
});

test("the panel's keyboard going away leaves the player as it found it", async (t) => {
  const page = await boot(t);
  keyboardOver(page, "queue-query");
  page.blur("queue-query");
  page.resize(VIEWPORT_HEIGHT);
  assert.equal(page.probe().keyboardUp, false);
  assert.deepEqual(classes(page), ["player-screen"]);
});

// ------------------------------------------------- nothing to measure with

// Every engine that can run this page has a visual viewport. This is what the
// page does on one that does not: it takes focus at its word, because the
// alternative is a conversation nobody can reach — which is the same stranding
// as the bug this all replaced, only at the other end.
test("with nothing to measure, focus in the composer is taken at its word", async (t) => {
  const page = await boot(t, { canMeasure: false });
  page.focus("question");
  assert.equal(page.probe().screen, "chat");
  assert.equal(page.probe().keyboardUp, true);
});

test("with nothing to measure, leaving the box is still the way back", async (t) => {
  const page = await boot(t, { canMeasure: false });
  page.focus("question");
  page.blur("question");
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

// ------------------------------------------------------------------- the sheet

// The one test here that reads the stylesheet, because the bug was in the
// stylesheet and nothing else in this file can see it: everything above proves
// the page knows which screen it is on, and none of it can prove the sheet is
// asking. The conversation coming back is the whole of what "you are on the
// chat screen" looks like, so if no media query can turn it on then no window
// size, and no text scale, can put somebody there.
const SHEET = readFileSync(
  fileURLToPath(new URL("../../src/somnia/web/style.css", import.meta.url)),
  "utf8",
);

test("no size of window can turn the conversation on by itself", async (t) => {
  const sheet = SHEET.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const block of mediaBlocks(sheet)) {
    assert.ok(
      !block.includes("#transcript"),
      `a media query is drawing the conversation: ${block.slice(0, 120)}`,
    );
  }
  // And it is on for exactly one reason. A test that only counted media queries
  // would pass on a sheet with no rule at all.
  assert.ok(sheet.includes("body.chat-screen #transcript {"));
});

// The other thing a class on <body> costs, and the one the sheet cannot say for
// itself. `#player-bar` is `display: contents`, which beats the browser's own
// `[hidden] { display: none }`, so the sheet has to hide it again by hand — and
// an attribute is weaker than a class, so the moment a screen name goes in front
// of `#player-bar` that hand-written rule is beaten and a page with no book open
// draws the player for a book that is not there. It was reachable: a short wide
// window before the first book is opened.
test("no screen lays the player out on a page with no book open", async (t) => {
  for (const [selector, body] of rules(SHEET)) {
    if (!selector.includes("#player-bar")) continue;
    if (!selector.includes("body.")) continue;
    if (!/\bdisplay\s*:/.test(body)) continue;
    assert.ok(
      selector.includes(":not([hidden])"),
      `this outranks #player-bar[hidden]: ${selector.trim()}`,
    );
  }
});

// Written while fixing one. The sheet is nine tenths prose and a comment
// terminator loose in the middle of a paragraph does not break it loudly: the
// parser reads the rest of the paragraph as a selector, swallows the next rule
// whole, and the page comes up looking almost right. One had been sitting above
// `.said` for long enough that the rule under it — the placement line's width,
// its leading and its colour — had not applied for the life of that comment,
// and nothing said so. This is the cheapest possible guard against the next
// one, and it lives in this file because this is the only suite that reads the
// stylesheet at all.
test("the stylesheet opens and closes every comment exactly once", async (t) => {
  let depth = 0;
  for (let at = 0; at < SHEET.length - 1; at++) {
    const pair = SHEET.slice(at, at + 2);
    // Both markers step the cursor past their own second character, because
    // CSS comments do not nest and do not overlap: the `*` in `/*` cannot also
    // be the `*` of the `*/` that ends it.
    if (pair === "/*" && depth === 0) {
      depth = 1;
      at++;
    } else if (pair === "*/") {
      assert.ok(depth === 1, `a comment is closed twice near ${where(at)}`);
      depth = 0;
      at++;
    }
  }
  assert.equal(depth, 0, "a comment is opened and never closed");
});

// A line number and the words around it, because "somewhere in 2500 lines" is
// not a failure anybody can act on.
function where(at) {
  const line = SHEET.slice(0, at).split("\n").length;
  return `line ${line}: ${SHEET.slice(Math.max(0, at - 60), at + 2)}`;
}

// Every plain rule in the sheet as `[selector, declarations]`, whether it sits
// at the top level or inside a media query — the pattern only matches a brace
// pair with no brace between, which is what a rule is and what a media query is
// not. Comments come out first, because this sheet's prose quotes selectors and
// whole rules at itself and every one of them would read as another rule here.
function rules(sheet) {
  const bare = sheet.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...bare.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => [m[1], m[2]]);
}

// Every `@media` block in the sheet, as its own text. Braces are counted rather
// than matched with a regex because these blocks contain rules, which contain
// braces of their own.
function mediaBlocks(sheet) {
  const blocks = [];
  let at = sheet.indexOf("@media");
  for (; at >= 0; at = sheet.indexOf("@media", at + 1)) {
    let depth = 0;
    for (let end = sheet.indexOf("{", at); end < sheet.length; end++) {
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
