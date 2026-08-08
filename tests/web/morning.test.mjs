// The morning after, which until now the page had no way of knowing it was in.
//
// A night ended by the sleep timer left nothing behind. The fade cleared the
// timer on its way out and then stopped the book through the ordinary path —
// which reports `pause`, the same word a thumb sends — so the record of the one
// thing worth knowing at seven in the morning did not exist anywhere: not on the
// server, which is never told a reason, and not in the page, which is discarded
// by the phone somewhere around two.
//
// That cost two things, and the file below is in two halves for them. The first
// is a bug: `rewindFor`'s longest rung was written for the night that ends with
// somebody asleep, and on a relaunch there was nothing to measure the silence
// from, so the one case it was built for was the one case it never ran in. The
// second is the screen — the morning as somewhere to arrive, with the time the
// sound went at the top of it and three ways to answer it underneath.

import assert from "node:assert/strict";
import { test } from "node:test";

import { boot, HALF_HEARD, NIGHT_BOOK, START_MS } from "./harness.mjs";

// Long enough ago that the silence is on the longest rung of the ladder. Three
// hours is a real night rather than a number chosen to clear an hour by a
// minute: the fade ran at one, and this is somebody waking at four.
const LAST_NIGHT = START_MS - 3 * 3_600_000;

// What the fade wrote down, as an earlier page left it.
function recorded({ at = LAST_NIGHT, positionMs = HALF_HEARD.position_ms } = {}) {
  return { "somnia-fade": JSON.stringify({ at, positionMs }) };
}

// What an earlier page wrote down about the timer, in stopping.test.mjs' shape.
function armed(choice, leftMs, at = START_MS - 60_000) {
  return { "somnia-sleep": JSON.stringify({ choice, leftMs, at }) };
}

// A list of places about the open book, as the last question left it. Only the
// three fields restorePlaces insists on are interesting here — this file is
// about the count under the first choice and never about the rows — so the
// places themselves are as plain as a valid record can be.
function kept(count) {
  return {
    "somnia-places": JSON.stringify({
      gid: HALF_HEARD.gid,
      title: HALF_HEARD.title,
      position_ms: HALF_HEARD.position_ms,
      places: Array.from({ length: count }, (_, at) => ({
        chunk_id: 11 + at,
        start_ms: 300_000 * (at + 1),
        chapter_idx: 0,
        chapter_title: "What They Have Heard",
        ahead: false,
        text: "The water was over the low part of the road.",
      })),
    }),
  };
}

// The page open on the long book, playing, ten minutes in. The tone book is
// twenty-four seconds long — a four-hundredth of the shortest sleep timer — so
// anything about a night needs a book measured in minutes.
//
// Nothing is ticked here, unlike stopping.test.mjs' version of this. Every test
// below that cares about *when* the night ended counts its own milliseconds from
// the boot clock, and a warm-up of a second spent on the fade-in would be a
// second nobody could see in the arithmetic.
async function inTheNight(t, options) {
  const page = await boot(t, { lastGid: NIGHT_BOOK.gid, ...options });
  page.audio.ready();
  page.click("playpause");
  page.seek(600_000, { play: true });
  page.audio.arrived();
  return page;
}

// Time passing with the sound on, until the timer has ended the night — and not
// one tick further. What it returns is how long that took, which makes the
// moment the sound stopped a number the test holds rather than one it would have
// to work out by reproducing the countdown's own arithmetic.
function untilItFades(page) {
  let spent = 0;
  // Twenty minutes of book at half a second a tick, which is far past any timer
  // set below. A fade that never lands is a failed assertion in the test that
  // called this, not a suite that runs for ever.
  for (let ticks = 0; ticks < 2400 && !page.audio.paused; ticks++) {
    page.tick(500);
    spent += 500;
    page.audio.fire("timeupdate");
  }
  return spent;
}

// The morning screen as somebody looking at it would read it: the sentence at
// the top, the three choices at the foot, and whether the first of them is drawn
// at all.
function morning(page) {
  const found = page.el("wake-found");
  return {
    said: page.el("wake-said").textContent,
    // Null rather than "" so that a choice nobody can see and a choice with
    // nothing written under it cannot be mistaken for each other.
    places: page.el("wake-places").hidden ? null : found.textContent,
    keep: page.el("wake-keep").textContent,
  };
}

// The time on the clock beside the bed, read out of the same instant by another
// route than the page's. It is deliberately not a literal: the timezone this run
// happens to be in decides the digits, and what is worth asserting is which
// instant is named — the fade's, and not now's.
function clockFace(ms) {
  return new Date(ms).toTimeString().slice(0, 5).replace(/^0/, "");
}

// ------------------------------------------------------- writing it down

test("the fade writes down when the night ended and where the book was", async (t) => {
  const page = await inTheNight(t, { stored: armed(1, 25_000) });
  const spent = untilItFades(page);
  assert.equal(page.probe().status, "goodnight");
  const record = JSON.parse(page.storage.getItem("somnia-fade"));
  // The wall clock at the moment the sound went, which is the fact the whole of
  // the morning is built out of and the one nobody was awake for.
  assert.equal(record.at, START_MS + spent);
  // And where it stopped, which is what the third choice offers to keep.
  assert.equal(record.positionMs, 600_000);
});

test("a night that ends at the end of a chapter is written down too", async (t) => {
  const page = await boot(t, { lastGid: NIGHT_BOOK.gid });
  page.audio.ready();
  for (let tap = 0; tap < 5; tap++) page.click("sleep");
  assert.equal(page.probe().sleep, "sleep timer · chapter end");
  // A quarter of a second short of the end of the first chapter, and then over
  // it. The book's own clock is what ends this kind of night, and it is a
  // different route into fallAsleep from the fade above.
  page.seek(1_799_000, { play: true });
  page.audio.arrived();
  page.tick(1000);
  page.audio.currentTime = 1800;
  page.audio.fire("timeupdate");
  assert.equal(page.audio.paused, true);
  const record = JSON.parse(page.storage.getItem("somnia-fade"));
  assert.equal(record.at, START_MS + 1000);
  assert.equal(record.positionMs, 1_800_000);
});

// The one end of a night that does not go through fallAsleep: the file ran out
// before the book's clock reached the chapter end it was told to stop at, so the
// check that watches for that end never fired and `ended` is where the night
// really finished. A morning that happened on some nights and not others would
// be worse than one that never came at all.
test("a night whose file runs out early is written down as well", async (t) => {
  const page = await boot(t);
  // Half a second less sound than the database says the book has.
  page.audio.ready(23.5);
  for (let tap = 0; tap < 5; tap++) page.click("sleep");
  page.seek(16_000, { play: true });
  page.audio.currentTime = 23.25;
  page.audio.fire("timeupdate");
  page.tick(1000);
  // A quarter of a second of sound, which moves the wall clock with it: the
  // page's timers count listening time off Date.now() between timeupdates, so
  // the harness advances both together.
  page.audio.advance(0.25);
  await page.settle();
  assert.equal(page.probe().status, "goodnight");
  const record = JSON.parse(page.storage.getItem("somnia-fade"));
  assert.equal(record.at, START_MS + 1250);
});

test("a book put down by a thumb is not a night that ended by itself", async (t) => {
  const page = await inTheNight(t);
  page.click("playpause");
  // The whole distinction this record exists to make. A pause is a pause on the
  // wire either way — the server is told `pause` for both — and only the page
  // is ever in a position to know which of the two it was.
  assert.equal(page.audio.paused, true);
  assert.equal(page.storage.getItem("somnia-fade"), null);
});

// ------------------------------------------------------- the rewind it feeds

test("a relaunch after a fade gets the long rewind at last", async (t) => {
  const page = await boot(t, {
    lastGid: HALF_HEARD.gid,
    stored: recorded(),
  });
  // `lastPauseAt` is a variable and the tab it lived in is gone, so before this
  // record the morning arrived here knowing nothing about the silence and gave
  // back nothing at all — on the one night the longest rung was written for.
  assert.equal(page.resumePoint(), HALF_HEARD.position_ms - 30_000);
});

test("a fade a few minutes old is still only a few minutes of silence", async (t) => {
  const page = await boot(t, {
    lastGid: HALF_HEARD.gid,
    stored: recorded({ at: START_MS - 10 * 60_000 }),
  });
  // The ladder is unchanged and this record only says where to start climbing
  // it: ten minutes is the middle rung, not the top one.
  assert.equal(page.resumePoint(), HALF_HEARD.position_ms - 20_000);
});

test("what the page saw for itself outranks what it read", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid, stored: recorded() });
  page.audio.ready();
  page.click("playpause");
  page.audio.arrived();
  await page.settle();
  // The long rewind was given, so the record is spent: leaving it standing
  // would be a wake screen at eight for somebody who was listening at half past
  // seven.
  assert.equal(page.storage.getItem("somnia-fade"), null);
  assert.equal(page.probe().positionMs, HALF_HEARD.position_ms - 30_000);
  // And a moment's silence after that gives nothing back, which is what the page
  // watching for itself has always done and what a record left lying about would
  // have overruled.
  const stopped = page.probe().positionMs;
  page.click("playpause");
  page.tick(5000);
  assert.equal(page.resumePoint(), stopped);
});

// ---------------------------------------------------------------- the screen

test("a launch after a fade opens on the morning", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid, stored: recorded() });
  assert.equal(page.probe().screen, "wake");
  assert.deepEqual([...page.body.classes].sort(), ["wake-screen"]);
  assert.deepEqual(morning(page), {
    said: `The timer faded you out at ${clockFace(LAST_NIGHT)}.`,
    // Nothing was asked last night, so there is nowhere to be shown and no slab
    // offering to show it.
    places: null,
    keep: "keep it where it stopped · 0:16:40",
  });
  // The shape of that time, said once here because every other assertion about
  // it is built from the same instant and could not catch a formatter reading
  // the seconds off the clock.
  assert.match(clockFace(LAST_NIGHT), /^\d{1,2}:\d{2}$/);
});

test("an ordinary launch is the player, as it always was", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid });
  assert.equal(page.probe().screen, "player");
  assert.equal(page.el("wake-said").textContent, "");
});

test("the morning counts the places in the same words the position line does", async (t) => {
  const page = await boot(t, {
    lastGid: HALF_HEARD.gid,
    stored: { ...recorded(), ...kept(3) },
  });
  page.audio.ready();
  // One number, drawn twice, out of one string. The design has had this wrong
  // twice — a pill saying "see all 7 places" over a line saying "4 places found"
  // over a list of four — and both times it was a count worked out in two
  // places.
  assert.equal(morning(page).places, "3 places found");
  assert.equal(page.el("places-found").textContent, "3 places found");
});

test("one place is said in the singular here too", async (t) => {
  const page = await boot(t, {
    lastGid: HALF_HEARD.gid,
    stored: { ...recorded(), ...kept(1) },
  });
  page.audio.ready();
  assert.equal(morning(page).places, "1 place found");
});

test("a list about another book is no list at all on this morning", async (t) => {
  const page = await boot(t, {
    lastGid: NIGHT_BOOK.gid,
    stored: { ...recorded(), ...kept(4) },
  });
  page.audio.ready();
  // The places were the answer to a question about a book that is not the one
  // open, and a slab offering to show them would be a promise about this one.
  assert.equal(morning(page).places, null);
  assert.equal(page.el("wake-places").hidden, true);
});

// ---------------------------------------------------------- the three choices

test("see where you might be opens the places and leaves the book alone", async (t) => {
  const page = await boot(t, {
    lastGid: HALF_HEARD.gid,
    stored: { ...recorded(), ...kept(3) },
  });
  page.audio.ready();
  const before = page.probe();
  page.click("wake-places");
  assert.equal(page.probe().screen, "player");
  assert.equal(page.probe().candidatesUp, true);
  assert.equal(page.el("candidate-list").children.length > 0, true);
  // Nothing about the book moved: this is the same list the position line
  // opens, raised from the screen somebody is on at seven in the morning.
  assert.equal(page.probe().positionMs, before.positionMs);
  assert.equal(page.audio.paused, true);
});

test("tell me what you remember opens the conversation", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid, stored: recorded() });
  page.click("wake-ask");
  assert.equal(page.probe().screen, "chat");
  // And it stays there. `asked` is what that screen means everywhere else, and
  // a screen set without it would be undone by the first resize.
  page.resize(420);
  assert.equal(page.probe().screen, "chat");
});

test("keep it where it stopped is the player, and nothing else", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid, stored: recorded() });
  page.audio.ready();
  const before = page.probe();
  page.click("wake-keep");
  assert.deepEqual(page.probe(), { ...before, screen: "player" });
  assert.equal(page.audio.paused, true);
});

test("any choice answers the morning for good", async (t) => {
  for (const choice of ["wake-places", "wake-ask", "wake-keep"]) {
    const page = await boot(t, {
      lastGid: HALF_HEARD.gid,
      stored: { ...recorded(), ...kept(2) },
    });
    page.audio.ready();
    assert.equal(page.probe().screen, "wake", choice);
    page.click(choice);
    // The record is gone, so the next launch is a launch and not another
    // morning about the same night.
    assert.equal(page.storage.getItem("somnia-fade"), null, choice);
    // And nothing measurable can put it back: the screen is not a place the
    // page returns to when a keyboard or a window changes its mind.
    page.resize(544);
    assert.notEqual(page.probe().screen, "wake", choice);
  }
});

test("the book starting to play takes the morning off the screen", async (t) => {
  const page = await boot(t, { lastGid: HALF_HEARD.gid, stored: recorded() });
  page.audio.ready();
  assert.equal(page.probe().screen, "wake");
  // The lock screen, which is the one transport that is not on this screen and
  // cannot be taken off it. A book playing under an unanswered morning would be
  // a book nothing on the page could stop.
  page.press("play");
  await page.settle();
  assert.equal(page.probe().screen, "player");
  assert.equal(page.audio.paused, false);
  assert.equal(page.storage.getItem("somnia-fade"), null);
});

// ------------------------------------------------- the page that did not die

test("a phone that kept the page still gets the morning", async (t) => {
  const page = await inTheNight(t, { stored: armed(1, 25_000) });
  const spent = untilItFades(page);
  // The tab surviving the night is luck rather than a different night, and
  // which of the two happened is not something the reader can see — so it must
  // not be something the app draws differently.
  assert.equal(page.probe().screen, "player");
  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  page.tick(3 * 3_600_000);
  page.document.visibilityState = "visible";
  page.document.fire("visibilitychange");
  assert.equal(page.probe().screen, "wake");
  assert.equal(
    morning(page).said,
    `The timer faded you out at ${clockFace(START_MS + spent)}.`,
  );
});

test("coming back to a night nobody ended is not a morning", async (t) => {
  const page = await inTheNight(t);
  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  page.tick(3 * 3_600_000);
  page.document.visibilityState = "visible";
  page.document.fire("visibilitychange");
  assert.equal(page.probe().screen, "player");
});

// ------------------------------------------------------- what is not a record

// Every one of these is a page opening at 2am, which is the one thing it has to
// be able to do. A key with rubbish in it reads as a night that ended some other
// way — no rewind and no screen — rather than as a reason to throw before
// anything has been drawn.
test("a record that is not one is a night that ended some other way", async (t) => {
  const rubbish = [
    "",
    "{",
    "null",
    "[]",
    '"1:47"',
    "{}",
    '{"at":"soon","positionMs":10}',
    // Half a record. A morning drawn from this would offer to keep the book at
    // `NaN`, on the one screen where every word is supposed to be a fact.
    `{"at":${LAST_NIGHT}}`,
    `{"positionMs":1000}`,
  ];
  for (const wrong of rubbish) {
    const page = await boot(t, {
      lastGid: HALF_HEARD.gid,
      stored: { "somnia-fade": wrong },
    });
    assert.equal(page.probe().screen, "player", wrong);
    assert.equal(page.resumePoint(), HALF_HEARD.position_ms, wrong);
  }
});

test("a fade from a night that is over is not this morning", async (t) => {
  const page = await boot(t, {
    lastGid: HALF_HEARD.gid,
    stored: recorded({ at: START_MS - 20 * 3_600_000 }),
  });
  // Somebody opening the book the following evening is starting a night rather
  // than finishing one — the same rule the sleep timer already follows, with a
  // longer bound because a morning is further from its night than a timer is.
  assert.equal(page.probe().screen, "player");
  assert.equal(page.resumePoint(), HALF_HEARD.position_ms);
});

test("a fade that has not happened yet is not a morning either", async (t) => {
  const page = await boot(t, {
    lastGid: HALF_HEARD.gid,
    stored: recorded({ at: START_MS + 60_000 }),
  });
  // A clock put back: the phone picked up the network's time in the night, or
  // was carried across a timezone. Nothing true can be said about how long ago
  // that fade was, so nothing is said.
  assert.equal(page.probe().screen, "player");
  assert.equal(page.resumePoint(), HALF_HEARD.position_ms);
});
