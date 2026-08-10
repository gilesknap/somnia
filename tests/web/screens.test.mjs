// Which screen the page is on, and the one thing that decides it.
//
// The player and the chat are the same document — the conversation never leaves
// it, and the whole of "going to the chat screen" is a class on <body> that the
// stylesheet reads. Everything below is about how that class is arrived at,
// because it used to be arrived at wrongly: the sheet asked
// `@media (max-height: 34rem)`, took that to mean "is the keyboard up?", and got
// it wrong for every short window — and permanently for any phone whose viewport
// is under 544 CSS px, which is what 34rem is in a media query whatever the page
// sets its root to. The player went, and nothing they could do to the phone
// brought it back.
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
// player at: 34rem in a media query, which is 34 times the browser's initial
// 16px and has nothing to do with the page's own root. It is above what a
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

// --------------------------------------------- asking for the conversation

// The route in that is a press rather than a measurement, and the reason it
// exists: a keyboard is evidence that somebody arrived on this screen and it is
// no way at all of deciding whether they may be here. Every test in this block
// is a night where the measurement said nothing useful and the conversation had
// to be reachable anyway.

// The dock, pressed. The finger going down, and then whatever the platform does
// about focus after it — which on the microphone is nothing at all.
function pressDock(page, id = "question") {
  page.touch(id);
  if (id === "question") page.focus(id);
}

test("a press on the composer is the chat screen before any keyboard", async (t) => {
  const page = await boot(t);
  pressDock(page);
  assert.equal(page.probe().screen, "chat");
  // And no keyboard has been claimed on the strength of a press: the overlays
  // shrink their rows for that, and nothing is over this page yet.
  assert.equal(page.probe().keyboardUp, false);
});

test("a keyboard that never shrinks the page still gets the conversation", async (t) => {
  const page = await boot(t);
  pressDock(page);
  // A keyboard drawn over the page instead of shrinking it: the viewport says
  // what it always said, and nothing that follows may take the screen back.
  page.resize(VIEWPORT_HEIGHT);
  assert.equal(page.wake(SETTLING_MS), true);
  assert.equal(page.probe().screen, "chat");
});

// The microphone had no route to this screen at all. It takes no focus and
// raises no keyboard, so there was nothing about it to measure — and holding it
// dictated a question into a transcript that was on the other screen, which
// looked like a microphone that did nothing.
test("a press on the microphone is the chat screen", async (t) => {
  const page = await boot(t);
  pressDock(page, "talk");
  assert.equal(page.probe().screen, "chat");
  assert.equal(page.probe().keyboardUp, false);
});

// The measurement that used to decide this screen, wrong in the direction that
// strands somebody: a height taken while a keyboard was already up teaches the
// page that the short screen is the whole screen, and no keyboard is ever
// visible again. It cost the conversation before; now it costs nothing.
test("a height taken while a keyboard was up cannot keep the conversation off", async (t) => {
  const page = await boot(t);
  // Nobody typing, so this is what the page believes it has to work with.
  page.resize(WITH_KEYBOARD);
  pressDock(page);
  assert.equal(page.probe().screen, "chat");
});

test("the keyboard closing under the finger that asked is the way back", async (t) => {
  const page = await boot(t);
  pressDock(page);
  page.resize(WITH_KEYBOARD);
  assert.equal(page.probe().screen, "chat");
  // Android's back button: the keyboard goes and the box keeps its focus, so
  // there is no blur to hear. The room coming back is the only thing said.
  page.resize(VIEWPORT_HEIGHT);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

test("the way back off chat forgets that they asked", async (t) => {
  const page = await boot(t);
  pressDock(page);
  page.resize(WITH_KEYBOARD);
  page.click("to-controls");
  assert.equal(page.probe().screen, "player");
  // The keyboard finishing its way out afterwards, and the address bar moving
  // on the next scroll. A page that still believed it was wanted here would put
  // the conversation back over the book on either of them.
  page.resize(VIEWPORT_HEIGHT);
  assert.equal(page.wake(SETTLING_MS), true);
  assert.equal(page.probe().screen, "player");
  assert.deepEqual(classes(page), ["player-screen"]);
});

test("leaving the box forgets that they asked", async (t) => {
  const page = await boot(t);
  pressDock(page);
  page.blur("question");
  assert.equal(page.probe().screen, "player");
  page.resize(WITH_KEYBOARD);
  assert.equal(page.probe().screen, "player");
});

// The other half of the same rule, and the one that decides where the app comes
// up. A box can take focus with nobody having touched the page — a browser
// restoring a document it had put away is the usual way — and a page that read
// that as a request would open on the conversation, with the book nowhere on it,
// for somebody who had done nothing but unlock their phone.
//
// A guard rather than a reproduction: the reader really did lose the player at
// boot, but to an old page served from a phone cache, not to this. It is here
// because the press is what the screen means, and a focus is not a press.
test("a focus nobody asked for does not open the chat screen", async (t) => {
  const page = await boot(t, { activated: false });
  page.focus("question");
  page.resize(WITH_KEYBOARD);
  assert.equal(page.probe().screen, "player");
  // `short-page` comes with it and is the right answer here. The page has been
  // given no evidence that anybody is typing — that is the whole of what this
  // test sets up — so 420px is simply what the page is, and 420px has no room
  // to draw the reading in. The reading gives way, the player does not, and the
  // difference between those two is what this section is about.
  assert.deepEqual(classes(page), ["player-screen", "short-page"]);
});

// ------------------------------------------------- a window is not a keyboard

// The issue, in one line. A desktop window dragged under 544px used to take the
// book, the chapter, both clocks and the scrub line off the screen and leave the
// conversation in their place, and nothing about a window being resized says
// anybody is typing.
test("a window dragged short with nobody typing is still the player", async (t) => {
  const page = await boot(t);
  page.resize(SHORT_WINDOW);
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

// The other half of the same issue, and the worse one, because it could not be
// undone: the old threshold was a flat 544 CSS px, so a phone whose viewport is
// shorter than that — which is a phone at a large display size, and this app is
// read by somebody who turns things up — was on the chat screen every night with
// the player gone for good. What stands in for that here is that no height at
// all can move the page to the other screen while nobody is typing. The reading
// still gives way on a window with no room for it; that is a rule about room, it
// leaves the transport and the dock where they are, and it is measured against
// the page's own root in fitting.test.mjs.
test("no height on its own moves the page to the chat screen", async (t) => {
  const page = await boot(t);
  // 884 is a window taller than the phone the design was drawn for; 544 is what
  // 34rem in a media query actually was; 272 is a window with barely a
  // transport's worth of room left in it.
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

// -------------------------------------------------- the header's two corners

// The header is one row on both screens and it holds a different thing in each
// corner on each of them, which is the second thing the page needed a screen
// for. Which pill is in which corner is the sheet's business and is tested
// further down, against the sheet. What is testable from in here is the one of
// the three that does something app.js knows about: the way back to the
// controls, which is a press and not a keyboard deciding to leave.

test("the header's way back off chat is a press", async (t) => {
  const page = await boot(t);
  keyboardOver(page);
  page.click("to-controls");
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
  assert.deepEqual(classes(page), ["player-screen"]);
});

// And the same way back, made out of the thread itself. It is the biggest
// target on the screen and the only one that needs no aiming, which is what
// makes taking the transport off this screen a trade rather than a loss.
test("a press on the thread is a way back off chat", async (t) => {
  const page = await boot(t);
  keyboardOver(page);
  page.click("transcript");
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
  assert.deepEqual(classes(page), ["player-screen"]);
});

// It changes nothing else, as the pill does not — and it can only fire on the
// screen it is a way off, which is the sheet's doing as well as the guard's:
// the thread is drawn on chat and nowhere else.
test("a press on the thread moves nothing but the screen, and nothing at all on the player", async (t) => {
  const page = await boot(t);
  const before = page.probe();
  keyboardOver(page);
  page.click("transcript");
  assert.deepEqual(page.probe(), before);
  // On the player it is not a control at all: a press changes nothing, and in
  // particular does not put the page on a screen it is already on by another
  // name.
  page.click("transcript");
  assert.deepEqual(page.probe(), before);
});

// The same promise the keyboard makes coming up, made again going down: the
// book is still playing, still where it was, and the conversation is still in
// the document waiting to be come back to.
test("the way back off chat moves nothing on the page but the screen", async (t) => {
  const page = await boot(t);
  const before = page.probe();
  keyboardOver(page);
  page.click("to-controls");
  assert.deepEqual(page.probe(), before);
});

// The reason the press does not simply call blur() and wait to be told. A
// keyboard nobody can measure is a keyboard nobody can watch go away, and this
// is the corner that exists so that somebody in that position still has a way
// back to the book.
test("with nothing to measure, the press off chat still lands", async (t) => {
  const page = await boot(t, { canMeasure: false });
  page.focus("question");
  assert.equal(page.probe().screen, "chat");
  page.click("to-controls");
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().keyboardUp, false);
});

// Both corners of the chat screen are drawn only while the composer has focus,
// because that focus is what the screen *is*. So a press on either of them that
// let the focus go would put the button out of the page between the finger going
// down and the click coming out, and a real browser then delivers that click to
// whatever is left in the corner — which is nothing. Chrome does it by mouse and
// by finger alike, and what it looked like on the phone was `start over` putting
// the keyboard away and clearing no conversation at all. Nothing above can see
// it: a test fires the click straight at the element and cannot lose it on the
// way. What is testable from here is the refusal itself.
test("neither corner of the chat screen takes the composer's focus", async (t) => {
  const page = await boot(t);
  keyboardOver(page);
  for (const id of ["to-controls", "restart"]) {
    let kept = false;
    page.el(id).fire("mousedown", { preventDefault: () => (kept = true) });
    assert.equal(kept, true, `${id} let the press move the focus`);
  }
});

// ------------------------------------------------------------------- the sheet

// The tests that read the stylesheet, because two of the things this issue is
// about are in the stylesheet and nothing else in this file can see them:
// everything above proves the page knows which screen it is on, and none of it
// can prove the sheet is asking. The conversation coming back is the whole of
// what "you are on the chat screen" looks like, so if no media query can turn
// it on then no window size, and no text scale, can put somebody there.
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

// The sheet with its prose taken out and its whitespace flattened, so a rule can
// be looked for as the one string it is. Written literally rather than picked
// apart with a parser: three declarations decide which pill is in which corner,
// two of them are one word long, and a test that reproduced the cascade to check
// them would be a second implementation of the thing it is checking.
const RULES = SHEET.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\s+/g, " ");

// The design is explicit that the right-hand corner is empty on the player, and
// says why: a press that throws something away has no business in the top corner
// of the screen somebody taps half asleep. So it is off by default and turned on
// by the chat screen, and not the other way about — a class that failed to be
// written can then only leave a corner empty, never fill it.
test("start over is drawn on the chat screen and nowhere else", async (t) => {
  assert.ok(RULES.includes("#to-controls, #restart { display: none; }"));
  assert.ok(
    RULES.includes(
      "body.chat-screen #to-controls, body.chat-screen #restart { display: flex; }",
    ),
  );
  for (const block of mediaBlocks(RULES)) {
    assert.ok(
      !block.includes("#restart"),
      `a media query is drawing start over: ${block.slice(0, 120)}`,
    );
  }
});

// And the other thing that corner holds, drawn the same way round: off unless a
// screen asks for it, so a class that never got written leaves an empty corner
// rather than a full one. `settings ›` is on the player and nowhere else — on
// chat that corner is `start over`, and the two must never be drawn at once.
//
// It is safe in the corner `start over` had to leave for the same reason
// Workshop was refused it: what a mis-tap costs. This one costs nothing. It
// opens a night screen in the night palette that destroys nothing by being
// looked at, which is what the two refusals were about and not the corner.
test("settings is drawn on the player and nowhere else", async (t) => {
  assert.ok(RULES.includes("#to-settings { display: none; }"));
  assert.ok(RULES.includes("body.player-screen #to-settings { display: flex; }"));
  for (const block of mediaBlocks(RULES)) {
    assert.ok(
      !block.includes("#to-settings"),
      `a media query is drawing the way to settings: ${block.slice(0, 120)}`,
    );
  }
});

// The conversation is the whole of the chat screen, and the player's rhythm is
// not on it. The three spacers are `flex: 1 1 0` siblings of #transcript in the
// body's one column — which is what pools the slack into one gap on the player
// — so left standing here they took 2:1:1 of the height a keyboard leaves and
// pushed the words into a hundred-pixel box at the top of the screen with 320
// pixels of nothing under them.
test("the player's spacers are not on the chat screen", async (t) => {
  assert.ok(RULES.includes("body.chat-screen .rhythm { display: none; }"));
});

// And the reading, said the same belt-and-braces way and for the same reason.
// Both rules are redundant as the sheet stands: `body.chat-screen #player-bar`
// is `display: none`, and nothing renders under a parent that is not there. A
// cleanup pass found this one and proposed deleting it — kept instead, and
// pinned here, because the rule it is redundant *with* is one line away from
// being changed back, and the two failures are not the same size. A dead rule
// costs nothing; the reading appearing over a conversation somebody is typing
// into is the screen losing its subject.
test("the reading is not on the chat screen either", async (t) => {
  assert.ok(RULES.includes("body.chat-screen #now-playing { display: none; }"));
});

// #now-playing is `display: contents` everywhere but one block, and that one
// block is why this test exists. It was written when the base rule was a flex
// column, so it said `display: flex` and left the direction to be inherited from
// a rule that is no longer there — and a flex container with no direction is a
// row. A phone on its side then laid the book's name, its position, the chapter,
// the clock and the circles out beside each other, each squeezed to about the
// width of a letter, with the strip of circles off the right of the screen.
// Rendered at 844x390 the title was 51px wide and the strip started at x=897.
//
// The assertion is on the invariant rather than on that block, because the bug
// was not a typo in it: it was a rule at a distance changing under it. Any
// future rule that makes this element a box has the same hole to fall into.
test("nothing makes the reading a flex box without saying which way it runs", async (t) => {
  let boxes = 0;
  for (const [selector, body] of rules(SHEET)) {
    const named = selector
      .split(",")
      .some((one) => one.trim().endsWith("#now-playing"));
    if (!named || !/display\s*:\s*flex/.test(body)) continue;
    boxes++;
    assert.ok(
      /flex-direction\s*:\s*column/.test(body),
      `the reading is a flex ROW here: ${selector.trim()}`,
    );
  }
  // A sheet that stopped making it a box at all would pass the loop above
  // without running it once, and the landscape layout would be gone rather than
  // fixed.
  assert.equal(boxes, 1, "exactly one block turns the reading into a box");
});

// The other half of the same bug, and the reason the grid drew two columns and
// filled neither. `#player-bar` is `display: contents`, so the grid's items are
// not the two the block names — they are Spacer A, the reading, Spacer C and the
// transport. Four things in two columns is two rows: the left column was one
// empty spacer, and the transport sat under the reading rather than beside it.
test("the player's spacers are not items of the landscape grid", async (t) => {
  const landscape = mediaBlocks(RULES).filter((block) =>
    block.includes("min-aspect-ratio: 1/1"),
  );
  assert.equal(landscape.length, 1, "the landscape block is not where it was");
  assert.ok(
    landscape[0].includes(
      "body.player-screen.short-page #player-bar:not([hidden]) .rhythm { display: none; }",
    ),
    "the landscape grid is holding the portrait rhythm",
  );
});

// What is left of the reading when the phone is on its side, and why it is not
// all of it. The block's first paragraph says nothing has to go because nothing
// is short of room across — true of width and false of height, which is the
// dimension that gets this block onto the screen. With the whole reading in it
// the left column stands 421px tall under a 61px header and a 41px status line,
// so it wants about 540px of window, and nothing that reaches this block has
// that: `short-page` is only written on a page under 34 of its own roots, which
// past the 460px cap is 869px at the design's text size.
//
// So the chapter, its clock and its circles go, and the name gets one line. What
// stays is the name, the clock and the sleep button — the control this block
// exists to keep reachable and the one thing here that a turn of the wrist is
// not a workaround for.
//
// The numbers below come from photographing the real page with a nine-hour book
// open, not from measuring the bare markup, and the difference between the two
// is the whole of why this comment was rewritten. Measured that way at 669x309 —
// a Pixel 6 Pro on its side at the text scale this page is read at — the first
// version of this block still put the sleep pill 45px under the bottom of the
// window: `1:12:08 of 9:41:33` wrapped in a column 60px too narrow, and the
// wrapped line pushed the pill off. Hence even columns rather than 1fr to
// 1.4fr, and hence the scrub line and the places count going too. As it stands
// the pill's bottom edge is at 295 in a 309px window.
test("the landscape reading keeps the name and the sleep timer", async (t) => {
  const [landscape] = mediaBlocks(RULES).filter((block) =>
    block.includes("min-aspect-ratio: 1/1"),
  );
  // The columns the reading has to fit in. Named because the wrap that lost the
  // sleep timer was a width problem showing up as a height one.
  assert.ok(
    landscape.includes("grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);"),
    "the landscape columns are uneven again, and the clock wraps when they are",
  );
  for (const gone of [
    "#chapter-title",
    "#chapter-clock",
    ".chapter-strip",
    "#whole-progress",
    "#places-found",
  ]) {
    assert.ok(
      landscape.includes(`body.player-screen.short-page ${gone}`),
      `${gone} is drawn in landscape, where there is no height for it`,
    );
  }
  assert.ok(
    landscape.includes(
      "body.player-screen.short-page #book-title { white-space: nowrap;",
    ),
    "the landscape title is free to take a second line",
  );
  // And the two that must not go, said as an assertion so that trimming this
  // block further has to be deliberate.
  for (const kept of ["#whereabouts", "#clock", "#sleep"]) {
    assert.ok(
      !landscape.includes(`body.player-screen.short-page ${kept} { display: none;`),
      `landscape has taken away ${kept}`,
    );
  }
});

// The other corner, which is one place holding one of two pills. `books ›`
// goes to the panel and `‹ controls` comes back, and exactly one of them is
// drawn at a time — a header with both would be two doors in one corner, and a
// header with neither has no way out of anything.
test("the left corner holds one pill on each screen", async (t) => {
  assert.ok(RULES.includes("body.chat-screen #books { display: none; }"));
  for (const block of mediaBlocks(RULES)) {
    assert.ok(
      !block.includes("#books"),
      `a media query is drawing the way to the books: ${block.slice(0, 120)}`,
    );
  }
});

// And the transport is not on the chat screen at all. It used to shrink and
// stay, on the argument that a book still playing must stay stoppable; three
// other things stop it — the keyboard going down, `‹ controls`, and the lock
// screen — and what the row cost was the height of the one screen in the app
// that is nothing but text.
test("the transport is not on the chat screen", async (t) => {
  assert.ok(
    RULES.includes("body.chat-screen #player-bar:not([hidden]) { display: none; }"),
  );
  for (const [selector] of rules(SHEET)) {
    assert.ok(
      !/body\.chat-screen\s+\.transport/.test(selector),
      `a rule is still drawing the transport on chat: ${selector.trim()}`,
    );
  }
});

// ------------------------------------------------------------- the morning

// The third screen, which is the one none of the tests above can arrive at: it
// is not a press and not a measurement, it is a fact about last night read out
// of storage at boot. morning.test.mjs owns everything the page does about it.
// What is testable from here is the same thing this block tests about the other
// two — that the sheet draws it, that nothing about the size of a window can,
// and that the screen it replaces is really off.

test("the morning is drawn on the wake screen and nowhere else", async (t) => {
  // Off by default and turned on by the class, which is the direction every
  // screen-scoped rule in this sheet runs in: a class that somehow never got
  // written leaves the reader on the player, which is the app. The other way
  // round it would be a morning nobody could get off, over a book they cannot
  // see, with no header to leave by.
  assert.ok(declared("#wake").includes("display: none"));
  assert.ok(declared("body.wake-screen #wake").includes("display: flex"));
  for (const block of mediaBlocks(RULES)) {
    assert.ok(
      !block.includes("#wake"),
      `a media query is drawing the morning: ${block.slice(0, 120)}`,
    );
  }
});

// And what it replaces, which is everything — including the header, which no
// other screen takes away. There is nothing to leave the morning for: `books ›`
// at 7am opens a panel over an unanswered question, and it sits in the corner a
// hand lands on first. Every way off that screen is one of the three presses on
// it.
//
// Read as a set of selectors rather than looked for as one string, because these
// five are one rule today and could be five tomorrow without anything about the
// screen having changed.
test("nothing the player draws is on the morning", async (t) => {
  const off = new Set();
  for (const [selector, body] of rules(SHEET)) {
    if (!/\bdisplay\s*:\s*none/.test(body)) continue;
    for (const one of selector.split(",")) {
      const said = one.trim();
      if (said.startsWith("body.wake-screen ")) {
        off.add(said.slice("body.wake-screen ".length));
      }
    }
  }
  for (const gone of [
    "header",
    "#status",
    "#composer",
    ".rhythm",
    // With the guard the rule below this one insists on, for the reason it
    // gives: a class on <body> outranks `#player-bar[hidden]`.
    "#player-bar:not([hidden])",
  ]) {
    assert.ok(off.has(gone), `the morning is still drawing ${gone}`);
  }
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

// Everything the sheet declares for one selector, as one flattened string. The
// selector is matched whole and on its own, so a rule written for several at
// once answers for each of them — and a rule whose declarations grew since the
// test was written still answers, which a literal `#wake { display: none; }`
// does not.
function declared(wanted) {
  const said = [];
  for (const [selector, body] of rules(SHEET)) {
    const named = selector.split(",").some((one) => one.trim() === wanted);
    if (named) said.push(body.replace(/\s+/g, " ").trim());
  }
  assert.ok(said.length, `nothing in the sheet draws ${wanted}`);
  return said.join(" ");
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
    // An `@media` with nothing after it has no `{` to find, and a scan started
    // at -1 reads no character, closes no brace and slices out the empty
    // string — which is a block that passes every assertion made about one.
    const open = sheet.indexOf("{", at);
    assert.ok(open >= 0, `an @media with no block near ${where(at)}`);
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
