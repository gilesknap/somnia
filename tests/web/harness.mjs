// The page, run without a browser.
//
// app.js is the largest single thing in somnia and, until this file, the only
// part of it no test ever ran: a state machine over one media element that
// does its real work at 2am with the screen off, where nobody is watching and
// nothing can be reproduced afterwards. Everything below exists so that it can
// be driven from a test instead of from a phone.
//
// It is a fake media element rather than a headless browser on purpose. What
// the page has to get right is mostly a *sequence* — metadata before src
// before play, the spurious pause a load fires swallowed, a report built at the
// moment it goes out rather than when it was asked for — and a real element
// decides for itself when to fire any of that, so a browser test can only wait
// and hope. Here every event is fired by hand, in the order the spec says a
// browser fires it, and a mistake in the order is a failing test rather than a
// night that goes quiet.
//
// A real browser still has the last word. Chrome over CDP against a real
// `somnia serve` is what proves the m4a decodes, that Range requests come back
// 206 and that the lock screen really follows; nothing here can prove any of
// that, and it does not try. This is for everything that happens in between.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const APP = fileURLToPath(
  new URL("../../src/somnia/web/app.js", import.meta.url),
);

// The tone book, as tests/tone_book.py seeds it and /api/book/900001 serves it:
// three chapters of exactly eight seconds, so every boundary is a round number
// and an off-by-one in the arithmetic has nowhere to hide. The shape is
// player.Manifest's, field for field — a harness that answered with a shape the
// server cannot produce would be testing a page somnia does not serve.
export const TONE_BOOK = {
  gid: 900001,
  title: "Three Tones",
  authors: "Somnia Test",
  status: "done",
  total_ms: 24000,
  position_ms: null,
  seq: 0,
  heard_to_ms: 24000,
  // How many chapters the book HAS, as against how many have been rendered.
  // Equal here, and in every fixture below that is finished, because that is
  // what a finished book looks like — the interesting case, where the two
  // disagree, is PART_READ.
  chapters_total: 3,
  // The whole book down one URL, named by how many chapters it holds, and how
  // much book that is on the render clock. This is what the element is given at
  // boot and never given again: the chapters below keep a url each, and they
  // are the fallback for a book with no stream — see chapterAtATime in app.js.
  stream_url: "api/stream/900001/3",
  stream_ms: 24000,
  chapters: [
    {
      idx: 0,
      title: "The First Tone",
      start_ms: 0,
      end_ms: 8000,
      url: "api/audio/900001/0",
    },
    {
      idx: 1,
      title: "The Second Tone",
      start_ms: 8000,
      end_ms: 16000,
      url: "api/audio/900001/1",
    },
    {
      idx: 2,
      title: "The Third Tone",
      start_ms: 16000,
      end_ms: 24000,
      url: "api/audio/900001/2",
    },
  ],
};

// Somewhere else to be taken to. Two chapters, a different length and a
// position of its own, so that a page which quietly kept the first book's
// numbers is caught by any of the three.
export const OTHER_BOOK = {
  gid: 900002,
  title: "Another Book",
  authors: "Somnia Test",
  status: "done",
  total_ms: 16000,
  position_ms: 4000,
  seq: 7,
  heard_to_ms: 16000,
  chapters_total: 2,
  stream_url: "api/stream/900002/2",
  stream_ms: 16000,
  chapters: [
    {
      idx: 0,
      title: "Elsewhere One",
      start_ms: 0,
      end_ms: 8000,
      url: "api/audio/900002/0",
    },
    {
      idx: 1,
      title: "Elsewhere Two",
      start_ms: 8000,
      end_ms: 16000,
      url: "api/audio/900002/1",
    },
  ],
};

// Rows in the database and no audio yet: the render has started and the first
// chapter has not landed. Being moved to one of these is the shape of the bug
// that left the page playing one book while every clock read another.
export const RENDERING_BOOK = {
  gid: 900003,
  title: "Still Being Read",
  authors: "Somnia Test",
  status: "rendering",
  total_ms: 0,
  position_ms: null,
  seq: 0,
  heard_to_ms: 0,
  // Nobody has written it down: the fetch and the parse are what produce this
  // number and neither has finished. 0 is what every book rendered before the
  // column existed says as well, which is every book on the live VPS, so the
  // page has to read it as "don't know" rather than as "no chapters".
  chapters_total: 0,
  // Nothing to join, so nothing is offered. A url advertised here would be one
  // that answers 404 at the moment somebody is trying to open the book.
  stream_url: null,
  stream_ms: 0,
  chapters: [],
};

// A render that stopped part way and is not running: three chapters were
// written down at the parse, one of them has audio, and nothing is going to
// add the other two until somebody asks again. It is the one shape that tells
// "the end of the book" and "the end of what has been read of it" apart, and
// before chapters_total existed there was no way for the page to know which of
// the two it had reached.
export const PART_READ = {
  gid: 900006,
  title: "Stopped Part Way",
  authors: "Somnia Test",
  status: "pending",
  total_ms: 8000,
  position_ms: 0,
  seq: 0,
  heard_to_ms: 0,
  chapters_total: 3,
  stream_url: "api/stream/900006/1",
  stream_ms: 8000,
  chapters: [
    {
      idx: 0,
      title: "As Far As It Got",
      start_ms: 0,
      end_ms: 8000,
      url: "api/audio/900006/0",
    },
  ],
};

// A book with the mark somewhere in the middle of it, which is the one shape
// none of the others have: every book above has been heard to the end or not
// started at all, and a candidate list is only interesting where some of the
// places are behind the listener and some are in front. Heard to the end of the
// first chapter, of two, with the position a little way behind that — so the
// "you are here" row has rows on both sides of it, and the boundary either side
// of the mark is also a boundary between two chapter titles, which is what makes
// a title withheld and a title shown tellable apart. The page never reads
// heard_to_ms; it is here so the tests can work out what the server would have
// said about each place.
export const HALF_HEARD = {
  gid: 900005,
  title: "Half Heard",
  authors: "Somnia Test",
  status: "done",
  total_ms: 3_600_000,
  position_ms: 1_000_000,
  seq: 2,
  heard_to_ms: 1_800_000,
  chapters_total: 2,
  stream_url: "api/stream/900005/2",
  stream_ms: 3_600_000,
  chapters: [
    {
      idx: 0,
      title: "What They Have Heard",
      start_ms: 0,
      end_ms: 1_800_000,
      url: "api/audio/900005/0",
    },
    {
      idx: 1,
      title: "What They Have Not",
      start_ms: 1_800_000,
      end_ms: 3_600_000,
      url: "api/audio/900005/1",
    },
  ],
};

// A book nobody counted. It has chapters and it plays perfectly well, and the
// number of chapters it is *supposed* to have was never written down — which is
// not an edge case but the ordinary state of every book on the box this runs
// on, all of them rendered before the column existed. The page has to say which
// chapter they are in without a denominator it does not have, rather than
// inventing one or saying "of 0".
export const UNCOUNTED_BOOK = {
  gid: 900007,
  title: "Nobody Counted",
  authors: "Somnia Test",
  status: "done",
  total_ms: 16000,
  position_ms: 0,
  seq: 0,
  heard_to_ms: 16000,
  chapters_total: 0,
  stream_url: "api/stream/900007/2",
  stream_ms: 16000,
  chapters: [
    {
      idx: 0,
      title: "One Of However Many",
      start_ms: 0,
      end_ms: 8000,
      url: "api/audio/900007/0",
    },
    {
      idx: 1,
      title: "Two Of However Many",
      start_ms: 8000,
      end_ms: 16000,
      url: "api/audio/900007/1",
    },
  ],
};

// A book nobody measured. It plays — two chapters with audio behind them — and
// its length was never written down, which is what every book rendered before
// the total_ms column existed says, and that is every book on the live box.
// UNCOUNTED_BOOK is missing its chapter *count*; this one is missing its
// *duration*, and the two are drawn by different arithmetic: the fraction
// through has 0 for a denominator here, and dividing by it gives a fill of
// Infinity% — a book drawn as finished, which is the one reading worse than
// drawing nothing, because it tells him he has heard all of something he has
// not started.
export const UNMEASURED_BOOK = {
  gid: 900009,
  title: "Nobody Measured",
  authors: "Somnia Test",
  status: "done",
  total_ms: 0,
  position_ms: 0,
  seq: 0,
  heard_to_ms: 0,
  chapters_total: 2,
  stream_url: "api/stream/900009/2",
  stream_ms: 16000,
  chapters: [
    {
      idx: 0,
      title: "The First Of Two",
      start_ms: 0,
      end_ms: 8000,
      url: "api/audio/900009/0",
    },
    {
      idx: 1,
      title: "The Second Of Two",
      start_ms: 8000,
      end_ms: 16000,
      url: "api/audio/900009/1",
    },
  ],
};

// A book re-rendered shorter than the mark somebody left in it: the server's
// own record puts them at forty seconds of a book now sixteen long. openBook
// takes `position_ms` from the manifest without clamping it, so this is the one
// way a position past the end gets into the page — `seekGlobal` clamps its
// argument, which means no amount of seeking can produce it. The fill and the
// clock have to hold the end of the line rather than run the knob off its
// track.
export const SHRUNK_BOOK = {
  gid: 900010,
  title: "Rendered Shorter",
  authors: "Somnia Test",
  status: "done",
  total_ms: 16000,
  position_ms: 40000,
  seq: 0,
  heard_to_ms: 16000,
  chapters_total: 2,
  stream_url: "api/stream/900010/2",
  stream_ms: 16000,
  chapters: [
    {
      idx: 0,
      title: "What Is Left Of It",
      start_ms: 0,
      end_ms: 8000,
      url: "api/audio/900010/0",
    },
    {
      idx: 1,
      title: "And The Rest Of That",
      start_ms: 8000,
      end_ms: 16000,
      url: "api/audio/900010/1",
    },
  ],
};

// A book that can be listened to while it is still being written down, which is
// the ordinary state of a book somnia was asked for this evening: `read` of its
// thirty-seven chapters have audio, and total_ms is how much exists rather than
// how long the book is. Anything drawn as a fraction of total_ms on this one
// over-reads, which is half the reason it is here.
//
// The other half is that this is the one book that is asked for twice. The page
// holds the answer from boot while the render carries on behind it, and what it
// is given on the next ask has to be the same book with more of it in: the same
// chapters at the same times, another row after them, and the whole of it down a
// URL the element has never loaded — `api/stream/900008/6` while it is holding
// `api/stream/900008/5`. The distance between those two is the render frontier.
// So it is a function of how much has been read rather than a fixed shape, and
// `page.serves` is how a test says another chapter has landed.
//
// Its `authors` is the catalog's own field, verbatim, for a book with two names
// on it: `Surname, Forename, dates`, semicolons between people. Every other
// fixture carries a single tidy name, so this is the only one that can catch a
// page printing the raw string.
export function growingBook(read) {
  return {
    gid: 900008,
    title: "The Moonstone",
    authors: "Collins, Wilkie, 1824-1889; Reade, Charles, 1814-1884",
    status: "rendering",
    total_ms: read * 600_000,
    position_ms: 1_800_000,
    seq: 0,
    heard_to_ms: 1_800_000,
    chapters_total: 37,
    stream_url: `api/stream/900008/${read}`,
    stream_ms: read * 600_000,
    chapters: Array.from({ length: read }, (_, idx) => ({
      idx,
      title: `Chapter ${idx + 1}`,
      start_ms: idx * 600_000,
      end_ms: (idx + 1) * 600_000,
      url: `api/audio/900008/${idx}`,
    })),
  };
}

// Five chapters in, which is where every test that does not care about it finds
// this book.
export const GROWING_BOOK = growingBook(5);

// A book somebody could actually fall asleep in. The tone book is twenty-four
// seconds long — shorter than the shortest rewind and a four-hundredth of the
// shortest sleep timer — so anything measured in minutes needs a book measured
// in minutes, and this is it: two half-hour chapters.
export const NIGHT_BOOK = {
  gid: 900004,
  title: "A Long Night",
  authors: "Somnia Test",
  status: "done",
  total_ms: 3_600_000,
  position_ms: 0,
  seq: 0,
  heard_to_ms: 3_600_000,
  chapters_total: 2,
  stream_url: "api/stream/900004/2",
  stream_ms: 3_600_000,
  chapters: [
    {
      idx: 0,
      title: "The Long First",
      start_ms: 0,
      end_ms: 1_800_000,
      url: "api/audio/900004/0",
    },
    {
      idx: 1,
      title: "The Long Second",
      start_ms: 1_800_000,
      end_ms: 3_600_000,
      url: "api/audio/900004/1",
    },
  ],
};

// A book with no stream to be had. Two chapters with audio behind them, and
// nothing offering the whole of it down one URL — because the join could not be
// made (one chapter of it will not open, and half a book is not this book), or
// because the somnia answering is older than the field. Either way it plays,
// a file at a time, the way every book played before: the per-chapter urls are
// the fallback and this is the fixture that proves the page still takes it.
export const UNJOINED_BOOK = {
  gid: 900011,
  title: "Would Not Join",
  authors: "Somnia Test",
  status: "done",
  total_ms: 16000,
  position_ms: 0,
  seq: 0,
  heard_to_ms: 16000,
  chapters_total: 2,
  stream_url: null,
  stream_ms: 0,
  chapters: [
    {
      idx: 0,
      title: "One On Its Own",
      start_ms: 0,
      end_ms: 8000,
      url: "api/audio/900011/0",
    },
    {
      idx: 1,
      title: "And Another",
      start_ms: 8000,
      end_ms: 16000,
      url: "api/audio/900011/1",
    },
  ],
};

const MANIFESTS = new Map(
  [
    TONE_BOOK,
    OTHER_BOOK,
    RENDERING_BOOK,
    NIGHT_BOOK,
    UNJOINED_BOOK,
    HALF_HEARD,
    PART_READ,
    UNCOUNTED_BOOK,
    UNMEASURED_BOOK,
    SHRUNK_BOOK,
    GROWING_BOOK,
  ].map((m) => [`api/book/${m.gid}`, m]),
);

// One book as /api/books lists it — player.BookEntry, field for field, built
// from the manifest of the same book so the two can never say different things
// about it. `chapters` is how many of them can be played, which is what tells a
// book still waiting on its first chapter from one there is something to open.
export function listed(book) {
  return {
    gid: book.gid,
    title: book.title,
    authors: book.authors,
    status: book.status,
    total_ms: book.total_ms,
    chapters: book.chapters.length,
    // How many it HAS, which is the manifest's own field: the two are equal on
    // a book that finished rendering and different on every book that did not,
    // and a coverage line is the difference between them read out loud.
    chapters_total: book.chapters_total,
    position_ms: book.position_ms,
    seq: book.seq,
    // When the reader said they were done with it, which no manifest carries —
    // it is not the render's business and `/api/book/{gid}` does not return it.
    // So a fixture that wants to be finished says so on itself, and everything
    // else is what every book somnia has is: still being read.
    finished_at: book.finished_at ?? null,
    // When somnia was first asked for the book, which no manifest carries
    // either. One date for every fixture unless a test says otherwise: a
    // library where every book arrived at the same moment is a library whose
    // order is decided by everything else, which is what most of these tests
    // want. A test about the ordering itself puts its own dates on the rows.
    created_at: book.created_at ?? "2026-01-01 00:00:00",
  };
}

// Every book somnia has, and what a page booted without a `library` of its own
// is given. Exported so that a test counting rows can say the rule it is really
// testing — every book but the one playing — instead of a number that the next
// fixture added above would quietly falsify.
export const EVERY_BOOK = [...MANIFESTS.values()];

// The eight the page registers. A browser throws for an action it has never
// heard of, which is the whole reason registration is wrapped in a try, so the
// fake throws too.
const ACTIONS = [
  "play",
  "pause",
  "stop",
  "seekbackward",
  "seekforward",
  "seekto",
  "previoustrack",
  "nexttrack",
  "skipad",
];

class FakeMediaMetadata {
  constructor(init) {
    Object.assign(this, init);
  }
}

// The page runs in its own vm context, which means its own Object, its own
// Array and its own prototypes: an object built inside it is not deepEqual to
// the same object built out here, however identical it reads. So everything
// handed back across that line is copied into this realm first, and a test can
// compare what it sees with a plain object literal.
function plain(value) {
  return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

// The lock screen, the notification shade and whatever is paired over
// Bluetooth. For most of the night this is the only transport there is, so it
// is faked in full rather than stubbed: what it was told, in what order, and
// whether it would have thrown.
class FakeSession {
  constructor(order) {
    this.order = order;
    this.handlers = {};
    this.positions = [];
    this.states = [];
    this._metadata = null;
    this._playbackState = "none";
  }

  get metadata() {
    return this._metadata;
  }

  set metadata(value) {
    this._metadata = plain(value);
    this.order.push(`metadata:${value && value.title}`);
  }

  get playbackState() {
    return this._playbackState;
  }

  set playbackState(value) {
    this._playbackState = value;
    this.states.push(value);
    this.order.push(`state:${value}`);
  }

  setActionHandler(action, fn) {
    if (!ACTIONS.includes(action)) throw new TypeError(`unsupported ${action}`);
    this.handlers[action] = fn;
  }

  // The platform's own validation, reproduced. Every guard around the call in
  // publishPosition exists to keep this from throwing, and a throw here would
  // leave the *previous* chapter's scrubber up rather than clearing it — so a
  // harness that quietly accepted anything would test none of them.
  setPositionState(state) {
    if (!Number.isFinite(state.duration) || state.duration < 0) {
      throw new TypeError(`bad duration ${state.duration}`);
    }
    if (
      !Number.isFinite(state.position) ||
      state.position < 0 ||
      state.position > state.duration
    ) {
      throw new TypeError(`bad position ${state.position} of ${state.duration}`);
    }
    if (!Number.isFinite(state.playbackRate)) {
      throw new TypeError(`bad rate ${state.playbackRate}`);
    }
    this.positions.push(plain(state));
  }

  // The scrubber as it stands, which is the only part of it anyone can see.
  last() {
    return this.positions[this.positions.length - 1];
  }

  // A press on the lock screen, a pillow speaker or a pair of headphones.
  press(action, details) {
    const handler = this.handlers[action];
    if (!handler) throw new Error(`nothing is listening for ${action}`);
    return handler(details);
  }
}

// Every id index.html gives a `hidden` attribute to. Kept as a list here
// because the page has no way of knowing: it shows these and never hides them
// at boot, so their starting state is the document's word and nothing else's.
const BORN_HIDDEN = new Set([
  "player-bar",
  "candidates",
  "candidates-book",
  "queue",
  // Workshop, which ships hidden like the two overlays above it and is the one
  // of the four that can only be reached through another.
  "workshop",
  // Settings, which ships hidden like the rest of them and is the one reached
  // from the right-hand corner of the header rather than the left.
  "settings",
  // The card the live rows sit in and the label over the rows that are over.
  // Both are in the document with nothing in them and both ship hidden, so a
  // page whose script has not run yet does not show a heading over an empty
  // box — and a test that saw them visible at boot would be testing a panel no
  // browser draws.
  "queue-working",
  "queue-ended",
  // What is playing under the panel, and the hairline inside it. The block
  // ships hidden because a page with no book open must not show a heading over
  // an empty space, and the hairline ships hidden because a book still being
  // rendered never gets one at all.
  "reading-now",
  "reading-track",
  // The label over the shelf, which goes with its rows the way the ended list's
  // does: a somnia with one book has nothing to put under it.
  "shelf-label",
  // The line at the foot of a shelf that was cut short, which ships hidden
  // because on most nights nothing is cut and a line that was always there
  // would be furniture rather than an answer.
  "shelf-more",
  // One book's own page, which ships hidden like the four overlays above it and
  // is the only one of them that can be reached only through two others.
  "book",
  // The library at the foot of Workshop, and the two lines inside it that are
  // answers rather than furniture: what a filter matched nothing with, and how
  // many books are finished. The section itself ships hidden because a somnia
  // with no books at all must not draw a filter and three orders over nothing.
  "have",
  "have-none",
  "have-finished-label",
  "toast",
  // The way back inside it, which ships hidden separately: the box comes up for
  // every sentence the page says and this is on the one that has something to
  // undo. A fake that handed it back visible would let a page offering an undo
  // on every toast pass.
  "toast-undo",
  // The count under the position line. The line is a plain readout until there
  // are places to open from it, so the document ships the count with nothing in
  // it and out of the way.
  "places-found",
  // The morning screen's first choice, which is the same list said as a slab.
  // It ships hidden for the same reason the count does and a stronger one: on
  // most mornings there is no list, and a 92dp press at the top of that screen
  // that answers by doing nothing is worse than two choices.
  "wake-places",
]);

// And the one id it gives a `disabled` attribute to, for the same reason: the
// position line is a way in to the places somnia last found, and on a page that
// has never been asked anything there is nothing behind it. The document ships
// it that way and the page only ever changes it, so a fake that handed it back
// live would let a control pass a test it fails in a browser.
const BORN_DISABLED = new Set(["places-open"]);

// And every id that is an <input> in the document. A browser hands back "" for
// the value of an empty box and never undefined, so a fake that left the
// property unset would make `.value.trim()` throw on a page that is perfectly
// well behaved — which is a test failing for the fake's reasons rather than the
// page's. The composer's box is here too, though tests write to it before
// anything reads it.
const BORN_TYPED = new Set([
  "question",
  "queue-query",
  "have-filter",
  // The two boxes on a book's page, which are the only inputs on this page that
  // arrive with something already in them.
  "book-name",
  "book-author",
]);

// Enough of a DOM node to build a list of places out of, and no more.
//
// It grew children the day the page started making them. Everything the page
// draws was a string in an element it was handed at boot until the candidate
// list, which is built node by node — so a fake whose append() threw its
// argument away could not be asked what is on the screen, which is the only
// question worth asking about a list of places to jump to. `registry` is how a
// created node gets found again: the page gives each pressable one an id, and a
// getElementById that auto-vivified a fresh object for that id would hand a test
// a different element from the one it is looking at.
class FakeElement {
  constructor(id, registry = null) {
    this.registry = registry;
    this.handlers = {};
    this.textContent = "";
    this.hidden = false;
    this.attributes = {};
    // data-* attributes, which the voice picker uses to carry which voice a
    // pill is for. A plain object is the whole of what the page asks of it:
    // it writes names and reads them back, and never touches the attribute
    // spelling a real DOM would derive from them.
    this.dataset = {};
    // Named properties are read and written straight — `el.style.width` — which
    // is how the page paints everything else. A custom property cannot be:
    // `--text-size` is not a JavaScript identifier, so the page reaches it
    // through setProperty, and it lands in the same object so that a test reads
    // both of them the same way. Non-enumerable, to stay out of anything that
    // walks the styles an element has been given.
    this.style = {};
    Object.defineProperty(this.style, "setProperty", {
      value: (name, value) => {
        this.style[name] = String(value);
      },
    });
    this.children = [];
    this.parent = null;
    // Which half of the play button is showing is a class rather than a glyph,
    // so a class list that can be read back is how a test sees the transport.
    this.classes = new Set();
    this.classList = {
      add: (name) => this.classes.add(name),
      remove: (name) => this.classes.delete(name),
      contains: (name) => this.classes.has(name),
      toggle: (name, on) =>
        (on ?? !this.classes.has(name))
          ? this.classes.add(name)
          : this.classes.delete(name),
    };
    this.id = id;
  }

  get id() {
    return this._id;
  }

  set id(value) {
    this._id = value;
    if (value && this.registry) this.registry.set(value, this);
  }

  get className() {
    return [...this.classes].join(" ");
  }

  set className(value) {
    this.classes = new Set(String(value).split(/\s+/).filter(Boolean));
  }

  // `once` is honoured because one listener in the page depends on it: the tap
  // that lets a refused play through arms itself for a single press, and a fake
  // that fired it twice would test a page no browser runs.
  addEventListener(type, fn, options = {}) {
    (this.handlers[type] ||= []).push({ fn, once: Boolean(options?.once) });
  }

  removeEventListener(type, fn) {
    const list = this.handlers[type];
    if (!list) return;
    const at = list.findIndex((entry) => entry.fn === fn);
    if (at >= 0) list.splice(at, 1);
  }

  fire(type, event = {}) {
    for (const entry of [...(this.handlers[type] || [])]) {
      if (entry.once) this.removeEventListener(type, entry.fn);
      entry.fn(event);
    }
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  append(...nodes) {
    for (const node of nodes) {
      node.parent = this;
      this.children.push(node);
    }
  }

  replaceChildren(...nodes) {
    for (const child of this.children) child.parent = null;
    this.children = [];
    this.append(...nodes);
  }

  remove() {
    const at = this.parent ? this.parent.children.indexOf(this) : -1;
    if (at >= 0) this.parent.children.splice(at, 1);
    this.parent = null;
  }

  focus() {}
  blur() {}
}

// How long the audio at a url really is, in seconds, according to the same
// manifests the fake server hands the page. A stream is the chapters it joins,
// laid end to end; a chapter file is that one chapter. Anything else — an
// element that was never given a source — is a duration nobody has said, which
// is what a browser reports before metadata arrives.
//
// The manifests are the booted page's own copy rather than the module's, because
// a render adding a chapter changes both halves of the answer at once: the book
// grows a row, and the join that holds it is a longer file at a URL that did not
// exist before. A fake that grew one and not the other would let a page pass
// having loaded a stream no server could have served it.
function lengthOfSource(manifests, url) {
  const stream = /^api\/stream\/(\d+)\/(\d+)$/.exec(url ?? "");
  if (stream) {
    const book = manifests.get(`api/book/${stream[1]}`);
    const held = book?.chapters.slice(0, Number(stream[2]));
    return held?.length ? held[held.length - 1].end_ms / 1000 : NaN;
  }
  const chapter = /^api\/audio\/(\d+)\/(\d+)$/.exec(url ?? "");
  if (!chapter) return NaN;
  const row = manifests.get(`api/book/${chapter[1]}`)?.chapters[
    Number(chapter[2])
  ];
  return row ? (row.end_ms - row.start_ms) / 1000 : NaN;
}

// One <audio> element for the life of the page, as index.html insists on. The
// events below are fired in the order a browser fires them, and the comments
// say which part of the spec each one is standing in for.
class FakeAudio extends FakeElement {
  constructor(order, clock, registry, manifests) {
    super("player", registry);
    this.order = order;
    this.clock = clock;
    this.manifests = manifests;
    this._src = "";
    this.currentTime = 0;
    this.duration = NaN;
    this.paused = true;
    this.ended = false;
    this.readyState = 0;
    this.error = null;
    this.volume = 1;
    this.playbackRate = 1;
    this.srcWrites = [];
    this.playCalls = 0;
    // What play() rejects with, for the two failures onPlayRejected tells
    // apart: the autoplay policy, which is worth offering a tap for, and
    // everything else, which is not.
    this.refuse = null;
  }

  get src() {
    return this._src;
  }

  set src(value) {
    this._src = value;
    this.srcWrites.push(value);
    this.order.push(`src:${value}`);
    this.readyState = 0;
    this.ended = false;
    this.currentTime = 0;
    this.duration = NaN;
    this.error = null;
    // Assigning src runs the media element load algorithm, which pauses a
    // playing element and fires a pause event at it. This is the spurious
    // pause the `swapping` guard exists for, and half the point of this fake.
    if (!this.paused) {
      this.paused = true;
      this.fire("pause");
    }
  }

  play() {
    this.playCalls++;
    if (this.refuse) {
      const error = new Error("refused");
      error.name = this.refuse;
      return Promise.reject(error);
    }
    this.order.push("play");
    this.paused = false;
    this.ended = false;
    this.fire("play");
    return Promise.resolve();
  }

  pause() {
    if (this.paused) return;
    this.paused = true;
    this.fire("pause");
  }

  // Metadata arrived: the point at which there is a duration to clamp a
  // pending offset against. `seeked` follows because landing at that offset is
  // a seek, and the page reports one.
  //
  // The duration is the real length of whatever was loaded, worked out from the
  // same manifests this fake's server answers with, because it is not a number
  // a test should have to keep in step: the element holds a whole book now, and
  // a test that said eight seconds out of habit would be testing a page whose
  // book ends after chapter one — which is `ended`, which is the one event that
  // takes the lock screen down. Pass one to say something else on purpose: a
  // truncated encode, or a stream that came up short of the book.
  ready(duration = lengthOfSource(this.manifests, this.src)) {
    this.duration = duration;
    this.readyState = 1;
    this.fire("loadedmetadata");
    this.fire("seeked");
  }

  // The element got where it was told to go. A browser fires `seeking` and then
  // `seeked` a little after currentTime is written, and the page listens for
  // the second — so a seek inside what is already loaded, which under one URL
  // per book is every seek, only finishes when a test says it did.
  arrived() {
    this.fire("seeked");
  }

  // Sound coming out. The wall clock moves with the element because in a
  // browser it does: the sleep timer counts listening time off Date.now()
  // between timeupdates, so a harness that let the two drift would be testing
  // a timer no phone could ever run.
  advance(seconds) {
    if (this.paused) return;
    this.clock.tick(seconds * 1000);
    this.currentTime = Math.min(this.currentTime + seconds, this.duration);
    this.fire("timeupdate");
    if (this.currentTime >= this.duration) {
      // Per spec, in this order: `ended` already reads true because it is a
      // function of the playback position, the element is paused, `pause`
      // fires, and only then `ended`.
      this.ended = true;
      this.paused = true;
      this.fire("pause");
      this.fire("ended");
    }
  }

  // The chapter stopped arriving: the tailnet went, or the file is not there.
  // A browser fires `error` and then pauses, which is the second pause that
  // must not be read as somebody putting the book down.
  fail() {
    this.error = { code: 2, message: "network" };
    this.fire("error");
    if (!this.paused) {
      this.paused = true;
      this.fire("pause");
    }
  }
}

// Everything app.js asks the clock is Date.now(): the fifteen-second
// heartbeat, the once-a-second gate on the lock screen, how long the sound has
// been off, and how much of the sleep timer is left. Driving it by hand is
// what makes all four observable from a test that runs in a millisecond.
// Where every test's night starts, so that a sleep timer written down by an
// earlier page can be given a time that is neither in the future nor stale.
export const START_MS = 1_700_000_000_000;

// The page with nothing over it, on the phone it is drawn for: 360x780 with a
// 20px root, which is a Pixel 6 Pro with Android's text scaling turned up. Every
// height a test hands to `resize` is measured against this one, so it is the
// phone's own height and not a number chosen to make the arithmetic tidy.
export const VIEWPORT_HEIGHT = 780;

class FakeClock {
  constructor() {
    this.ms = START_MS;
  }

  tick(ms) {
    this.ms += ms;
  }

  now() {
    return this.ms;
  }
}

// The sleep timer outlives the page on purpose, so the storage it outlives it
// in has to be real enough to be read back.
class FakeStorage {
  constructor(initial = {}) {
    this.items = new Map(Object.entries(initial));
  }

  getItem(key) {
    return this.items.has(key) ? this.items.get(key) : null;
  }

  setItem(key, value) {
    this.items.set(key, String(value));
  }

  removeItem(key) {
    this.items.delete(key);
  }
}

class FakeBlob {
  constructor(parts, options) {
    this.text = parts.join("");
    this.type = options && options.type;
  }
}

// Appended to app.js before it runs. The page is a script and exports nothing
// — the browser wants one file it can load with one <script> — so this is how
// a test reaches the state machine from inside its own scope, the same place
// the page's own event handlers see it from.
//
// It is a template literal, so **never put a backtick in anything you add
// below** — not in a comment, not around an identifier. A stray one ends the
// string early and the failure is a SyntaxError pointing at whatever word came
// next, in every one of these suites at once, which reads like the harness
// having broken rather than like a punctuation mark in a comment.
const EPILOGUE = `
globalThis.__page = {
  probe: () => ({
    gid,
    seq,
    positionMs,
    untouched,
    swapping,
    wantsSound,
    // Which way this book is being played: one file per chapter, or the whole
    // of it. A fact about what was loaded rather than about what the manifest
    // says now, and a test that wants to know whether a boundary will load
    // anything is asking this.
    perChapter: holdingOneChapter,
    // Whether the page has given up on this book's join and will play it a file
    // at a time from here. Beside perChapter rather than folded into it: the
    // decision and its effect are a rung of the ladder apart — the flag is set
    // on an error and the element only finds out at the next load — and a test
    // that could see the effect alone could not tell a page that decided late
    // from one that never decided at all.
    fellBack: fellBackToChapters,
    // How much book the source it is holding covers, and whether the sound is
    // stopped a fraction short of the end of that. The pair is the render
    // frontier as the page sees it: streamMs stays where it was while the
    // manifest grows past it, which is what makes "the element was not reloaded
    // when the book got longer" a thing a test can look at rather than infer.
    streamMs,
    atFrontier,
    idx: current && current.idx,
    // The book, over the chapter, over how many chapters there are. All three
    // come off the manifest and are drawn in one pass, so a page that named the
    // book once at boot and then let a chapter swap leave it behind is a
    // failure here rather than a wrong headline at 2am.
    book: bookTitle.textContent,
    chapter: chapterTitle.textContent,
    chapterCount: chapterCount.textContent,
    clock: clock.textContent,
    // The same pair as the clock above, drawn as a line. Reported as the raw
    // width string so a test can tell "0%" — nobody wrote down how long the
    // book is — apart from a fill that was never set at all.
    through: wholePlayed.style.width,
    // The chapter's own clock, and whether there is anywhere left to skip to.
    // Both are drawn from the chapter row rather than from the element, so a
    // test that watches them is watching the book's clock and not the
    // decoder's — which is the distinction the whole timeline rests on.
    chapterClock: chapterClock.textContent,
    canSkipOn: !nextChapter.disabled,
    status: statusLine.textContent,
    // Whether that sentence is drawn in the failure red rather than the amber.
    // Beside the words and not instead of them, because the split between the
    // two is a judgement about each sentence — a wait is amber, something that
    // needs a person is red — and a test that only reads the text cannot tell
    // that the frontier has quietly been recoloured.
    statusFailed: statusLine.classList.contains("failed"),
    // The page's two channels, side by side, because the only interesting
    // thing about either is what the other one is doing at the same moment:
    // the toast is what was said once and the status line is what still
    // stands, and a change in one of them that moved the other is the bug.
    // Empty when nothing is being said — the box is emptied as well as hidden
    // so this cannot report a sentence nobody can see.
    //
    // Off the sentence rather than off the box, because the box now holds a
    // button as well: read from the outside, a toast with a way back on it
    // would report as "moved to 1:20:20undo" in a browser and as the sentence
    // alone here, which is a harness that agrees with the page about everything
    // except the one thing it was added to watch.
    toast: toastSaid.textContent,
    // Whether that sentence is standing beside a way back. The pair is the
    // whole of what this control is: an undo offered on a press that cannot be
    // undone, or missing from the one that can, are both bugs no reading of the
    // sentence alone would catch.
    undo: !toastUndo.hidden,
    // How much of the light the page is taking off the room, as a number. Set
    // once at boot from storage and by nothing else yet.
    dim: Number(dimLayer.style.opacity),
    // The root every size on the page is measured off, as the page wrote it —
    // the string and not a number, so a test can tell a root that was set from
    // one that was never touched at all.
    text: document.documentElement.style["--text-size"],
    sleep: sleepButton.textContent,
    spokenSleep: sleepButton.getAttribute("aria-label"),
    armed: sleepButton.classList.contains("armed"),
    playing: playpause.classList.contains("playing"),
    fading: fade !== null,
    sleepLeftMs,
    volume: player.volume,
    // Whether a list of places is over the page, and how many of the ones on it
    // have been asked to show their words. Both belong in the probe rather than
    // beside it: what cancel promises is that everything else in this object is
    // the same afterwards, and a promise about "everything else" needs the two
    // things that are allowed to change to be in the same place as the rest.
    candidatesUp: !candidates.hidden,
    revealed: candidateList.children.filter((li) =>
      li.classList.contains("revealed"),
    ).length,
    // Whether Books is over the page, whether Workshop is over that, and
    // whether there is a wake scheduled. All three are in the probe for the
    // same reason as the two above: close promises that everything else in this
    // object is unchanged, and a timer still running after close is exactly the
    // promise being broken — a radio wake every five seconds, all night, beside
    // somebody asleep.
    //
    // The wake belongs to Workshop now, which is the screen the queue rows are
    // on. queueUp true with workshopUp false and queuePolling false is the
    // ordinary state of a night: the book list is open and nothing is asking
    // the server anything.
    queueUp: !queuePanel.hidden,
    workshopUp: !workshop.hidden,
    // And whether one book's own page is over that. It is in the probe for the
    // reason the two above it are: a screen that outlived the one it was opened
    // from is the one state on this page with no way out of it, and close
    // promises everything else in this object is unchanged.
    bookUp: !bookPanel.hidden,
    queuePolling: queuePoll !== 0,
    // And whether Settings is over the page. It is here for the same reason as
    // the three above and for one of its own: it is the one overlay that asks
    // the server nothing at all, so what a test has to be able to see is that
    // opening and closing it left every other field in this object alone.
    settingsUp: !settingsPanel.hidden,
    // Which of the two screens the page is on, and whether there is a keyboard
    // over whatever is showing. Two facts and not one: a keyboard over the books
    // panel is a keyboard with the player still behind it, and an overlay that
    // shrank its rows for a screen nobody is on would be the same bug this pair
    // replaced. Both are in the probe rather than beside it because cancel and
    // close promise that everything in this object is unchanged, and a press
    // that quietly moved the page to another screen is that promise broken.
    screen: whichScreen,
    keyboardUp: document.body.classList.contains("keyboard-up"),
  }),
  seekGlobal,
  openBook,
  follow,
  resumePoint,
  // The last query's places, put back on the screen. It is the one entry point
  // here that a thumb also has - the position line presses it - and it is
  // exposed for what happens before that press: a list read out of storage at
  // boot is only a real list if this can raise it and a row can then be gone to.
  showRemembered,
  // The four pure functions the whole timeline rests on. They are worth
  // reaching for directly: every clamp in them is there because a decoder, a
  // render clock or a book shorter than a thirty-second step disagreed with
  // the arithmetic once, and none of those are reproducible on demand.
  math: {
    locate,
    toElementSeconds,
    toGlobalMs,
    toBookMs,
    timestamp,
    chapterTime,
    rewindFor,
  },
};
`;

/**
 * Boot the page against a fake browser, and hand back the levers.
 *
 * `t` is the node:test context, and is only used to clear whatever timers the
 * page still has pending when the test ends — the retry backoff and the
 * wait-for-the-render ladder both schedule minutes ahead, and a test that left
 * one running would hold the whole run open.
 */
export async function boot(t, options = {}) {
  const {
    lastGid = 900001,
    reply = { accepted: true },
    sentenceStart = null,
    // What is being said where the "you are here" rule falls — the one thing on
    // the list of places the page has to go back and ask for, because the rule
    // names no passage and the answer that drew the list carried none for it.
    //
    // A passage by default, because that is what a book with text in it
    // answers, and the interesting arms are the two that are not: `null` is a
    // book nobody has played a second of or one whose text was never indexed,
    // and `gone.passage` is the tailnet. Both have to leave the row with no
    // reveal on it rather than with one that does nothing.
    passageText = "The lamps were going out along the road.",
    stored = {},
    answer = { reply: "…" },
    // Which books there are at all. Every fixture, unless a test says
    // otherwise — and the one that says otherwise says `[]`, which is a somnia
    // that has never rendered anything and is the state the books panel exists
    // for.
    //
    // The rows are player.BookEntry's shape, field for field, drawn from the
    // manifests themselves so the two can never disagree about a book. That
    // matters now the shelf draws from them: a harness that answered with only
    // a gid, as this one did while nothing read the rest, would let a page pass
    // that cannot say where any book was left.
    library = null,
    // Whether this browser has a visual viewport at all. Every engine that can
    // run this page does, so `false` is the arm and not the ordinary case — it
    // is here because what that arm decides is whether the conversation can be
    // reached at all on an engine that cannot be measured.
    canMeasure = true,
    // Whether anybody has touched this page yet. False is a page nobody has
    // pressed — a document some browser has restored, where a box can end up
    // focused and a keyboard can come up having asked nobody. Which browser and
    // by what route is deliberately not said here: the page's rule is that a
    // press is what wants the chat screen and a focus is not one, and it holds
    // whatever engines turn out to do. Every other test here is a page with a
    // thumb on it.
    activated = true,
    // The query on the address the app was opened at. "?chapters" is the one
    // the page reads: play the book a file at a time, the way it was played
    // before the whole of it came down one URL.
    query = "",
  } = options;

  // Everything the element and the media session did, in the order they did
  // it. A boundary is only correct as a sequence, so order is the assertion.
  const order = [];
  const clock = new FakeClock();
  const session = new FakeSession(order);
  const elements = new Map();
  // This page's own copy of what the server knows, because one thing really
  // does change underneath a page in the night: a render finishes a chapter and
  // the book the page opened is not the book it will be asked about next. A test
  // says so with `page.serves`, and a copy per boot is what keeps that from
  // being a chapter every other suite in the run silently inherits.
  const manifests = new Map(MANIFESTS);
  // What /api/books answers with, made once rather than per request — because
  // the writes a book's page makes change it. A rename that left this list
  // alone would be a fake server that forgot what it had just been told, and
  // the page would be judged for redrawing the old name faithfully.
  const shelfRows = library ?? EVERY_BOOK.map(listed);
  const audio = new FakeAudio(order, clock, elements, manifests);
  const localStorage = new FakeStorage(stored);
  const sessionStorage = new FakeStorage();

  const el = (id) => {
    if (!elements.has(id)) {
      const node = new FakeElement(id, elements);
      // index.html ships these with a `hidden` attribute on them, and a fake
      // that handed every element back visible would let an overlay pass a test
      // it fails in a browser: the page never hides these itself, it only ever
      // shows them, so their starting state comes from the document or from
      // nowhere at all.
      node.hidden = BORN_HIDDEN.has(id);
      node.disabled = BORN_DISABLED.has(id);
      if (BORN_TYPED.has(id)) node.value = "";
      elements.set(id, node);
    }
    return elements.get(id);
  };

  let minted = 0;
  const fetches = [];
  const posts = [];
  const beacons = [];
  const sentenceAsks = [];
  const passageAsks = [];
  const asks = [];
  let positionReply = reply;
  let askReply = answer;
  let holding = false;
  let dropping = false;
  const held = [];

  // The queue, as the panel sees it. Everything about it is per-test, because
  // there is no such thing as a default queue: an empty one and an unreachable
  // one look identical on the wire and mean opposite things, which is half of
  // what the panel is judged on.
  const submits = [];
  const stops = [];
  const searches = [];
  // Every book the page asked to be made the current one, and whether the
  // server is refusing to — which is what it does for a book with nothing to
  // play, and the one refusal a press on the shelf can meet.
  const opens = [];
  let openRefused = false;
  // Every time the page asked for the roster, and every sample it played. The
  // second one is the whole of what the picker does that a class on a pill
  // cannot show: a voice is chosen by hearing it.
  const voiceAsks = [];
  const samples = [];
  const samplers = [];
  let queueItems = [];
  let catalogFound = [];
  // The roster the picker draws, as /api/voices answers it. Two of the six the
  // server really ships, which is enough for every question a test has — which
  // one is chosen, that the choice is remembered, that it reaches the submit —
  // and short enough to read in an assertion.
  let voiceRoster = [
    { id: "af_heart", name: "heart", says: "American, warm and unhurried" },
    { id: "bm_george", name: "george", says: "British, a man, low" },
  ];
  // Every rename and every delete the page asked for, and what somnia said
  // back. Two answers rather than one flag each: the delete's refusal is a book
  // that is being rendered, which is a 200 with `ok` false and a sentence — and
  // it is the arm of this that has to leave the screen standing.
  const renames = [];
  const removes = [];
  const finishes = [];
  let renameAnswer = { ok: true, found: true, said: "It is called that now." };
  let removeAnswer = {
    ok: true,
    found: true,
    said: "Three Tones is gone, with everything rendered of it.",
  };
  let submitAnswer = { ok: true, id: 1, said: "It is next to be rendered." };
  let stopAnswer = { ok: true, state: "cancelled", said: "Taken out." };
  // Which of the six the tailnet is eating at the moment. Held apart rather
  // than as one switch because the interesting failures are one-sided: a submit
  // that never landed while the list is still arriving is the press that must
  // leave no row behind, and it cannot be staged with a server that is simply
  // gone.
  const gone = {
    queue: false,
    submit: false,
    stop: false,
    catalog: false,
    voices: false,
    open: false,
    books: false,
    passage: false,
    // The two writes a book's own page makes. Held apart from `books` above
    // because the interesting failure is one-sided: a rename that never landed
    // while the list is still arriving perfectly well is a box that has to put
    // back what the server still holds.
    rename: false,
    remove: false,
    finish: false,
  };

  const fakeWindow = new FakeElement("window");
  const fakeDocument = new FakeElement("document");
  // What is left of the page after whatever the platform has put over it, which
  // is the one thing that can tell a keyboard from a window somebody dragged
  // shorter. A FakeElement because all the page asks of it is a height and a
  // resize listener, and the listener half is already here.
  const visualViewport = new FakeElement("visual-viewport");
  visualViewport.height = VIEWPORT_HEIGHT;
  if (canMeasure) fakeWindow.visualViewport = visualViewport;
  // <body>, which the page writes both of its two states onto: which screen it
  // is on, and whether there is a keyboard over it. It is not in the id
  // registry because nothing ever asks the document for it — the page reaches it
  // through document.body, as a browser hands it over.
  fakeDocument.body = new FakeElement("body");
  // <html>, carrying one thing, and it is the size of every word on the page:
  // the root the whole rem scale is measured off. Handed over the way a browser
  // hands it over rather than through the id registry, for the same reason
  // <body> is — nothing ever asks the document for it by name.
  fakeDocument.documentElement = new FakeElement("html");
  fakeDocument.getElementById = el;
  fakeDocument.visibilityState = "visible";
  // Made without an id, so nothing is registered until the page gives it one —
  // which it does for every node a thumb can land on, and for none of the rest.
  fakeDocument.createElement = (tag) => {
    const node = new FakeElement(null, elements);
    node.tagName = String(tag).toUpperCase();
    return node;
  };

  // Cleared when the test ends. The page has no idea it is in one, and it is
  // entitled to be waiting five seconds for a chapter that will never come.
  const timers = new Set();
  // The same waits, with what they were asked for and what they will do — so a
  // test can say "there is a five second wake pending" and then have it happen,
  // instead of waiting five real seconds for it. Everything else in this
  // harness fires events by hand for exactly this reason; a poll is no
  // different from a boundary, and a suite that slept for its timers would take
  // longer than the night it is testing.
  const scheduled = new Map();
  // Whether the test is over. A request that was in flight when it ended still
  // comes back, and what it does when it comes back is usually to ask for
  // another wake — so without this the last thing a torn-down page does is
  // schedule a timer nobody will ever clear, and the whole run sits there until
  // it fires. The page is entitled to do that; a browser would simply have
  // thrown the document away underneath it.
  let over = false;

  const context = {
    console: { error() {}, log() {}, warn() {} },
    document: fakeDocument,
    window: fakeWindow,
    localStorage,
    sessionStorage,
    // A fresh one every time it is asked for, which is the whole of what the
    // page uses it for: starting over throws the conversation away by minting a
    // new name for it, and a stub that answered the same string twice would let
    // a page that never minted anything pass.
    crypto: { randomUUID: () => `test-token-${++minted}` },
    Blob: FakeBlob,
    MediaMetadata: FakeMediaMetadata,
    // A voice sample, which is the one sound this page makes that is not the
    // book. Deliberately not a FakeAudio: it has none of the book's machinery
    // on it — no chapters, no reports, no media session — and a stand-in that
    // had would invite a test to assert the picker does something to the night
    // that it must not.
    Audio: class {
      constructor() {
        this.src = "";
        this.paused = true;
        // Kept so a test can ask whether the sample is still going. The page
        // holds the only other reference to it, and "is a stranger still
        // reading out of a screen nobody is looking at" is not answerable from
        // the list of things that were started.
        samplers.push(this);
      }

      play() {
        this.paused = false;
        samples.push(this.src);
        return Promise.resolve();
      }

      pause() {
        this.paused = true;
      }
    },
    URLSearchParams,
    // The address the app was opened at. Only the query is ever read, and only
    // once, at load: `?chapters` is how the same phone can be made to play the
    // book the old way on the same night, and a page that read it later than
    // this could be in two minds about a book half way through one.
    location: { search: query },
    // The clock, and one thing more than it used to be. Everything the page
    // asks the wall for is Date.now(), which is the fake clock — but the
    // morning screen names the time the fade happened, and naming an hour and a
    // minute means constructing a date around a millisecond. So the real Date
    // is handed over with only `now` replaced: `new Date(ms)` behaves exactly
    // as a browser's does, in the timezone the test run is in, which is why
    // nothing here asserts a literal `1:47`.
    //
    // `new Date()` with no argument is therefore the real present and not the
    // fake clock. Nothing in app.js does that, and anything that started to
    // would be reading a second clock — which is worth a failing test rather
    // than a fake that quietly answered for both.
    Date: class extends Date {
      static now() {
        return clock.now();
      }
    },
    navigator: {
      language: "en-GB",
      userActivation: { hasBeenActive: activated },
      mediaSession: session,
      vibrate() {},
      sendBeacon(url, blob) {
        beacons.push({ url, type: blob.type, body: JSON.parse(blob.text) });
        return true;
      },
    },
    setTimeout: (fn, ms) => {
      if (over) return 0;
      const id = setTimeout(() => {
        timers.delete(id);
        scheduled.delete(id);
        fn();
      }, ms);
      timers.add(id);
      scheduled.set(id, { ms, fn });
      return id;
    },
    clearTimeout: (id) => {
      timers.delete(id);
      scheduled.delete(id);
      clearTimeout(id);
    },
    fetch: async (url, init) => {
      fetches.push(url);
      if (url === "api/books") {
        if (gone.books) throw new Error("no route to host");
        return json({
          last_gid: lastGid,
          books: shelfRows,
        });
      }
      // Making a book the one a cold launch opens, which is the whole of
      // switching books. It answers with the book's own position and count —
      // untouched, because the route writes neither — and the page throws that
      // body away and asks for the manifest, which is the point: nothing here
      // is a second place a position is remembered.
      if (url.startsWith("api/book/") && url.endsWith("/open")) {
        if (gone.open) throw new Error("no route to host");
        opens.push(url);
        if (openRefused) {
          return { ok: false, json: async () => ({ error: "no book to open" }) };
        }
        const opened = manifests.get(url.slice(0, -"/open".length));
        return json({
          gid: opened ? opened.gid : 0,
          position_ms: opened ? opened.position_ms : null,
          seq: opened ? opened.seq : 0,
        });
      }
      // What a book is called here, and taking one away. Both are answered
      // exactly as server.py answers them — a refusal is a 200 with a sentence
      // in it, and only a gid that is not here is a 404 — because a page tested
      // against a kinder server is a page that treats "it is being rendered" as
      // a failure.
      if (url.endsWith("/name") && init?.method === "POST") {
        if (gone.rename) throw new Error("no route to host");
        const named = JSON.parse(init.body);
        renames.push(named);
        if (renameAnswer.ok) {
          const gid = Number(url.split("/")[2]);
          const book = manifests.get(`api/book/${gid}`);
          // A copy, and this is not fussiness: the map is per boot but the
          // manifests in it are the module's own fixtures, so a rename written
          // through one of them is a book called something else in every suite
          // that runs after this one.
          if (book) {
            manifests.set(`api/book/${gid}`, {
              ...book,
              title: named.title,
              authors: named.authors,
            });
          }
          for (const row of shelfRows) {
            if (row.gid === gid) {
              row.title = named.title;
              row.authors = named.authors;
            }
          }
        }
        return json(renameAnswer);
      }
      if (url.startsWith("api/book/") && init?.method === "DELETE") {
        if (gone.remove) throw new Error("no route to host");
        removes.push(url);
        // A book that really goes takes its manifest with it, so a page that
        // asked about it again would meet the 404 a real somnia gives — and a
        // refusal leaves it exactly where it was, which is the whole of what a
        // refusal means.
        if (removeAnswer.ok) {
          manifests.delete(url);
          const gid = Number(url.split("/")[2]);
          const at = shelfRows.findIndex((row) => row.gid === gid);
          if (at !== -1) shelfRows.splice(at, 1);
        }
        return json(removeAnswer);
      }
      // Finished, or not after all, which is one column and its own undo. The
      // stamp is whatever the server would have written; nothing on the page
      // reads it as a date, and everything reads it as whether there is one.
      if (url.endsWith("/finished") && init?.method === "POST") {
        if (gone.finish) throw new Error("no route to host");
        const asked = JSON.parse(init.body);
        finishes.push({ url, finished: asked.finished });
        const gid = Number(url.split("/")[2]);
        for (const row of shelfRows) {
          if (row.gid === gid) {
            row.finished_at = asked.finished ? "2026-08-10 21:00:00" : null;
          }
        }
        return json({
          ok: true,
          found: true,
          said: asked.finished
            ? "It is finished."
            : "It is back on the shelf.",
        });
      }
      if (manifests.has(url)) return json(manifests.get(url));
      // The agent, stood in for by whatever the test decided it would say. The
      // question is kept because half of what the page owes a turn is that the
      // right one was asked, and that a conversation started over is not.
      if (url === "api/ask") {
        asks.push(JSON.parse(init.body));
        return json(typeof askReply === "function" ? askReply() : askReply);
      }
      // The queue and the catalog, which between them are the whole of the
      // panel's conversation with the server. Every one of them is answered
      // exactly as server.py answers it — a refusal is a 200 with a sentence in
      // it, not a status code — because a page that treated "already here" as a
      // failure would be a page tested against a server somnia does not run.
      if (url === "api/queue" && init?.method === "POST") {
        if (gone.submit) throw new Error("no route to host");
        submits.push(JSON.parse(init.body));
        return json(submitAnswer);
      }
      if (url === "api/queue") {
        if (gone.queue) throw new Error("no route to host");
        return json({ items: queueItems });
      }
      if (url.startsWith("api/queue/")) {
        if (gone.stop) throw new Error("no route to host");
        stops.push(url);
        return json(stopAnswer);
      }
      if (url.startsWith("api/catalog")) {
        if (gone.catalog) throw new Error("no route to host");
        searches.push(url);
        return json({ query: url, entries: catalogFound });
      }
      // The voices a book may be asked for in. Counted, because the page is
      // supposed to ask for this once and keep it: it changes when somnia is
      // deployed and not while somebody is looking at a list of books.
      if (url === "api/voices") {
        if (gone.voices) throw new Error("no route to host");
        voiceAsks.push(url);
        return json({ voices: voiceRoster });
      }
      if (url.startsWith("api/sentence/")) {
        sentenceAsks.push(url);
        return json({ start_ms: sentenceStart });
      }
      if (url.startsWith("api/passage/")) {
        if (gone.passage) throw new Error("no route to host");
        passageAsks.push(url);
        return json({ text: passageText });
      }
      if (url === "api/position") {
        // A report that never gets out at all, which is a different thing from
        // one that is answered late: the page is told nothing, so whatever it
        // was carrying is still owed. Held is the tailnet being slow; this is
        // the tailnet being gone.
        if (dropping) throw new Error("no route to host");
        const answer = positionReply;
        posts.push({
          body: JSON.parse(init.body),
          keepalive: Boolean(init.keepalive),
        });
        // A report that has gone out and not come back: 2am, tailnet asleep.
        // Holding one is the only way to see what the page does with a reply
        // that arrives about a book it has since left. What it is answered
        // with is read at release rather than here, because that is when the
        // server would decide it — and because the interesting refusals are
        // about things that had not happened yet when the report went out.
        if (holding) {
          return new Promise((resolve) => {
            held.push(() => resolve(json(positionReply)));
          });
        }
        return json(answer);
      }
      return { ok: false, json: async () => ({ error: "no such thing" }) };
    },
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(readFileSync(APP, "utf8") + EPILOGUE, context);

  // One turn of the microtask queue per await. Two is what boot costs: the
  // book list, then the manifest.
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
  await settle();
  await settle();

  const page = {
    audio,
    session,
    storage: localStorage,
    // The two least testable moments of the night are the last two: the page
    // being backgrounded, and the page dying. Both are events on these.
    window: fakeWindow,
    document: fakeDocument,
    // Where the page says which screen it is on and whether a keyboard is over
    // it. The classes are what the stylesheet reads, so they are what a test
    // about a screen has to look at — the probe reports the same two facts, and
    // a page that set the variable without writing the class would pass one and
    // fail the other.
    body: fakeDocument.body,
    el,
    // The viewport coming up short, which is what a keyboard arriving looks like
    // from inside the page — and, with nothing focused, what a window being
    // dragged looks like. The two are the same event and telling them apart is
    // the whole of what these tests are about.
    resize: (height) => {
      visualViewport.height = height;
      visualViewport.fire("resize");
    },
    // Focus, said by hand as a browser says it. Which box matters: the
    // composer's keyboard is the chat screen and the books panel's is a
    // keyboard over an overlay with the player still behind it.
    focus: (id) => el(id).fire("focus"),
    blur: (id) => el(id).fire("blur"),
    // A finger going down on something, which is where every press on this page
    // really starts and is the whole of how the chat screen is asked for. It is
    // not `click`: the two are a keyboard and a focus apart on a phone, and what
    // the page promises is that the screen has already changed by the first of
    // them.
    touch: (id) => el(id).fire("pointerdown", { preventDefault() {} }),
    order,
    posts,
    beacons,
    fetches,
    sentenceAsks,
    passageAsks,
    asks,
    storageSession: sessionStorage,
    settle,
    tick: (ms) => clock.tick(ms),
    probe: () => plain(context.__page.probe()),
    // The state machine itself, for the moves that arrive from the agent
    // rather than from a thumb.
    seek: (...args) => context.__page.seekGlobal(...args),
    openBook: (...args) => context.__page.openBook(...args),
    openPlaces: () => context.__page.showRemembered(),
    follow: (...args) => context.__page.follow(...args),
    resumePoint: () => context.__page.resumePoint(),
    math: Object.fromEntries(
      Object.entries(context.__page.math).map(([name, fn]) => [
        name,
        (...args) => plain(fn(...args)),
      ]),
    ),
    click: (id) => el(id).fire("click"),
    press: (...args) => session.press(...args),
    // Typing a question and pressing send, which is the only way into ask() and
    // therefore the only way a list of places ever reaches the screen. Four
    // turns of the queue: the post, its body, and whatever the answer set off.
    ask: async (text) => {
      el("question").value = text;
      el("composer").fire("submit", { preventDefault() {} });
      for (let turn = 0; turn < 4; turn++) await settle();
    },
    // What the agent will say to the next question.
    answers: (body) => {
      askReply = body;
    },
    // What the queue is, what the catalog finds in it, and what the two write
    // routes say back. Set per test in the style of `answers` above: the panel
    // is a readout of somebody else's state machine, so every test that draws a
    // row has to say what the server would have said.
    queueView: (items) => {
      queueItems = items;
    },
    catalogEntries: (entries) => {
      catalogFound = entries;
    },
    // The roster the server would serve, and what the picker has since played.
    voices: (roster) => {
      voiceRoster = roster;
    },
    voiceAsks,
    samples,
    // Whether a voice sample is playing right now, as against which ones were
    // ever started.
    sampling: () => samplers.some((one) => !one.paused),
    submitReply: (body) => {
      submitAnswer = body;
    },
    stopReply: (body) => {
      stopAnswer = body;
    },
    // The server refusing to open a book, which is what it answers for a book
    // there is nothing to play of and for one that is not there at all.
    refuseToOpen: (on) => {
      openRefused = on;
    },
    // The render has finished another chapter. From here on everything the page
    // can ask about that book answers with the longer one — the manifest, and
    // the length of whatever join it names — which is the only thing that
    // changes underneath a page between eleven and morning.
    //
    // It says nothing to the page. Nothing does: the page finds out by asking,
    // and when it asks is most of what the frontier is about.
    serves: (book) => {
      manifests.set(`api/book/${book.gid}`, book);
    },
    // The tailnet eating one endpoint and not the others.
    unreachable: (which) => Object.assign(gone, which),
    submits,
    stops,
    searches,
    opens,
    renames,
    removes,
    finishes,
    // What the two writes on a book's page say back, set per test the way the
    // queue's two are: the refusals are the whole subject of that screen, and a
    // page can only be judged against a server that gives them.
    saysRename: (answer) => {
      renameAnswer = answer;
    },
    saysRemove: (answer) => {
      removeAnswer = answer;
    },
    reply: (answer) => {
      positionReply = answer;
    },
    hold: (on) => {
      holding = on;
    },
    drop: (on) => {
      dropping = on;
    },
    // Let every held report come back at once, oldest first.
    release: () => {
      while (held.length) held.shift()();
    },
    // Only the reports, only the interesting fields, in order — which is how
    // every assertion about them reads.
    reports: () =>
      posts.map((p) => [p.body.gid, p.body.reason, p.body.position_ms]),
    // Every wake the page is still waiting on, in the order it asked for them,
    // said as the delays it asked for. A cleared timer is gone from here, which
    // is what makes "nothing is scheduled" assertable at all.
    waits: () => [...scheduled.values()].map((wake) => wake.ms),
    // That wake, now. The oldest one asked for exactly this delay, and only
    // that one: two different things waiting the same five seconds is the
    // ordinary case — the queue poll and a confirmation forgetting itself both
    // do — and a helper that fired both together could not tell a page that
    // survives one of them from a page that does not.
    wake: (ms) => {
      const due = [...scheduled].find(([, wake]) => wake.ms === ms);
      if (!due) return false;
      const [id, wake] = due;
      clearTimeout(id);
      timers.delete(id);
      scheduled.delete(id);
      wake.fn();
      return true;
    },
    stop: () => {
      over = true;
      for (const id of timers) clearTimeout(id);
      timers.clear();
      scheduled.clear();
    },
  };
  t?.after(page.stop);
  return page;
}

function json(body) {
  return { ok: true, json: async () => body };
}
