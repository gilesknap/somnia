// The end of the night, and the four other ways the sound stops.
//
// A pause means four different things and only one of them is the listener: a
// swap fires one, a chapter running out fires one, a chapter that will not load
// fires one, and a thumb fires one. Telling them apart is the whole of what
// this file is about — that, and the two things the Audiobookshelf app did that
// the page had to learn, which are stopping the book before it plays all night
// and giving back the last thing they took in.

import assert from "node:assert/strict";
import { test } from "node:test";

import { boot, START_MS } from "./harness.mjs";

// Time passing with the sound on. The element's own clock is deliberately left
// where it is: everything below is measured in minutes and the tone book's
// chapters are eight seconds long, so a boundary crossing in the middle of a
// sleep timer would be a different test. Half a second at a time because that
// is roughly what timeupdate comes off the media pipeline at, and because
// countDownToSleep refuses to be charged more than two seconds for one tick.
function listen(page, ms) {
  for (let left = ms; left > 0; left -= 500) {
    page.tick(Math.min(500, left));
    page.audio.fire("timeupdate");
  }
}

async function playing(t, options) {
  const page = await boot(t, options);
  page.audio.ready();
  page.click("playpause");
  // The fade the page comes back from silence with, spent. Nothing below is
  // about it, and while it is running the sleep timer is not counting.
  listen(page, 1000);
  return page;
}

// Ten minutes into the long book, playing. The element is given the chapter's
// real duration because every seek is clamped against it: told the tone book's
// eight seconds, a jump to ten minutes in would land at the end of the file.
async function inTheNight(t, options) {
  const page = await boot(t, { lastGid: 900004, ...options });
  page.audio.ready(1800);
  page.click("playpause");
  listen(page, 1000);
  page.seek(600_000, { play: true });
  page.audio.fire("seeked");
  return page;
}

// ------------------------------------------------------------- the pause guard

test("the pause a chapter swap fires is not the listener stopping", async (t) => {
  const page = await playing(t);
  page.audio.currentTime = 7.7;
  page.audio.fire("timeupdate");
  assert.equal(page.probe().status, "");
  assert.equal(page.session.playbackState, "playing");
  assert.equal(page.probe().wantsSound, true);
});

test("the pause a chapter failing to load fires is not the listener stopping", async (t) => {
  const page = await playing(t);
  page.audio.fail();
  // Nobody can tell from here whether this is the night ending or five seconds
  // of it, so the page assumes the kinder one and keeps trying.
  assert.equal(page.probe().status, "the book stopped arriving");
  assert.equal(page.probe().wantsSound, true);
  assert.equal(page.session.playbackState, "paused");
  assert.equal(page.probe().swapping, false);
});

test("a chapter that fails after they stopped is not fought for", async (t) => {
  const page = await playing(t);
  page.click("playpause"); // they put the book down
  page.audio.fail();
  assert.equal(page.probe().status, "that chapter didn't arrive");
  assert.equal(page.probe().wantsSound, false);
});

test("the sound really coming out is what takes the message down", async (t) => {
  const page = await playing(t);
  page.audio.fail();
  assert.equal(page.probe().status, "the book stopped arriving");
  // A stall that refilled by itself never reloads anything, so `playing` is
  // the one event that proves the network came back.
  page.audio.fire("playing");
  assert.equal(page.probe().status, "");
});

test("our own pause says nothing alarming", async (t) => {
  const page = await playing(t);
  page.click("playpause");
  assert.equal(page.audio.paused, true);
  assert.equal(page.probe().status, "");
  assert.equal(page.probe().playing, false);
  assert.equal(page.session.playbackState, "paused");
});

test("a pause nobody here asked for says something else took the sound", async (t) => {
  const page = await playing(t);
  // A call, an alarm, another app. Do not resume: an alarm should stop the
  // book, not be talked over.
  page.audio.pause();
  assert.equal(page.probe().status, "something else took the sound");
  assert.equal(page.probe().wantsSound, false);
});

test("a paused player is always at full volume", async (t) => {
  const page = await playing(t, { stored: armed(1, 25_000) });
  listen(page, 6000); // into the fade
  assert.equal(page.probe().fading, true);
  assert.equal(page.probe().volume < 1, true);
  page.click("playpause");
  // Nothing else on the page has to remember that the timer turned the sound
  // down, and a resume by any route is never silent.
  assert.equal(page.probe().volume, 1);
  assert.equal(page.probe().fading, false);
});

// --------------------------------------------------------------- the sleep timer

// What an earlier page wrote down before it was discarded.
function armed(choice, leftMs, at = START_MS - 60_000) {
  return { "somnia-sleep": JSON.stringify({ choice, leftMs, at }) };
}

test("one tap walks the choices and the last takes it all back", async (t) => {
  const page = await boot(t);
  // One string, not a word that changes meaning depending on what is beside
  // it: `sleep` alone said neither what the control was nor what it was doing.
  assert.deepEqual(
    [page.probe().sleep, page.probe().armed, page.probe().spokenSleep],
    ["sleep timer · off", false, "Sleep timer, off"],
  );
  const walked = [];
  for (let tap = 0; tap < 6; tap++) {
    page.click("sleep");
    walked.push(page.probe().sleep);
  }
  // Six taps wrap, so the worst a mis-tap can do is offer to end the night
  // early, and the next tap takes it back.
  assert.deepEqual(walked, [
    "sleep timer · 15m",
    "sleep timer · 30m",
    "sleep timer · 45m",
    "sleep timer · 60m",
    "sleep timer · chapter end",
    "sleep timer · off",
  ]);
  assert.equal(page.probe().armed, false);
});

test("the timer says what it is doing to a screen reader as well", async (t) => {
  const page = await boot(t);
  page.click("sleep");
  // The same state, said twice: the pill is short because it is glanced at and
  // the spoken form is a sentence because it is heard. Both come off the same
  // branch in drawSleep, so they cannot come to disagree about the setting —
  // and both are checked here, because only one of them can be looked at.
  assert.equal(page.probe().sleep, "sleep timer · 15m");
  assert.equal(page.probe().spokenSleep, "Sleep timer, 15 minutes left");
  assert.equal(page.probe().armed, true);
  for (let tap = 0; tap < 4; tap++) page.click("sleep");
  assert.equal(page.probe().sleep, "sleep timer · chapter end");
  assert.equal(
    page.probe().spokenSleep,
    "Sleep timer, at the end of this chapter",
  );
});

test("the timer counts listening time, not clock time", async (t) => {
  const page = await playing(t, { stored: armed(1, 900_000) });
  const started = page.probe().sleepLeftMs;
  listen(page, 60_000);
  assert.equal(started - page.probe().sleepLeftMs, 60_000);
  // Someone who pauses to ask a question and then reads the answer meant to
  // hear the rest of what they had asked for — and a timer that had run out
  // while they read would answer them by ending the night.
  page.click("playpause");
  const held = page.probe().sleepLeftMs;
  listen(page, 60_000);
  assert.equal(page.probe().sleepLeftMs, held);
  // Seeking fires timeupdate whether or not there is any sound, which is the
  // one way a paused book could otherwise be charged for the time.
  page.tick(5000);
  page.audio.fire("timeupdate");
  assert.equal(page.probe().sleepLeftMs, held);
});

test("a timer that outlived the page is still counting down", async (t) => {
  const page = await boot(t, { stored: armed(1, 300_000) });
  // The minutes they had left are still the minutes they have left, whether
  // the reload took two seconds or the phone killed the tab an hour ago.
  assert.equal(page.probe().sleep, "sleep timer · 5m");
  page.audio.ready();
  page.click("playpause");
  listen(page, 61_000);
  assert.equal(page.probe().sleep, "sleep timer · 4m");
});

test("a timer from a night that is over is not applied to this one", async (t) => {
  const page = await boot(t, {
    stored: armed(1, 300_000, START_MS - 7 * 3_600_000),
  });
  // Someone opening the book the following evening is starting a night rather
  // than finishing one.
  assert.equal(page.probe().sleep, "sleep timer · off");
  assert.equal(page.probe().sleepLeftMs, null);
});

test("the countdown is written down as it goes, not only when it is set", async (t) => {
  const page = await playing(t, { stored: armed(1, 300_000) });
  listen(page, 45_000);
  const saved = JSON.parse(page.storage.getItem("somnia-sleep"));
  // The tab can be discarded between one timeupdate and the next, and a timer
  // that came back with the whole of its hour still to run would be an hour of
  // book nobody asked for.
  assert.equal(saved.choice, 1);
  assert.equal(saved.leftMs < 300_000, true);
  // Two writes a minute rather than two hundred and forty. The readout is in
  // whole minutes, so half a minute of slop after a crash cannot be seen.
  assert.equal(saved.leftMs - page.probe().sleepLeftMs <= 30_000, true);
});

test("the timer ends in a fade that reaches silence at the time it named", async (t) => {
  const page = await playing(t, { stored: armed(1, 25_000) });
  assert.equal(page.probe().volume, 1);
  listen(page, 6000);
  // Twenty seconds of getting quieter, so it begins before the moment the
  // timer named rather than at it.
  assert.equal(page.probe().sleep, "sleep timer · fading");
  assert.equal(page.audio.paused, false);
  const half = page.probe().volume;
  assert.equal(half > 0 && half < 1, true);
  listen(page, 21_000);
  assert.equal(page.audio.paused, true);
  assert.equal(page.probe().status, "goodnight");
  // The timer is spent, not still counting: coming back afterwards is a
  // decision to set another one, which is one tap.
  assert.equal(page.probe().sleep, "sleep timer · off");
  assert.equal(page.probe().volume, 1);
});

test("a nudge during the fade brings the sound back", async (t) => {
  const page = await playing(t, { stored: armed(1, 25_000) });
  listen(page, 6000);
  assert.equal(page.probe().fading, true);
  // Nobody who is asleep skips forward thirty seconds, so a jump during the
  // fade is somebody still awake.
  page.click("back30");
  listen(page, 1000);
  assert.equal(page.probe().volume, 1);
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().sleep, "sleep timer · off");
});

test("reaching for the control during the fade brings the sound back too", async (t) => {
  const page = await playing(t, { stored: armed(1, 25_000) });
  listen(page, 6000);
  page.click("sleep");
  listen(page, 1000);
  assert.equal(page.probe().volume, 1);
  assert.equal(page.audio.paused, false);
  // And the tap they made is the new setting, not a cancellation of the old.
  assert.equal(page.probe().sleep, "sleep timer · 15m");
});

test("the end of the chapter is not crossed when the night ends there", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  for (let tap = 0; tap < 5; tap++) page.click("sleep");
  assert.equal(page.probe().sleep, "sleep timer · chapter end");
  page.click("playpause");
  page.audio.currentTime = 7.7;
  page.audio.fire("timeupdate");
  // The whole of what "end of chapter" asks for is that this boundary is not
  // crossed, so the swap lead must not take it either.
  assert.equal(page.audio.srcWrites.length, 1);
  page.audio.advance(0.4);
  await page.settle();
  assert.equal(page.audio.srcWrites.length, 1);
  assert.equal(page.audio.paused, true);
  assert.equal(page.probe().status, "goodnight");
  assert.equal(page.probe().sleep, "sleep timer · off");
});

// --------------------------------------------------------------- the way back

test("the rewind is sized by how long the sound was off", async (t) => {
  const { math } = await boot(t);
  // A pause is three unlike things wearing the same name: a moment taken to
  // hear something in the room, a question asked and answered, and falling
  // asleep with the phone still in a hand.
  assert.equal(math.rewindFor(20_000), 0);
  assert.equal(math.rewindFor(60_000), 8000);
  assert.equal(math.rewindFor(10 * 60_000), 20_000);
  assert.equal(math.rewindFor(3 * 3_600_000), 30_000);
});

test("a moment's silence gives nothing back", async (t) => {
  const page = await inTheNight(t);
  page.click("playpause");
  page.tick(5000);
  assert.equal(page.resumePoint(), 600_000);
});

test("an hour's silence lands on the start of the sentence they were in", async (t) => {
  const page = await inTheNight(t, { sentenceStart: 566_000 });
  page.click("playpause");
  await page.settle();
  // Asked at the pause and spent at the resume, never the other way round: a
  // phone that has been face down for an hour is the least likely thing on the
  // tailnet to answer quickly.
  assert.equal(page.sentenceAsks.length, 1);
  assert.equal(page.sentenceAsks[0], "api/sentence/900004/570000");
  page.tick(2 * 3_600_000);
  // Half a minute back is 0:09:30, mid-sentence. The passage being spoken
  // there began at 0:09:26, and after an hour they have the whole of it to
  // place.
  assert.equal(page.resumePoint(), 566_000);
  page.click("playpause");
  assert.equal(page.sentenceAsks.length, 1);
});

test("only the longest rung snaps to a sentence", async (t) => {
  const page = await inTheNight(t, { sentenceStart: 566_000 });
  page.click("playpause");
  await page.settle();
  page.tick(10 * 60_000);
  // The sentence was looked up half a minute behind where they stopped,
  // because that is where the long rewind lands. Applying it to a shorter rung
  // would quietly turn twenty seconds back into half a minute back.
  assert.equal(page.resumePoint(), 580_000);
});

test("a sentence found out about somewhere else is not used", async (t) => {
  const page = await inTheNight(t, { sentenceStart: 566_000 });
  page.click("playpause");
  await page.settle();
  page.tick(2 * 3_600_000);
  // The book has been moved since, so what was found out is about somewhere
  // else entirely.
  page.seek(900_000);
  assert.equal(page.resumePoint(), 870_000);
});

test("pressing play after a night gives the time back and plays it", async (t) => {
  const page = await inTheNight(t, { sentenceStart: 566_000 });
  page.click("playpause");
  await page.settle();
  page.tick(2 * 3_600_000);
  page.click("playpause");
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().positionMs, 566_000);
  // From silence, however short the fade. A book coming back at full volume in
  // a dark room is the loudest thing that happens all night.
  assert.equal(page.probe().volume < 1, true);
});
