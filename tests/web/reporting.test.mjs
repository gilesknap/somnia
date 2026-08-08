// Where they have got to, and being told they are wrong about it.
//
// The page is the only thing that knows where the sound is while it plays, so
// saying so is not bookkeeping — it is the whole of somnia's memory of the
// night. The other half of the same conversation is the refusal: the only
// thing that can turn a report down is the agent having moved the book, and
// the refusal carries where to go instead. Everything below is one or the
// other, and the last three are the state-machine bugs three reviewers found
// in exactly this pair.

import assert from "node:assert/strict";
import { test } from "node:test";

import { boot } from "./harness.mjs";

async function playing(t, options) {
  const page = await boot(t, options);
  page.audio.ready();
  page.click("playpause");
  await page.settle();
  return page;
}

// ------------------------------------------------------------- the report gate

test("a book they only opened is never written down", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  page.tick(60_000);
  page.audio.fire("timeupdate");
  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  page.window.fire("pagehide");
  await page.settle();
  assert.deepEqual(page.posts, []);
  assert.deepEqual(page.beacons, []);
});

test("a seek is reported at once", async (t) => {
  const page = await playing(t);
  page.posts.length = 0;
  page.seek(4000);
  page.audio.fire("seeked");
  await page.settle();
  // A jump is the one thing the fifteen-second heartbeat cannot approximate:
  // between one tick and the next they may be an hour away.
  assert.deepEqual(page.reports(), [[900001, "seek", 4000]]);
  assert.equal(page.posts[0].body.seq, 0);
  // And nothing played to get there, which is how the server knows it for a
  // jump rather than for four seconds of listening.
  assert.equal(page.posts[0].body.played_ms, 0);
});

test("ticks between heartbeats say nothing, and the fifteenth second does", async (t) => {
  const page = await playing(t);
  page.posts.length = 0;
  page.audio.advance(0.5);
  page.audio.advance(0.5);
  assert.deepEqual(page.posts, []);
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.deepEqual(
    page.posts.map((p) => p.body.reason),
    ["tick"],
  );
});

test("a paused page does not tick", async (t) => {
  const page = await playing(t);
  page.click("playpause");
  await page.settle();
  page.posts.length = 0;
  page.tick(60_000);
  page.audio.fire("timeupdate");
  await page.settle();
  assert.deepEqual(page.posts, []);
});

test("a pause is reported however recent the last report was", async (t) => {
  const page = await playing(t);
  page.audio.advance(1);
  page.audio.advance(1);
  page.posts.length = 0;
  page.click("playpause");
  await page.settle();
  // Someone who pauses at 2am may not touch the phone again for a week, so
  // this is the position that has to be right.
  assert.deepEqual(
    page.posts.map((p) => p.body.reason),
    ["pause"],
  );
  assert.equal(page.posts[0].body.position_ms, 2000);
  // And it carries the second that played since the last report with it. A
  // pause is the best evidence there is that they listened up to here, and
  // throwing it away leaves the mark behind the position with no way back.
  assert.equal(page.posts[0].body.played_ms, 1000);
});

test("only one report is in flight at a time", async (t) => {
  const page = await playing(t);
  page.hold(true);
  page.posts.length = 0;
  page.seek(4000);
  page.audio.fire("seeked");
  await page.settle();
  page.seek(6000);
  page.audio.fire("seeked");
  await page.settle();
  assert.equal(page.posts.length, 1);
});

test("a report held back is built when it goes out, not when it was asked for", async (t) => {
  const page = await playing(t);
  page.hold(true);
  page.posts.length = 0;
  page.seek(4000);
  page.audio.fire("seeked"); // in flight
  await page.settle();
  page.seek(6000);
  page.audio.fire("seeked"); // owed
  // They kept moving while both were queued. A retry would deliver a stale
  // position over a newer one; what must not happen is the LAST position being
  // the one that got dropped.
  page.seek(9000);
  page.audio.arrived();
  page.hold(false);
  page.release();
  for (let turn = 0; turn < 4; turn++) await page.settle();
  assert.equal(page.posts.length, 2);
  assert.equal(page.posts[1].body.position_ms, 9000);
});

test("going into the background asks to outlive the page", async (t) => {
  const page = await playing(t);
  page.audio.advance(1);
  page.posts.length = 0;
  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  await page.settle();
  // From here the page can be frozen or discarded without warning, and this is
  // the last moment a normal request is certain to be allowed out.
  assert.deepEqual(
    page.posts.map((p) => p.body.reason),
    ["hidden"],
  );
  assert.equal(page.posts[0].keepalive, true);
});

test("the page says one last thing on its way out", async (t) => {
  const page = await playing(t);
  page.audio.advance(3);
  page.window.fire("pagehide");
  // fetch does not survive teardown — the document is gone before the
  // connection is made — but a beacon is the browser's promise to deliver
  // after the page has stopped existing.
  assert.equal(page.beacons.length, 1);
  assert.equal(page.beacons[0].url, "api/position");
  assert.equal(page.beacons[0].type, "application/json");
  assert.deepEqual(
    [page.beacons[0].body.reason, page.beacons[0].body.position_ms],
    ["unload", 3000],
  );
});

// ------------------------------------------------------- what really played

// The spoiler guard is on the other end of these. It cannot see the difference
// between fifteen seconds of listening and a fifteen-second jump — both arrive
// as a position further on than the last one — so the page is the thing that
// has to say which it was, and it says it by counting the media clock. What
// follows is every way that count can be got wrong.

test("a report says how much of the book has really played", async (t) => {
  const page = await playing(t);
  page.audio.advance(1);
  page.posts.length = 0;
  page.tick(15_000);
  page.audio.advance(1);
  await page.settle();
  assert.deepEqual(
    page.posts.map((p) => [p.body.position_ms, p.body.played_ms]),
    [[2000, 1000]],
  );
});

test("a jump moves the position and not the playback", async (t) => {
  const page = await playing(t);
  page.audio.advance(0.5);
  page.audio.advance(0.5);
  page.posts.length = 0;
  // Half a second of listening, and five and a half seconds of book. Whether
  // it was a thumb on +30, a scrub on the lock screen or the agent taking them
  // somewhere, the sound was not on for the distance.
  page.seek(6000);
  page.audio.fire("seeked");
  await page.settle();
  // Nothing at all, not even the half second: it was earned over the ground
  // behind the jump and can only justify standing there. Carried across, it
  // would be spent on the distance instead — which is what an agent move does
  // every time, because the move refuses the report in flight and the seek
  // that follows the refusal is the very next thing said.
  assert.deepEqual(
    page.posts.map((p) => [p.body.position_ms, p.body.played_ms]),
    [[6000, 0]],
  );
});

test("a refused report does not leave its playback to pay for the move", async (t) => {
  const page = await playing(t);
  page.audio.advance(0.5);
  page.audio.advance(0.5);
  page.reply({
    accepted: false,
    gid: 900001,
    position_ms: 6000,
    seq: 1,
    reason: "moved",
  });
  page.posts.length = 0;
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  page.audio.fire("seeked");
  await page.settle();
  const [refused, followed] = page.posts;
  assert.deepEqual(
    [refused.body.reason, refused.body.position_ms, refused.body.played_ms],
    ["tick", 1500, 1000],
  );
  // The same playback, arriving a moment later from four and a half seconds
  // further on, would have covered most of the move.
  assert.deepEqual(
    [followed.body.reason, followed.body.position_ms, followed.body.played_ms],
    ["seek", 6000, 0],
  );
});

test("playback a report never got out with is carried by the next one", async (t) => {
  const page = await playing(t);
  page.audio.advance(0.5);
  page.drop(true);
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  page.drop(false);
  page.posts.length = 0;
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  // A second of listening, in two heartbeats, one of which went nowhere. Spent
  // on the report that was never taken, the mark would be left half a second
  // behind the position — and a mark behind the position refuses everything
  // after it for the rest of the book.
  assert.deepEqual(
    page.posts.map((p) => p.body.played_ms),
    [1000],
  );
});

test("a chapter boundary is listening like any other second", async (t) => {
  const page = await playing(t);
  // Straight across the boundary at the rate sound comes off the pipeline, and
  // then far enough for a heartbeat to carry what it saw.
  for (let tick = 0; tick < 18; tick++) page.audio.advance(0.5);
  page.posts.length = 0;
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  // Nine and a half seconds of book, boundary and all, and every millisecond of
  // it after the first sample is claimed — that one is the baseline the rest are
  // measured from, and it is the only one the whole stretch costs.
  //
  // It used to cost a great deal more. A boundary was a swap, and a swap threw
  // the baseline away and stepped over four hundred milliseconds of rendered
  // silence, so the guard was told about a chapter change and about landing in
  // the new file, in two reports, with nothing played between them. With the
  // whole book down one URL there is no discontinuity to step over and nothing
  // to forgive: the media clock runs on, and what it says is what was heard.
  assert.deepEqual(
    page.posts.map((p) => [p.body.reason, p.body.position_ms, p.body.played_ms]),
    [["tick", 9500, 9000]],
  );
});

// ------------------------------------------------------------------- following

test("a refusal takes them where the agent said, and plays it", async (t) => {
  const page = await playing(t);
  page.reply({
    accepted: false,
    gid: 900001,
    position_ms: 20_000,
    seq: 3,
    reason: "moved",
  });
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.equal(page.probe().positionMs, 20_000);
  // A move the agent made is a seek like any other, and lands with nothing
  // loaded: twenty seconds into the book is twenty seconds into the file.
  assert.equal(page.audio.srcWrites.length, 1);
  assert.equal(page.audio.currentTime, 20);
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().chapter, "The Third Tone");
});

test("the next report carries the count the refusal gave it", async (t) => {
  const page = await playing(t);
  page.reply({
    accepted: false,
    gid: 900001,
    position_ms: 20_000,
    seq: 3,
    reason: "moved",
  });
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  page.audio.arrived();
  page.reply({ accepted: true, gid: 900001 });
  page.posts.length = 0;
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.equal(page.posts[0].body.seq, 3);
});

test("a move already applied moves nothing", async (t) => {
  const page = await playing(t);
  page.follow({ gid: 900001, position_ms: 20_000, seq: 3 });
  page.audio.arrived();
  // The same move arrives twice by design — the reply to the question that
  // caused it, and the refusal of the next report — so the second one has to
  // cost nothing.
  page.follow({ gid: 900001, position_ms: 4000, seq: 3 });
  assert.equal(page.probe().positionMs, 20_000);
  assert.equal(page.probe().seq, 3);
});

test("a move with no count in it is not a move", async (t) => {
  const page = await playing(t);
  page.follow(null);
  page.follow({ gid: 900001, position_ms: 4000 });
  assert.equal(page.probe().positionMs, 0);
});

test("a move to another book opens that book, at its own place", async (t) => {
  const page = await playing(t);
  page.follow({ gid: 900002, position_ms: 4000, seq: 7 });
  for (let turn = 0; turn < 3; turn++) await page.settle();
  page.audio.ready();
  // The move was written before the answer came back, so that book's manifest
  // already carries the new position and the new count: opening it *is*
  // following it.
  assert.equal(page.probe().gid, 900002);
  assert.equal(page.probe().positionMs, 4000);
  assert.equal(page.probe().seq, 7);
  assert.equal(page.probe().chapter, "Elsewhere One");
  assert.equal(page.probe().clock, "0:00:04 of 0:00:16");
  assert.equal(page.audio.paused, false);
});

test("a book that has gone stops the page talking about it", async (t) => {
  const page = await playing(t);
  page.reply({ accepted: false, gid: 900001, reason: "gone" });
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.equal(page.probe().status, "that book isn't here any more");
  // Whatever is still in the element can play out, but there is nothing left
  // to write to.
  page.posts.length = 0;
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.deepEqual(page.posts, []);
});

// ------------------------------------------------- what three reviewers found

test("following a book with no chapters yet leaves the book playing", async (t) => {
  const page = await playing(t);
  page.audio.advance(2);
  page.follow({ gid: 900003, position_ms: 0, seq: 1 });
  for (let turn = 0; turn < 3; turn++) await page.settle();
  // Adopting the manifest before checking it had chapters left the element
  // playing one book while every clock, seek and boundary read another book's
  // rows: the time said "of 0:00:00" and locate() threw on the next press of
  // anything for the rest of the night.
  assert.equal(page.probe().gid, 900001);
  assert.equal(page.probe().clock, "0:00:02 of 0:00:24");
  assert.equal(page.probe().status, "the first chapter is still being read");
  page.click("fwd30");
  assert.equal(page.probe().positionMs, 24_000);
  assert.equal(page.audio.srcWrites.at(-1), "api/stream/900001/3");
});

test("a refusal about the book they have left is ignored", async (t) => {
  const page = await playing(t);
  page.audio.advance(2);
  // A heartbeat about book A goes out and does not come back.
  page.hold(true);
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.equal(page.posts.at(-1).body.gid, 900001);
  // Meanwhile the agent moves them to book B and the page follows.
  page.follow({ gid: 900002, position_ms: 4000, seq: 7 });
  for (let turn = 0; turn < 3; turn++) await page.settle();
  page.audio.ready();
  assert.equal(page.probe().gid, 900002);
  // The report about A comes back refused: the agent moved A as well. Reading
  // that as "go here" would take them straight back to the book they were just
  // taken out of.
  page.reply({
    accepted: false,
    gid: 900001,
    position_ms: 21_000,
    seq: 5,
    reason: "moved",
  });
  page.hold(false);
  page.release();
  for (let turn = 0; turn < 4; turn++) await page.settle();
  assert.equal(page.probe().gid, 900002);
  assert.equal(page.probe().positionMs, 4000);
  assert.equal(page.probe().chapter, "Elsewhere One");
});

test("a book that is gone cannot silence the book they are on now", async (t) => {
  const page = await playing(t);
  page.audio.advance(2);
  page.hold(true);
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  page.follow({ gid: 900002, position_ms: 4000, seq: 7 });
  for (let turn = 0; turn < 3; turn++) await page.settle();
  page.audio.ready();
  page.reply({ accepted: false, gid: 900001, reason: "gone" });
  page.hold(false);
  page.release();
  for (let turn = 0; turn < 4; turn++) await page.settle();
  // A stale "gone" about the book they left must not null out the gid of the
  // one they are on, or the rest of the night goes unrecorded.
  assert.equal(page.probe().gid, 900002);
  page.posts.length = 0;
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.deepEqual(
    page.posts.map((p) => p.body.gid),
    [900002],
  );
});

test("the book they are taken out of is left where they got to", async (t) => {
  const page = await playing(t);
  page.posts.length = 0;
  for (let tick = 0; tick < 12; tick++) page.audio.advance(0.5);
  // Six seconds of listening, and no heartbeat due: the pause a swap fires is
  // swallowed as spurious, so without a parting word this book would keep
  // whatever position its last heartbeat happened to catch.
  assert.deepEqual(page.posts, []);
  page.follow({ gid: 900002, position_ms: 4000, seq: 7 });
  for (let turn = 0; turn < 3; turn++) await page.settle();
  const parting = page.posts.find((p) => p.body.gid === 900001);
  assert.deepEqual(
    [parting.body.reason, parting.body.position_ms],
    ["switch", 6000],
  );
  // And the playback that belongs to it goes with it, because this is the last
  // chance to say so: a mark left behind the position they were left at would
  // refuse everything they play the next time they open this book.
  assert.equal(parting.body.played_ms, 5500);
  // None of which is the new book's. The first thing said about that one
  // claims nothing, or six seconds of somewhere else would be six seconds of
  // it that nobody has heard.
  page.audio.ready();
  await page.settle();
  const opened = page.posts.find((p) => p.body.gid === 900002);
  assert.equal(opened.body.played_ms, 0);
});

test("a book they only opened is not written down when they leave it", async (t) => {
  const page = await boot(t);
  page.audio.ready();
  page.follow({ gid: 900002, position_ms: 4000, seq: 7 });
  for (let turn = 0; turn < 3; turn++) await page.settle();
  assert.equal(page.probe().gid, 900002);
  assert.deepEqual(
    page.posts.filter((p) => p.body.gid === 900001),
    [],
  );
});

test("being moved inside the same book parts from nothing", async (t) => {
  const page = await playing(t);
  page.audio.advance(1);
  page.posts.length = 0;
  await page.openBook(900001, { play: true });
  for (let turn = 0; turn < 3; turn++) await page.settle();
  assert.equal(
    page.posts.some((p) => p.body.reason === "switch"),
    false,
  );
});
