// The two things the page can say without being asked, and the layer it says
// them through.
//
// #status has been the only voice on this page since the beginning, and it is
// asked to hold two unlike things: "listening…", which is over in a moment,
// and "tap anywhere to carry on", which is an instruction that stands until it
// is obeyed. A line that clears itself after a few seconds cannot hold the
// second kind — so the toast is a second channel rather than a replacement,
// and the whole of what is asserted below is that the two never touch.
//
// The dim layer is the other half. It is black, it covers everything including
// both overlays, and it is what lets the page go darker than the phone's own
// minimum brightness. Being over everything is exactly why it must never take
// a press: the page arms a document-wide pointerdown after the platform
// refuses to start the sound, and a layer that swallowed that press would
// leave a paused book in the dark with the only way back under it. The CSS
// half of that promise — `pointer-events: none` — is a render's job to check;
// what is checked here is that the page hangs nothing on the layer and that a
// tap anywhere still reaches the book while a sentence is up.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { boot, HALF_HEARD } from "./harness.mjs";

// How long a sentence stands before it forgets itself.
const TOAST_MS = 2800;

// ------------------------------------------------------------------ the toast

test("the sleep timer says what it did, and the sentence goes away by itself", async (t) => {
  const page = await boot(t);
  assert.equal(page.probe().toast, "");

  page.click("sleep");
  assert.equal(page.probe().toast, "fading out in 15 min");
  // Not a wake left running: the page is asleep in a pocket for the rest of the
  // night and every pending timer is a radio wake beside somebody.
  assert.deepEqual(page.waits(), [TOAST_MS]);

  assert.equal(page.wake(TOAST_MS), true);
  assert.equal(page.probe().toast, "");
  assert.deepEqual(page.waits(), []);
});

test("a second sentence replaces the first rather than stacking under it", async (t) => {
  const page = await boot(t);
  page.click("sleep");
  page.click("sleep");
  // One box, one sentence, one timer. Two sentences on screen at 2am is two
  // things to read to find out which of them is still true, and the older one
  // never is.
  assert.equal(page.probe().toast, "fading out in 30 min");
  assert.deepEqual(page.waits(), [TOAST_MS]);

  // The last press of the six takes the timer off again, and the sentence has
  // to say so — a box still reading "fading out in 60 min" over a night with
  // no end scheduled is the one lie this control can tell.
  for (let tap = 0; tap < 4; tap++) page.click("sleep");
  assert.equal(page.probe().toast, "no sleep timer");
  assert.deepEqual(page.waits(), [TOAST_MS]);
});

test("the end of the chapter is said in words, not in minutes", async (t) => {
  const page = await boot(t);
  for (let tap = 0; tap < 5; tap++) page.click("sleep");
  assert.equal(page.probe().sleep, "sleep timer · chapter end");
  assert.equal(page.probe().toast, "fading out at the end of the chapter");
});

// ------------------------------------------------- two channels, not one

test("a sentence that goes away cannot erase one that has to stand", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  // The real 2am sequence: the app was backgrounded, the platform refused the
  // sound, and the page is now holding an instruction that is true until it is
  // obeyed.
  page.audio.refuse = "NotAllowedError";
  page.click("playpause");
  await page.settle();
  const standing = page.probe().status;
  assert.equal(standing, "tap anywhere to carry on");

  page.click("sleep");
  assert.equal(page.probe().toast, "fading out in 15 min");
  assert.equal(page.probe().status, standing);
  // And no way back beside it. The undo is on the one sentence that has
  // something to undo — see choosing.test.mjs — and every other press the page
  // reports is already undone by pressing the opposite thing. A sleep timer
  // offering an undo would be a control for what the control beside it does.
  assert.equal(page.probe().undo, false);

  page.wake(TOAST_MS);
  assert.equal(page.probe().toast, "");
  // Byte for byte. The toast came and went and the line that matters did not
  // move — which is the whole reason there are two of them.
  assert.equal(page.probe().status, standing);

  // And the press the instruction was asking for still lands. The layer is
  // over everything on the page, the toast is under it, and neither is allowed
  // to be the thing a thumb hits instead of the book. For its few seconds the
  // sentence lies across the box and part of the microphone, so nothing is
  // hung on it either — `pointer-events: none` in the sheet is the other half,
  // and that half is a render's to check.
  //
  // The box, not what is in it: #toast-undo is a real press and turns pointer
  // events back on for itself, which is the one hole in the rule and is bought
  // with the one thing on this page that cannot be undone. It is hidden here,
  // as it is on every sentence but that one, so this box is a sentence and
  // nothing else.
  assert.deepEqual(Object.keys(page.el("toast").handlers), []);
  page.audio.refuse = null;
  page.document.fire("pointerdown");
  await page.settle();
  assert.equal(page.audio.paused, false);
});

// -------------------------------------------------------------- the dim layer

test("the room is taken darker than the phone will go, by a little", async (t) => {
  const page = await boot(t);
  // A twelfth of the light off, which is a dim and not a fog: everything is
  // still legible through it, and the page it is over was already the darkest
  // thing the phone can draw.
  assert.equal(page.probe().dim, 0.12);
  assert.equal(page.el("dim").hidden, false);
  // Nothing is reached through it, so nothing is hung on it. A press that had
  // to be caught here and forwarded is a press that can be dropped.
  assert.deepEqual(Object.keys(page.el("dim").handlers), []);
});

test("a level written down before is the one the page opens at", async (t) => {
  const page = await boot(t, { stored: { "somnia-dim": "0.45" } });
  // It outlives the page for the same reason the sleep timer does: a
  // backgrounded tab is discarded whenever the phone wants the memory back,
  // and coming back at full brightness in a dark room is the whole of what
  // this setting exists to prevent.
  assert.equal(page.probe().dim, 0.45);
});

test("a level that makes no sense is not applied", async (t) => {
  for (const junk of ["", "dark", "-1", "0.9", "null"]) {
    const page = await boot(t, { stored: { "somnia-dim": junk } });
    // Above 0.6 the page stops being readable at all, and there is nothing on
    // screen yet to turn it back down with — a half-written record must not be
    // able to black the page out.
    assert.equal(page.probe().dim, 0.12, `stored ${JSON.stringify(junk)}`);
  }
});

test("a level of nothing at all is a page with no dim on it", async (t) => {
  // 0 is a level somebody can mean, and it has to survive the fallback that
  // catches an unset key — `Number(null)` is 0, which is the trap.
  const page = await boot(t, { stored: { "somnia-dim": "0" } });
  assert.equal(page.probe().dim, 0);
});

// ------------------------------------------------------ and the two presses
//
// `how dark the room` on Settings, and what made a settings screen safe to set
// this from is that the screen is a night one: the layer is over it, so it is
// still set by looking at what it is doing rather than by picturing a number.

test("a press dims the page and writes the level down", async (t) => {
  const page = await boot(t);
  page.click("dim-up");
  assert.equal(page.probe().dim, 0.18);
  assert.equal(page.storage.getItem("somnia-dim"), "0.18");
  page.click("dim-down");
  page.click("dim-down");
  assert.equal(page.probe().dim, 0.06);
  assert.equal(page.storage.getItem("somnia-dim"), "0.06");
});

// Ten presses of `+` may not black the page out, because the control that would
// undo it is underneath the layer that just went up.
test("the dark has a floor that no number of presses gets under", async (t) => {
  const page = await boot(t);
  for (let i = 0; i < 20; i += 1) page.click("dim-up");
  assert.equal(page.probe().dim, 0.6);
  assert.equal(page.el("dim-up").disabled, true);
  for (let i = 0; i < 20; i += 1) page.click("dim-down");
  assert.equal(page.probe().dim, 0);
  assert.equal(page.el("dim-down").disabled, true);
  // And the readout says where it is, rather than a number nobody can picture.
  assert.equal(page.el("dim-fill").style.width, "0%");
});

// 0.06 in binary floating point walks to 0.18000000000000002 in three presses,
// and that is what would land in storage and come back on the next launch. The
// page would be the right darkness and the record of it would be a number
// nobody chose.
test("what is written down is a level somebody could have meant", async (t) => {
  const page = await boot(t);
  for (let i = 0; i < 3; i += 1) page.click("dim-up");
  assert.equal(page.storage.getItem("somnia-dim"), "0.3");
});

// What is on disk is what somebody chose. Opening the page does not round it to
// this version's step and write it back.
test("opening the page does not edit the level it found", async (t) => {
  const page = await boot(t, { stored: { "somnia-dim": "0.45" } });
  assert.equal(page.probe().dim, 0.45);
  assert.equal(page.storage.getItem("somnia-dim"), "0.45");
});

// ----------------------------------------------------------- how big it is
//
// `how big the words` on Settings, which is the whole page and not the screen
// it is on: it sets the root, and every size and every gap in the sheet is a
// rem measured off that.
//
// It exists because the setting it stands in for does not arrive. Android's
// font size reaches a native app through `sp`; a web page gets it only if
// Chrome hands a multiplier to its text autosizer, and on the phone this app is
// read on nothing is handed over — measured on the device, unpinned, with a
// bare paragraph that did not move. All of this is the page answering for
// itself instead.

test("the page opens at the size the design was drawn at", async (t) => {
  const page = await boot(t);
  // 1, and the sheet does the rest: it divides the screen by 18 because the
  // design is 360 CSS px across at a 20px root. A page nobody has set is the
  // page as drawn, on whatever phone is holding it.
  assert.equal(page.probe().text, "1");
  // The readout says where that sits in the range, which is the middle: the
  // page has to be able to go both ways from what was drawn.
  assert.equal(page.el("text-fill").style.width, "50%");
});

test("a size written down before is the one the page opens at", async (t) => {
  const page = await boot(t, { stored: { "somnia-text": "1.2" } });
  // The same reason the dim level outlives the page: a backgrounded tab is
  // thrown away whenever the phone wants the memory back, and coming back at a
  // size he cannot read is the whole of what this setting exists to prevent.
  assert.equal(page.probe().text, "1.2");
});

test("a size that makes no sense is not applied", async (t) => {
  for (const junk of ["", "big", "-1", "0", "4", "null"]) {
    const page = await boot(t, { stored: { "somnia-text": junk } });
    // A half-written record must not be able to leave the page at a size with
    // no words on it, or at one no thumb can find the way back from.
    assert.equal(page.probe().text, "1", `stored ${JSON.stringify(junk)}`);
  }
});

test("a press resizes the page and writes the size down", async (t) => {
  const page = await boot(t);
  page.click("text-up");
  assert.equal(page.probe().text, "1.1");
  assert.equal(page.storage.getItem("somnia-text"), "1.1");
  page.click("text-down");
  page.click("text-down");
  assert.equal(page.probe().text, "0.9");
  assert.equal(page.storage.getItem("somnia-text"), "0.9");
});

// Both ends are measured, not chosen. 1.2 puts the page at 15rem across, the
// last width the player holds; a step past that is 13.8rem, where the book's
// title truncates to one line and the chapter title clips through its own
// descenders — and neither of those is a scroll, so neither would have been
// caught by the thing that usually catches a layout going wrong.
test("the size has both ends, and no number of presses gets past them", async (t) => {
  const page = await boot(t);
  for (let i = 0; i < 20; i += 1) page.click("text-up");
  assert.equal(page.probe().text, "1.2");
  assert.equal(page.el("text-up").disabled, true);
  assert.equal(page.el("text-fill").style.width, "100%");
  for (let i = 0; i < 20; i += 1) page.click("text-down");
  assert.equal(page.probe().text, "0.8");
  assert.equal(page.el("text-down").disabled, true);
  assert.equal(page.el("text-fill").style.width, "0%");
});

// 0.1 in binary floating point has the same habit 0.06 does. Stepping along the
// list rather than doing arithmetic on the value is what keeps a multiplier of
// 1.2000000000000002 out of storage and off the page.
test("what is written down is a size somebody could have meant", async (t) => {
  const page = await boot(t);
  for (let i = 0; i < 2; i += 1) page.click("text-up");
  assert.equal(page.storage.getItem("somnia-text"), "1.2");
  assert.equal(page.probe().text, "1.2");
});

// What is on disk is what somebody chose. Opening the page does not round it to
// this version's steps and write it back — the rule the dim level keeps.
test("opening the page does not edit the size it found", async (t) => {
  const page = await boot(t, { stored: { "somnia-text": "1.05" } });
  assert.equal(page.probe().text, "1.05");
  assert.equal(page.storage.getItem("somnia-text"), "1.05");
  // It still draws a readout, and a press still moves to the nearer of the two
  // sizes it sits between rather than to an end of the range.
  assert.equal(page.el("text-fill").style.width, "50%");
  page.click("text-up");
  assert.equal(page.probe().text, "1.1");
});

// ------------------------------------------------------- how far a skip is
//
// `how far the skip buttons move` on Settings, which renames the two
// most-pressed buttons in the app — so what they say and what they do are one
// setting and not two.

// What the three options say about themselves, which is the half of "which one
// is chosen" that is not a colour. Read as a whole rather than one at a time:
// what a screen reader has to be able to answer is which of the three, and that
// is a property of the group.
function pressed(page) {
  return Object.fromEntries(
    [15, 30, 60].map((s) => [s, page.el(`jump-${s}`).attributes["aria-pressed"]]),
  );
}

test("the transport says thirty until somebody says otherwise", async (t) => {
  const page = await boot(t);
  assert.equal(page.el("back30").textContent, "−30");
  assert.equal(page.el("fwd30").textContent, "+30");
  assert.equal(page.el("jump-30").classList.contains("chosen"), true);
  assert.equal(page.el("jump-15").classList.contains("chosen"), false);
  // And it says so in the accessibility tree as well as in amber. The class is
  // paint: without this, three identically labelled buttons on the one screen
  // whose job is to report a setting back, and nothing to say which is already
  // true.
  assert.deepEqual(pressed(page), { 15: "false", 30: "true", 60: "false" });
});

test("choosing a skip size renames the buttons and moves the book by it", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid });
  page.audio.ready(1800);
  page.click("playpause");
  await page.settle();
  const at = page.audio.currentTime;

  page.click("jump-15");
  assert.equal(page.el("back30").textContent, "−15");
  assert.equal(page.el("fwd30").textContent, "+15");
  assert.equal(page.el("back30").attributes["aria-label"], "Back 15 seconds");
  assert.equal(page.el("jump-15").classList.contains("chosen"), true);
  assert.equal(page.el("jump-30").classList.contains("chosen"), false);
  assert.deepEqual(pressed(page), { 15: "true", 30: "false", 60: "false" });
  assert.equal(page.storage.getItem("somnia-jump"), "15");

  // And the press moves the book by what the label says. A setting that renamed
  // the button and left it skipping thirty would be the worst of both.
  page.click("fwd30");
  await page.settle();
  assert.equal(Math.round(page.audio.currentTime - at), 15);
});

test("a skip size written down before is the one the page opens at", async (t) => {
  const page = await boot(t, { stored: { "somnia-jump": "60" } });
  assert.equal(page.el("back30").textContent, "−60");
  assert.equal(page.el("jump-60").classList.contains("chosen"), true);
});

// Only one of the three, and nothing else. A stored 45 would draw a transport
// whose labels no control on the page could change back.
test("a skip size that is not on offer is not adopted", async (t) => {
  for (const junk of ["", "45", "0", "-30", "thirty"]) {
    const page = await boot(t, { stored: { "somnia-jump": junk } });
    assert.equal(
      page.el("back30").textContent,
      "−30",
      `stored ${JSON.stringify(junk)}`,
    );
  }
});

// ------------------------------------------------- the screen they are set on
//
// Both of the settings above used to be lodgers. Dim was on Books, on the
// argument that it can only be judged against the dark page it changes — true,
// and no more true of Books than of any other night screen. Skip size was in
// Workshop, on the argument that a thing set once is configuration — which is
// wrong about when it is discovered, because nobody decides thirty seconds is
// too far except in the dark, mid-book, having missed the same sentence twice.
//
// So they share a screen now, reached from the corner of the player that has
// been empty since `start over` went to chat. What is asserted here is the two
// things that can go wrong with an overlay: that it is not up until somebody
// opens it, and that opening it and closing it again changed nothing.

test("the settings screen is not up until somebody opens it", async (t) => {
  const page = await boot(t);
  assert.equal(page.probe().settingsUp, false);
  page.click("to-settings");
  assert.equal(page.probe().settingsUp, true);
  page.click("settings-close");
  assert.equal(page.probe().settingsUp, false);
});

// The inert open. Nothing here asks the server anything, nothing here moves the
// book, and the way out is `‹ controls` in the same corner as every other way
// out on the page — so the whole screen is a promise that the night it was
// opened in is exactly the night it is closed into.
test("settings changes nothing else about the page", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid });
  page.audio.ready(1800);
  page.click("playpause");
  await page.settle();
  const before = page.probe();

  page.click("to-settings");
  await page.settle();
  page.click("settings-close");
  await page.settle();
  assert.deepEqual(page.probe(), before);
});

// The one line on the screen that is not a control. It answers "am I looking at
// the deploy I just made?", which is a question with no other route to it from a
// phone — the number otherwise lives on the box, behind an ssh.
test("the box's version is on the screen, and was asked for once at load", async (t) => {
  const page = await boot(t);

  // Before anybody has opened anything: the caption is written on the way in,
  // so that Settings can go on fetching nothing at all when it is opened.
  assert.equal(page.el("settings-version").textContent, "0.8.dev76+g778d26abf");
  assert.deepEqual(page.versionAsks, ["api/version"]);

  page.click("to-settings");
  await page.settle();
  page.click("settings-close");
  await page.settle();

  // Opening the screen asked nothing. A version is not a thing that changes
  // while somebody is looking at it, and this screen's whole promise is that
  // the night it was opened in is the night it is closed into.
  assert.deepEqual(page.versionAsks, ["api/version"]);
});

// The commit is the point, not decoration. A box is expected to be ahead of the
// tags — somnia-install.sh defaults to main and not the last release — so the
// one form of this string that could not answer the question is a bare release
// number two deploys share.
test("the version carries the commit that tells two deploys apart", async (t) => {
  const page = await boot(t, { version: "0.8.dev77+gdeadbee12" });
  assert.equal(page.el("settings-version").textContent, "0.8.dev77+gdeadbee12");
});

// Offline is the state this caption is most likely to be read in and least able
// to answer from: /api/ is the one thing the service worker does not serve out
// of its cache, so there is no last-known number to fall back to. Saying so is
// the whole of the honest answer, and a remembered one would be the lie told on
// exactly the night the question is being asked.
test("a box that cannot be reached leaves the version saying unknown", async (t) => {
  const page = await boot(t, { gone: { version: true } });
  assert.equal(page.el("settings-version").textContent, "unknown");
});

// And the markup itself, because the two tests above are true of the harness
// and this is what makes them true of the page. `unknown` is the page's answer
// for a box it could not reach, so it has to ship in the document: a caption
// written only by the script is a blank line on exactly the run where the
// script's one job failed.
test("the version caption ships with its own answer in it", async () => {
  const markup = readFileSync(
    fileURLToPath(new URL("../../src/somnia/web/index.html", import.meta.url)),
    "utf8",
  );
  const caption = markup.replace(/<!--[\s\S]*?-->/g, "").match(
    /<p class="setting-note" id="settings-version">([^<]*)<\/p>/,
  );
  assert.ok(caption, "no version caption in the settings markup");
  assert.equal(caption[1].trim(), "unknown");
});

// The one thing that had to be true for a settings screen to be allowed to hold
// the dim control at all: this is a night screen, so the layer is over it. A
// press moves the darkness of the page doing the pressing, which is the whole
// of why the level is chosen by looking rather than by reading a number — and
// it is the one thing Workshop, where the layer goes to zero, could not offer.
test("the room stays dark while the darkness is being set", async (t) => {
  const page = await boot(t, { stored: { "somnia-dim": "0.3" } });
  page.click("to-settings");
  assert.equal(page.probe().dim, 0.3);
  page.click("dim-up");
  assert.equal(page.probe().dim, 0.36);
  page.click("settings-close");
  // And it is the setting that moved, not a layer lifted for one screen.
  assert.equal(page.probe().dim, 0.36);
  assert.equal(page.storage.getItem("somnia-dim"), "0.36");
});

// A book the platform refused to start is waiting for a touch anywhere, and
// every control on this screen is a touch. The screen borrows that listener on
// the way in so the first press on `+` darkens the room without also starting
// the book, and hands it back on the way out, where it is true again.
test("a press on settings does not start a book that is waiting for a touch", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid });
  page.audio.ready(1800);
  page.audio.refuse = "NotAllowedError";
  page.click("playpause");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");

  // The screen is open and the listener has been borrowed, so a touch on it is
  // a touch on a control and nothing else.
  page.click("to-settings");
  page.audio.refuse = null;
  page.document.fire("pointerdown");
  await page.settle();
  assert.equal(page.audio.paused, true);

  // And the way out hands it back, because by then it is true again: the book
  // is still stopped and still waiting for the touch it was promised.
  page.click("settings-close");
  page.document.fire("pointerdown");
  await page.settle();
  assert.equal(page.audio.paused, false);
});

// The instruction and the thing it describes, which used to be able to
// disagree. The sentence was written where the listener was armed and taken
// down nowhere at all, so a tap started the book and left "tap anywhere to
// carry on" standing over it — on the one line that holds sentences which do
// not clear themselves, so it stayed for the rest of the night.
test("the instruction to tap goes when the tap happens", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid });
  page.audio.ready(1800);
  page.audio.refuse = "NotAllowedError";
  page.click("playpause");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");

  page.audio.refuse = null;
  page.document.fire("pointerdown");
  await page.settle();

  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().status, "");
});

// And the other way out of it: something took the listener away, so the
// instruction is no longer true either.
test("the instruction to tap goes when the listener is taken away", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid });
  page.audio.ready(1800);
  page.audio.refuse = "NotAllowedError";
  page.click("playpause");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");

  page.click("to-settings");
  await page.settle();
  assert.equal(page.probe().status, "");

  // Handed back on the way out, sentence and all, because by then it is true
  // again — which is the invariant the two halves have to keep together.
  page.click("settings-close");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");
});
