// The chapter strip: the two circles that move a whole chapter at a time, the
// count between them that says which chapter of how many, and the clock under
// the chapter's name that says how much of this one is left.
//
// The book's own clock has been on the screen since the beginning and is tested
// in playing.test.mjs. What is here is a second clock at a different scale, the
// count that replaced it between the two buttons, and the thing those tests
// cannot cover: that the buttons under a thumb and the buttons on the lock
// screen are the same two functions, so a chapter skip means the same thing
// whether it came from the page, from the notification, or from a pillow
// speaker at 2am.

import assert from "node:assert/strict";
import { test } from "node:test";

import { boot, UNCOUNTED_BOOK } from "./harness.mjs";

// The tone book is three chapters of exactly eight seconds, so every number
// below is exact and an off-by-one has nowhere to hide.
async function playing(t) {
  const page = await boot(t);
  page.audio.ready();
  page.click("playpause");
  return page;
}

test("the chapter clock counts the chapter and not the book", async (t) => {
  const page = await playing(t);
  page.seek(20_000, { play: true });
  // Twenty seconds into the book is four into chapter three, and the two
  // clocks have to disagree in exactly that way. A chapter clock reading
  // 0:00:20 would be the book's clock wearing a different label, which is the
  // whole reason for having a second one.
  assert.equal(page.probe().clock, "0:00:20 of 0:00:24");
  assert.equal(page.probe().chapterClock, "0:04 of 0:08");
});

test("the count between the circles says which chapter of how many", async (t) => {
  const page = await playing(t);
  // The one number on this screen that answers "how much of this book is left"
  // without arithmetic, which is what somebody deciding whether to set a sleep
  // timer is actually asking.
  assert.equal(page.probe().chapterCount, "1 of 3");
  page.click("nextchapter");
  assert.equal(page.probe().chapterCount, "2 of 3");
  page.click("nextchapter");
  assert.equal(page.probe().chapterCount, "3 of 3");
  // And the circle either side of it still says where there is nothing to go
  // to, rather than going nowhere quietly.
  assert.equal(page.probe().canSkipOn, false);
});

test("a book nobody counted says which chapter and no denominator", async (t) => {
  const page = await boot(t, { lastGid: UNCOUNTED_BOOK.gid });
  page.audio.ready();
  // chapters_total 0 means nobody wrote the number down — which is true of
  // every book on the box this runs on, all of them rendered before the column
  // existed. "1 of 0" is the sentence this prevents, and inventing a
  // denominator from the chapters that happen to have landed would be worse: a
  // book still being read would say "1 of 1" and then "1 of 2" an hour later.
  assert.equal(page.probe().chapterCount, "chapter 1");
  page.click("nextchapter");
  assert.equal(page.probe().chapterCount, "chapter 2");
  assert.equal(page.probe().canSkipOn, false);
});

test("a chapter under an hour drops the leading hour, and over it keeps it", async (t) => {
  const page = await boot(t);
  const { chapterTime } = page.math;
  // The book's clock always carries "0:" because a book is hours long. A
  // twelve-minute chapter that borrowed it would put the least informative
  // digit on the page where the eye lands first.
  assert.equal(chapterTime(0), "0:00");
  assert.equal(chapterTime(41_000), "0:41");
  assert.equal(chapterTime(221_000), "3:41");
  assert.equal(chapterTime(3_599_000), "59:59");
  // An hour-long chapter is rare and not impossible, and it must not read as
  // "0:00" once it wraps.
  assert.equal(chapterTime(3_600_000), "1:00:00");
  assert.equal(chapterTime(3_821_000), "1:03:41");
  // Negative is what a seek clamped past the start of a chapter can hand it.
  assert.equal(chapterTime(-500), "0:00");
});

test("the next chapter button walks forward and stops at the end", async (t) => {
  const page = await playing(t);
  page.click("nextchapter");
  assert.equal(page.probe().positionMs, 8000);
  assert.equal(page.probe().chapter, "The Second Tone");
  // A skip lands at the top of the chapter, so its own clock starts again.
  assert.equal(page.probe().chapterClock, "0:00 of 0:08");

  page.click("nextchapter");
  assert.equal(page.probe().positionMs, 16_000);

  // Nowhere left to go. It says so rather than doing something.
  assert.equal(page.probe().canSkipOn, false);
  page.click("nextchapter");
  assert.equal(page.probe().positionMs, 16_000);
});

test("the previous chapter button restarts this one before it leaves it", async (t) => {
  const page = await playing(t);
  page.seek(22_000, { play: true });
  // Five seconds into the last chapter, so "previous" means the top of it —
  // what it means on every music player anyone has used, and the more
  // forgiving of the two answers for a thumb that missed.
  page.click("prevchapter");
  assert.equal(page.probe().positionMs, 16_000);
  // Now it is at the top, so the same press goes back a chapter.
  page.click("prevchapter");
  assert.equal(page.probe().positionMs, 8000);
});

test("previous on the first chapter starts it again rather than doing nothing", async (t) => {
  const page = await playing(t);
  page.seek(6000, { play: true });
  page.click("prevchapter");
  // There is no chapter before this one, and a button that does nothing at all
  // is indistinguishable from a page that has stopped working.
  assert.equal(page.probe().positionMs, 0);
  assert.equal(page.probe().chapter, "The First Tone");
});

test("the buttons and the lock screen are the same two functions", async (t) => {
  const byThumb = await playing(t);
  byThumb.click("nextchapter");
  byThumb.click("nextchapter");

  const byRemote = await playing(t);
  byRemote.press("nexttrack");
  byRemote.press("nexttrack");

  // The page and the notification cannot be allowed to drift: for most of the
  // night the lock screen is the only transport there is, and a skip that
  // meant one thing in the hand and another in the dark would be found out at
  // the worst possible moment.
  assert.equal(byThumb.probe().positionMs, byRemote.probe().positionMs);
  assert.equal(byThumb.probe().chapter, byRemote.probe().chapter);
  assert.equal(byThumb.probe().chapterClock, byRemote.probe().chapterClock);
});

test("skipping a chapter reports the seek once, at the top of the chapter", async (t) => {
  const page = await playing(t);
  await page.settle();
  const before = page.posts.length;
  page.click("nextchapter");
  page.audio.arrived();
  await page.settle();
  // One report, and it is a seek, which is what a press of this button is. It
  // used to be two — the skip loaded the chapter's own file, and a source
  // landing is reported as well — and two reports for one press is how the
  // later one comes to be refused if they ever disagree about the position. A
  // refusal is read as the agent having moved the book, which would carry
  // somebody somewhere nobody asked to go. There is nothing to load now, so
  // there is nothing to say twice.
  assert.deepEqual(
    page.posts.slice(before).map((p) => [p.body.reason, p.body.position_ms]),
    [["seek", 8000]],
  );
});

test("there is somewhere to skip to until the last chapter", async (t) => {
  const page = await playing(t);
  assert.equal(page.probe().canSkipOn, true);
  page.seek(8000, { play: true });
  assert.equal(page.probe().canSkipOn, true);
  page.seek(16_000, { play: true });
  assert.equal(page.probe().canSkipOn, false);
  // And back again: the book is still being read on some nights, and a chapter
  // that did not exist a minute ago is the normal case rather than the odd one.
  page.seek(4000, { play: true });
  assert.equal(page.probe().canSkipOn, true);
});
