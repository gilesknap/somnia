// Getting the book back when it stops arriving.
//
// Wifi power save, a DHCP renewal and a tailscale re-key each take the tailnet
// away for a few seconds in the middle of the night, and the page answers all
// three with one ladder: a few seconds of grace for a buffer that might refill
// by itself, then a reload, then a longer wait and another reload, doubling to
// half a minute. None of it had a test until this file. Neither `waiting` nor
// `stalled` was fired anywhere in the suite, and "still trying to reach the
// book" — one of the two sentences reported off the handset in issue #31 —
// appeared in no assertion at all. That is how the failure came back as a night
// that went quiet rather than as a red test here.
//
// The first section is a record of what this design costs, not a statement of
// what it ought to do. Every rung of the ladder puts the chapter's URL back on
// the element, and assigning src runs the load algorithm, which empties it —
// so every attempt to get the book back first throws away the notification
// that is the only thing on a locked screen saying anything about the book at
// all. Whether it comes back is up to a network that has just proved it cannot
// be relied on. When a chapter boundary stops being a load, these tests are to
// be rewritten to say a boundary makes no attempt at all; they are not to be
// deleted, because a real error will still take this path.

import assert from "node:assert/strict";
import { test } from "node:test";

import { boot } from "./harness.mjs";

// The rungs, as app.js sizes them: RETRY_MIN_MS, doubling, capped at
// RETRY_MAX_MS, with STALL_GRACE_MS as the floor once a stall has been waited
// out. Written here as plain numbers on purpose — the page is a script and
// exports nothing, so a test that read them from the source could not tell a
// backoff that changed from a backoff that was never there.
const GRACE_MS = 8000;
const FIRST_MS = 2000;
const LONGEST_MS = 30_000;

// Sound coming out of chapter one, which is where the network has something to
// take away.
async function playing(t, options) {
  const page = await boot(t, options);
  page.audio.ready();
  page.click("playpause");
  return page;
}

// ------------------------------------------------------ what a retry costs

test("a retry is the whole chapter loaded again", async (t) => {
  const page = await playing(t);
  page.audio.fail();
  assert.deepEqual(page.waits(), [FIRST_MS]);
  page.order.length = 0;
  assert.equal(page.wake(FIRST_MS), true);
  // The same four steps, in the same order, as the chapter boundary in
  // playing.test.mjs — and they mean the same thing to the platform, which is
  // that the element was emptied and whatever was hanging on it went with it.
  // The difference is only in the odds: a boundary does this when the next
  // file is there to be had, and this does it because it is not.
  assert.deepEqual(page.order, [
    "metadata:The First Tone",
    "src:api/audio/900001/0",
    "play",
    "state:playing",
  ]);
  assert.equal(page.audio.srcWrites.length, 2);
  assert.equal(page.probe().status, "still trying to reach the book");
});

test("every rung of the ladder is another chapter loaded again", async (t) => {
  const page = await playing(t);
  const rungs = [];
  for (let attempt = 0; attempt < 6; attempt++) {
    page.audio.fail();
    const [next] = page.waits();
    rungs.push(next);
    page.wake(next);
  }
  // The backoff bounds how often this happens and not whether it happens. Half
  // a minute is as patient as it ever gets, so an outage that lasts an hour is
  // something like a hundred and twenty of these, each one an element emptied
  // and a notification asked to come back — beside somebody asleep, with no
  // screen on to say what is going on.
  assert.deepEqual(rungs, [
    FIRST_MS,
    4000,
    GRACE_MS,
    16_000,
    LONGEST_MS,
    LONGEST_MS,
  ]);
  assert.equal(page.audio.srcWrites.length, 1 + rungs.length);
});

test("a retry puts them back where they had got to", async (t) => {
  const page = await playing(t, { lastGid: 900004 });
  page.audio.ready(1800);
  page.seek(600_000, { play: true });
  page.audio.fire("seeked");
  page.audio.fail();
  page.wake(FIRST_MS);
  page.audio.ready(1800);
  // Reloading is the whole of the way back, and reloading from the top of the
  // file would answer five seconds of lost tailnet by making them hear the
  // last ten minutes again. The offset survives the reload and is applied when
  // there is a duration to clamp it against.
  assert.equal(page.audio.currentTime, 600);
  assert.equal(page.probe().positionMs, 600_000);
});

// ------------------------------------------------------------- the grace

test("a buffer that has run dry is given a few seconds and no words", async (t) => {
  const page = await playing(t);
  page.audio.fire("waiting");
  assert.deepEqual(page.waits(), [GRACE_MS]);
  // Most of these refill on their own and nobody hears more than a gap.
  // Announcing every ordinary rebuffer would put a line on the screen — and in
  // a screen reader's ear, through the live region — for something that is
  // already over by the time it is read.
  assert.equal(page.probe().status, "");
  assert.equal(page.audio.srcWrites.length, 1);
});

test("both names the browser has for a dry buffer open the same door", async (t) => {
  const page = await playing(t);
  page.audio.fire("stalled");
  // `waiting` is the playhead having nothing to play and `stalled` is the
  // download having gone quiet. Which of them a phone fires is the phone's
  // business, so the page must not have learnt only one of them.
  assert.deepEqual(page.waits(), [GRACE_MS]);
});

test("a stall that refills by itself reloads nothing", async (t) => {
  const page = await playing(t);
  page.audio.fire("waiting");
  page.audio.fire("playing");
  // The sound really coming out is the only proof worth having, and it is the
  // proof that costs nothing: the grace is dropped, the element is untouched,
  // and the notification never knew anything had happened.
  assert.deepEqual(page.waits(), []);
  assert.equal(page.audio.srcWrites.length, 1);
  assert.equal(page.probe().status, "");
});

test("a stall that never refills starts the ladder no lower than the grace", async (t) => {
  const page = await playing(t);
  page.audio.fire("waiting");
  assert.equal(page.wake(GRACE_MS), true);
  assert.equal(page.audio.srcWrites.length, 2);
  assert.equal(page.probe().status, "still trying to reach the book");
  // Not two seconds. A server that takes the connection and never answers — a
  // proxy black hole, a re-key caught mid-handshake — fires no error at all,
  // so nothing else would ever grow this wait, and the ladder would sit on its
  // bottom rung asking every two seconds until the battery went. It can only
  // be more patient than the stall it waited out, never less.
  assert.deepEqual(page.waits(), [GRACE_MS]);
});

test("a reload that stalls again goes straight onto the ladder", async (t) => {
  const page = await playing(t);
  page.audio.fail();
  page.wake(FIRST_MS);
  assert.deepEqual(page.waits(), []);
  page.audio.fire("waiting");
  // Four seconds, which is the next rung, and not eight seconds of grace
  // ahead of it. There is nothing left of "this will probably refill" once the
  // page is already fighting for the chapter, and a page that gave the grace
  // again every time would interleave the two forever: grace, wait, grace,
  // wait, a request every nineteen seconds however long the night's outage.
  assert.deepEqual(page.waits(), [4000]);
});

test("a stall and the failure that follows it are one chain and not two", async (t) => {
  const page = await playing(t);
  page.audio.fire("waiting");
  assert.deepEqual(page.waits(), [GRACE_MS]);
  page.audio.fail();
  // `waiting` fires just before the error that follows it, so both chains are
  // live for a moment. Exactly one wake may survive that: two of them reload
  // the same chapter twice over, and the effective backoff becomes whichever
  // of the pair is shorter.
  assert.deepEqual(page.waits(), [FIRST_MS]);
});

// ----------------------------------------------------------- the way back

test("the sound coming out puts the ladder back on its bottom rung", async (t) => {
  const page = await playing(t);
  page.audio.fail();
  page.wake(FIRST_MS);
  page.audio.fire("playing");
  assert.equal(page.probe().status, "");
  assert.deepEqual(page.waits(), []);
  page.audio.fail();
  // Two seconds again. A book that came back and then lost the tailnet an hour
  // later is a fresh outage, and starting it half a minute up the ladder would
  // charge it for one that is long over.
  assert.deepEqual(page.waits(), [FIRST_MS]);
});

test("the network coming back does not wait out the rest of the backoff", async (t) => {
  const page = await playing(t);
  page.audio.fail();
  page.wake(FIRST_MS);
  page.audio.fail();
  assert.deepEqual(page.waits(), [4000]);
  page.window.fire("online");
  // The wait was only ever a guess about a network nobody can see, and being
  // wrong about it in this direction costs one request. The rung is given back
  // as well as the wake, or the next failure would resume a ladder that had
  // been climbed for an outage that is over.
  assert.equal(page.audio.srcWrites.length, 3);
  assert.deepEqual(page.waits(), []);
  page.audio.fail();
  assert.deepEqual(page.waits(), [FIRST_MS]);
});

test("the network coming back to a book that never went is not a reload", async (t) => {
  const page = await playing(t);
  page.window.fire("online");
  // `online` says the wifi is up, which is not the same thing as the tailnet
  // being up and is no reason at all to touch an element that is playing.
  assert.equal(page.audio.srcWrites.length, 1);
  assert.deepEqual(page.waits(), []);
});

test("coming back to the page tries again without waiting", async (t) => {
  const page = await playing(t);
  page.audio.fail();
  page.document.visibilityState = "visible";
  page.document.fire("visibilitychange");
  // The phone may have been in a pocket for hours, and a page frozen there
  // cannot have been running its own timers. Somebody looking at the screen is
  // the one moment worth spending a request on.
  assert.equal(page.audio.srcWrites.length, 2);
  assert.deepEqual(page.waits(), []);
});

// ------------------------------------------------ when it is them who stopped

test("a book put down while it is stalling stops trying", async (t) => {
  const page = await playing(t);
  page.audio.fire("waiting");
  assert.deepEqual(page.waits(), [GRACE_MS]);
  page.click("playpause");
  // A page that reloaded chapters under a book somebody had put down would be
  // spending the battery on nobody, and would put a sentence about the network
  // on a screen nobody asked to see one on.
  assert.deepEqual(page.waits(), []);
  assert.equal(page.probe().status, "");
  assert.equal(page.probe().wantsSound, false);
});

test("a stall in a book nobody is listening to is not fought", async (t) => {
  const page = await playing(t);
  page.click("playpause");
  page.audio.fire("waiting");
  page.audio.fire("stalled");
  // A paused element can still say its buffer ran dry — the phone is entitled
  // to throw the buffer away the moment the sound stops. Nothing here is worth
  // eight seconds of grace, let alone the reload at the end of it.
  assert.deepEqual(page.waits(), []);
  assert.equal(page.audio.srcWrites.length, 1);
});
