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

// ------------------------------------------------------- across a boundary

test("a chapter boundary is playing like any other second", async (t) => {
  const page = await playing(t);
  // Straight across the boundary at the rate sound comes off the pipeline, and
  // then far enough for a heartbeat to carry where it got to.
  for (let tick = 0; tick < 18; tick++) page.audio.advance(0.5);
  page.posts.length = 0;
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  // Nine and a half seconds of book, boundary and all, reported as one place
  // on one clock. It used to be two reports and a discontinuity: a boundary
  // was a swap, and a swap stepped over four hundred milliseconds of rendered
  // silence. With the whole book down one URL there is nothing to step over.
  //
  // What the page used to say alongside this — how much of that stretch had
  // really come out of the speaker — is gone with the mark it was counted for
  // (ADR 10). The position was always the honest half of this report, and it is
  // now the whole of it.
  assert.deepEqual(
    page.posts.map((p) => [p.body.reason, p.body.position_ms]),
    [["tick", 9500]],
  );
  assert.equal("played_ms" in page.posts[0].body, false);
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
  // In the red: nothing is retrying and nothing is going to fix this, because
  // the book is out of the database. Somebody has to choose another one.
  assert.equal(page.probe().statusFailed, true);
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
  // And the new book is reported on in its own right, from its own place.
  page.audio.ready();
  await page.settle();
  const opened = page.posts.find((p) => p.body.gid === 900002);
  assert.equal(opened.body.position_ms, 4000);
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
