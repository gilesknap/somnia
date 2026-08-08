// The books panel.
//
// The one screen has gained a second overlay, and the argument for it is
// weaker than the argument for the first: a list of places answers a question
// the listener just asked, whereas this is a thing somebody goes looking for.
// So it is held to the same three promises the list is held to, and to two more
// of its own.
//
// The three: the book plays underneath it, nothing has moved while it is up,
// and `close` puts it away having changed nothing at all — including the tap
// that a refused play was waiting for, which the panel borrows and gives back.
//
// The two: it costs nothing when nobody is looking at it, which means no
// request before it is opened, no wake after it is closed, and no wake at all
// while the page is in somebody's pocket; and the presses that do change the
// night are exactly the ones on a book, so everything else on it can be
// pressed in the dark and cost nothing.
//
// It used to be that nothing on this panel opened a book, and that was held to
// be what kept ADR 3's "changing books is done by asking" literally true. The
// ADR's amendment is what changed: what it objected to was browsing a library
// to find something new, which is the search at the foot of this panel and is
// still a separate act. Tapping one of the books you already have is not that,
// and the shelf's own section below is about the promises that press keeps —
// the book left behind keeps its position, the switch reaches the server before
// anything else can fail, and nothing about it looks like an agent move.
//
// Everything below is about those. The words on the rows get one test each
// because they are the whole of what the panel is for — at 2am the difference
// between "not responding" and "chapter 4 of 39" is the difference between
// getting up and going back to sleep.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  boot,
  EVERY_BOOK,
  GROWING_BOOK,
  HALF_HEARD,
  listed,
  OTHER_BOOK,
  PART_READ,
  RENDERING_BOOK,
  TONE_BOOK,
  UNCOUNTED_BOOK,
} from "./harness.mjs";

// How often the panel asks, in the page's own units. Named here so that a test
// which asserts the wake and a test which fires it cannot drift apart.
const POLL_MS = 5000;

// How long the first press of `stop reading this` stands, before the button
// forgets it was ever asked.
const CONFIRM_MS = 5000;

// How long the page's second voice says a thing for. Named here because a press
// that opens a book leaves exactly this one wake behind it, and "nothing is
// scheduled" has to be able to tell that from a poll still running.
const TOAST_MS = 2800;

// A rendering job, as queue.view hands one over: chapters counted from the
// chapters table, a total that is 0 until the parse wrote it down, and a
// `responding` derived from a heartbeat the page never sees.
function job(overrides = {}) {
  return {
    id: 1,
    gid: 271,
    title: "Black Beauty",
    authors: "Anna Sewell",
    state: "rendering",
    place: 0,
    chapters_done: 3,
    chapters_total: 39,
    rendered_ms: 4_320_000,
    stopping: false,
    responding: true,
    error: "",
    submitted_at: "2026-08-06 21:00:00",
    started_at: "2026-08-06 21:00:10",
    ...overrides,
  };
}

function waiting(overrides = {}) {
  return job({
    id: 2,
    gid: 120,
    title: "Treasure Island",
    authors: "Robert Louis Stevenson",
    state: "queued",
    place: 1,
    chapters_done: 0,
    chapters_total: 0,
    rendered_ms: 0,
    started_at: "",
    ...overrides,
  });
}

function entry(overrides = {}) {
  return {
    gid: 120,
    title: "Treasure Island",
    authors: "Robert Louis Stevenson",
    have: null,
    ...overrides,
  };
}

// The page, open on a finished book, having played nothing. Nothing is waiting
// on a timer in this state, which is what makes "the only wake pending is the
// poll" an assertion rather than a hope.
async function opened(t, options) {
  const page = await boot(t, { lastGid: HALF_HEARD.gid, ...options });
  page.audio.ready(1800);
  return page;
}

async function playing(t, options) {
  const page = await opened(t, options);
  page.click("playpause");
  await page.settle();
  return page;
}

// Open Books and let its one fetch — the shelf — land.
async function books(page) {
  page.click("books");
  await page.settle();
  await page.settle();
  return page;
}

// And on to Workshop, which is where the queue lives now. Two presses, because
// that is what it is: the render queue is daytime work and Books is the night
// screen it is reached through.
async function workshop(page) {
  await books(page);
  page.click("to-workshop");
  await page.settle();
  await page.settle();
  return page;
}

// The one part of a row, wherever the drawing put it. A row is a small tree
// now — a line with the name and the stage at either end of it, a line under
// them, a hairline, an action — and a helper that indexed children by position
// would break on the next wrapper and pass on the one after it.
function part(node, name) {
  if (node.classList.contains(name)) return node;
  for (const child of node.children) {
    const found = part(child, name);
    if (found) return found;
  }
  return null;
}

function words(node, name) {
  // Null rather than "" so a row that has no such part and a row whose part has
  // lost its words cannot be mistaken for each other.
  const found = part(node, name);
  return found ? found.textContent : null;
}

// The rows, as somebody looking at them would read them out. Read out of the
// DOM rather than out of the payload: what the server said is its own business,
// and the only thing worth asserting is what ended up on the screen.
//
// `stage` is the word in the corner — which of somnia's four states this is —
// and `state` is the line under the name, which is what is actually happening
// inside that state. `bar` is the width of the progress hairline, or null where
// there is no hairline at all, which is the whole of the guard against drawing
// a lying 0%.
function jobs(page, id = "queue-live") {
  return page.el(id).children.map((li) => ({
    name: words(li, "job-name"),
    stage: words(li, "job-stage"),
    state: words(li, "job-state"),
    bar: part(li, "job-fill")?.style.width ?? null,
    stop: words(li, "job-stop"),
  }));
}

function results(page) {
  return page.el("queue-results").children.map((li) => ({
    name: words(li, "found-name"),
    by: words(li, "found-by"),
    have: words(li, "found-have"),
    add: words(li, "found-add"),
  }));
}

// Everything a night is, plus everything a night leaves behind. Close promises
// all of it back unchanged, so all of it is snapshotted — the same shape
// choosing.test.mjs holds cancel to.
function night(page) {
  return {
    probe: page.probe(),
    posts: page.posts.length,
    beacons: page.beacons.length,
    order: page.order.length,
    srcWrites: page.audio.srcWrites.length,
    currentTime: page.audio.currentTime,
    paused: page.audio.paused,
    playCalls: page.audio.playCalls,
  };
}

async function search(page, text) {
  page.el("queue-query").value = text;
  page.el("queue-search").fire("submit", { preventDefault() {} });
  await page.settle();
  await page.settle();
}

// ------------------------------------------------------- costing nothing shut

test("nothing asks about the queue until somebody opens the panel", async (t) => {
  const page = await opened(t);
  assert.equal(page.probe().queueUp, false);
  assert.equal(page.probe().queuePolling, false);
  assert.equal(
    page.fetches.some((url) => url.startsWith("api/queue")),
    false,
  );
  // And no wake is pending either: a page nobody has opened the panel on is a
  // page with nothing to do about the queue, all night.
  assert.deepEqual(page.waits(), []);
});

// The night screen does not ask either, and that is the runtime half of the
// split. Somebody who opens Books at 2am to change books gets one request for
// the shelf and then silence — no five-second wake, no radio, nothing. The
// queue is a daytime list and it is only asked for on the daytime screen.
test("Books asks for the shelf and nothing else, and schedules no wake", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  const before = page.fetches.length;
  await books(page);
  assert.equal(page.probe().queueUp, true);
  assert.equal(page.probe().workshopUp, false);
  assert.deepEqual(page.fetches.slice(before), ["api/books"]);
  assert.equal(page.probe().queuePolling, false);
  assert.deepEqual(page.waits(), []);
});

test("opening Workshop asks once at once and then every five seconds", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  assert.equal(page.probe().workshopUp, true);
  assert.equal(
    page.fetches.filter((url) => url === "api/queue").length,
    1,
    "the screen asks the moment it goes up, rather than five seconds later",
  );
  // The only wake pending is its own, and it is the five seconds the page says
  // it is.
  assert.deepEqual(page.waits(), [POLL_MS]);
  assert.equal(page.wake(POLL_MS), true);
  await page.settle();
  await page.settle();
  assert.equal(page.fetches.filter((url) => url === "api/queue").length, 2);
  assert.deepEqual(page.waits(), [POLL_MS]);
});

test("closing Workshop stops the asking and leaves no wake behind", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  page.click("workshop-close");
  await page.settle();
  assert.equal(page.probe().workshopUp, false);
  // Books is still standing behind it. `‹ books` is a close, not a route back.
  assert.equal(page.probe().queueUp, true);
  assert.equal(page.probe().queuePolling, false);
  // Not merely "stopped": a wake still scheduled is a radio waking every five
  // seconds all night beside somebody asleep.
  assert.deepEqual(page.waits(), []);
  const asked = page.fetches.filter((url) => url === "api/queue").length;
  await page.settle();
  assert.equal(page.fetches.filter((url) => url === "api/queue").length, asked);
});

// The one state the page cannot be left in. Nothing opens Workshop without
// opening Books first, so leaving Books while Workshop is up is not reachable
// by any press — and it is guarded anyway, because a screen standing over a
// panel that has gone would have no way out of it at all.
test("Workshop cannot outlive the screen it was opened from", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  page.click("queue-close");
  await page.settle();
  assert.equal(page.probe().workshopUp, false);
  assert.equal(page.probe().queueUp, false);
  assert.equal(page.probe().queuePolling, false);
  assert.deepEqual(page.waits(), []);
});

test("the phone going in a pocket stops it, and coming back starts it", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  const asked = () => page.fetches.filter((url) => url === "api/queue").length;

  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  await page.settle();
  // A hidden page's timers are throttled to roughly one wake a minute, which is
  // untimely exactly when nobody is watching. Nothing is pending.
  assert.equal(page.probe().queuePolling, false);
  assert.deepEqual(page.waits(), []);
  const quiet = asked();

  page.document.visibilityState = "visible";
  page.document.fire("visibilitychange");
  await page.settle();
  await page.settle();
  // Back in front of them, and the queue may have moved on entirely while the
  // phone was asleep, so this asks now rather than in five seconds.
  assert.equal(asked(), quiet + 1);
  assert.deepEqual(page.waits(), [POLL_MS]);
});

test("a page coming back with both screens shut asks nothing", async (t) => {
  const page = await opened(t);
  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  page.document.visibilityState = "visible";
  page.document.fire("visibilitychange");
  await page.settle();
  await page.settle();
  assert.equal(
    page.fetches.some((url) => url.startsWith("api/queue")),
    false,
  );
  assert.deepEqual(page.waits(), []);
});

// -------------------------------------------------------------------- inert

test("close leaves a night that never started exactly as it found it", async (t) => {
  const page = await opened(t);
  page.queueView([job(), waiting()]);
  const before = night(page);
  await books(page);
  assert.equal(page.probe().queueUp, true);
  page.click("queue-close");
  await page.settle();
  const after = night(page);
  assert.deepEqual(after.probe, before.probe);
  assert.equal(after.posts, before.posts);
  assert.equal(after.beacons, before.beacons);
  assert.equal(after.order, before.order);
  assert.equal(after.srcWrites, before.srcWrites);
  assert.equal(after.currentTime, before.currentTime);
  assert.equal(after.playCalls, before.playCalls);
  // A book that was only ever opened is still a book that was only ever opened.
  assert.equal(page.probe().untouched, true);
  assert.deepEqual(page.posts, []);
  assert.deepEqual(page.beacons, []);
});

test("the two screens ask about two lists, and about no book", async (t) => {
  const page = await playing(t);
  const before = page.fetches.length;
  page.queueView([job(), waiting()]);
  await workshop(page);
  page.wake(POLL_MS);
  await page.settle();
  page.click("queue-close");
  await page.settle();
  // Every request the two screens made, and there is nothing else in the list.
  // Books asks which books there are; Workshop asks for the queue and goes on
  // asking. Neither of them is `api/book/{gid}`: two in-flight manifests can
  // leave `current` holding a row from a manifest that is no longer the
  // manifest. Nor is either of them api/position, which is the one thing on
  // this page that can move somebody backwards.
  assert.deepEqual(
    page.fetches.slice(before),
    ["api/books", "api/queue", "api/queue"],
    "each screen reads its own list and neither asks about a book",
  );
});

test("a book waiting for a touch is still waiting after close", async (t) => {
  const page = await opened(t);
  // The app was backgrounded and the platform refused the sound until it is
  // touched: the real 2am sequence, and the reason showQueue borrows the
  // listener at all.
  page.audio.refuse = "NotAllowedError";
  page.click("playpause");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");
  const playCalls = page.audio.playCalls;

  page.queueView([job()]);
  await books(page);
  // With the listener still armed the first press anywhere on this overlay
  // would have started the book — `close` especially, the one control that
  // promises to change nothing.
  page.document.fire("pointerdown");
  assert.equal(page.audio.playCalls, playCalls);
  assert.equal(page.audio.paused, true);

  page.click("queue-close");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");
  page.audio.refuse = null;
  page.document.fire("pointerdown");
  await page.settle();
  assert.equal(page.audio.paused, false);
});

test("a render finishing under the panel ends nobody's night", async (t) => {
  const page = await playing(t, {
    stored: { "somnia-sleep": JSON.stringify({ choice: 3, leftMs: 1_800_000 }) },
  });
  page.queueView([job()]);
  await books(page);
  const before = page.probe();
  const reports = page.posts.length;
  assert.equal(before.wantsSound, true);

  // The book somebody else's press queued has finished. The panel is a readout
  // of that and nothing else: sharing the ladder that watches THIS book grow
  // would have cleared wantsSound and thrown away the sleep timer because an
  // unrelated render stopped being 'rendering'.
  page.queueView([job({ state: "done", chapters_done: 39 })]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(page.probe().wantsSound, true);
  assert.equal(page.probe().sleepLeftMs, before.sleepLeftMs);
  assert.equal(page.probe().armed, before.armed);
  assert.equal(page.probe().status, before.status);
  assert.equal(page.posts.length, reports);
});

test("the panel survives an agent answer and a move without closing", async (t) => {
  const page = await playing(t);
  page.queueView([job()]);
  await books(page);

  page.answers({ reply: "Ginger is the chestnut mare in the next box." });
  await page.ask("who is ginger");
  assert.equal(page.probe().queueUp, true);

  // And a move the agent made by the other route, which takes a list of places
  // down because those rows would be lying about where the book is. This panel
  // says nothing about where the book is, holds no payload, and has nothing to
  // be stale about — so none of the six closeCandidates() call sites grows a
  // twin.
  page.reply({
    accepted: false,
    gid: HALF_HEARD.gid,
    position_ms: 2_000_000,
    seq: 3,
    reason: "moved",
  });
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.equal(page.probe().positionMs, 2_000_000);
  assert.equal(page.probe().queueUp, true);
});

// -------------------------------------------------------------- reading now

// The block at the top of the panel, as somebody opening it in the dark would
// read it: the label over it, which book is playing under this, the line under
// that, and whether there is a hairline at all and how far it has got.
//
// There is no `press` in here any more, because there is no button: the block
// itself is the press. What it would have said is in `meta` — see the block's
// comment in index.html.
//
// `bar` is null where no hairline is drawn, which is the whole of the guard
// against a bar that over-reads: while a book is still arriving, total_ms is
// how much of it exists rather than how long it is.
function reading(page) {
  return {
    up: !page.el("reading-now").hidden,
    label: page.el("reading-label").textContent,
    title: page.el("reading-title").textContent,
    meta: page.el("reading-meta").textContent,
    bar: page.el("reading-track").hidden
      ? null
      : page.el("reading-fill").style.width,
  };
}

test("Books names the book playing under it, by its title alone", async (t) => {
  const page = await boot(t, { lastGid: GROWING_BOOK.gid });
  page.audio.ready(600);
  page.queueView([]);
  await books(page);
  assert.deepEqual(reading(page), {
    up: true,
    // Paused, so the block is offering to start it.
    label: "reading now",
    // The title, and nothing else. This block used to read
    // `The Moonstone — Collins, Wilkie, 1824-1889 · Reade, Charles, 1814-1884`,
    // which was right at 21dp on a panel doing eight jobs and is three lines of
    // a night screen at 29. Who wrote it is catalogue metadata about a book
    // somebody already owns and chose; where it earns its room is Workshop's
    // search results, and that is the only list in the app that carries it now.
    title: "The Moonstone",
    // Where the press lands, which is what the pill under this block used to
    // say. Not `30m in`, which is what this line said while the pill was
    // holding the time: a place is more use than a distance, and the line is
    // free to say it now.
    meta: "chapter 4 of 37 · picks up at 0:30:00",
    // Five chapters of thirty-seven have audio, so total_ms is how much exists
    // and not how long the book is.
    bar: null,
  });
});

test("a book nobody counted says which chapter it is in and stops there", async (t) => {
  const page = await boot(t, { lastGid: UNCOUNTED_BOOK.gid });
  page.audio.ready(8);
  page.queueView([]);
  await books(page);
  // The same guard the player's own count carries, and for the same reason: 0
  // means nobody wrote the number down, which is every book rendered before the
  // column existed. `chapter 1 of 0` is the sentence this prevents — and the
  // half of the line that is still true is still said.
  assert.equal(reading(page).meta, "chapter 1 · picks up at 0:00:00");
  // Nothing is in front of the mark that has not been rendered — the book is
  // finished — so the hairline is honest here even without a denominator for
  // the chapters.
  assert.equal(reading(page).bar, "0%");
});

test("a book still arriving gets no hairline rather than one that over-reads", async (t) => {
  const growing = await boot(t, { lastGid: GROWING_BOOK.gid });
  growing.audio.ready(600);
  await books(growing);
  assert.equal(reading(growing).bar, null);

  // The same lie from the other direction: this render stopped at one chapter
  // of three and nothing is going to add the other two, so total_ms is a third
  // of the book and a bar drawn from it would reach the end at a third of the
  // way through.
  const stopped = await boot(t, { lastGid: PART_READ.gid });
  stopped.audio.ready(8);
  await books(stopped);
  assert.equal(reading(stopped).bar, null);

  // And a book that is all here, where the fraction means what it looks like.
  const whole = await opened(t);
  await books(whole);
  assert.equal(reading(whole).bar, "27.8%");
});

test("tapping the block starts the book and takes the panel away with it", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  assert.equal(reading(page).meta, "chapter 1 of 2 · picks up at 0:16:40");

  page.click("reading-open");
  await page.settle();
  assert.equal(page.audio.paused, false);
  // The panel is the thing they were on their way through, not the thing they
  // came for. It goes with the press rather than being left over a book that
  // has just started sounding.
  assert.equal(page.probe().queueUp, false);
  assert.equal(page.probe().queuePolling, false);
  // And nothing is left waiting: a poll still scheduled is a radio wake every
  // five seconds all night beside somebody asleep.
  assert.deepEqual(page.waits(), []);
});

test("a book already sounding is offered back rather than started again", async (t) => {
  const page = await playing(t);
  page.queueView([job()]);
  await books(page);
  // No time offered, because there is nothing to move to — and the label over
  // the block says the same thing at a glance.
  assert.equal(reading(page).meta, "chapter 1 of 2 · playing");
  assert.equal(reading(page).label, "playing now");
  const playCalls = page.audio.playCalls;

  page.click("reading-open");
  await page.settle();
  // Nothing to start. The press is the way back to the controls and that is
  // all it is, which is what the line said it would be.
  assert.equal(page.audio.playCalls, playCalls);
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().queueUp, false);
});

test("picking it up leaves no tap waiting over a book that is now playing", async (t) => {
  const page = await opened(t);
  // The real 2am sequence: the app was backgrounded, the platform refused the
  // sound until the screen is touched, and the panel borrowed that listener
  // when it went up.
  page.audio.refuse = "NotAllowedError";
  page.click("playpause");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");

  page.queueView([job()]);
  await books(page);
  page.audio.refuse = null;
  page.click("reading-open");
  await page.settle();
  assert.equal(page.audio.paused, false);

  // `close` hands that listener back, because after close the book really is
  // still paused and still waiting. This press is not close: it IS the touch
  // the platform was waiting for, and re-arming here would leave a listener
  // over a book that is already sounding — so the next thing touched anywhere
  // on the page would start it a second time.
  const playCalls = page.audio.playCalls;
  page.document.fire("pointerdown");
  await page.settle();
  assert.equal(page.audio.playCalls, playCalls);
});

test("with no book open the block goes rather than standing empty", async (t) => {
  const page = await boot(t, { lastGid: null, library: [] });
  page.queueView([]);
  await books(page);
  // The same rule the card of live rows follows: a heading over nothing is a
  // claim that something should be there, which at 2am is a reason to get up.
  assert.equal(page.el("reading-now").hidden, true);
});

// ------------------------------------------------------------ on the shelf

// The books somnia already has, under the one it is playing, each a press that
// resumes it where it was left.
//
// The rows are read out of the DOM, as the queue's are: what /api/books said is
// its own business and the only thing worth asserting is what somebody would
// read in the dark. `opens` is false where the row is not a press at all, which
// is the whole of the guard against a book nobody can play yet being offered
// and then refused — and since the press is the row rather than a pill on the
// end of it, what says so is the tag rather than a label.
function shelf(page) {
  return page.el("shelf").children.map((li) => ({
    name: words(li, "shelved-name"),
    meta: words(li, "shelved-meta"),
    bar: part(li, "shelved-fill")?.style.width ?? null,
    opens: part(li, "shelved-open")?.tagName === "BUTTON",
  }));
}

// A press on a shelf row, and everything it sets off: the server being told,
// the manifest, the parting position of the book being left, and the first
// chapter of the new one.
async function pick(page, gid) {
  page.click(`shelf-open-${gid}`);
  for (let turn = 0; turn < 4; turn++) await page.settle();
}

test("the shelf says where each book was left and what is happening to it", async (t) => {
  const page = await opened(t, {
    library: [OTHER_BOOK, GROWING_BOOK, PART_READ, RENDERING_BOOK].map(listed),
  });
  page.queueView([]);
  await books(page);
  assert.deepEqual(shelf(page), [
    {
      name: "Another Book",
      // Where that book was left, on its own clock, which is the whole
      // question a shelf answers that a list of titles does not.
      meta: "0:00:04 in",
      bar: "25%",
      opens: true,
    },
    {
      // The title alone, as `reading now` above it, out of one function. Two
      // authors held apart by the page's own separator is what this row used to
      // say and is Workshop's job now — a shelf is read in the dark to
      // recognise a book you already own, and the title is what does that.
      name: "The Moonstone",
      // Still arriving, so no hairline: total_ms is how much of it exists
      // rather than how long it is, and a bar drawn from that reaches the end
      // at chapter five of thirty-seven.
      meta: "0:30:00 in · being read now",
      bar: null,
      opens: true,
    },
    {
      // A render that stopped part way. It plays, so it is offered — and it
      // says what it is in the same words the search results below use for it.
      name: "Stopped Part Way",
      meta: "0:00:00 in · part rendered",
      bar: null,
      opens: true,
    },
    {
      // Nothing to play at all. Marked rather than offered and then refused: a
      // press that was never available cannot be a press that did nothing. The
      // row is a plain div, so there is nothing on it to land on.
      name: "Still Being Read",
      meta: "the first chapter is still being read",
      bar: null,
      opens: false,
    },
  ]);
});

test("a book nobody has started says so rather than saying 0:00:00", async (t) => {
  const page = await opened(t, { library: [TONE_BOOK].map(listed) });
  page.queueView([]);
  await books(page);
  // "never started" and "at the very beginning" are different answers to
  // "where am I?", and the manifest keeps them apart with a null. So does this.
  assert.equal(shelf(page)[0].meta, "not started");
  // And there is nothing to draw a hairline from either, where every other row
  // has one: an empty track reads as a book at zero rather than at nothing.
  assert.equal(shelf(page)[0].bar, null);
});

test("the book playing underneath is not on the shelf as well", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  // It is the block above, with a press of its own that says where it lands.
  // A second row for it would be two controls doing one thing — and the row
  // would be the worse of them, because it would adopt the server's copy of
  // the position, which is up to fifteen seconds behind the sound.
  assert.equal(reading(page).title, "Half Heard");
  assert.equal(
    shelf(page).some((row) => row.name.startsWith("Half Heard")),
    false,
  );
  // Every other book somnia has is there, though — counted from the library
  // the page was booted with, so a fixture added to it moves this with it.
  assert.equal(shelf(page).length, EVERY_BOOK.length - 1);
});

test("a shelf row is opened where it was left, and takes the panel with it", async (t) => {
  const page = await playing(t);
  page.queueView([]);
  await books(page);
  await pick(page, OTHER_BOOK.gid);

  // The server is told before anything else is asked, which is the half of
  // this that outlives the tab: a page discarded a second later comes back on
  // the book they chose rather than the one they left.
  assert.deepEqual(
    page.fetches.filter((url) => url.includes(String(OTHER_BOOK.gid))),
    [`api/book/${OTHER_BOOK.gid}/open`, `api/book/${OTHER_BOOK.gid}`],
  );
  assert.equal(page.probe().gid, OTHER_BOOK.gid);
  assert.equal(page.probe().positionMs, OTHER_BOOK.position_ms);
  // The count comes from that book's own manifest. Nothing about this press is
  // an agent move, so the page is in step with the server and its next report
  // is taken rather than refused.
  assert.equal(page.probe().seq, OTHER_BOOK.seq);
  assert.equal(page.audio.paused, false);
  // The last word about the book being left, sent while it was still this
  // page's book — otherwise it would keep whatever its last heartbeat caught.
  assert.deepEqual(
    page.reports().filter((report) => report[1] === "switch"),
    [[HALF_HEARD.gid, "switch", HALF_HEARD.position_ms]],
  );
  // The panel goes with the press, the same as `pick it up` — the question it
  // was opened with has just been answered.
  assert.equal(page.probe().queueUp, false);
  assert.equal(page.probe().toast, "opened · Another Book");
  // And the panel's poll went with it. The one wake left is that sentence
  // taking itself off again, which is the only thing on the page still owed
  // anything — a poll left running is a radio wake every five seconds all
  // night beside somebody asleep.
  assert.deepEqual(page.waits(), [TOAST_MS]);
});

test("each book keeps its own place, so changing your mind costs one press", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  await pick(page, OTHER_BOOK.gid);
  assert.equal(page.probe().positionMs, OTHER_BOOK.position_ms);

  // And back, which is the whole argument for letting a thumb do this at all:
  // nothing was written to the book they left, so it is exactly where it was.
  await books(page);
  assert.equal(
    shelf(page).some((row) => row.name.startsWith("Half Heard")),
    true,
  );
  await pick(page, HALF_HEARD.gid);
  assert.equal(page.probe().gid, HALF_HEARD.gid);
  assert.equal(page.probe().positionMs, HALF_HEARD.position_ms);
});

test("a switch the server will not make leaves the night where it was", async (t) => {
  const page = await playing(t);
  page.queueView([]);
  await books(page);
  // What the server answers for a book there is nothing to play of, and for a
  // book that is not there at all — a page holding a list from a database that
  // has moved on.
  page.refuseToOpen(true);
  await pick(page, OTHER_BOOK.gid);
  assert.deepEqual(page.opens, [`api/book/${OTHER_BOOK.gid}/open`]);
  // Nothing was asked about that book and nobody was moved to it. The order is
  // what buys this: the page does not leave the book it is on until the switch
  // it depends on has really been made.
  assert.equal(page.fetches.includes(`api/book/${OTHER_BOOK.gid}`), false);
  assert.equal(page.probe().gid, HALF_HEARD.gid);
  assert.equal(page.audio.paused, false);
  // Said where somebody standing on the shelf can read it. The panel's own
  // line is the foot of a scroller three screens below this press, and #status
  // is under the panel — so the sentence goes in the voice that lies over both
  // overlays, at the bottom by the thumb, which is where the same press says
  // `opened` when it works.
  assert.equal(page.probe().toast, "couldn't reach that book");
  assert.equal(page.el("queue-said").textContent, "");
  assert.equal(page.probe().queueUp, true);
  assert.equal(page.el(`shelf-open-${OTHER_BOOK.gid}`).disabled, false);

  // The tailnet eating the request outright is the same answer, because from
  // here the two are the same thing: the switch did not happen.
  page.refuseToOpen(false);
  page.unreachable({ open: true });
  await pick(page, OTHER_BOOK.gid);
  assert.equal(page.probe().gid, HALF_HEARD.gid);
  assert.equal(page.probe().toast, "couldn't reach that book");
});

test("a row the agent has moved them onto presses through to pick it up", async (t) => {
  const page = await playing(t);
  page.queueView([]);
  await books(page);
  // The one thing on this panel that can go stale under somebody: the shelf is
  // drawn when they arrive, and the agent can move the night to one of its
  // books while they are still reading it. The row is not redrawn — nothing on
  // this panel redraws under a thumb — so the press is what has to be right.
  page.answers({
    reply: "Taking you there.",
    move: { gid: OTHER_BOOK.gid, position_ms: 4_000, seq: 9 },
  });
  await page.ask("take me to the other book");
  await page.settle();
  assert.equal(page.probe().gid, OTHER_BOOK.gid);
  assert.equal(page.probe().queueUp, true);

  const before = page.opens.length;
  await pick(page, OTHER_BOOK.gid);
  // Nothing is asked and nothing is opened. Re-opening would adopt the
  // server's copy of the position, which is up to fifteen seconds behind the
  // sound — so a press on the book already playing is the press above it,
  // which starts it where it is and takes the panel away.
  assert.equal(page.opens.length, before);
  assert.equal(page.probe().positionMs, 4_000);
  assert.equal(page.probe().queueUp, false);
  assert.equal(page.audio.paused, false);
});

test("a book cannot be opened twice by pressing twice", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  page.click(`shelf-open-${OTHER_BOOK.gid}`);
  page.click(`shelf-open-${OTHER_BOOK.gid}`);
  for (let turn = 0; turn < 4; turn++) await page.settle();
  // Two presses a frame apart are the ordinary way a thumb double-taps
  // something that has not answered yet, and the second of them would be a
  // second switch: another parting report, and the book opened underneath
  // itself at the position the first press had already left.
  assert.deepEqual(page.opens, [`api/book/${OTHER_BOOK.gid}/open`]);
});

test("the shelf is asked for when somebody arrives, not every five seconds", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  const asked = () => page.fetches.filter((url) => url === "api/books").length;
  const atBoot = asked();
  await books(page);
  assert.equal(asked(), atBoot + 1);

  // A shelf changes when a render finishes, which is hours; the queue changes
  // while somebody watches it, which is why only one of the two is worth a
  // request every five seconds.
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(asked(), atBoot + 1);

  // Coming back to a phone that has been in a pocket is the other moment
  // somebody is looking, and by then a render may have finished.
  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  page.document.visibilityState = "visible";
  page.document.fire("visibilitychange");
  await page.settle();
  await page.settle();
  assert.equal(asked(), atBoot + 2);
});

test("a shelf that could not be asked for again is left exactly as it was", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  const drawn = shelf(page);
  assert.equal(drawn.length > 0, true);

  // The phone went in a pocket and came back, and by then the tailnet has gone.
  page.unreachable({ queue: true, books: true });
  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  page.document.visibilityState = "visible";
  page.document.fire("visibilitychange");
  await page.settle();
  await page.settle();
  // An empty shelf and an unreachable server look identical and mean opposite
  // things, so the rows are left exactly as they were — and this screen's own
  // line of doubt is what says which of the two this is. It has one now: the
  // queue's line went to Workshop with the queue, and the shelf cannot borrow a
  // sentence from a screen nobody is looking at.
  assert.deepEqual(shelf(page), drawn);
  assert.equal(page.el("shelf-note").textContent, "couldn't reach somnia");

  // A panel opened for the first time on a server that cannot be reached has
  // nothing to leave up, because close forgets the shelf on purpose. What keeps
  // the empty list from reading as "one book" is the same line.
  page.click("queue-close");
  await page.settle();
  await books(page);
  assert.deepEqual(shelf(page), []);
  assert.equal(page.el("shelf-note").textContent, "couldn't reach somnia");
});

// And the same line goes when the box comes back, rather than standing over a
// shelf that has just been redrawn from a good answer.
test("a shelf that arrives takes the doubt off the screen with it", async (t) => {
  const page = await opened(t);
  page.unreachable({ books: true });
  await books(page);
  assert.equal(page.el("shelf-note").textContent, "couldn't reach somnia");
  page.unreachable({ books: false });
  page.click("queue-close");
  await page.settle();
  await books(page);
  assert.equal(page.el("shelf-note").textContent, "");
  assert.equal(shelf(page).length > 0, true);
});

test("close forgets the shelf as well as the queue", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  assert.equal(shelf(page).length > 0, true);
  page.click("queue-close");
  await page.settle();
  // Nothing left drawn and nothing left labelled, so the next opening cannot
  // flash a shelf from a night that is over.
  assert.deepEqual(shelf(page), []);
  assert.equal(page.el("shelf-label").hidden, true);
});

test("a shelf that lands after close does not draw itself over a shut panel", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  // Opened and left again inside the time a tailnet takes to answer, which is
  // an ordinary thing to do and the one way a request outlives the panel that
  // made it: nothing here is cancelled when the panel goes.
  page.click("books");
  page.click("queue-close");
  await page.settle();
  await page.settle();
  // Close forgets the shelf on purpose. An answer that adopted itself anyway
  // would leave a shelf from a night that is over in the DOM, to be found by
  // whoever opens the panel next.
  assert.deepEqual(shelf(page), []);
  assert.equal(page.el("shelf-label").hidden, true);
});

test("a somnia with one book has no shelf and no label over it", async (t) => {
  const page = await opened(t, { library: [HALF_HEARD].map(listed) });
  page.queueView([]);
  await books(page);
  // The only book there is is the one playing, and it is named above. A label
  // over nothing is a claim that something should be there.
  assert.deepEqual(shelf(page), []);
  assert.equal(page.el("shelf-label").hidden, true);
});

// ------------------------------------------------- one screen, one sentence
//
// The cut that made two screens out of one is *when* each is used, and the only
// way that stays true is if nothing daytime is drawn at night and nothing
// nightly is drawn in daylight. These are that, written down.

test("nothing daytime is on the night screen, and nothing nightly in daylight", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  // Books answers "what shall I listen to": the book playing, the shelf, how
  // dark, and the quiet row to the other screen. Not the search, not the queue,
  // not what the server last said.
  for (const id of ["reading-now", "shelf", "dim-row", "to-workshop"]) {
    assert.equal(page.el(id).hidden, false, id);
  }
  assert.equal(page.el("workshop").hidden, true);

  page.click("to-workshop");
  await page.settle();
  await page.settle();
  // And Workshop answers "get me a new book, and tell me it worked". Books is
  // still standing behind it, unchanged — this is an overlay and not a route.
  assert.equal(page.el("workshop").hidden, false);
  assert.equal(page.el("queue").hidden, false);
  for (const id of ["queue-search", "queue-results", "jump-row"]) {
    assert.equal(page.el(id).hidden, false, id);
  }
});

// The other half of "nothing nightly in daylight", and the one that is not a
// screen at all: the sheet of black the whole app is read through.
test("the dim layer comes off Workshop and goes back on at `‹ books`", async (t) => {
  const page = await opened(t, { stored: { "somnia-dim": "0.42" } });
  page.queueView([]);
  await books(page);
  // Books is a night screen and is read through it, like everything else.
  assert.equal(page.probe().dim, 0.42);

  page.click("to-workshop");
  await page.settle();
  await page.settle();
  // Workshop is not. At a level somebody chose for 3am this screen was
  // unreadable whatever its ink did, and dimming a screen read in daylight is
  // wrong at any level.
  assert.equal(page.probe().dim, 0);

  page.click("workshop-close");
  await page.settle();
  // The level was never touched — the layer was lifted, not the setting — so
  // the room comes back exactly as dark as it was, and nothing was written.
  assert.equal(page.probe().dim, 0.42);
  assert.equal(page.storage.getItem("somnia-dim"), "0.42");
});

// The one thing on Books that the split could have quietly deleted. The shelf
// and the queue used to be asked for on the same press and the queue's poll
// owned the single line for "couldn't reach somnia" — so moving the queue out
// left the shelf able to fail with nothing on screen to say it had.
test("each screen says for itself whether the box could be reached", async (t) => {
  const page = await opened(t);
  page.unreachable({ books: true, queue: true });
  await books(page);
  assert.equal(page.el("shelf-note").textContent, "couldn't reach somnia");
  page.click("to-workshop");
  await page.settle();
  await page.settle();
  assert.equal(page.el("queue-note").textContent, "couldn't reach somnia");
});

// ------------------------------------------------------------------- the words

test("a render says which chapter it is on and how much is ready to play", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  assert.deepEqual(jobs(page), [
    {
      name: "Black Beauty — Anna Sewell",
      // Which stage, in the corner, in the panel's own word for it. The server
      // calls this state 'rendering'; nobody at 2am wants to know what the
      // server calls it.
      stage: "narrating",
      // The chapter being worked on, which is the number the journal's
      // "rendering chapter 4/39" line uses, and how much of it can be listened
      // to now. No percentage in words: chapters differ in length by an order
      // of magnitude, so a number drawn from 4/39 is not a fraction of the
      // work.
      state: "chapter 4 of 39 · 1h12m read so far",
      // The same fraction drawn rather than stated. 3 of 39 done, which is the
      // fourth being worked on.
      bar: "7.7%",
      stop: "stop reading this",
    },
  ]);
});

test("the corner says the stage, in the panel's word for it", async (t) => {
  const page = await opened(t);
  page.queueView([
    waiting(),
    job(),
    job({ id: 3, state: "done", chapters_done: 39 }),
    job({ id: 4, state: "failed", error: "No HTML edition." }),
    job({ id: 5, state: "cancelled", chapters_done: 4 }),
  ]);
  await workshop(page);
  assert.deepEqual(
    [...jobs(page), ...jobs(page, "queue-gone")].map((row) => row.stage),
    ["queued", "narrating", "ready", "failed", "stopped"],
  );
});

test("nothing on the panel ever says it is fetching the text as a stage", async (t) => {
  const page = await opened(t);
  // The design drew a pipeline with a fetch step in it — queued, fetching
  // text, narrating, ready — and somnia's queue has no such state: a book whose
  // text has not been parsed is 'rendering' like any other. So the corner says
  // the stage the server really is at, and the honest line about not knowing
  // the count goes under the name where it belongs.
  page.queueView([job({ chapters_total: 0, chapters_done: 0, rendered_ms: 0 })]);
  await workshop(page);
  assert.equal(jobs(page)[0].stage, "narrating");
  assert.equal(jobs(page)[0].state, "fetching the text");
  assert.equal(
    jobs(page).some((row) => row.stage === "fetching text"),
    false,
  );
});

test("a book nobody has counted gets no progress bar rather than an empty one", async (t) => {
  const page = await opened(t);
  page.queueView([
    job({ chapters_total: 0, chapters_done: 0 }),
    job({ id: 7, chapters_done: 13 }),
  ]);
  await workshop(page);
  // 0 means nobody has written the total down — the parse is what produces it,
  // and it is 0 for ever on every book rendered before the column existed. A
  // bar drawn from that sits at nothing on a render that is working perfectly
  // well, which is a lie somebody gets out of bed about.
  assert.equal(jobs(page)[0].bar, null);
  assert.equal(jobs(page)[1].bar, "33.3%");
});

test("the progress bar is the same element from one poll to the next", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  const first = page.el("queue-live").children[0];
  const bar = part(first, "job-fill");
  page.queueView([job({ chapters_done: 20 })]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  // The list is rebuilt every five seconds. A fill made fresh each time has no
  // width to move from, so the half-second slide the design asks for would be a
  // transition that never once runs — and a bar that jumps reads as a page that
  // reloaded.
  assert.equal(part(page.el("queue-live").children[0], "job-fill"), bar);
  assert.equal(bar.style.width, "51.3%");
});

test("a book that is only in the line says where in the line it is", async (t) => {
  const page = await opened(t);
  page.queueView([job(), waiting()]);
  await workshop(page);
  assert.deepEqual(
    jobs(page).map((row) => row.state),
    ["chapter 4 of 39 · 1h12m read so far", "1st in line"],
  );
});

test("a render that has said nothing for five minutes says so", async (t) => {
  const page = await opened(t);
  page.queueView([job({ responding: false })]);
  await workshop(page);
  // Not "rendering", which would be a claim about a process that may have died
  // with the box. The heartbeat is the only evidence either way and the server
  // has already read it.
  assert.equal(jobs(page)[0].state, "not responding");
  // The stage is still the stage — the server has this job as 'rendering' and
  // saying anything else in that corner would be inventing a state — but it has
  // stopped being the warm word on the panel. Amber here means the box is
  // working, and the line under it has just said that it may not be.
  const stage = part(page.el("queue-live").children[0], "job-stage");
  assert.equal(stage.textContent, "narrating");
  assert.equal(stage.classList.contains("now"), false);
});

test("a render that has been asked to stop says it is stopping", async (t) => {
  const page = await opened(t);
  page.queueView([job({ stopping: true })]);
  await workshop(page);
  // It stays 'rendering' until the child reaches the end of its sentence, and
  // printing that would look like the press had been ignored.
  assert.equal(jobs(page)[0].state, "stopping at the end of this sentence");
});

test("a book whose text has not been parsed yet says so rather than counting", async (t) => {
  const page = await opened(t);
  page.queueView([job({ chapters_total: 0, chapters_done: 0, rendered_ms: 0 })]);
  await workshop(page);
  // 0 means nobody has written the number down, which is not the same as a
  // book with no chapters — "chapter 1 of 0" is the sentence this exists to
  // stop.
  assert.equal(jobs(page)[0].state, "fetching the text");
});

test("what went wrong is said in the server's own words, under the live rows", async (t) => {
  const page = await opened(t);
  page.queueView([
    job(),
    job({
      id: 9,
      gid: 4321,
      title: "",
      authors: "",
      state: "failed",
      // The parse is what failed, so nothing was ever counted and nothing of it
      // was ever rendered.
      chapters_total: 0,
      chapters_done: 0,
      error: "Gutenberg has book 4321 but no HTML edition, so somnia cannot read it.",
    }),
  ]);
  await workshop(page);
  // Live above, over: the question at 2am is "is anything happening", and it is
  // answered by looking at the top of the panel.
  assert.deepEqual(
    jobs(page).map((row) => row.name),
    ["Black Beauty — Anna Sewell"],
  );
  assert.deepEqual(jobs(page, "queue-gone"), [
    {
      // No name in the catalog and none from the parse, because the parse is
      // what failed.
      name: "book 4321",
      stage: "failed",
      state:
        "Gutenberg has book 4321 but no HTML edition, so somnia cannot read it.",
      // Nothing was ever counted, so there is no hairline to draw.
      bar: null,
      // Nothing to stop, and nothing to dismiss either: the row leaves by
      // itself after a day, because after a day a failure is history and
      // history is in the journal.
      stop: null,
    },
  ]);
  // And the two lists are told apart by more than a gap now: the live rows are
  // in a card that says what it is, and the rows that are over are under a
  // label of their own. Both go when there is nothing in them.
  assert.equal(page.el("queue-working").hidden, false);
  assert.equal(page.el("queue-ended").hidden, false);
});

test("an empty half of the panel takes its heading with it", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await workshop(page);
  // A card headed "the server is working" with nothing in it is a claim that
  // something should be happening, which at 2am is a reason to get up and look.
  assert.equal(page.el("queue-working").hidden, true);
  assert.equal(page.el("queue-ended").hidden, true);

  page.queueView([job()]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(page.el("queue-working").hidden, false);
  assert.equal(page.el("queue-ended").hidden, true);

  // And closing puts both away, so the next opening does not flash a card from
  // a night that is over.
  page.click("queue-close");
  await page.settle();
  assert.equal(page.el("queue-working").hidden, true);
});

test("a render somebody stopped says whether any of it is playable", async (t) => {
  const page = await opened(t);
  page.queueView([
    job({ id: 5, state: "cancelled", chapters_done: 4 }),
    job({ id: 6, gid: 120, title: "Treasure Island", authors: "", state: "cancelled", chapters_done: 0 }),
  ]);
  await workshop(page);
  // Two quite different things, and the difference is whether asking for it
  // again is picking something up or starting it.
  assert.deepEqual(
    jobs(page, "queue-gone").map((row) => row.state),
    ["stopped part way — what was read still plays", "taken out of the queue"],
  );
});

// -------------------------------------------------------------------- stopping

test("stopping a render takes two presses", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  page.click("queue-stop-1");
  await page.settle();
  // Nothing has gone anywhere. The button says what the second press will do
  // instead of asking in a dialog, which would be an overlay over an overlay.
  assert.deepEqual(page.stops, []);
  assert.equal(jobs(page)[0].stop, "really stop?");

  page.stopReply({
    ok: true,
    state: "rendering",
    said: "Black Beauty stops at the end of the sentence it is reading.",
  });
  page.click("queue-stop-1");
  await page.settle();
  await page.settle();
  assert.deepEqual(page.stops, ["api/queue/1/stop"]);
  assert.equal(page.el("queue-said").textContent.includes("Black Beauty"), true);
});

test("a stop that was armed and left alone forgets itself", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  page.click("queue-stop-1");
  await page.settle();
  assert.equal(jobs(page)[0].stop, "really stop?");
  // Two things are waiting five seconds here: the poll that redraws the list,
  // and this button forgetting it was asked. The label has to survive the first
  // and give way to the second.
  assert.deepEqual(page.waits(), [POLL_MS, CONFIRM_MS]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(jobs(page)[0].stop, "really stop?");

  page.wake(CONFIRM_MS);
  await page.settle();
  // Back to what it was, by itself: a button left saying "really stop?" over a
  // book somebody put down is a press away from ending a render nobody meant to
  // end.
  assert.equal(jobs(page)[0].stop, "stop reading this");
  assert.deepEqual(page.stops, []);
});

test("an armed stop survives the list being redrawn under it", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  page.click("queue-stop-1");
  await page.settle();
  // The poll lands between the two presses, which at five seconds each is not a
  // corner case but the ordinary way this goes.
  page.queueView([job({ chapters_done: 4 })]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(jobs(page)[0].state, "chapter 5 of 39 · 1h12m read so far");
  assert.equal(jobs(page)[0].stop, "really stop?");
  page.click("queue-stop-1");
  await page.settle();
  assert.deepEqual(page.stops, ["api/queue/1/stop"]);
});

test("a row is a readout and not a target", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  const before = night(page);
  page.el("job-1").fire("click");
  await page.settle();
  // The only pressable thing on a row is its own action, so there is nothing to
  // mis-hit into: no seek, no book opened, no request of any kind.
  assert.deepEqual(page.stops, []);
  assert.deepEqual(night(page), before);
});

// --------------------------------------------------------------- adding a book

test("a search asks once per press, not once per keystroke", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await workshop(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure island");
  assert.deepEqual(page.searches, ["api/catalog?q=treasure%20island"]);
  assert.deepEqual(results(page), [
    {
      // The title over the author, rather than both in one string. The design
      // wants `Author · year · formats` under the name; somnia's catalog has
      // the author and not the other two, so the line says what it knows.
      name: "Treasure Island",
      by: "Robert Louis Stevenson",
      have: null,
      add: "add this book",
    },
  ]);
});

test("a book somnia already has is marked and offers no button", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await workshop(page);
  page.catalogEntries([
    entry({ gid: 271, title: "Black Beauty", have: "rendering" }),
    entry({ gid: 11, title: "Alice", have: "done" }),
    entry({ gid: 120, have: "queued" }),
  ]);
  await search(page, "b");
  assert.deepEqual(
    results(page).map((row) => [row.have, row.add]),
    [
      // A press that was never available cannot be a press that did nothing,
      // and at 2am those two feel completely different.
      ["being read now", null],
      ["already here", null],
      ["in the queue", null],
    ],
  );
});

test("a render that died is offered again, because that retry was impossible", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await workshop(page);
  page.catalogEntries([entry({ have: "pending" })]);
  await search(page, "treasure");
  assert.deepEqual(results(page), [
    {
      name: "Treasure Island",
      by: "Robert Louis Stevenson",
      have: "part rendered",
      add: "finish this one",
    },
  ]);
});

test("a press queues the book once and says where it landed", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await workshop(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure");
  page.submitReply({
    ok: true,
    id: 2,
    said: "Treasure Island is in the queue, behind one other book.",
  });
  page.queueView([job(), waiting()]);
  page.click("queue-add-120");
  await page.settle();
  await page.settle();
  await page.settle();
  assert.deepEqual(page.submits, [{ gid: 120 }]);
  assert.equal(
    page.el("queue-said").textContent,
    "Treasure Island is in the queue, behind one other book.",
  );
  // The row it just made is on the screen without waiting out the poll, and the
  // result it was pressed on no longer offers a press.
  assert.deepEqual(
    jobs(page).map((row) => row.state),
    ["chapter 4 of 39 · 1h12m read so far", "1st in line"],
  );
  assert.deepEqual(
    results(page).map((row) => [row.have, row.add]),
    [["in the queue", null]],
  );
});

test("a book cannot be queued twice by pressing twice", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await workshop(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure");
  page.click("queue-add-120");
  page.click("queue-add-120");
  await page.settle();
  await page.settle();
  await page.settle();
  assert.deepEqual(page.submits, [{ gid: 120 }]);
});

test("a refusal is an answer and is shown as one", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await workshop(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure");
  // 200 with a sentence, as /api/queue answers: a refusal is the answer
  // somebody reads twice, and a throw in a fetch wrapper would have skipped it.
  page.submitReply({
    ok: false,
    id: 0,
    said: "Treasure Island is already here, all of it.",
  });
  page.click("queue-add-120");
  await page.settle();
  await page.settle();
  await page.settle();
  assert.equal(
    page.el("queue-said").textContent,
    "Treasure Island is already here, all of it.",
  );
});

// ------------------------------------------------------------ offline honesty

test("a queue that cannot be reached leaves the last list up and says so", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await workshop(page);
  const drawn = jobs(page);

  page.unreachable({ queue: true });
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  // An empty queue and an unreachable server look identical and mean opposite
  // things, so the list is left exactly as it was and the doubt is said
  // underneath it.
  assert.deepEqual(jobs(page), drawn);
  assert.equal(page.el("queue-note").textContent, "couldn't reach somnia");
  // And it keeps asking: the tailnet coming back is the ordinary case.
  assert.deepEqual(page.waits(), [POLL_MS]);

  page.unreachable({ queue: false });
  page.queueView([job({ chapters_done: 5 })]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(page.el("queue-note").textContent, "");
  assert.equal(jobs(page)[0].state, "chapter 6 of 39 · 1h12m read so far");
});

test("a submit that never landed draws no row and says nothing was added", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await workshop(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure");
  page.unreachable({ submit: true });
  page.click("queue-add-120");
  await page.settle();
  await page.settle();
  assert.equal(
    page.el("queue-said").textContent,
    "couldn't reach somnia — nothing has been added",
  );
  // No optimistic row. A queue entry that never existed on the server is
  // exactly the state a wrong press must not be able to leave behind.
  assert.deepEqual(jobs(page), []);
  // And the press is available again, because trying again is the whole of what
  // there is to do about it.
  assert.equal(results(page)[0].add, "add this book");
});

test("a search that cannot be reached says so rather than saying nothing", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await workshop(page);
  page.unreachable({ catalog: true });
  await search(page, "treasure");
  assert.equal(page.el("queue-said").textContent, "couldn't reach somnia");
  assert.deepEqual(results(page), []);
});

// ------------------------------------------------- what the denominator buys

test("running out of audio part way through a book does not call it the end", async (t) => {
  // A render that stopped at chapter one of three and is not running: the
  // manifest is the whole truth about it, and before chapters_total existed
  // there was nothing in that truth to tell this from a finished book.
  const page = await boot(t, { lastGid: PART_READ.gid });
  page.audio.ready(8);
  page.click("playpause");
  await page.settle();
  page.audio.advance(8);
  await page.settle();
  assert.equal(page.probe().status, "the rest of this book hasn't been read yet");
  // The sleep timer and the fight to keep the sound going are left alone: the
  // night is not over, there is simply nothing more to play yet.
  assert.equal(page.probe().wantsSound, true);
});

test("running out of audio at the end of a finished book still says so", async (t) => {
  const page = await boot(t, { lastGid: TONE_BOOK.gid });
  page.audio.ready(8);
  page.click("playpause");
  await page.settle();
  for (let chapter = 0; chapter < 3; chapter++) {
    page.audio.advance(8);
    await page.settle();
    page.audio.ready(8);
    await page.settle();
  }
  assert.equal(page.probe().status, "that is the end of the book");
  assert.equal(page.probe().wantsSound, false);
});

test("a somnia with no books says which two presses add one", async (t) => {
  const page = await boot(t, { lastGid: null, library: [] });
  // The one state that most needs the panel, and the one with no book, no
  // manifest and no gid to press anything about.
  //
  // It names the controls by the words on them, so the sentence, the header
  // pill and the row at the foot of Books all have to be changed together —
  // which is why both words are written out here. And there are two of them
  // now: adding a book is Workshop's job and Workshop is behind Books, so a
  // sentence naming one press would send somebody to a screen with no search
  // on it.
  assert.equal(
    page.probe().status,
    "nothing yet — press books, then Workshop, to add one",
  );
});
