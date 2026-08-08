// Listening to a book faster than it is being read.
//
// somnia renders a chapter every three and a quarter minutes and the whole
// point of that is that the book can be started before it is finished. So a
// book added at eleven is playable within minutes and spends the next few hours
// growing underneath whoever is listening to it — which means the ordinary
// night on a new book ends up at the render frontier, the place where the audio
// stops and the book does not.
//
// The frontier is where the fix for issue #31 could have been undone. The book
// comes down one URL now, and that URL is a join of the chapters that existed
// when it was built; run off the end of it and the element fires `ended`, and
// `ended` takes the player out of the platform's media session, which is the
// lock screen panel gone — not for the moment it takes to load something, but
// for the whole of the wait. That wait was measured at 3321 seconds on the
// five-chapter book. A night could cross forty boundaries without a blink and
// still go dark at the one place a listener is most likely to reach.
//
// So the sound is stopped a fraction short of the end of what has been read
// instead. A pause suspends the session rather than ending it: the panel stays
// up with a play button on it for as long as the render takes, which is what
// somebody half awake should find at 2am when the book is waiting for more of
// itself. These are the tests of that, and of the two things that have to agree
// with it — the ladder that waits for the book to grow, which used to ask
// whether the element had ended, and the manifest that grows without the
// element being reloaded under anybody.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  boot,
  growingBook,
  GROWING_BOOK,
  PART_READ,
  START_MS,
} from "./harness.mjs";

// The wait for a book to grow, as app.js sizes it: RENDER_ASK_MS, and the rung
// after it. The first ask goes out at once, from inside the timeupdate that
// found the frontier, so what a wake is ever seen at here is the second question
// the page has asked — and RENDER_ASK_MS itself is what the two tests about a
// night that ended look for the absence of.
//
// Written here as plain numbers for the reason reaching.test.mjs gives — the
// page exports nothing, so a test that read the constants from the source could
// not tell a wait that changed from a wait that was never there.
const FIRST_ASK_MS = 5000;
const NEXT_ASK_MS = 10_000;

// A sleep timer an earlier page wrote down, restored at boot: `choice` is an
// index into SLEEP_CHOICES and 1 is fifteen minutes. It is how a test gets a
// timer with seconds left on it without listening to a quarter of an hour of
// book first.
function armed(choice, leftMs, at = START_MS - 60_000) {
  return { "somnia-sleep": JSON.stringify({ choice, leftMs, at }) };
}

// The Moonstone, five chapters of ten minutes read out of thirty-seven, with
// the sound coming out where the server left them: half an hour in, which is
// the top of chapter four.
async function listening(t) {
  const page = await boot(t, { lastGid: GROWING_BOOK.gid });
  page.audio.ready();
  page.click("playpause");
  return page;
}

// Into the fifth chapter, which is the last one the join holds, and then on to
// seven hundred milliseconds before the end of it. Both samples matter: the
// boundary is crossed on the media clock like any other, and only after it is
// crossed is the chapter they are in the chapter the book runs out in.
//
// It stops short of the mark the page stops at, which is four hundred
// milliseconds before the join. Every test below takes the last step itself.
function upToTheFrontier(page) {
  page.audio.currentTime = 2400.1;
  page.audio.fire("timeupdate");
  page.audio.currentTime = 2999.3;
  page.audio.fire("timeupdate");
}

// ------------------------------------------------- inside the one source

test("a growing book crosses every boundary it holds without loading anything", async (t) => {
  const page = await listening(t);
  page.seek(0, { play: true });
  page.order.length = 0;
  // Four boundaries, ten minutes apart, each one a sample of the media clock
  // landing the far side of a number in the manifest.
  for (const at of [600, 1200, 1800, 2400]) {
    page.audio.currentTime = at + 0.1;
    page.audio.fire("timeupdate");
  }
  // A book still being read is no different from a finished one here: the join
  // it was given holds every chapter that existed when it was made, and every
  // boundary inside it is a new title on the notification and nothing else.
  assert.deepEqual(page.order, [
    "metadata:Chapter 2",
    "metadata:Chapter 3",
    "metadata:Chapter 4",
    "metadata:Chapter 5",
  ]);
  assert.equal(page.audio.srcWrites.length, 1);
  assert.equal(page.probe().streamMs, 3_000_000);
});

// ------------------------------------------------------------ the frontier

test("the sound stops a moment short of the end of what has been read", async (t) => {
  const page = await listening(t);
  upToTheFrontier(page);
  // Seven hundred milliseconds of chapter left, which is still the chapter.
  assert.equal(page.audio.paused, false);
  page.order.length = 0;
  page.audio.advance(0.25);
  assert.equal(page.audio.paused, false);
  page.audio.advance(0.25);

  // Stopped, and stopped by the page rather than by the file running out. The
  // difference is the whole of this file: the element still holds its source
  // and still has a fifth of a second of it left, so nothing has been emptied
  // and nothing has ended.
  assert.equal(page.audio.paused, true);
  assert.equal(page.audio.ended, false);
  assert.equal(page.audio.currentTime < page.audio.duration, true);
  assert.equal(page.audio.srcWrites.length, 1);
  // And the platform is told one thing: paused. A pause suspends the session
  // and leaves the panel up with a play button on it; `ended` would have taken
  // the panel down for the whole of the render wait, and over Bluetooth nothing
  // in this page can get it back.
  assert.deepEqual(page.order, ["state:paused"]);
  assert.equal(page.session.playbackState, "paused");
  assert.equal(page.session.metadata.title, "Chapter 5");
  // Waiting, and saying so where somebody who unlocks the phone can read it.
  assert.equal(page.probe().atFrontier, true);
  assert.equal(page.probe().status, "waiting for the next chapter to be read");
  // The ask that went out from inside this timeupdate found nothing, so what is
  // pending is the rung after it.
  await page.settle();
  assert.deepEqual(page.waits(), [NEXT_ASK_MS]);

  // And it stays short of the end for as long as the wait lasts. A playhead
  // that is not moving cannot reach anything, so there is no later moment at
  // which this source can run out — which is what makes the panel's survival a
  // property of the whole wait rather than of its first second.
  page.audio.advance(5);
  assert.equal(page.audio.ended, false);
  assert.equal(page.audio.currentTime, 2999.8);
});

test("the chapter that lands is carried on into from where the sound stopped", async (t) => {
  const page = await listening(t);
  upToTheFrontier(page);
  page.audio.advance(0.5);
  assert.equal(page.audio.paused, true);

  page.serves(growingBook(6));
  await page.settle();
  assert.equal(page.wake(NEXT_ASK_MS), true);
  await page.settle();
  await page.settle();

  // The one load of the night, and it is this one. The guard that decided to
  // make it asked whether the page had stopped at the frontier, not whether the
  // element had ended — the element never ends here, and a page that asked the
  // old question would have waited beside a chapter that had already arrived
  // until morning.
  assert.equal(page.audio.srcWrites.length, 2);
  assert.equal(page.audio.srcWrites.at(-1), "api/stream/900008/6");
  assert.equal(page.probe().atFrontier, false);
  assert.deepEqual(page.waits(), []);
  assert.equal(page.probe().status, "");

  page.audio.ready();
  // Back where it stopped rather than at the top of the new chapter. Those four
  // hundred milliseconds are inside the half second of silence ingest leaves at
  // the end of every chapter, so they are heard twice and nobody hears them at
  // all — where landing at the join would have cut the last words of chapter
  // five off for good.
  assert.equal(page.audio.currentTime, 2999.8);
  assert.equal(page.probe().positionMs, 2_999_800);
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().streamMs, 3_600_000);
});

test("the frontier asks at once for audio that may already be there", async (t) => {
  const page = await listening(t);
  // Three more chapters were read while they listened, and the page has no idea:
  // nothing refreshes the manifest with the screen off. visibilitychange is the
  // only thing that does, and a phone in a pocket does not fire one, so the
  // page's picture of the book is the one it booted with — which is why the
  // branch that loads a longer join at once cannot be what saves this night.
  page.serves(growingBook(8));
  upToTheFrontier(page);
  page.audio.advance(0.5);
  // Asked from inside the timeupdate that found the frontier, before the wait
  // is left to a timer. That matters more than the five seconds it saves: the
  // page has just paused, so it is no longer audible, and a backgrounded page
  // that is not making a sound has its timers throttled to roughly one wake a
  // minute. This ask is the one that certainly goes out.
  assert.deepEqual(page.waits(), []);
  await page.settle();
  await page.settle();

  assert.equal(page.audio.srcWrites.at(-1), "api/stream/900008/8");
  assert.equal(page.probe().atFrontier, false);
  assert.equal(page.probe().status, "");
  page.audio.ready();
  assert.equal(page.audio.paused, false);
  assert.equal(page.audio.currentTime, 2999.8);
});

test("a chapter file that runs out is waited for the same way", async (t) => {
  // ?chapters plays the book a file at a time, which is what a book with no
  // join gets and what the same phone can be made to do on the same night. The
  // element really does end there — a chapter file ends where its chapter does
  // — and that is the other half of why the wait asks whether the page stopped
  // at the frontier rather than whether the element ended: one flag, set on
  // both routes, and the arriving chapter is picked up either way.
  const page = await boot(t, {
    lastGid: GROWING_BOOK.gid,
    query: "?chapters",
  });
  page.audio.ready();
  page.click("playpause");
  page.seek(2_400_000, { play: true });
  page.audio.ready();
  page.audio.advance(600);
  await page.settle();
  assert.equal(page.audio.ended, true);
  assert.equal(page.probe().atFrontier, true);
  assert.equal(page.probe().status, "waiting for the next chapter to be read");

  page.serves(growingBook(6));
  await page.settle();
  // The same immediate ask as the pause route makes, from the same one flag —
  // so what is pending here is the rung after it.
  assert.equal(page.wake(NEXT_ASK_MS), true);
  await page.settle();
  await page.settle();
  assert.equal(page.audio.srcWrites.at(-1), "api/audio/900008/5");
  assert.equal(page.probe().atFrontier, false);
  assert.equal(page.probe().chapter, "Chapter 6");
});

test("a book that is not being read is not waited for at the frontier", async (t) => {
  // A render that stopped part way: one chapter of three, and nothing running
  // that is going to add the others. There is nothing to hold the panel open
  // for — the next chapter is not minutes away, it is not coming at all — so
  // the file is allowed to run out and the page says so.
  const page = await boot(t, { lastGid: PART_READ.gid });
  page.audio.ready();
  page.click("playpause");
  page.audio.advance(8);
  await page.settle();
  assert.equal(page.audio.ended, true);
  assert.equal(page.probe().atFrontier, false);
  assert.deepEqual(page.waits(), []);
  assert.equal(page.probe().status, "the rest of this book hasn't been read yet");
  // Amber, and this is the assertion the failure colour was argued out of.
  // Running out of read book is the commonest thing that happens in a night and
  // nothing is wrong when it does — the render catches up and the book carries
  // on. Painting it red would put "something is broken" on the most benign
  // event there is, and leave the colour meaning nothing by morning.
  assert.equal(page.probe().statusFailed, false);
});

test("a finished book is still allowed to end", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  page.click("playpause");
  page.seek(23_000, { play: true });
  page.audio.advance(1);
  await page.settle();
  // The end of the tone book is the end of the tone book. Nothing about the
  // frontier may reach a book that has been read to the end: a page that
  // suspended itself here would leave the last chapter unfinishable and the
  // notification offering a play button on a book with nothing left in it.
  assert.equal(page.audio.ended, true);
  assert.equal(page.probe().atFrontier, false);
  assert.equal(page.probe().status, "that is the end of the book");
  assert.equal(page.session.playbackState, "paused");
});

// --------------------------------------------- the manifest grows, quietly

test("a chapter arriving while they listen loads nothing under them", async (t) => {
  const page = await listening(t);
  // Two chapters land in the time it takes to listen to part of one, which is
  // what nuc2 does: it renders at better than real time and pulls away from
  // whoever is listening. The page finds out because it came back in front of
  // somebody, which is the one moment it asks about a book it is already
  // playing.
  page.serves(growingBook(6));
  page.document.fire("visibilitychange");
  await page.settle();
  page.serves(growingBook(7));
  page.document.fire("visibilitychange");
  await page.settle();

  // This is what turns a chapter landing from a load into arithmetic. Adopting
  // each new join as it arrived would be a hundred and fifteen loads between
  // eleven and morning — every one of them an element emptied and a panel asked
  // to come back — for a longer timeline the listener will not reach for hours.
  assert.equal(page.audio.srcWrites.length, 1);
  assert.equal(page.probe().streamMs, 3_000_000);
  // The page knows the book is longer all the same, and says so.
  assert.equal(page.probe().clock, "0:30:00 of 1:10:00");
  assert.equal(page.probe().chapterCount, "4 of 37");
});

test("the load waits until they reach it, and then does not wait", async (t) => {
  const page = await listening(t);
  page.serves(growingBook(6));
  page.document.fire("visibilitychange");
  await page.settle();
  upToTheFrontier(page);
  page.order.length = 0;
  page.audio.advance(0.5);

  // The audio past the frontier was already here, so there is nothing to wait
  // for and nothing to be gained by stopping in front of it: the longer join is
  // taken at once and the sound carries on. The load is the same load either
  // way — this is five seconds of silence at 2am that nobody has to sit through.
  assert.deepEqual(page.order, [
    "metadata:Chapter 5",
    "src:api/stream/900008/6",
    "play",
    "state:playing",
  ]);
  assert.equal(page.audio.srcWrites.length, 2);
  assert.equal(page.probe().atFrontier, false);
  assert.deepEqual(page.waits(), []);
  assert.equal(page.probe().status, "");
});

test("a place that arrived after the book was opened is loaded to reach it", async (t) => {
  const page = await listening(t);
  page.serves(growingBook(6));
  page.document.fire("visibilitychange");
  await page.settle();

  // A row chosen in the chapter that has just been read, which is the ordinary
  // way to use a book that is still growing. The element is holding a join that
  // stops before it, so seeking inside what is loaded would clamp the press to
  // the last moment of chapter five — and answer with the same wrong place
  // however many times it was pressed.
  page.seek(3_100_000, { play: true });
  assert.equal(page.audio.srcWrites.length, 2);
  assert.equal(page.audio.srcWrites.at(-1), "api/stream/900008/6");
  page.audio.ready();
  assert.equal(page.audio.currentTime, 3100);
  assert.equal(page.probe().positionMs, 3_100_000);
  assert.equal(page.probe().chapter, "Chapter 6");
});

// ------------------------------------------------ and then reaching it again

// A place in the chapter that has only just been read, offered by the agent and
// tapped. It is the one press on this page that refreshes the manifest without
// the wait for the render knowing anything about it, which is what makes it the
// way a night ends up at a second frontier with the first one's wait still live.
function offerChapterSix() {
  return {
    gid: GROWING_BOOK.gid,
    title: GROWING_BOOK.title,
    position_ms: 3_000_000,
    places: [
      {
        chunk_id: 61,
        start_ms: 3_590_000,
        chapter_idx: 5,
        chapter_title: "Chapter 6",
        ahead: true,
        text: "The diamond, and where it went.",
      },
    ],
  };
}

test("a second frontier is waited for on the chapter it stopped at", async (t) => {
  const page = await listening(t);
  upToTheFrontier(page);
  page.audio.advance(0.5);
  await page.settle();
  await page.settle();
  assert.equal(page.probe().atFrontier, true);

  // Chapter six is read while they are stopped in front of it, and they are
  // awake: they ask somnia a question and tap the row it comes back with, which
  // is a place in the chapter that has just landed. The press refreshes the
  // manifest and seeks, and the book is playing again ten seconds from the end
  // of what is now the last chapter.
  page.serves(growingBook(6));
  page.answers({ reply: "here it is", candidates: offerChapterSix() });
  await page.ask("the bit with the diamond");
  page.click("candidate-go-61");
  await page.settle();
  await page.settle();
  page.audio.ready();
  assert.equal(page.audio.srcWrites.at(-1), "api/stream/900008/6");
  assert.equal(page.probe().idx, 5);

  // Ten seconds later they are at the frontier again, one chapter further on
  // than the wait that is still running was told about.
  page.audio.currentTime = 3599.3;
  page.audio.fire("timeupdate");
  page.audio.advance(0.5);
  await page.settle();
  await page.settle();
  assert.equal(page.audio.paused, true);
  assert.equal(page.probe().atFrontier, true);
  assert.equal(page.probe().status, "waiting for the next chapter to be read");

  // And chapter seven lands. A wait still holding the first frontier's chapter
  // would not recognise this as the chapter it was stopped in front of, would
  // fall through to "the book got longer, nothing to do", and would take its own
  // timer down on the way out — leaving a paused book, an empty status line and
  // nothing anywhere still asking. That is a night that goes quiet with the
  // audio already on the disk, which is the failure this whole branch exists to
  // end.
  page.serves(growingBook(7));
  assert.equal(page.wake(NEXT_ASK_MS), true);
  await page.settle();
  await page.settle();
  assert.equal(page.audio.srcWrites.at(-1), "api/stream/900008/7");
  assert.equal(page.probe().atFrontier, false);
  assert.equal(page.probe().status, "");
  page.audio.ready();
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().positionMs, 3_599_800);
});

// ------------------------------------------- when the night was to end here

test("a night that was to end at this chapter ends at the frontier", async (t) => {
  const page = await listening(t);
  // Asked for in the chapter it is about, which is the fifth: the timer ends
  // the night at the end of the chapter the sound is in when it is set, and
  // this book runs out at the end of that one.
  page.audio.currentTime = 2400.1;
  page.audio.fire("timeupdate");
  for (let tap = 0; tap < 5; tap++) page.click("sleep");
  assert.equal(page.probe().sleep, "sleep timer · chapter end");
  page.audio.currentTime = 2999.3;
  page.audio.fire("timeupdate");
  page.audio.advance(0.5);

  // The frontier and the end of the chapter are the same moment here, and the
  // frontier gets there four hundred milliseconds first. Left to the check that
  // watches for the chapter's own end, the night would never end at all: the
  // sound would stop at the frontier, the next chapter would land twenty
  // minutes later, and the page would start the book again over somebody who
  // had asked it to stop.
  assert.equal(page.audio.paused, true);
  assert.equal(page.audio.ended, false);
  assert.equal(page.probe().status, "goodnight");
  assert.equal(page.probe().sleep, "sleep timer · off");
  // Nothing is waiting for the book to grow, so a chapter landing at three in
  // the morning finds nobody listening for it. The wake still pending is the
  // toast the last tap on the sleep control put up, which forgets itself.
  assert.equal(page.probe().atFrontier, false);
  assert.equal(page.waits().includes(FIRST_ASK_MS), false);
  page.serves(growingBook(6));
  assert.equal(page.audio.paused, true);
  assert.equal(page.audio.srcWrites.length, 1);
});

test("a fade that is already running is not handed back by the frontier", async (t) => {
  // The other timer, the one with a time on it. Fifteen minutes was asked for
  // twenty-five seconds ago on a page that has since been discarded, which is
  // how a night gets a timer with seconds left on it without a quarter of an
  // hour of listening first.
  const page = await boot(t, {
    lastGid: GROWING_BOOK.gid,
    stored: armed(1, 25_000),
  });
  page.audio.ready();
  page.audio.currentTime = 2400.1;
  page.audio.fire("timeupdate");
  page.click("playpause");
  page.audio.currentTime = 2986.6;
  page.audio.fire("timeupdate");
  // A few seconds of book, and the timer is spent: it clears itself and starts
  // the twenty-second fade that is the last thing it does. Five and a half
  // rather than five, because the fade in that a press of play brings the sound
  // back through is nine hundred milliseconds the timer is not charged for. One
  // step further on so the volume has really started to come down.
  for (let step = 0; step < 12; step++) page.audio.advance(0.5);
  assert.equal(page.probe().fading, true);
  assert.equal(page.probe().sleep, "sleep timer · fading");
  assert.equal(page.probe().volume < 1, true);

  // And part way through that fade the sound reaches the render frontier, which
  // is the ordinary collision on a book being listened to while it renders. The
  // pause the frontier makes puts the volume back and throws the fade away, so
  // nothing is left to reach the end of it: without this the night neither ends
  // nor says goodnight, and the chapter that lands twenty minutes later starts
  // the book again, at full volume, over somebody who had asked for it to stop.
  page.audio.currentTime = 2999.3;
  page.audio.fire("timeupdate");
  page.audio.advance(0.5);
  assert.equal(page.audio.paused, true);
  assert.equal(page.probe().status, "goodnight");
  assert.equal(page.probe().volume, 1);
  assert.equal(page.probe().sleep, "sleep timer · off");
  assert.equal(page.probe().atFrontier, false);

  // And nothing is listening for the book to grow. This is the assertion the
  // night rests on: a wait armed here carries the sound back with it.
  assert.equal(page.waits().includes(FIRST_ASK_MS), false);
  assert.equal(page.waits().includes(NEXT_ASK_MS), false);
  page.serves(growingBook(6));
  await page.settle();
  await page.settle();
  assert.equal(page.audio.paused, true);
  assert.equal(page.audio.srcWrites.length, 1);
});
