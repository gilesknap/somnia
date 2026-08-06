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
import { test } from "node:test";

import { boot } from "./harness.mjs";

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
  assert.equal(page.probe().sleep, "chapter end");
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

  page.wake(TOAST_MS);
  assert.equal(page.probe().toast, "");
  // Byte for byte. The toast came and went and the line that matters did not
  // move — which is the whole reason there are two of them.
  assert.equal(page.probe().status, standing);

  // And the press the instruction was asking for still lands. The layer is
  // over everything on the page, the toast is under it, and neither is allowed
  // to be the thing a thumb hits instead of the book. For 2.8 seconds the
  // sentence lies across the box and part of the microphone, so nothing is
  // hung on it either — `pointer-events: none` in the sheet is the other half,
  // and that half is a render's to check.
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
