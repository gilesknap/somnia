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
// what it ought to do. Every rung of the ladder puts a URL back on the element,
// and assigning src runs the load algorithm, which empties it — so every
// attempt to get the book back first throws away the notification that is the
// only thing on a locked screen saying anything about the book at all. Whether
// it comes back is up to a network that has just proved it cannot be relied on.
//
// Two things have changed about that, and between them they are the whole of
// what this file now enforces.
//
// What brings the page here. When these were written a chapter boundary was a
// load, so the same four steps ran at every boundary all night — around a
// hundred and fifteen of them on a nine-hour book — and the odds were the only
// difference between an ordinary boundary and a network failure. The book
// arrives down one URL now and a boundary asks the network for nothing at all,
// which is asserted below rather than left to the player's own suite: a
// boundary that started making requests again would put the storm back exactly
// where it was.
//
// And where the ladder ends. It used to climb to half a minute and stay
// there until morning, which is right for a network that went and wrong for
// a URL that is never going to answer — and that second one is a night that
// never comes back, which is the half of issue 31 the blink was not. So a
// join that has never once been loaded is asked for twice and then given up
// on: the book drops to the file-at-a-time path the manifest has always
// carried, and blinks at every boundary for the rest of the night. That is a
// worse night. It is not a lost one, and those were the only two on offer.
//
// The distinction the fallback rests on is the difficult part, and the last
// section is about nothing else: a join that has once handed the page a
// duration is a file that exists, so its later failures are the wire and are
// waited out however many of them there are, while a join that has never
// answered has nothing to wait for.

import assert from "node:assert/strict";
import { test } from "node:test";

import { boot, growingBook, GROWING_BOOK, OTHER_BOOK } from "./harness.mjs";

// The rungs, as app.js sizes them: RETRY_MIN_MS, doubling, capped at
// RETRY_MAX_MS, with STALL_GRACE_MS as the floor once a stall has been waited
// out. Written here as plain numbers on purpose — the page is a script and
// exports nothing, so a test that read them from the source could not tell a
// backoff that changed from a backoff that was never there.
const GRACE_MS = 8000;
const FIRST_MS = 2000;
const LONGEST_MS = 30_000;

// The whole book's join, which is the only URL any of these tests is about
// until the last section.
const JOIN = "api/stream/900001/3";

// Sound coming out of chapter one, which is where the network has something to
// take away. `ready()` is not a detail: it is the element handing the page a
// duration, which is the page's only proof that the join really exists, and
// everything in the first three sections rests on that proof having been given.
async function playing(t, options) {
  const page = await boot(t, options);
  page.audio.ready();
  page.click("playpause");
  return page;
}

// The same book, wanted just as much, with nothing ever answering for it. The
// element is never told a duration, so the page has been given no evidence that
// the URL in the manifest is a file on the box — which is the whole difference
// between this and `playing` above.
async function askingForNothing(t, options) {
  const page = await boot(t, options);
  page.click("playpause");
  return page;
}

// ------------------------------------------------------ what a retry costs

test("a boundary asks for nothing, so there is nothing to retry", async (t) => {
  const page = await playing(t);
  page.audio.currentTime = 7.9;
  page.audio.fire("timeupdate");
  page.audio.advance(0.25);
  // The first sample the far side of the boundary between chapters one and two.
  // Nothing was fetched, so nothing failed, so nothing below this line has
  // anything to do — no grace, no wait, no sentence on the screen. This is the
  // ladder's frequency stated as an assertion: the storm at 2am was a hundred
  // and fifteen loads a night meeting a network that dropped some of them, and
  // taking the loads away took the storm with them.
  assert.deepEqual(page.waits(), []);
  assert.equal(page.audio.srcWrites.length, 1);
  assert.equal(page.probe().status, "");
  assert.equal(page.probe().idx, 1);
});

test("a retry is the whole book loaded again", async (t) => {
  const page = await playing(t);
  page.audio.fail();
  assert.deepEqual(page.waits(), [FIRST_MS]);
  page.order.length = 0;
  assert.equal(page.wake(FIRST_MS), true);
  // Four steps, and to the platform they mean the element was emptied and
  // whatever was hanging on it went with it. A chapter boundary used to do
  // exactly this — the same four, in the same order — a hundred and fifteen
  // times a night; it does none of it now. This is what is left, and it is the
  // case the ladder was written for: the book stopped arriving.
  //
  // It costs more than it did. What comes back down the wire is the whole
  // book's header before a single frame decodes, and then a range request back
  // to where they were. That is the price of a boundary costing nothing.
  assert.deepEqual(page.order, [
    "metadata:The First Tone",
    "src:api/stream/900001/3",
    "play",
    "state:playing",
  ]);
  assert.equal(page.audio.srcWrites.length, 2);
  assert.equal(page.probe().status, "still trying to reach the book");
});

test("every rung of the ladder is the whole book loaded again", async (t) => {
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
  // And it goes on asking for the same URL, six failures in, because that URL
  // has already played: the page has held a duration off it, which a 404 does
  // not hand out. Whatever this is, it is the wire, and there is nothing to
  // fall back to that the wire would not eat as well. Giving up here would
  // spend the rest of the night blinking to fix a network problem.
  assert.equal(page.probe().fellBack, false);
  assert.equal(
    page.audio.srcWrites.every((url) => url === JOIN),
    true,
  );
});

test("a retry puts them back where they had got to", async (t) => {
  const page = await playing(t, { lastGid: 900004 });
  // Ten minutes into the second half-hour chapter, so that where they are in
  // the chapter and where they are in the book are different numbers — the
  // element holds the book, and landing at the chapter's offset would put them
  // twenty minutes short of where the tailnet left them.
  page.seek(2_400_000, { play: true });
  page.audio.arrived();
  page.audio.fail();
  page.wake(FIRST_MS);
  page.audio.ready();
  // Reloading is the whole of the way back, and reloading from the top would
  // answer five seconds of lost tailnet by making them hear the last forty
  // minutes again. The offset survives the reload and is applied when there is
  // a duration to clamp it against.
  assert.equal(page.audio.currentTime, 2400);
  assert.equal(page.probe().positionMs, 2_400_000);
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

// ------------------------------------------- when the join is not coming back

test("a join that never answers is given up on after two tries", async (t) => {
  const page = await askingForNothing(t);
  page.audio.fail();
  // Once is not an answer. A re-key catches the first request of the night now
  // and then, and a page that fell back on one failure would blink through a
  // night that only ever needed two seconds of patience.
  assert.equal(page.probe().fellBack, false);
  assert.equal(page.wake(FIRST_MS), true);
  assert.equal(page.audio.srcWrites.at(-1), JOIN);

  page.audio.fail();
  // Twice, on a URL that has never once handed this page a duration. Whatever
  // is at the other end of it, it is not a file: a build ffmpeg gave up on, a
  // version reaped out from under a manifest, a deploy that moved the data
  // directory. None of those gets better by being asked again at half-minute
  // intervals until morning, which is what the ladder alone would have done.
  assert.equal(page.probe().fellBack, true);
  // And the next attempt is at the bottom of the ladder rather than four
  // seconds up it. The wait was earned by a question nobody is asking now.
  assert.deepEqual(page.waits(), [FIRST_MS]);
  assert.equal(page.wake(FIRST_MS), true);
  assert.equal(page.audio.srcWrites.at(-1), "api/audio/900001/0");
});

test("a book given up on plays a file at a time, boundaries and all", async (t) => {
  const page = await askingForNothing(t);
  page.audio.fail();
  page.wake(FIRST_MS);
  page.audio.fail();
  page.wake(FIRST_MS);
  page.audio.ready();
  // The fallback is real, and this is what "real" has to mean: the chapter
  // arrives, the sound comes back, and the sentence about the network comes off
  // the screen. Nothing is said about which URL it came down — the listener
  // cannot act on that, and at 2am a sentence they can do nothing about is
  // worse than none.
  assert.equal(page.probe().perChapter, true);
  assert.equal(page.probe().status, "");
  assert.equal(page.audio.paused, false);

  page.order.length = 0;
  page.audio.advance(8);
  await page.settle();
  // And the boundary is a load again, which is the cost being paid in full:
  // the element is emptied, the notification is asked to come back, and over
  // Bluetooth that is the blink this whole branch was written to remove. It
  // still beats a book that never comes back at all.
  assert.deepEqual(page.order, [
    "metadata:The Second Tone",
    "src:api/audio/900001/1",
    "play",
    "state:playing",
  ]);
  assert.equal(page.probe().chapter, "The Second Tone");
});

test("a join that is only slow is never given up on", async (t) => {
  const page = await askingForNothing(t);
  // Nothing has been proved about this URL either — but nothing has been
  // disproved. A stall is a buffer that has not filled yet, and the page's
  // whole opinion about those is that most of them fill by themselves; a book
  // on the far side of a wifi power-save nap looks exactly like this, and is
  // fine.
  page.audio.fire("waiting");
  assert.equal(page.wake(GRACE_MS), true);
  assert.equal(page.wake(GRACE_MS), true);
  assert.equal(page.probe().fellBack, false);
  assert.equal(
    page.audio.srcWrites.every((url) => url === JOIN),
    true,
  );
  // And the ladder has climbed while it waited, which is the right shape for a
  // network nobody can see: the next dry buffer waits sixteen seconds rather
  // than eight. Only an error ever says a URL is not there, and no error has
  // been fired here — a slow join and a missing one are not the same thing and
  // the page must never learn to confuse them.
  page.audio.fire("waiting");
  assert.deepEqual(page.waits(), [16_000]);
  assert.equal(page.probe().fellBack, false);
});

test("giving up on one book's join is not giving up on another's", async (t) => {
  const page = await askingForNothing(t);
  page.audio.fail();
  page.wake(FIRST_MS);
  page.audio.fail();
  assert.equal(page.probe().fellBack, true);

  await page.openBook(OTHER_BOOK.gid);
  // A concatenation that could not be made is a fact about the book it was made
  // from. Carried across, one book whose build failed at nine in the evening
  // would have every book opened after it blinking at every boundary — the
  // blink outliving its reason by the whole night.
  assert.equal(page.probe().fellBack, false);
  assert.equal(page.audio.srcWrites.at(-1), "api/stream/900002/2");
  assert.equal(page.probe().perChapter, false);
});

test("a longer join that is not there drops the book to a file at a time", async (t) => {
  // The Moonstone, five chapters read out of thirty-seven, listened to as it is
  // written. The join it was opened on is real and has played for half an hour;
  // the longer one the page reaches for at the frontier is the one that is
  // missing, which is the ordinary way for this to go wrong — the build that
  // fails is the build that happens while somebody is waiting on it.
  const page = await boot(t, { lastGid: GROWING_BOOK.gid });
  page.audio.ready();
  page.click("playpause");
  page.audio.currentTime = 2400.1;
  page.audio.fire("timeupdate");
  page.audio.currentTime = 2999.3;
  page.audio.fire("timeupdate");
  page.audio.advance(0.5);
  assert.equal(page.probe().atFrontier, true);

  page.serves(growingBook(6));
  // The first ask after the audio runs out, as app.js sizes it: RENDER_ASK_MS.
  assert.equal(page.wake(5000), true);
  await page.settle();
  await page.settle();
  assert.equal(page.audio.srcWrites.at(-1), "api/stream/900008/6");

  page.audio.fail();
  assert.equal(page.wake(FIRST_MS), true);
  page.audio.fail();
  // The proof is per URL and not per book. The five-chapter join arrived and is
  // known to exist; the six-chapter one is a different file with a different
  // name, and nothing about the first says anything about the second. A page
  // that counted the proof book-wide would sit at the frontier asking for a
  // file that was never written, all night, with the panel up and no sound.
  assert.equal(page.probe().fellBack, true);
  assert.equal(page.wake(FIRST_MS), true);
  page.audio.ready();
  // Chapter five's own file, at the place the sound stopped four hundred
  // milliseconds short of the end of it, out of the audio that was always
  // there — a join was only ever a copy of those.
  assert.equal(page.audio.srcWrites.at(-1), "api/audio/900008/4");
  assert.equal(page.probe().chapter, "Chapter 5");
  assert.equal(page.audio.paused, false);
});
