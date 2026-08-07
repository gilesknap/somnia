// The book as one timeline. somnia renders a file per chapter, but nobody
// listens to a chapter, so everything the page does counts in global
// milliseconds and which file that lands in is meant to be invisible. These
// are the tests that it stays invisible: the arithmetic that maps one to the
// other, the swap at a boundary, and the transport that is not on the screen.

import assert from "node:assert/strict";
import { test } from "node:test";

import { boot, SHRUNK_BOOK, TONE_BOOK, UNMEASURED_BOOK } from "./harness.mjs";

// Get to sound coming out of chapter one, which is where most of these start.
async function playing(t) {
  const page = await boot(t);
  page.audio.ready();
  page.click("playpause");
  return page;
}

test("opening the app holds the book but does not start it", async (t) => {
  const page = await boot(t);
  assert.deepEqual(page.fetches, ["api/books", "api/book/900001"]);
  assert.deepEqual(page.audio.srcWrites, ["api/audio/900001/0"]);
  assert.equal(page.audio.playCalls, 0);
  page.audio.ready();
  // Opening the app at 2am to ask a question is not listening, and a book they
  // only opened must keep its null position: "never started" and "at the very
  // beginning" are different answers to "where am I?".
  assert.deepEqual(page.posts, []);
  assert.equal(page.probe().untouched, true);
});

test("the readout counts the whole book from the first frame", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  assert.equal(page.probe().chapter, "The First Tone");
  assert.equal(page.probe().clock, "0:00:00 of 0:00:24");
  assert.equal(page.probe().playing, false);
});

test("the book is named above the chapter, and stays named across a boundary", async (t) => {
  const page = await playing(t);
  // The manifest has carried the book's own title since the beginning and the
  // page drew everything else about it — the chapter, both clocks, the lock
  // screen's album — while the one thing somebody half awake needs to check
  // they are in the right book was on no screen at all.
  assert.equal(page.probe().book, "Three Tones");
  assert.equal(page.probe().chapter, "The First Tone");

  page.audio.currentTime = 7.7;
  page.audio.fire("timeupdate");
  page.audio.ready();
  // The chapter under it changed and the headline did not. It is drawn every
  // pass off the manifest rather than written once when the book opened, so
  // there is no path by which a swap can leave it holding the last book.
  assert.equal(page.probe().chapter, "The Second Tone");
  assert.equal(page.probe().book, "Three Tones");
});

test("the lock screen is told the chapter, the book and the author", async (t) => {
  const page = await boot(t);
  const { metadata } = page.session;
  assert.equal(metadata.title, "The First Tone");
  assert.equal(metadata.album, "Three Tones");
  assert.equal(metadata.artist, "Somnia Test");
  assert.deepEqual(
    metadata.artwork.map((art) => art.src),
    ["icon-192.png", "icon-512.png"],
  );
});

test("every remote button has a handler, whether or not this phone has one", async (t) => {
  const page = await boot(t);
  // Android only surfaces the buttons something is listening for, so an
  // unregistered nexttrack is a pillow speaker whose skip button does nothing.
  assert.deepEqual(Object.keys(page.session.handlers).sort(), [
    "nexttrack",
    "pause",
    "play",
    "previoustrack",
    "seekbackward",
    "seekforward",
    "seekto",
    "stop",
  ]);
});

test("nothing claims to be playing until something is", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  assert.deepEqual(page.session.states, []);
  page.click("playpause");
  assert.equal(page.session.playbackState, "playing");
  assert.equal(page.probe().playing, true);
});

// ------------------------------------------------------- boundary arithmetic

test("a millisecond before a boundary is still the chapter before it", async (t) => {
  const { math } = await boot(t);
  assert.deepEqual(math.locate(7999), {
    idx: 0,
    chapter: TONE_BOOK.chapters[0],
    offset_ms: 7999,
  });
  assert.deepEqual(math.locate(8000), {
    idx: 1,
    chapter: TONE_BOOK.chapters[1],
    offset_ms: 0,
  });
});

test("a place off either end of the book lands inside it", async (t) => {
  const { math } = await boot(t);
  assert.deepEqual(math.locate(-5000), {
    idx: 0,
    chapter: TONE_BOOK.chapters[0],
    offset_ms: 0,
  });
  // Past the end is the end of the last chapter, not the start of nothing.
  assert.equal(math.locate(99_999).idx, 2);
  assert.equal(math.locate(99_999).offset_ms, 8000);
});

test("an offset is never set at or past the duration", async (t) => {
  const { math } = await boot(t);
  // Assigning currentTime >= duration lands at the end and fires `ended` at
  // once, which silently skips a whole chapter — and the render clock can
  // legitimately exceed the container clock, so this is not hypothetical.
  assert.equal(math.toElementSeconds(8000, 8), 7.95);
  assert.equal(math.toElementSeconds(4000, 8), 4);
  // No duration yet, so nothing to clamp against.
  assert.equal(math.toElementSeconds(4000, NaN), 4);
  assert.equal(math.toElementSeconds(-100, 8), 0);
});

test("a decoder running past the end of a chapter is still in that chapter", async (t) => {
  const { math } = await boot(t);
  const second = TONE_BOOK.chapters[1];
  assert.equal(math.toGlobalMs(second, 4), 12_000);
  // One AAC frame past what was rendered, which a decoder that ignores the
  // edit list really does report. Unclamped it would claim the next chapter.
  assert.equal(math.toGlobalMs(second, 8.03), 16_000);
  assert.equal(math.toGlobalMs(second, -0.2), 8000);
});

test("the clock is the same shape the agent speaks", async (t) => {
  const { math } = await boot(t);
  assert.equal(math.timestamp(0), "0:00:00");
  assert.equal(math.timestamp(24_000), "0:00:24");
  assert.equal(math.timestamp(3_661_000), "1:01:01");
  assert.equal(math.timestamp(-500), "0:00:00");
});

// ------------------------------------------------------------ the chapter swap

test("a boundary names the new chapter before it starts it", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  page.click("playpause");
  page.audio.currentTime = 7.7; // inside the swap lead
  page.order.length = 0;
  page.audio.fire("timeupdate");
  // Metadata first: the metadata current at the moment playback starts is the
  // one the notification adopts, so setting it afterwards labels the new
  // chapter with the old one's title. And nothing pauses in between — handing
  // audio focus back even for an instant is what tears the notification down.
  assert.deepEqual(page.order, [
    "metadata:The Second Tone",
    "src:api/audio/900001/1",
    "play",
    "state:playing",
  ]);
  assert.equal(page.session.playbackState, "playing");
});

test("a tick during a swap does not swap again", async (t) => {
  const page = await playing(t);
  page.audio.currentTime = 7.7;
  page.audio.fire("timeupdate");
  assert.equal(page.audio.srcWrites.length, 2);
  page.audio.fire("timeupdate");
  assert.equal(page.audio.srcWrites.length, 2);
  // Nor is the position dragged back to whatever the element is reading while
  // it holds two chapters at once.
  assert.equal(page.probe().positionMs, 7700);
});

test("a swap lands at the start of the file and keeps playing", async (t) => {
  const page = await playing(t);
  page.audio.currentTime = 7.7;
  page.audio.fire("timeupdate");
  page.audio.ready();
  assert.equal(page.audio.currentTime, 0);
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().swapping, false);
  assert.equal(page.probe().chapter, "The Second Tone");
  assert.equal(page.session.metadata.title, "The Second Tone");
});

test("the readout is global and the scrubber is not", async (t) => {
  const page = await playing(t);
  page.seek(8500, { play: true });
  page.audio.ready();
  page.tick(1000);
  page.audio.fire("timeupdate");
  assert.equal(page.probe().clock, "0:00:08 of 0:00:24");
  // The deliberate asymmetry. A whole-book scrubber on a twelve-hour novel is
  // three minutes to the pixel: useless for the nudge someone wants, and one
  // sleepy thumb from the ending.
  assert.deepEqual(page.session.last(), {
    duration: 8,
    position: 0.5,
    playbackRate: 1,
  });
});

test("the lock screen is not told the time more than once a second", async (t) => {
  const page = await playing(t);
  page.tick(1000);
  page.audio.fire("timeupdate");
  const published = page.session.positions.length;
  page.audio.fire("timeupdate");
  page.audio.fire("timeupdate");
  assert.equal(page.session.positions.length, published);
  page.tick(1000);
  page.audio.fire("timeupdate");
  assert.equal(page.session.positions.length, published + 1);
});

// --------------------------------------------------------------------- seeking

test("a seek inside the file already loaded does not fetch it again", async (t) => {
  const page = await playing(t);
  page.seek(5000);
  // The branch that keeps the autoplay policy out of the common case: a seek
  // on a live element needs no permission at all, so it asks for none.
  assert.equal(page.audio.srcWrites.length, 1);
  assert.equal(page.audio.currentTime, 5);
  assert.equal(page.audio.paused, false);
});

test("a seek into another chapter loads the chapter it lands in", async (t) => {
  const page = await playing(t);
  page.seek(15_900);
  assert.equal(page.audio.srcWrites.at(-1), "api/audio/900001/1");
  page.audio.ready();
  assert.equal(page.audio.currentTime, 7.9);
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().clock, "0:00:15 of 0:00:24");
});

test("an element holding an error is reloaded rather than seeked", async (t) => {
  const page = await playing(t);
  page.audio.fail();
  // It will not fetch again until it is loaded afresh, so setting currentTime
  // on it would be a press of play that was never going to make a sound.
  page.seek(3000, { play: true });
  assert.equal(page.audio.srcWrites.length, 2);
  assert.equal(page.audio.srcWrites.at(-1), "api/audio/900001/0");
});

test("thirty seconds forward from the last chapter stops at the end", async (t) => {
  const page = await playing(t);
  page.seek(20_000, { play: true });
  page.audio.ready();
  page.click("fwd30");
  assert.equal(page.probe().positionMs, 24_000);
  page.audio.ready();
  // Clamped short of the duration, or the element would end the chapter the
  // instant it was told where to be.
  assert.equal(page.audio.currentTime, 7.95);
});

test("thirty seconds back from the top of a chapter lands in the one before", async (t) => {
  const page = await playing(t);
  page.seek(16_500, { play: true });
  page.audio.ready();
  page.click("back30");
  // Which is what "back a bit" means to somebody listening to a book rather
  // than to a pile of files.
  assert.equal(page.probe().positionMs, 0);
  assert.equal(page.audio.srcWrites.at(-1), "api/audio/900001/0");
});

// -------------------------------------------------- the buttons on the pillow

test("a remote skip moves by exactly what the platform asked for", async (t) => {
  const page = await playing(t);
  page.seek(17_000, { play: true });
  page.audio.ready();
  page.press("seekforward", { seekOffset: 3 });
  assert.equal(page.probe().positionMs, 20_000);
  page.press("seekbackward", { seekOffset: 3 });
  assert.equal(page.probe().positionMs, 17_000);
  // A remote with no opinion is given our idea of "a bit", and it is allowed
  // to leave the chapter.
  page.press("seekbackward", {});
  assert.equal(page.probe().positionMs, 0);
});

test("a scrub is read back on the scale it was published", async (t) => {
  const page = await playing(t);
  page.seek(9000, { play: true });
  page.audio.ready();
  page.press("seekto", { seekTime: 3 });
  assert.equal(page.probe().positionMs, 11_000);
  page.press("seekto", {});
  assert.equal(page.probe().positionMs, 11_000);
});

test("next and previous walk the chapters and stop at the ends", async (t) => {
  const page = await playing(t);
  page.press("nexttrack");
  page.audio.ready();
  assert.equal(page.probe().positionMs, 8000);
  page.press("nexttrack");
  page.audio.ready();
  assert.equal(page.probe().positionMs, 16_000);
  page.press("nexttrack");
  assert.equal(page.probe().positionMs, 16_000);
  page.seek(22_000, { play: true });
  page.audio.ready();
  // Five seconds in, "previous" means the start of this chapter — what it
  // means on every music player anyone has used.
  page.press("previoustrack");
  assert.equal(page.probe().positionMs, 16_000);
  page.press("previoustrack");
  page.audio.ready();
  assert.equal(page.probe().positionMs, 8000);
});

test("stop stops the sound and never lets go of the notification", async (t) => {
  const page = await playing(t);
  page.press("stop");
  assert.equal(page.audio.paused, true);
  // Emptying the element is the documented way to dismiss the media
  // notification, and dismissing it face down in a pocket is the one state
  // this page cannot recover from.
  assert.equal(page.audio.src, "api/audio/900001/0");
  assert.equal(page.session.metadata.title, "The First Tone");
});

// ----------------------------------------------------------- the end of a file

test("a chapter that ends without a duration still advances", async (t) => {
  const page = await boot(t);
  page.audio.ready(NaN); // no duration, so the swap lead can never fire
  page.click("playpause");
  page.audio.ended = true;
  page.audio.paused = true;
  page.audio.fire("pause");
  page.audio.fire("ended");
  // `ended` decides that a chapter is over, never the clock: a truncated
  // encode becomes a skip rather than a book that hangs at 2am.
  assert.equal(page.audio.srcWrites.at(-1), "api/audio/900001/1");
  assert.equal(page.audio.paused, false);
});

test("the end of the last chapter is the end of the book", async (t) => {
  const page = await playing(t);
  page.seek(16_000, { play: true });
  page.audio.ready();
  page.audio.advance(7.9);
  assert.equal(page.probe().status, "");
  page.audio.advance(0.2);
  await page.settle();
  assert.equal(page.audio.srcWrites.length, 2);
  assert.equal(page.probe().status, "that is the end of the book");
  assert.equal(page.probe().playing, false);
  // The pause before `ended` was swallowed as spurious, quite rightly, so this
  // is the only chance to stop the notification offering to pause a book that
  // has finished.
  assert.equal(page.session.playbackState, "paused");
  assert.equal(page.probe().wantsSound, false);
});

// ------------------------------------------------- the corner that throws away

// It used to ask first: one press put `sure? tap again` where the label was, on
// a three-second fuse, and only the second press did anything. That was the
// right answer while this corner was on the player, where a sleepy thumb finds
// it. It is the chat screen's corner now, and there the press costs nothing but
// questions that can be asked again — so it is one tap, and the two tests that
// used to be here are these two: everything happens on the first press, and
// nothing is left running behind it.

test("start over throws the conversation away on the first press", async (t) => {
  const page = await playing(t);
  page.seek(12_000, { play: true });
  page.audio.ready();
  await page.ask("the bit where the horse dies");
  assert.equal(page.el("transcript").children.length, 2);

  const stale = page.storageSession.getItem("somnia-token");
  page.click("restart");
  await page.settle();
  // The whole of it, at once: the transcript is the one line the page opens
  // with, the conversation the server was holding is thrown away, and the name
  // it went by is not the name the next question carries.
  assert.deepEqual(
    page.el("transcript").children.map((line) => line.textContent),
    ["Where do you want to be?"],
  );
  assert.equal(page.fetches.includes("api/forget"), true);
  assert.notEqual(page.storageSession.getItem("somnia-token"), stale);
  // Still where the book was, and still playing it. Nothing in here is a seek,
  // which is the half of this control most easily got wrong: "start over" is a
  // sentence about a book as easily as about a chat, and a press that took
  // somebody back to the beginning of a nine-hour novel would be the one
  // mistake on this page nothing could undo.
  assert.equal(page.probe().positionMs, 12_000);
  assert.equal(page.probe().playing, true);
});

test("start over leaves nothing armed and nothing waiting", async (t) => {
  const page = await boot(t);
  page.click("restart");
  await page.settle();
  // No fuse, so no phone put down face up with a question on it and no wake to
  // clear.
  assert.deepEqual(page.waits(), []);
  // And nothing armed: no class, and not a word written into the corner. The
  // label is the document's own now and the page never touches it, so an empty
  // string here is the whole of "app.js has nothing to say about that word" —
  // which is what it would have to have again to ask anybody anything.
  assert.equal(page.el("restart").classes.has("armed"), false);
  assert.equal(page.el("restart").textContent, "");

  const stale = page.storageSession.getItem("somnia-token");
  page.click("restart");
  await page.settle();
  // And the next press is the same press again, not the second half of the
  // last one: an already-empty conversation is thrown away again, with a new
  // name, which is the only shape this control has now.
  assert.notEqual(page.storageSession.getItem("somnia-token"), stale);
  assert.deepEqual(
    page.el("transcript").children.map((line) => line.textContent),
    ["Where do you want to be?"],
  );
});

test("no position is ever published that the platform would refuse", async (t) => {
  const page = await playing(t);
  // The fake throws on a duration or position the real API throws on, so
  // playing a book end to end through every kind of move is the assertion.
  for (const ms of [0, 7999, 8000, 15_999, 16_000, 23_999]) {
    page.seek(ms, { play: true });
    page.audio.ready();
    page.tick(1000);
    page.audio.advance(0.5);
  }
  assert.equal(
    page.session.positions.every(
      (p) => p.duration > 0 && p.position >= 0 && p.position <= p.duration,
    ),
    true,
  );
  assert.equal(page.session.positions.length > 10, true);
});

// The book as a line, which the design asked for twice: two clocks to subtract
// is not a sense of how much book is left. What it must never become is a
// control — 24 seconds of tone book hides it, but a nine-hour novel is about
// ninety seconds to the pixel, and a thumb that lands on it in the dark would
// be past the spoiler guard and into the ending. So these check what it draws,
// and nothing here presses it, because there is nothing to press.
test("the line under the clock fills with the book, not the chapter", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  // Six seconds into a 24-second book is a quarter of the way through it, and
  // three quarters of the way through the eight-second chapter it is in. The
  // line is the book's, so a quarter is the only right answer.
  page.seek(6000);
  assert.equal(page.probe().through, "25%");
  assert.equal(page.probe().clock, "0:00:06 of 0:00:24");
});

test("a book nobody measured draws an empty line rather than a full one", async (t) => {
  // total_ms of 0 is a book whose length was never written down. Dividing by it
  // gives Infinity, and a fill of Infinity% is a book drawn as finished — the
  // one reading that is worse than drawing nothing, because it says they have
  // heard all of something they have not started.
  //
  // The book has to be reached the way the page reaches one — the last gid,
  // answered by the manifest behind it. Handing boot an inline book does
  // nothing: it takes no such option, so the assertion below passed against
  // the tone book and its perfectly good twenty-four seconds.
  const page = await boot(t, { lastGid: UNMEASURED_BOOK.gid });
  page.audio.ready();
  assert.equal(page.probe().through, "0%");
  // And it stays empty once it is being listened to, which is the reading that
  // matters: a fill computed at boot only is empty for every book alive.
  page.seek(8000);
  assert.equal(page.probe().through, "0%");
});

test("a seek past the end of the book stops at the end of the line", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  // The end of the line and nowhere else: "not past 100" is also true of an
  // empty line, and an empty line here would be the opposite bug.
  page.seek(999000);
  assert.equal(page.probe().through, "100%");
});

test("a mark past the end of a re-rendered book lands at the end of it", async (t) => {
  // The mark the server holds is forty seconds into a book now sixteen long,
  // and openBook takes `position_ms` from the manifest without clamping it —
  // which makes this the only way a position past the end reaches the page at
  // all, since seekGlobal clamps everything handed to it.
  const page = await boot(t, { lastGid: SHRUNK_BOOK.gid });
  page.audio.ready();
  // It lands in the last chapter of the book that exists, not past the end of
  // one that does not. 15950 rather than 16000 because an offset is never set
  // at the duration — see "an offset is never set at or past the duration"
  // above, where sitting exactly on it fires `ended` and skips a chapter.
  assert.equal(page.probe().positionMs, 15950);
  assert.equal(page.probe().chapter, "And The Rest Of That");
  assert.equal(page.probe().clock, "0:00:15 of 0:00:16");
  // So the knob stays on its track by a hair, and the fill's own `Math.min`
  // never has to fire. That clamp is the second line of defence, not the one
  // holding here.
  assert.equal(page.probe().through, "99.6875%");
});
