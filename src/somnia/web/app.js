// The 2am client. Push to talk, let go, get taken back to the passage.
//
// Speech recognition is push-to-talk rather than always-listening on purpose:
// a bedroom is full of speech that was not meant for somnia, and holding a
// button is the one gesture that survives being half asleep.
//
// The book plays here as well. somnia renders it one file per chapter, but
// nobody listens to a chapter — they listen to a book — so everything below
// counts in global milliseconds, the same clock the search results and the
// agent speak, and which file that lands in is an implementation detail kept
// to a handful of functions. The server joins the chapters back into one file
// for exactly that reason: given the whole book down one URL, crossing a
// chapter is arithmetic and the media element is never touched at all.
//
// Most of the controls are not on this page at all. With the screen off the
// book is driven from the lock screen and from whatever is paired over
// Bluetooth, so the media session below is not decoration — for most of the
// night it is the only transport there is.

const transcript = document.getElementById("transcript");
const composer = document.getElementById("composer");
const question = document.getElementById("question");
const talk = document.getElementById("talk");
const restart = document.getElementById("restart");
// The header's other left-hand pill: the way back off the chat screen. It is a
// second button rather than `books` relabelled because the two do different
// things, and a control whose action is held in a variable is one the sheet
// cannot draw and a reader cannot trust. Which of them is in the corner is the
// screen's business, and the screen is a class on <body>.
const toControls = document.getElementById("to-controls");
const statusLine = document.getElementById("status");
const player = document.getElementById("player");
const playerBar = document.getElementById("player-bar");
const bookTitle = document.getElementById("book-title");
const chapterTitle = document.getElementById("chapter-title");
const chapterWord = document.getElementById("chapter-word");
const chapterCount = document.getElementById("chapter-count");
const clock = document.getElementById("clock");
// The position line, which is also the way back to the places somnia last
// found, and the count that says so. It is a control only on the nights there
// is something behind it; see drawPlaces.
const placesOpen = document.getElementById("places-open");
const placesFound = document.getElementById("places-found");
const wholePlayed = document.getElementById("whole-played");
const sleepButton = document.getElementById("sleep");
const playpause = document.getElementById("playpause");
const back30 = document.getElementById("back30");
const fwd30 = document.getElementById("fwd30");
const chapterClock = document.getElementById("chapter-clock");
const prevChapter = document.getElementById("prevchapter");
const nextChapter = document.getElementById("nextchapter");
// The morning screen, and the four things drawn on it. Two are written out of
// the record the fade left — what time it went and where it stopped — and the
// third is the same count the position line carries, drawn from the same place
// so the two can never say different numbers about one list.
const wakeSaid = document.getElementById("wake-said");
const wakePlaces = document.getElementById("wake-places");
const wakeFound = document.getElementById("wake-found");
const wakeAsk = document.getElementById("wake-ask");
const wakeKeep = document.getElementById("wake-keep");
const candidates = document.getElementById("candidates");
const candidatesBook = document.getElementById("candidates-book");
const summaryLine = document.getElementById("candidates-summary");
const candidateList = document.getElementById("candidate-list");
const candidatesCancel = document.getElementById("candidates-cancel");
// Books, the night panel. `queuePanel` rather than `queue` because "the queue"
// in this file means the rows the server is holding, and those are not on this
// screen at all any more — they are in Workshop, which is a photograph of them
// taken every five seconds and only while somebody is looking.
//
// The id stayed `queue` when the panel became Books and then when the queue left
// it, which is two chances to rename it not taken. Both were declined for the
// same reason the header's pill says `books` over an element called `#books`: an
// id is not a word anybody reads at 2am, and renaming one across the sheet, the
// tests and this file is a diff that hides the change actually being made.
const booksButton = document.getElementById("books");
const queuePanel = document.getElementById("queue");
// Workshop, the daytime screen, and the pill in Books' header that is the only
// way to it.
const workshop = document.getElementById("workshop");
const workshopClose = document.getElementById("workshop-close");
const toWorkshop = document.getElementById("to-workshop");
// The card the live rows sit in, and the label over the rows that are over.
// Both are drawn empty in the document and shown only when there is something
// in them: a card with a heading and no rows under it says something should be
// happening, which at 2am is a reason to get up.
const queueWorking = document.getElementById("queue-working");
const queueLive = document.getElementById("queue-live");
const queueEnded = document.getElementById("queue-ended");
const queueGone = document.getElementById("queue-gone");
const queueNote = document.getElementById("queue-note");
const queueSearch = document.getElementById("queue-search");
const queueQuery = document.getElementById("queue-query");
const queueResults = document.getElementById("queue-results");
const queueSaid = document.getElementById("queue-said");
const queueClose = document.getElementById("queue-close");
// What is playing under the panel, at the top of it. `reading` and not `queue`
// because this is the one part of that overlay that is about a book rather than
// about the rows the server is holding, and the two must not be muddled here of
// all places.
const readingNow = document.getElementById("reading-now");
const readingLabel = document.getElementById("reading-label");
// The block itself, which is the press: there is no button under it any more.
const readingOpen = document.getElementById("reading-open");
const readingTitle = document.getElementById("reading-title");
const readingMeta = document.getElementById("reading-meta");
const readingTrack = document.getElementById("reading-track");
const readingFill = document.getElementById("reading-fill");
// The books somnia already has, under the one it is playing, and the label over
// them. The label goes with the rows — the rule every other list on this panel
// follows, because a heading over nothing is a claim that something is there.
const shelfLabel = document.getElementById("shelf-label");
const shelf = document.getElementById("shelf");
// Whether that shelf is what somnia has or the last thing it said before the
// tailnet went. Its own line, on its own screen — see askForTheShelf.
const shelfNote = document.getElementById("shelf-note");
// Settings, the third night screen, and the pill in the player's other corner
// that is the only way to it. It holds the two controls that had nowhere to be —
// how dark the room is, and how far `−30` and `+30` move — and it is a night
// screen rather than part of Workshop because both of them are reached for in
// the dark with the book already playing.
const settingsPanel = document.getElementById("settings");
const settingsClose = document.getElementById("settings-close");
const toSettings = document.getElementById("to-settings");
// The page's second voice, and the sheet of black over the whole of it. The
// voice is three nodes: the box, the sentence in it, and the one press it is
// ever allowed to carry.
const toastLine = document.getElementById("toast");
const toastSaid = document.getElementById("toast-said");
const toastUndo = document.getElementById("toast-undo");
const dimLayer = document.getElementById("dim");
// The two presses that move that sheet, and the readout between them. On a
// night screen, which is the whole of what makes a settings surface safe to set
// this from: the layer is over Settings exactly as it is over the player, so
// every press dims the page the press is on.
const dimDown = document.getElementById("dim-down");
const dimUp = document.getElementById("dim-up");
const dimFill = document.getElementById("dim-fill");
// And the same three for the size of the words, which is the control above it
// on the same screen and drawn by the same rules in the sheet.
const textDown = document.getElementById("text-down");
const textUp = document.getElementById("text-up");
const textFill = document.getElementById("text-fill");
// What `−30` and `+30` mean, set on Settings and read on the player. Kept by
// their value rather than in an array of elements, because what the rest of this
// file asks is "which one is 30?" and never "which one is second?".
const jumpButtons = new Map([
  [15, document.getElementById("jump-15")],
  [30, document.getElementById("jump-30")],
  [60, document.getElementById("jump-60")],
]);

// One conversation per launch of the app. The server holds the history; this
// is only the name it goes by.
let token = sessionStorage.getItem("somnia-token");
if (!token) {
  token = crypto.randomUUID();
  sessionStorage.setItem("somnia-token", token);
}

function say(text, kind) {
  const line = document.createElement("p");
  line.className = `said ${kind}`;
  line.textContent = text;
  transcript.append(line);
  transcript.scrollTop = transcript.scrollHeight;
  return line;
}

// Answers are read, never spoken back. The book is the only thing this page
// says out loud — nothing below turns an answer into speech — because an
// answer read over the book would be somnia interrupting itself, and the phone
// is on a bedside table next to someone who may be asleep again by the time it
// lands.
//
// Two kinds of sentence come through here and they are not the same news. Most
// of them are somnia saying what it is doing — listening, waiting, goodnight,
// and above all "the rest of this book hasn't been read yet", which is the
// render frontier and is the most common thing that happens in a night. Nothing
// is wrong in any of those; the book comes back on its own.
//
// The rest need a person: a chapter that never arrived, a book that cannot be
// reached, a book that is not there any more. Those pass `failed` and are drawn
// in the red rather than the amber — see --failed in style.css for why failure
// is not allowed to borrow the colour that already means five other things.
//
// The flag is deliberately per-call and not sticky. Every one of these
// sentences replaces the last, so the colour has to be decided by whichever
// sentence is standing, and a `failed` that outlived the sentence that set it
// would leave the frontier drawn red — the exact confusion this split exists to
// prevent. Clearing the line clears it too, because "" passes nothing.
function setStatus(text, failed) {
  statusLine.textContent = text;
  statusLine.classList.toggle("failed", Boolean(failed));
}

// The other voice, and why there are two.
//
// #status above holds the sentences that have to stand: "listening…" for as
// long as a button is held, "tap anywhere to carry on" until somebody does,
// "the rest of this book hasn't been read yet" until they go somewhere it has.
// A line that cleared itself after a few seconds could not hold any of those —
// the instruction would be gone and the state it describes would not.
//
// This holds the other kind: what the press they just made did. It is true
// when it is read and untrue a minute later, so it takes itself off, and it
// happens at the bottom of the screen near the thumb that caused it rather
// than at the top where the reading is.
//
// One box, one sentence. A second one replaces the first in place rather than
// pushing it up a stack: the older sentence is never the one still true, and a
// box that jumped every time a control was pressed would read as an alarm on a
// page whose whole argument is that nothing moves unless it has to.
const TOAST_MS = 2800;

// Longer, for the one sentence that is not only a sentence. 2.8 seconds is how
// long it takes to read what a press did; a way back has to outlast the moment
// somebody realises they wanted it, which is after they have read the sentence
// and not during. Six is the design's number and it is the right shape: long
// enough that the realisation still has somewhere to land, short enough that
// the microphone is not covered for a meaningful part of the night.
const TOAST_UNDO_MS = 6000;

let toastTimer = 0;
// What the way back does, or null on every other sentence the page says. It is
// held here rather than left on the button so that "is there a way back on
// offer?" has one answer: the handler below is hung on the element once, at
// boot, and it is this that decides whether a press means anything.
let toastAction = null;

function toast(text, undo = null) {
  clearTimeout(toastTimer);
  toastSaid.textContent = text;
  toastAction = undo;
  toastUndo.hidden = !undo;
  toastLine.hidden = false;
  toastTimer = setTimeout(forgetToast, undo ? TOAST_UNDO_MS : TOAST_MS);
}

// Emptied as well as hidden, so that "is anything being said?" has one answer
// and not two that can disagree. The way back goes with it, for the same
// reason: a handler still holding a position after the box has gone is a press
// that could land on a sentence nobody can see.
function forgetToast() {
  clearTimeout(toastTimer);
  toastTimer = 0;
  toastLine.hidden = true;
  toastSaid.textContent = "";
  toastAction = null;
  toastUndo.hidden = true;
}

// The way back is withdrawn the moment anything else moves the book, and the
// sentence it was offered beside is left standing.
//
// It has to be, because what it holds is a position and not an intention: the
// book can move again inside those six seconds by three routes that have
// nothing to do with this press — a thumb on −30, a chapter skip, the agent
// answering the next question — and an undo pressed afterwards would take them
// somewhere they had already chosen to leave. That is not a way back, it is a
// fourth move.
//
// The sentence stays because it is still true. "moved to 1:20:20" is a receipt
// for something that really happened, and it reads no worse for the fact that
// the offer beside it has expired.
function withdrawUndo() {
  if (!toastAction) return;
  toastAction = null;
  toastUndo.hidden = true;
}

// Taken down before it is acted on, so that whatever the way back says about
// itself is not overwritten by the box it was offered in taking itself off.
toastUndo.addEventListener("click", () => {
  const back = toastAction;
  if (!back) return;
  forgetToast();
  back();
});

// How dark the page takes the room, over and above what the phone will do.
// Android holds its own backlight above a floor and this room is below it, so
// the last of the light comes off in a layer of black over everything.
//
// Beside the sleep timer in localStorage, and for the same reason: it is an
// instruction about the dark that outlives a tab the phone discarded while it
// was in a pocket. Unlike the timer it never goes stale — a room that was dark
// last night is dark tonight.
//
// What writes it is `how dark the room` on Settings, and the only thing that
// screen had to be for this to be safe is a night screen: the layer is over it
// exactly as it is over the player, so every press dims the page it is being set
// on, the right level is the one it looks right at, and there is nothing to
// picture from a number.
const DIM_KEY = "somnia-dim";
const DIM_DEFAULT = 0.12;
// Past this the page stops being readable, and the control that would turn it
// back down is under the layer that just went up. A half-written record must
// not be able to black out the only transport in the room, and neither must ten
// presses of `+`.
const DIM_MAX = 0.6;
// Ten presses from clear to the floor. Small enough that no single press can
// lose the page, coarse enough that the whole range is walkable in the dark
// without anybody counting.
const DIM_STEP = 0.06;

let dimLevel = DIM_DEFAULT;

// The level on the layer, on the readout, and in the two presses that change
// it. Everything that sets `dimLevel` comes through here, so the four cannot
// disagree.
function drawDim() {
  // Everywhere but Workshop. That screen is read sitting up with the lights on,
  // and the layer over it would be taking light off the one page in this app
  // that has none to spare — at a level chosen for 3am it made the whole thing
  // unreadable whatever the ink did. The level itself is untouched: this is the
  // layer being lifted for as long as that screen is up, not the setting being
  // changed, so `how dark` reads the same when Books is back in front.
  //
  // Written here rather than as a rule in the sheet because this is the one
  // property on this element the page sets inline, and an inline opacity beats
  // any stylesheet that tried to zero it.
  dimLayer.style.opacity = String(workshop.hidden ? dimLevel : 0);
  // The fill is the level against the range it can be set to, not against 1:
  // this is a readout of a control, and the control stops at DIM_MAX.
  dimFill.style.width = `${Math.round((dimLevel / DIM_MAX) * 1000) / 10}%`;
  // A press at either end says it can do nothing rather than doing nothing
  // quietly — the rule the position readout follows when a book has no places.
  dimDown.disabled = dimLevel <= 0;
  dimUp.disabled = dimLevel >= DIM_MAX;
}

// Rounded to the step before anything is written down, because 0.06 in binary
// floating point walks to 0.18000000000000002 in three presses and that is what
// would land in storage and come back on the next launch. The page would still
// be the right darkness; the record of it would be a number nobody chose.
function setDim(level) {
  dimLevel = Math.min(DIM_MAX, Math.max(0, Math.round(level / DIM_STEP) * DIM_STEP));
  drawDim();
  try {
    localStorage.setItem(DIM_KEY, String(dimLevel));
  } catch (error) {
    // Storage refused. The level still applies to this session, which is the
    // half of it that matters tonight.
    console.error(error);
  }
}

function restoreDim() {
  let level = DIM_DEFAULT;
  try {
    const saved = localStorage.getItem(DIM_KEY);
    // `Number(null)` and `Number("")` are both 0, and 0 is a level somebody
    // can mean — so nothing written down has to be told apart from a level of
    // nothing before the range is checked at all, or a page that has never
    // been set opens with no dim on it. NaN fails both comparisons, which is
    // how every other kind of rubbish falls through to the default.
    const asked = saved?.trim() ? Number(saved) : NaN;
    if (asked >= 0 && asked <= DIM_MAX) level = asked;
  } catch (error) {
    // Storage refused. The page ships at 0.12 and this changes nothing.
    console.error(error);
  }
  // Not through setDim: what is on disk is what somebody chose, and rounding it
  // to this version's step and writing it straight back would edit a record
  // nobody asked to have edited. It is only drawn.
  dimLevel = level;
  drawDim();
}

restoreDim();

dimDown.addEventListener("click", () => setDim(dimLevel - DIM_STEP));
dimUp.addEventListener("click", () => setDim(dimLevel + DIM_STEP));

// ------------------------------------------------------------- how big it is
//
// The root font size, chosen on Settings, applied to the whole page.
//
// It owes its existence to the root above it. That root is a fraction of the
// screen, which is what makes the page match the design on any phone at any
// setting — and the same thing takes browser zoom and Android's display size
// out of play, because both of them work by changing how many CSS px the screen
// is and the root now moves with that. A page that took away the reader's only
// way to resize it and gave nothing back would be an accessibility failure
// dressed as a fix. This is what it gives back.
//
// It is better placed than what it replaces, which is why this is not merely
// restitution. Zoom is several screens into Chrome's settings and retunes every
// app on the phone; this is one press from the player, on a night screen, and
// moves nothing but somnia. And it moves the ROOT, so every rem length goes
// with it — gutters, gaps, radii, the three spacer floors — and the player's
// rhythm survives being resized.
const TEXT_KEY = "somnia-text";
// Multipliers on the root the sheet works out for itself, not sizes of their
// own. The sheet divides the screen by 18 because that is what the design is —
// 360 CSS px across at a 20px root — and this is the only number that moves it,
// so 1 is the page exactly as drawn and the arithmetic stays in the one
// declaration that owns it.
//
// The ceiling is measured, not chosen. 1.2 puts the page at 15rem across, the
// last width the player holds; one step past that is 13.8rem, where the book's
// title truncates to one line and the chapter title clips through its own
// descenders. Neither of those is a scroll, so the range was set by looking at
// renders rather than by reading SCROLLS.
//
// Five steps of 0.1 — enough of a change to be worth a press, few enough to
// walk end to end in the dark without counting.
const TEXT_STEPS = [0.8, 0.9, 1, 1.1, 1.2];
const TEXT_DEFAULT = 1;

let textSize = TEXT_DEFAULT;

// Which step a size is at, or the nearest one to it. A size restored from a
// version with different steps is still a size somebody chose: it has to draw a
// readout and it has to be able to be stepped away from, and `indexOf` alone
// would give it an empty bar and a jump to the end of the range.
function nearestStep() {
  const at = TEXT_STEPS.indexOf(textSize);
  if (at >= 0) return at;
  return TEXT_STEPS.reduce(
    (best, step, i) =>
      Math.abs(step - textSize) < Math.abs(TEXT_STEPS[best] - textSize) ? i : best,
    0,
  );
}

// The size on the page, on the readout, and in the two presses that change it —
// the same four-way agreement `drawDim` keeps, for the same reason.
function drawText() {
  // One custom property, set inline on the root, which the sheet's own
  // `font-size` multiplies. Nothing here computes a size: a second copy of
  // `screen / 18` living in JavaScript is the copy that would drift, and the
  // sheet's default of 1 means a launch before this line runs is the design's
  // own size rather than an unstyled page.
  document.documentElement.style.setProperty("--text-size", String(textSize));
  // Where the size is along the range, drawn rather than stated. A multiplier
  // means nothing to somebody holding the phone; how far along the sizes it is
  // means everything.
  const last = TEXT_STEPS.length - 1;
  textFill.style.width = `${Math.round((nearestStep() / last) * 1000) / 10}%`;
  textDown.disabled = textSize <= TEXT_STEPS[0];
  textUp.disabled = textSize >= TEXT_STEPS[last];
}

// One step along the list, in whichever direction. Walking the list rather than
// doing arithmetic on the value keeps every size that can be stored a size that
// is on it — 0.1 in binary floating point has the same habit 0.06 does, and a
// multiplier of 1.2000000000000002 is a record nobody chose.
function stepText(by) {
  const to = Math.min(TEXT_STEPS.length - 1, Math.max(0, nearestStep() + by));
  setText(TEXT_STEPS[to]);
}

function setText(size) {
  textSize = size;
  drawText();
  try {
    localStorage.setItem(TEXT_KEY, String(textSize));
  } catch (error) {
    // Storage refused. The size still applies tonight, which is the half of it
    // being read right now.
    console.error(error);
  }
}

function restoreText() {
  let size = TEXT_DEFAULT;
  try {
    const saved = localStorage.getItem(TEXT_KEY);
    const asked = saved?.trim() ? Number(saved) : NaN;
    // The range and not the list: a size written by a version with different
    // steps is still one somebody chose and still one this page can draw.
    // Anything outside it — or any rubbish at all, which fails both
    // comparisons as NaN — falls through to the design's own root.
    if (asked >= TEXT_STEPS[0] && asked <= TEXT_STEPS[TEXT_STEPS.length - 1]) {
      size = asked;
    }
  } catch (error) {
    // Storage refused. The page opens at what the sheet says, which is the size
    // it was drawn at.
    console.error(error);
  }
  // Drawn, not set: what is on disk is what somebody chose, and rounding it to
  // this version's steps and writing it back would edit a record nobody asked
  // to have edited. The rule the dim level is restored under.
  textSize = size;
  drawText();
}

restoreText();

textDown.addEventListener("click", () => stepText(-1));
textUp.addEventListener("click", () => stepText(1));

// ---------------------------------------------------------- how far a skip is
//
// What `−30` and `+30` mean, chosen on Settings and read on the player.
//
// It was chosen in Workshop, on the argument that a thing set once is
// configuration and configuration is daytime work. What that got wrong is when
// it is discovered: nobody decides thirty seconds is the wrong distance sitting
// up in daylight — they decide it lying in the dark, having missed the same
// sentence twice with a narrator who leaves long gaps. A control found at 2am
// and settable only by daylight is one nobody gets round to.
//
// Beside the dim level in localStorage and for the same reason: it is a fact
// about how this person uses the app, not about tonight. The sleep timer is the
// one setting that is *not* kept that way — it expires after six hours on
// purpose, because a timer is an intent about one night and a night that
// inherited last night's would end early.
const JUMP_KEY = "somnia-jump";
// Fifteen seconds is a sentence, thirty is a paragraph, a minute is a page. Past
// that the chapter arrows are the better instrument, which is why the list stops
// where it does rather than going on to five minutes.
const JUMP_CHOICES = [15, 30, 60];
const JUMP_DEFAULT = 30;

let jumpStep = JUMP_DEFAULT;

// The two labels on the most-pressed row in the app, and the three pills on
// Settings that set them.
//
// Built as one string each rather than a sign beside a number: the design asks
// for that everywhere on this page, and the reason is that two flex children
// lose the space between them and land on different baselines. The aria-label
// is written out in words for the same reason it always was — a screen reader
// saying "minus thirty" is reading arithmetic aloud.
function drawJump() {
  back30.textContent = `−${jumpStep}`;
  fwd30.textContent = `+${jumpStep}`;
  back30.setAttribute("aria-label", `Back ${jumpStep} seconds`);
  fwd30.setAttribute("aria-label", `Forward ${jumpStep} seconds`);
  // Which of the three is the one in force, said twice: once in amber for the
  // eye and once in the accessibility tree for everybody else. The class is
  // paint and nothing else — a reader who cannot see the amber had three
  // identically labelled buttons and no way to tell which of them was already
  // true, on the one screen in the app whose whole job is to report a setting
  // back. Written on every button rather than only the chosen one, because the
  // false is the half that carries the information: three buttons of which two
  // say "not this" is a group with an answer in it.
  for (const [seconds, button] of jumpButtons) {
    const chosen = seconds === jumpStep;
    button.classList.toggle("chosen", chosen);
    button.setAttribute("aria-pressed", String(chosen));
  }
}

function setJump(seconds) {
  if (!JUMP_CHOICES.includes(seconds)) return;
  jumpStep = seconds;
  drawJump();
  try {
    localStorage.setItem(JUMP_KEY, String(seconds));
  } catch (error) {
    console.error(error);
  }
}

function restoreJump() {
  try {
    const saved = Number(localStorage.getItem(JUMP_KEY));
    // Only one of the three, and nothing else. A stored 45 would draw a
    // transport whose labels no control on the page could change back.
    if (JUMP_CHOICES.includes(saved)) jumpStep = saved;
  } catch (error) {
    console.error(error);
  }
  drawJump();
}

restoreJump();

for (const [seconds, button] of jumpButtons) {
  button.addEventListener("click", () => setJump(seconds));
}

// A short buzz confirms the button caught the press, for a listener who can't
// see much and shouldn't be listening for a beep. Android honours this; iOS
// ignores it, which is why the button also changes colour and pulses.
function buzz(ms) {
  navigator.vibrate?.(ms);
}

async function ask(text) {
  if (!text) return;
  // Whatever the last answer offered is about a question that is over. Leaving
  // it up would put a list of places over a conversation that has moved on, and
  // the row they pressed would be an answer to the question above the one they
  // are looking at.
  closeCandidates();
  say(text, "you");
  question.value = "";
  const pending = say("…", "agent pending");
  const asked = token;
  setStatus("thinking…");
  try {
    const response = await fetch("api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      // The open book travels with the question. Without it the agent could see
      // the three books on the shelf and nothing saying which one was making
      // the sound, so the only honest answer to "where was I" was "which book?"
      // — asked over the book they were listening to, every single turn.
      //
      // Read here rather than captured with `asked`, because it is a fact about
      // the moment the question is sent. `gid` is null until a book is open,
      // and the server treats that as "no book" rather than refusing the turn.
      body: JSON.stringify({ token, question: text, gid }),
    });
    const body = await response.json();
    // They started over while this was in flight: the answer belongs to a
    // conversation that no longer exists, and appearing now would be a reply
    // to a question no longer on the screen.
    if (token !== asked) return;
    if (!response.ok) throw new Error(body.error || "no answer");
    pending.className = "said agent";
    pending.textContent = body.reply || "…nothing to say.";
    // An answer does one of two things and never both. Either the turn knew
    // where they meant and moved the book — the short way round, since the same
    // move arrives as the refusal of the next report within fifteen seconds, so
    // it is only ever a head start and applying it twice costs nothing — or it
    // did not, and hands back the places it is choosing between for them to
    // decide.
    //
    // Both cannot arrive: the move_to tool refuses to run at all once a turn
    // has offered a list, and the server writes "move" only when there is no
    // "candidates". If they ever did, the list wins, because nothing has been
    // moved under a listener who has not chosen yet — and a move that really
    // happened comes back as the refusal of the next report anyway.
    if (body.candidates?.places?.length) showCandidates(body.candidates);
    else if (body.move) {
      // The turn knew where they meant, so there is no list to raise, no close
      // to press and nothing that incidentally gives the keyboard back. This is
      // the whole of the way back to the book for a search that found one place,
      // by voice or by keyboard alike.
      //
      // On `body.move` and not on whether follow() did anything: the move may
      // already have been applied by the other route — the refusal of the next
      // report, which can beat the answer here — and the book is at the place
      // they asked for either way. What decides the screen is that the answer to
      // their question was a book that moved.
      follow(body.move);
      backToTheBook();
    }
  } catch (error) {
    pending.className = "said failed";
    pending.textContent = "Couldn't reach somnia. Still here?";
    console.error(error);
  }
  setStatus("");
  transcript.scrollTop = transcript.scrollHeight;
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(question.value.trim());
});

// One press, and there is no second one to wait for.
//
// It took two until this corner learned which screen it was on, and the button
// itself was the question: `sure? tap again` where the label had been, on a
// three-second fuse. That was the right answer to the wrong control. `start
// over` was in the top corner of the *player* then, which is the screen a hand
// reaches for in the dark with the room black and the eyes shut, and a press
// that throws something away sitting there wants asking about twice.
//
// It is not there any more. The only screen it is on is the one somebody is
// typing into, looking at, with a keyboard up under it — and on that screen
// what the press costs is questions that can be asked again in the same words.
// So the confirm was guarding a risk that has been designed out of the corner
// rather than talked out of it, and a page that still asked would be charging
// two presses for the cheapest thing on it. The queue's `stop reading this`
// keeps its two presses and its longer fuse, because that one ends hours of
// rendering and lives on a panel anybody can wander into.
//
// It is a press at all only because of the guard at the foot of this file: a
// pill the sheet draws only while the composer has focus must not be allowed
// to take that focus away from it.
restart.addEventListener("click", startOver);

// What is thrown away is the conversation, and only the conversation. The book
// keeps playing, keeps its position and keeps its sleep timer: "start over"
// means the questions, not the night. A press here that took somebody back to
// the beginning of a nine-hour book would be the one mistake on this page
// nothing could undo.
function startOver() {
  const stale = token;
  token = crypto.randomUUID();
  sessionStorage.setItem("somnia-token", token);
  fetch("api/forget", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token: stale }),
  }).catch(() => {});
  // A list left up over a cleared transcript is exactly the stranding this page
  // promises cannot happen: an overlay offering places, with nothing behind it
  // to say what was asked or why. `closeCandidates` takes it off the screen and
  // `forgetPlaces` takes it out of the key, so the position line stops offering
  // a way back to it as well.
  closeCandidates();
  forgetPlaces();
  transcript.replaceChildren();
  setStatus("");
  say("Where do you want to be?", "agent");
  question.focus();
}

// ------------------------------------------------------------------- playing

// Play the book a file at a time, the way it was played before the whole of it
// came down one URL — `?chapters` on the address the app was opened at.
//
// It is here so that one man with one phone can compare the two on the same
// night, over the same Bluetooth speaker, without a second deploy: install the
// app, open the shortcut, then open the same page again with ?chapters on it
// and listen across a boundary each way. The difference the whole change is
// about — whether the lock screen panel survives — is a property of the
// handset and of nothing in this repo, so it can only be settled by hearing it,
// and an answer from two different nights is an answer about two different
// nights.
//
// The page has to be able to do this anyway. `stream_url` is absent from the
// manifest of a book with no audio yet, and from every somnia serving a
// manifest older than that field, so playing a chapter at a time is not a
// fallback bolted on for the experiment — it is the other ordinary case, and
// this only forces it.
const PER_CHAPTER = new URLSearchParams(location.search).has("chapters");

// What "back a bit" means is `jumpStep`, further up: it is a setting now rather
// than a constant, so the constant that used to be here is gone rather than
// left beside it as a second answer to the same question.

// How far into a chapter "previous" stops meaning the one before and starts
// meaning the top of this one. The same five seconds every music player has
// used for forty years, and the reason a double press goes back a whole
// chapter while a single one only starts this chapter again.
const CHAPTER_RESTART_MS = 5000;

// The ways to be asleep before the book is, in minutes, with the end of the
// chapter after them and nothing at either end of the list. One tap walks it.
const SLEEP_CHOICES = [null, 15, 30, 45, 60, "chapter"];

// Twenty seconds of getting quieter, ending in silence at the moment the timer
// named — so it begins before that moment, not at it. Long enough that the
// book leaving is not itself the thing that wakes someone, and short enough
// that "fifteen minutes" stays an honest description of fifteen minutes.
const FADE_OUT_MS = 20_000;

// Short, because this is the sound they just asked for.
const FADE_IN_MS = 900;

// The most a rewind ever gives back, and how far behind it a sentence may
// begin and still be worth going to. Beyond that the index has a hole in it,
// and two minutes of a book someone has already heard is not a kindness.
const LONG_REWIND_MS = 30_000;
const SENTENCE_REACH_MS = 45_000;

// How often a playing book says where it has got to. Fifteen seconds is what a
// phone dying costs: few enough writes that a night is a few hundred of them,
// close enough together that waking up never means hearing a chapter twice.
// It is counted on timeupdate rather than by a timer on purpose — a hidden
// page's setInterval is throttled to roughly one wake a minute, so anything
// hung off a timer misbehaves exactly when nobody is watching, whereas
// timeupdate comes off the media pipeline and keeps firing with the screen off.
const HEARTBEAT_MS = 15_000;

// How long to leave a book that is still rendering before asking whether it has
// grown, and the longest that wait ever gets. Kokoro takes minutes over a
// chapter, so asking every few seconds all night would be a hundred requests
// for one answer — but the ask made the moment the audio runs out is the one
// the listener is waiting on, and that one is worth being quick about.
const RENDER_ASK_MS = 5_000;
const RENDER_ASK_MAX_MS = 60_000;

// How far short of the end of what has been read the sound is stopped, when
// what has been read is not the whole book. Two things fix the size of it.
//
// It must be worth more than one timeupdate. They come off the media pipeline
// about four times a second, so a mark closer to the end than one sample can be
// stepped clean over — and what is on the far side of it is `ended`, which is
// the one event that takes the player out of the platform's media session.
//
// It must be less than the half second of silence ingest leaves at the end of
// every chapter (paragraph_silence_ms, config.py), so that stopping early stops
// in that silence rather than in the middle of a word. Nothing is lost either
// way — the sound comes back from where it stopped, not from the join — but a
// sentence cut off is a sentence somebody has to go back for in the morning.
//
// Four hundred milliseconds is inside both, with room for the sample rate to be
// half what it is.
const FRONTIER_LEAD_MS = 400;

// How long a stall is given to sort itself out before the chapter is put back
// under it, and how long to leave between attempts once something has actually
// failed. Two seconds because a tailnet re-key is usually over before that;
// thirty at the top because a VPS that is down is down, and a phone that
// retried flat out until morning is a phone with no battery in the morning.
const STALL_GRACE_MS = 8_000;
const RETRY_MIN_MS = 2_000;
const RETRY_MAX_MS = 30_000;

// How many times a join that has never played must fail, far enough apart to be
// two answers rather than one outage, before the page stops asking for it and
// reads the book a file at a time instead.
//
// Two, because one is a coincidence — the first request of the night caught by
// a re-key, a proxy that dropped a connection. What it costs to find out is not
// two requests but half a minute, because the second failure only counts once
// RETRY_MAX_MS has passed since the first; see joinThatArrived for why the
// spacing and not the count is what carries the argument.
const JOIN_TRIES = 2;

// The lock screen, the notification shade and whatever is paired over
// Bluetooth all reach the page through this one object, so it is the whole of
// what somnia can be controlled by while the phone is face down. It is still
// only a courtesy: a browser without one plays the book perfectly well, and
// so every use of it below is guarded rather than assumed.
const session = navigator.mediaSession ?? null;

// Both sizes the installed app ships, so the platform takes the one that fits
// its slot rather than scaling the other. What appears on the lock screen at
// 2am should look like the thing they pressed to get there.
const ARTWORK = [
  { src: "icon-192.png", sizes: "192x192", type: "image/png" },
  { src: "icon-512.png", sizes: "512x512", type: "image/png" },
];

let manifest = null;
let gid = null; // which book, once the manifest has said
// {idx, chapter} — which chapter the sound is in. Not which file the element
// is holding: with the whole book down one URL those are different questions,
// and this is the one every clock, title and scrubber on the page asks.
let current = null;
let positionMs = 0;
// How many times the agent has moved this book, as of the last thing we heard
// from the server. Our own reports never raise it, so a higher number coming
// back can only be a move this page has not applied.
let seq = 0;
// Nothing is written until something happens. Opening the app at 2am to ask a
// question is not listening, and a book they only opened must keep its null
// position: "never started" and "at the very beginning" are different answers
// to "where am I?", and only one of them would be true.
let untouched = true;
let sending = false; // one report in flight at a time
let owed = null; // a report that arrived while one was in flight
let lastSentAt = 0;
// How much of the book has really come out of the speaker, counted off the
// media clock rather than off the wall clock. It is the whole of the evidence
// the spoiler guard has, and only this page can give it: a jump moves the
// position without moving this, a phone asleep in a pocket moves neither, and
// a chapter that buffered for ten seconds moves the wall clock and not this.
let playedMs = 0;
// Where that clock was last sampled, or null when the next sample is only a
// baseline. A seek and a source loaded afresh both move the position with
// nothing played, so the distance either of them moved is never counted as a
// step. A chapter boundary is neither, and costs the count nothing.
let playedFrom = null;
// How much of it the server has taken. Only an accepted report spends any:
// a refusal did not raise the mark, and a reply that never arrived may as well
// not have, so either way the next report carries the playback again. A mark
// left behind the position by one lost report never catches up, and a guard
// that has stopped rising is not a guard.
let playedTaken = 0;
// Where to land once the file has a duration to clamp against. It stays set
// until it is applied, so a loadedmetadata that arrives four minutes late —
// after the tailnet came back — still lands in the right place instead of
// starting the chapter from nothing.
let pendingOffsetMs = null;
let swapping = false; // a source is being loaded
let weArePausing = false; // tell our own pause from the platform's
let lastPublishedAt = 0; // when the lock screen was last told the time
// When the sound stopped, so that pressing play again can tell a moment's
// silence from a night's. Zero once it has been spent, so the same pause is
// never given back twice.
let lastPauseAt = 0;
// A fade in flight: where the volume came from, where it is going, and whether
// silence is the end of the night at the other side of it.
let fade = null;
let sleepChoice = 0; // an index into SLEEP_CHOICES
// Listening time left before the fade begins, or null when the night has no
// end scheduled.
let sleepLeftMs = null;
let sleepCountedAt = 0;
let sleepSavedAt = 0;
// Where the sentence they stopped in began, found out at the pause.
let sentenceHint = null;
// Whether the sound is meant to be on. `paused` cannot answer that: an element
// whose chapter failed to load is paused, so is one whose buffer ran dry at
// 3am, and the difference between those and a thumb on the pause button is the
// whole of whether the page should be fighting to get the book back.
let wantsSound = false;
// A stall being given a moment, a reload waiting out its backoff, and the boot
// waiting out its own. Zero for "nothing pending", which is what clearTimeout
// takes for an answer.
let stallTimer = 0;
let retryTimer = 0;
let retryDelay = RETRY_MIN_MS;
let bootTimer = 0;
let bootDelay = RETRY_MIN_MS;
// Whether what is on the status line is about the network. Only what this page
// put there is ever taken away again: "goodnight" is about something else and
// is still true.
let troubled = false;
// The book the page has run out of audio on and is waiting to grow, or null:
// which book, how long to leave it before asking again, which chapter it ran
// out after, and whether the sound was on when it did.
let awaiting = null;

// Global milliseconds -> the chapter that owns them, and how far into its file.
// A linear scan: a book is a few hundred chapters and this runs once per seek.
function locate(ms) {
  const chapters = manifest.chapters;
  const t = Math.max(0, Math.min(ms, manifest.total_ms));
  let i = 0;
  while (i + 1 < chapters.length && chapters[i + 1].start_ms <= t) i++;
  return { idx: i, chapter: chapters[i], offset_ms: t - chapters[i].start_ms };
}

// Global offset -> a number this element will accept, clamped by the container.
function toElementSeconds(offset_ms, duration) {
  const s = Math.max(0, offset_ms / 1000);
  if (!Number.isFinite(duration) || duration <= 0) return s;
  // 50ms of headroom: assigning currentTime >= duration lands at the end and
  // fires `ended` at once, which skips a whole chapter when a chapter is what
  // is loaded, and ends the night when the whole book is. The render clock can
  // legitimately exceed the container clock, so this is not hypothetical.
  return Math.min(s, duration - 0.05);
}

// Where the element is, on the book's clock, when it is holding one chapter.
// Clamped to that chapter's own span: a decoder that ignores the edit list runs
// up to one AAC frame past what was rendered, and a position reported from
// inside that padding would claim to be in the next chapter.
function toGlobalMs(chapter, currentTime) {
  const t = chapter.start_ms + Math.round(currentTime * 1000);
  return Math.max(chapter.start_ms, Math.min(t, chapter.end_ms));
}

// The same question of an element holding the whole book, where the answer is
// the reading itself: the stream is the chapters laid end to end in order, so
// it runs on the book's own clock and the conversion is identity. Measured
// rather than assumed — against the real forty-nine-chapter book the audio
// lands within 0.12s of where the render clock says, and the error does not
// accumulate.
//
// There is no per-chapter clamp to make here, and no edit list to overshoot:
// one file, one edit list, and a position inside the frame of silence at a join
// is a position in the next chapter, which is exactly where the sound is.
function toBookMs(currentTime) {
  const t = Math.round(currentTime * 1000);
  return Math.max(0, Math.min(t, manifest.total_ms));
}

// This book's join has been given up on: it was asked for and it did not come,
// twice, from a box that was answering. From here the book is played a file at
// a time for as long as it stays open, which blinks at every boundary and is
// the failure this whole change was made to end.
//
// It is still the right answer. Once the one URL the book comes down is not
// there, the only two nights on offer are one that blinks and one that goes
// silent, and a night that blinks is a night. The manifest keeps a url per
// chapter for exactly this.
//
// Per book, not per night. A concatenation that could not be made is a fact
// about the book it was made from — one unreadable chapter file, one ffmpeg run
// that gave up — and letting it decide how the next book is played would spread
// one bad join across the whole shelf.
let fellBackToChapters = false;

// The URL the element was last given. Remembered here rather than read back off
// `player.src`, because the element answers with the address resolved against
// the page and everything below compares it with the relative one the manifest
// wrote.
let sourceUrl = "";

// The last join that got as far as handing this page a duration, and how many
// times the one being asked for now has failed without doing so.
//
// The pair is the whole of how "this join is not coming" is told from "the
// tailnet went away for five seconds", and telling them apart is the difficulty
// here because the two want opposite things: the second wants the ladder's
// patience, and the first wants the page to stop asking.
//
// KNOWN: a media element does not get a duration out of a 404. So a URL that
// has once been loaded is a file that exists on the box, and every later failure
// of it is the wire — wifi power save, a DHCP renewal, a tailscale re-key — for
// which the answer is to go on trying until morning and never to fall back.
//
// A URL that has never loaded is the hard one, and the count alone is not enough
// to judge it. Two failures two seconds apart are not two answers about a URL;
// they are one outage seen twice, and the outages just listed are exactly that
// shape. It cost a night to find out: at the frontier the join being asked for
// is new by construction and has never loaded by definition, so four seconds of
// re-key spent both tries on a file that was there all along and the book blinked
// its way through the rest of the night. So the failures have to be spread as
// wide as the ladder's own patience — RETRY_MAX_MS, which is where it stops
// waiting longer because a box that is down is down — before JOIN_TRIES of them
// mean the join is not coming. A join that is really missing costs half a minute
// of trying before the page reads the book a file at a time instead.
//
// Counted per URL, because that is what the evidence is about: a book whose
// five-chapter join plays and whose six-chapter join was never written has one
// good URL and one bad one, and a count carried between them is a count of
// neither.
//
// What none of it can tell apart is a book opened while the tailnet is down,
// where nothing has been proved because nothing has been reached. Its manifest
// did arrive seconds earlier, which is most of an answer and not all of one, so
// a night whose network is gone for more than half a minute at the moment the
// book is opened falls back and blinks. That is the right way to be wrong:
// falling back on a join that was fine costs a blink at every boundary, and not
// falling back on a join that is missing costs the night.
let joinThatArrived = "";
let joinThatFailed = "";
let joinsThatFailed = 0;
let joinFailedAt = 0;

// Whether the next thing loaded would be a file at a time. True when the server
// offered no stream for this book — a join that could not be made, a book with
// no audio yet, a somnia older than the field — when the page has given up on
// the one it was offered, and when the address said to.
function chapterAtATime() {
  return PER_CHAPTER || fellBackToChapters || !manifest?.stream_url;
}

// Whether the element is holding one chapter or the whole book. A fact about
// what was loaded and not about what the manifest says now, because those are
// different questions and the answer is used to read the element's clock: a
// book can gain a stream between one poll and the next, and a page that changed
// its mind about what it was holding would read half an hour into a chapter
// file as half an hour into the book, and put the listener four chapters back.
let holdingOneChapter = false;

// How much book that source holds, on the book's clock. For the whole book down
// one URL it is the render frontier as it stood when the source was loaded, and
// deliberately not as it stands now: the manifest is asked again all night and
// grows, while the element goes on holding the join it was given. The gap
// between this number and `manifest.total_ms` is a chapter that exists and is
// not in the element, and everything below is about that gap.
let streamMs = 0;

// Whether the sound is stopped a fraction short of the end of that source,
// waiting for the rest of the book to be read.
//
// Cleared by the three things that mean it is not stopped there any more: a
// source loaded, a place seeked to, and sound coming out. A stale one is not
// harmless — askForMore reads it to decide whether an arriving chapter is
// something to carry on into, and left set under a book somebody had moved or
// put down it would start the sound again on its own.
let atFrontier = false;

// Whether the source the element is holding stops short of the book. Either the
// audio is already there and this source does not hold it, or the render is
// still running and will make some.
//
// False for a chapter file, always: one of those stops short of the book by
// design, and the file running out is how that path crosses a boundary at all.
function sourceIsShortOfTheBook() {
  if (holdingOneChapter || !manifest) return false;
  return manifest.total_ms > streamMs || manifest.status === "rendering";
}

// The narrower half of that: audio the manifest names which this source does
// not hold. It is the difference between something to load and nothing to do
// but wait, and it is only ever true because the page refreshed the manifest
// without reloading the element — which is the whole of the deferral that keeps
// a night to one load or none.
function audioPastTheSource() {
  if (holdingOneChapter || !manifest) return false;
  return manifest.total_ms > streamMs;
}

// The furthest into the source the sound is allowed to get. The lead is taken
// off the book's clock and then run through toElementSeconds, so the 50 ms of
// headroom there is kept underneath it: the render clock and the container
// clock disagree by a frame in either direction, and this has to be short of
// the end of whichever of the two is shorter.
function frontierSeconds() {
  return toElementSeconds(streamMs - FRONTIER_LEAD_MS, player.duration);
}

// Whether a place in the book is inside what this source holds, and so somewhere
// the element can be taken to without loading anything.
function insideTheSource(ms, at) {
  if (holdingOneChapter) return at.idx === current.idx;
  // Past this source's frontier, with the audio for it in the manifest: it is a
  // different join at a different URL and only a load reaches it. Without this
  // the seek would be clamped to the end of what was loaded, so a row chosen in
  // a chapter that landed after the book was opened would answer with the last
  // moment of the chapter before it — and answer with it again on every press.
  return !(audioPastTheSource() && ms >= streamMs);
}

// Where the sound is, on the book's clock, whichever of the two the element is
// holding. Every reading of the media clock in the page goes through here.
function whereTheSoundIs() {
  return holdingOneChapter
    ? toGlobalMs(current.chapter, player.currentTime)
    : toBookMs(player.currentTime);
}

// h:mm:ss, the same shape format_timestamp gives the agent, so what is on the
// screen and what somnia says out of the model agree to the second.
function timestamp(ms) {
  const seconds = Math.floor(Math.max(0, ms) / 1000);
  const mm = String(Math.floor(seconds / 60) % 60).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${Math.floor(seconds / 3600)}:${mm}:${ss}`;
}

// The same clock at chapter scale, which is nearly always minutes. Carrying the
// book's leading "0:" onto a twelve-minute chapter would put the least
// informative digit on the page in the position the eye reads first, and make
// the two clocks on screen look like the same number twice.
function chapterTime(ms) {
  const seconds = Math.floor(Math.max(0, ms) / 1000);
  const ss = String(seconds % 60).padStart(2, "0");
  if (seconds < 3600) return `${Math.floor(seconds / 60)}:${ss}`;
  const mm = String(Math.floor(seconds / 60) % 60).padStart(2, "0");
  return `${Math.floor(seconds / 3600)}:${mm}:${ss}`;
}

function drawPlayer() {
  if (!manifest || !current) return;
  // Which book, above which chapter of it. Drawn every pass rather than once
  // when the book opened, so there is no path — a boundary, a refreshed
  // manifest, a move to another book — by which the headline can be left naming
  // the last
  // one. The fallback is the queue panel's, from bookName: a book that has been
  // through nothing but the local catalog may have no name at all, and "book
  // 1342" is a good deal better than an empty line where the title goes.
  bookTitle.textContent = manifest.title || `book ${gid}`;
  chapterTitle.textContent = current.chapter.title;
  const whole = timestamp(manifest.total_ms);
  clock.textContent = `${timestamp(positionMs)} of ${whole}`;
  // And whether that line is a way in to anything, which is a question about
  // the book it has just been drawn for: places belong to the book they were
  // found in, so this is asked on the same pass rather than once when a list
  // was last shown.
  drawPlaces();
  // The same pair as the line above it, drawn instead of written. Clamped both
  // ends: a position past the last chapter — a book re-rendered shorter than
  // the mark somebody left in it — would otherwise run the fill off the end of
  // its track and take the knob with it. A book with no total is drawn empty
  // rather than full, because nobody knowing how long it is does not mean it
  // has been finished.
  const through = manifest.total_ms
    ? Math.min(100, Math.max(0, (positionMs / manifest.total_ms) * 100))
    : 0;
  wholePlayed.style.width = `${through}%`;
  // Off the chapter row and the book's own clock, never off the element's
  // currentTime: that number is the whole book's when the whole book is loaded,
  // and while a source is arriving it belongs to whichever of two things the
  // element happens to be holding.
  const into = positionMs - current.chapter.start_ms;
  const length = current.chapter.end_ms - current.chapter.start_ms;
  chapterClock.textContent = `${chapterTime(into)} of ${chapterTime(length)}`;
  // Which chapter of how many, in the gap between the two buttons that change
  // it. The denominator is chapters_total — how many chapters the book HAS, as
  // against how many have been rendered — because a count taken from the
  // chapters that happen to have landed would read "1 of 1" at eleven o'clock
  // and "1 of 2" an hour later, on a book that has forty.
  //
  // 0 means nobody wrote the number down. That is every book rendered before
  // the column existed, which is every book on the box this runs on, so it is
  // not an edge case to be swept up: the count says which chapter they are in
  // and stops, and the word above it goes rather than saying "chapter" twice.
  const total = manifest.chapters_total || 0;
  const number = current.idx + 1;
  chapterWord.hidden = total === 0;
  chapterCount.textContent = total
    ? `${number} of ${total}`
    : `chapter ${number}`;
  // A book still being read grows a chapter at a time, so this is asked every
  // draw rather than once when the manifest lands.
  nextChapter.disabled = !manifest.chapters[current.idx + 1];
  // Which half of the button's drawing shows. A class rather than the glyph it
  // used to hold: how big the symbol is and where in the button it sits are no
  // longer whatever the phone's symbol font happened to think.
  playpause.classList.toggle("playing", !player.paused);
  playpause.setAttribute("aria-label", player.paused ? "Play" : "Pause");
  drawSleep();
  // The books panel says which book this is and offers it back, out of the same
  // three things this function has just drawn from. Here rather than once when
  // the panel goes up, because the agent can move the book — or the sound can
  // cross into the next chapter — while somebody is reading the panel, and a
  // block painted once would then be naming a place the book has left. It costs
  // nothing while the panel is shut; see drawReadingNow.
  drawReadingNow();
}

// What the notification says. The chapter is the title because it is the part
// that changes and the part they are in; the book is the album, which is where
// a phone expects to find the name that stays the same all night.
function announceChapter(chapter) {
  if (!session || typeof MediaMetadata !== "function") return;
  session.metadata = new MediaMetadata({
    title: chapter.title,
    artist: manifest?.authors || "",
    album: manifest?.title || "",
    artwork: ARTWORK,
  });
}

function reportPlaybackState(state) {
  if (session) session.playbackState = state;
}

// The lock screen scrubber, kept honest by the book's own clock.
//
// It is chapter-scale on purpose. A whole-book scrubber on a twelve-hour novel
// gives three minutes to the pixel: useless for the nudge someone actually
// wants, and one sleepy thumb away from flinging them past the spoiler guard
// into the ending. Where they are in the book is the agent's business and the
// API's; what the notification owes them is the chapter, and it names it.
//
// Both numbers are derived from the chapter row and positionMs — the render
// clock, the one the search results and the saved position speak — and not
// from the element. That keeps the arithmetic on `duration` where it belongs,
// in the conversion functions above, and it means the pair can never be the
// NaN-and-stale-currentTime that setPositionState throws on.
//
// Which matters more now than it did, and this is the place to say why. The
// element holds the whole book, so a position state that is never published —
// because this returned early, or because setPositionState threw — leaves the
// platform to draw the scrubber from the element itself, and that is now twelve
// hours long rather than twelve minutes. What used to degrade to roughly the
// right size degrades to exactly the wrong one. Nothing below may be loosened
// without a test that walks a boundary and reads back what the panel was told.
function publishPosition() {
  if (!session?.setPositionState || !current) return;
  const span = (current.chapter.end_ms - current.chapter.start_ms) / 1000;
  if (!(span > 0)) return;
  const into = (positionMs - current.chapter.start_ms) / 1000;
  session.setPositionState({
    duration: span,
    // Clamped rather than trusted: for the few milliseconds between a boundary
    // starting and its metadata arriving, positionMs still belongs to the
    // chapter being left. A throw here would leave the PREVIOUS chapter's
    // state up rather than clearing it, and a scrubber showing the wrong place
    // with complete confidence is worse than one showing nothing.
    position: Math.min(Math.max(into, 0), span),
    playbackRate: player.playbackRate || 1,
  });
}

// The book has reached another chapter, and that is the whole of what happens.
//
// It touches the element at nothing. That is the fix for issue 31: crossing a
// chapter is a new title on the notification and a new name on the screen, and
// with the whole book down one URL there is no source to assign, no load
// algorithm to run, no element to empty and therefore nothing for the platform
// to take the media session down with. Over Bluetooth that teardown is slow
// enough to see and sometimes never finishes, and the night ends there.
//
// `current` is set before the metadata rather than after: everything the
// notification is told is drawn from it, and a page that announced a chapter it
// had not yet entered would name the wrong one for the rest of the book.
function enterChapter({ idx, chapter }) {
  current = { idx, chapter };
  announceChapter(chapter);
  drawPlayer();
}

// The one place in this page a URL reaches the media element.
//
// Reached at boot, and afterwards only by a reload — a source that failed, or a
// book that has grown past the stream it was given. It is not on the path of an
// ordinary chapter boundary and must never be put back on it.
//
// The metadata goes on before the source, and so before play(): the metadata
// current at the moment playback starts is the one the notification adopts, so
// setting it afterwards labels what is playing with the last chapter's title.
// Nothing else here is allowed to touch the session while a source is arriving
// — no pause, no playbackState, no second element — because handing audio focus
// back even for an instant is what tears the notification down, and once it is
// gone nothing in this page can get it back.
function loadSource({ idx, chapter, offset_ms }, { play }) {
  swapping = true;
  enterChapter({ idx, chapter });
  // Which of the two this is, decided once, here, and remembered — see
  // holdingOneChapter. How much book it holds is decided in the same breath and
  // for the same reason: the manifest can grow between one of these and the
  // next, and the frontier belongs to what was loaded rather than to what the
  // server has since said.
  holdingOneChapter = chapterAtATime();
  streamMs = holdingOneChapter ? chapter.end_ms : manifest.stream_ms;
  // Whatever this is being loaded for, the sound is no longer stopped at the
  // end of the last source. Usually this load is the answer to that.
  atFrontier = false;
  // Where to land, said in the loaded thing's own milliseconds: a chapter file
  // starts at the chapter, the whole book starts at the beginning of the book.
  // Applied at loadedmetadata, when there is a duration to clamp it against.
  pendingOffsetMs = holdingOneChapter ? offset_ms : chapter.start_ms + offset_ms;
  // Written down before it is handed over, because what happens to it after
  // that is the only evidence the page ever gets about whether the URL is real
  // — see joinThatArrived.
  sourceUrl = holdingOneChapter ? chapter.url : manifest.stream_url;
  player.src = sourceUrl;
  if (play) player.play().catch(onPlayRejected);
  drawPlayer();
}

// Every seek arrives here: a transport button now, and the lock screen, a
// Bluetooth skip and the agent moving the book later. Routing them all through
// the global timeline is what lets a thirty-second nudge at the start of
// chapter five land in chapter four, which is what a listener means by "back a
// bit" in a book that only happens to be stored as separate files.
function seekGlobal(ms, { play = null } = {}) {
  if (!manifest) return;
  // The book is going somewhere, so a list of places it might go is answered
  // however it got here — a row, a thumb on −30, the lock screen, or the agent
  // moving the book by the other route while they were still reading. A list
  // left up over a book that has since moved offers rows whose "you are here"
  // is a lie, and the next press acts on it.
  closeCandidates();
  // And for the same reason one line up: a way back to where the book was
  // before the last `goto` is a lie the moment the book has been somewhere
  // else since. Every seek on this page comes through here, whoever made it,
  // which is what makes this the one place that has to say so.
  //
  // Before the seek rather than after, which is what lets `goto` itself use
  // this function and then offer a fresh way back on the line below: the old
  // offer is gone by the time the new one is written.
  withdrawUndo();
  // Somebody meant this — a thumb, a lock screen, or the agent. Whatever
  // happens next is worth recording, even if they never press play.
  untouched = false;
  // Nobody who is asleep skips forward thirty seconds or asks to be taken to
  // the fair, so a jump during the fade is somebody still awake. The sound
  // comes back rather than stopping under them mid-sentence.
  if (fade?.thenSleep) startFade(1, FADE_IN_MS);
  const at = locate(ms);
  positionMs = Math.max(0, Math.min(ms, manifest.total_ms));
  // They are somewhere of their own choosing now, which is not the end of what
  // has been read however near it they land. Left set, a chapter arriving ten
  // minutes later would take a book they had moved and start it playing.
  atFrontier = false;
  // Every seek in the page comes through here, which is what makes this the
  // one place the played clock has to be set aside: the ground between where
  // they were and where they are going is not ground anybody heard, and
  // counted as a step it would be a skip that paid for itself.
  playedFrom = null;
  // Playback still owed is given up at the same moment, and this is the one
  // place it is right to give it up. It was earned over the ground behind the
  // jump and can only ever justify standing there; carried across, the first
  // report from the far side spends it on the distance instead. That is not
  // hypothetical — an agent move refuses the heartbeat in flight, and the page
  // follows the refusal with a seek, so the two arrive in that order every
  // time: in a real browser the refused report's seven seconds paid for a
  // twelve-second move, and the mark stepped over four seconds nobody heard.
  // The cost is that a jump can leave the mark up to one report behind the
  // furthest they really got, which is the same direction as every other
  // choice here: the guard stops early rather than late.
  playedTaken = playedMs;
  if (
    current &&
    player.readyState > 0 &&
    !player.error &&
    insideTheSource(ms, at)
  ) {
    // Within what the element is already holding, which under one URL per book
    // is everywhere in the book that had been read when it was loaded. This
    // branch is what keeps autoplay policy out of the common case: a seek on a
    // live element needs no permission at all, so it does not ask for any.
    //
    // An element holding an error is not a live one however much of the file it
    // still has: it will not fetch again until it is loaded afresh, so a press
    // of play after the tailnet went would set currentTime on something that
    // was never going to make a sound. Sending it down the other branch is what
    // makes the transport a way back as well.
    //
    // The chapter is named before the clock is moved, for the same reason the
    // load path names it before assigning a source: whatever the notification
    // is holding at the moment the sound resumes is what it shows.
    if (at.idx !== current.idx) enterChapter(at);
    player.currentTime = toElementSeconds(
      holdingOneChapter ? at.offset_ms : positionMs,
      player.duration,
    );
    if (play === true && player.paused) player.play().catch(onPlayRejected);
  } else {
    loadSource(at, { play: play ?? !player.paused });
  }
  drawPlayer();
}

// `rewind` is true for the two controls a listener presses themselves, and for
// nothing else. A move the agent made lands exactly where it said it would, a
// chapter boundary carries straight on, and opening the app does not start the
// book at all, so none of those want anything given back.
function ensurePlaying({ rewind = false } = {}) {
  const to = rewind ? resumePoint() : positionMs;
  lastPauseAt = 0;
  // Read one line above and spent here: the book is playing again, so whatever
  // last night's fade still had to say has now been said. The morning goes with
  // it — a press on the lock screen while the wake screen is up is a choice, and
  // the transport is not drawn on that screen, so a book playing under it would
  // be a book nothing on the page could stop.
  spendTheFade();
  if (waking) leaveTheMorning();
  // From silence, however short the fade. A book coming back at full volume in
  // a dark room is the loudest thing that happens all night, and the sound of
  // it is what someone reaching for the phone at 3am is trying to avoid.
  //
  // Only when it really is stopped: a platform that sends `play` to something
  // already playing fires no play event back, so there would be nothing left
  // to bring the volume up again and the book would go silently on.
  if (rewind && player.paused) player.volume = 0;
  // An element that has reached the end of its file starts the chapter over
  // from nothing if it is simply told to play — so a night that ended on a
  // chapter boundary would begin the morning with the whole chapter again.
  // Going back through the timeline lands on the start of the next one, which
  // is where the book actually is.
  if (player.ended || to !== positionMs) {
    seekGlobal(to, { play: true });
    return;
  }
  player.play().catch(onPlayRejected);
}

function pauseHere() {
  weArePausing = true;
  player.pause();
}

// The sound has come to the end of what has been read of this book, and the
// book is not over: the render is still going, or it went on while this source
// was playing. Reached from timeupdate a fraction of a second before the source
// runs out, because the one thing that must not happen here is `ended`.
//
// `ended` takes the player out of the platform's media session, and on a locked
// phone that is the panel gone — not for a moment but for the whole of the
// wait, which was measured at 3321 seconds on the five-chapter book. A pause
// suspends the session instead: the panel stays up, with a play button on it,
// for as long as the render takes. That is what somebody half awake should find
// at 2am when the book is waiting for more of itself.
//
// This is the ordinary path and not an edge of one. A book added at eleven is
// playable within minutes and renders a chapter every three and a quarter
// minutes for hours after that, so any book listened to on the night it was
// added arrives here.
function reachTheFrontier() {
  // They asked for the night to end at the end of this chapter, and this is as
  // near the end of it as the sound is ever going to get: the check that
  // watches for the chapter's own end is four hundred milliseconds further on
  // and will never be reached. Without this the night would not end at all —
  // it would be handed back twenty minutes later when the next chapter landed
  // and the page started the book again over somebody who had asked it to stop.
  if (sleepsAtChapterEnd()) {
    clearSleep();
    fallAsleep();
    return;
  }
  // The other timer, already spent: the fade it started is running and silence
  // is where it is going. This is the night ending and the frontier must not
  // take it over, because the pause below is what would: the pause handler puts
  // the volume back and throws the fade away, so nothing is left to reach the
  // end of it and say goodnight. The night would then be handed back twenty
  // minutes later by the chapter that landed — the sound coming on again at
  // full volume, over somebody who had asked for it to stop, with no timer left
  // to stop it a second time before morning.
  //
  // The fade is given up rather than finished. There is no audio left to fade
  // over; what is left of the twenty seconds is a fade over the end of a file.
  if (fade?.thenSleep) {
    fallAsleep();
    return;
  }
  // The rest of it is already here: the manifest was asked again while they
  // were still listening to what this source holds — by the page coming back in
  // front of somebody, or by the ask a previous frontier made — and it named
  // audio this source does not have. So there is nothing to ask for and nothing
  // to be gained by stopping in front of it: the longer join is taken at once,
  // with no round trip in the way, and the sound carries on.
  if (audioPastTheSource()) {
    // Whatever was being waited for is here, so the sentence about waiting for
    // it comes down. Usually there is no wait to stop — this is the first time
    // the page has reached the frontier at all — and stopping nothing costs
    // nothing.
    stopAwaiting();
    loadSource(locate(positionMs), { play: wantsSound });
    return;
  }
  // Nowhere the page knows of, which on a phone in a pocket is most of the time
  // — nothing refreshes the manifest with the screen off, so this is as likely
  // to be a page that has not asked as a book that has not grown. Stop here and
  // ask, on the same ladder a chapter file running out has always used, whose
  // first question awaitMore puts to the server straight away.
  //
  // What the sound was doing is read before the pause, because the pause is what
  // takes it away: `wantsSound` is false the moment the handler runs, and it is
  // the whole of whether the book starts itself again when the chapter lands.
  const play = wantsSound;
  atFrontier = true;
  pauseHere();
  awaitMore(gid, { play, at: current.idx });
}

// ------------------------------------------------------- the end of the night

// The two things the Audiobookshelf app did that this page had to learn: stop
// the book before it plays all night, and give back the last thing they heard
// before they stopped taking it in. Still to come, and deliberately not here:
// shaking the phone to buy another quarter of an hour, which needs a motion
// permission and a threshold nobody can guess at from a desk.
//
// Everything below is driven from timeupdate, for the reason given at
// HEARTBEAT_MS: a backgrounded page's timers are throttled to roughly one wake
// a minute, and a fade stepped once a minute is not a fade. timeupdate comes
// off the media pipeline four times a second for as long as there is sound,
// which is exactly as long as either of these has anything to do.

function startFade(to, ms, { thenSleep = false } = {}) {
  fade = { from: player.volume, to, ms, at: Date.now(), thenSleep };
  stepFade();
}

// Volume back to whole, whatever was being done to it. The invariant this
// keeps is that a paused player is always at full volume: nothing else on the
// page has to remember that the sleep timer turned the sound down, and a
// resume by any route — a thumb, the lock screen, the agent — is never silent.
function endFade() {
  fade = null;
  player.volume = 1;
}

function stepFade() {
  if (!fade) return;
  const ratio = fade.ms > 0 ? Math.min(1, (Date.now() - fade.at) / fade.ms) : 1;
  // Ramped on the square root of the volume rather than on the volume itself.
  // Loudness as an ear hears it falls away far more slowly than amplitude
  // does, so a straight line from one to zero stays sounding like full volume
  // for most of its length and then drops off in the last second or two —
  // which is the shape of being woken up, not of falling asleep.
  const from = Math.sqrt(fade.from);
  const level = (from + (Math.sqrt(fade.to) - from) * ratio) ** 2;
  // iOS does not let a page set the volume at all. There this does nothing
  // until the pause at the end of it, which is abrupt, but still puts the book
  // down at the time it was asked to.
  player.volume = Math.min(1, Math.max(0, level));
  if (ratio < 1) return;
  const sleeping = fade.thenSleep;
  fade = null;
  if (sleeping) fallAsleep();
}

function fallAsleep() {
  pauseHere();
  // Only now, with the sound already stopped. Putting the volume back an
  // instant sooner would be twenty seconds of fading out followed by one
  // moment at full volume, which is the one thing this was here to prevent.
  player.volume = 1;
  // The one thing about tonight that nothing else writes down. Every route into
  // here is the timer ending a night, and the pause it just made reports
  // `pause` — the same word a thumb sends — so without this the morning cannot
  // tell a book put down at eleven from one that faded out at 1:47.
  //
  // After the pause and not before it, so that the two records of this moment
  // are made in one order and not two: the pause handler writes `lastPauseAt`,
  // which is this page's own memory of when the sound stopped, and this is the
  // same fact written where a discarded tab cannot take it.
  rememberTheFade();
  setStatus("goodnight");
  drawPlayer();
}

// The timer outlives the page, because the page does not outlive the night. A
// backgrounded tab is discarded whenever the phone wants the memory back, and
// reloading is also the first thing anyone does to a page that looks stuck —
// either way a timer kept only in a variable was silently disarmed, with
// nothing on screen to say it had gone, and the book played until morning.
//
// localStorage rather than the sessionStorage the token uses. sessionStorage
// dies with the tab, which is exactly the death this is about; and unlike the
// conversation, which is meant to start fresh every launch, an armed sleep
// timer is an instruction about tonight that nobody has cancelled.
const SLEEP_KEY = "somnia-sleep";

// How often the countdown is written down. The readout is in whole minutes, so
// half a minute of slop after a crash cannot be seen, and this is two writes a
// minute rather than two hundred and forty.
const SLEEP_SAVE_MS = 30_000;

// Older than this and the night it belonged to is over. Someone opening the
// book the following evening is starting a night rather than finishing one, and
// a timer they could not remember setting would end it early for no reason they
// could see.
const SLEEP_STALE_MS = 6 * 3_600_000;

function saveSleep() {
  sleepSavedAt = Date.now();
  try {
    if (SLEEP_CHOICES[sleepChoice] === null) {
      localStorage.removeItem(SLEEP_KEY);
      return;
    }
    const state = { choice: sleepChoice, leftMs: sleepLeftMs, at: Date.now() };
    localStorage.setItem(SLEEP_KEY, JSON.stringify(state));
  } catch (error) {
    // Storage refused or full. The timer still works for as long as this page
    // lives, which is all it ever did before.
    console.error(error);
  }
}

// What they asked for last time this page was alive, if it still stands.
function restoreSleep() {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(SLEEP_KEY) || "null");
  } catch (error) {
    console.error(error);
  }
  if (!saved || !(Date.now() - saved.at < SLEEP_STALE_MS)) return;
  const choice = SLEEP_CHOICES[saved.choice];
  // Anything else is a half-written record or a list of choices that has
  // changed shape since. Neither is worth ending a night over.
  if (choice === undefined || choice === null) return;
  if (typeof choice === "number" && typeof saved.leftMs !== "number") return;
  sleepChoice = saved.choice;
  sleepLeftMs = typeof choice === "number" ? saved.leftMs : null;
  // Listening time, not clock time — the same rule as while it is counting. The
  // minutes they had left are still the minutes they have left, whether the
  // reload took two seconds or the phone killed the tab an hour ago.
  sleepCountedAt = Date.now();
  drawSleep();
}

function sleepsAtChapterEnd() {
  return SLEEP_CHOICES[sleepChoice] === "chapter";
}

function clearSleep() {
  sleepChoice = 0;
  sleepLeftMs = null;
  saveSleep();
}

sleepButton.addEventListener("click", () => {
  sleepChoice = (sleepChoice + 1) % SLEEP_CHOICES.length;
  const choice = SLEEP_CHOICES[sleepChoice];
  sleepLeftMs = typeof choice === "number" ? choice * 60_000 : null;
  sleepCountedAt = Date.now();
  // A fade already running is the timer having fired. Reaching for the control
  // at all means they are awake enough to have changed their mind about it, so
  // the sound comes back rather than the setting quietly applying to a book
  // that is already going quiet.
  if (fade?.thenSleep) startFade(1, FADE_IN_MS);
  drawSleep();
  saveSleep();
  // Said in the words somebody would use, once, rather than left to be read
  // off a pill that says "sleep 30m". The pill is the readout and this is the
  // answer to the press — including on the sixth press, which takes the timer
  // off again: a box still promising to fade out over a night with no end
  // scheduled is the one lie this control can tell.
  toast(sleepSentence());
  buzz(10);
});

function sleepSentence() {
  const choice = SLEEP_CHOICES[sleepChoice];
  if (choice === null) return "no sleep timer";
  if (choice === "chapter") return "fading out at the end of the chapter";
  return `fading out in ${choice} min`;
}

// What the pill says, and what it says out loud, decided in one place.
//
// The visible label is one pre-assembled string — `sleep timer · 24 min left`
// — and not a word with a value appended to it. `sleep` on its own was the
// control's name on the nights it was off and a state on the nights it was on,
// and the only thing telling those two readings apart was whether anything
// followed it. Half asleep that is not a distinction anybody makes. Now the
// pill always says both what it is and what it is set to, which is also what
// makes it the one control on the page that can be read without being
// understood first.
//
// What follows the dot is what is *left*, not what it was set to. `30m` read
// as either at 1am, and only one of the two is a question anybody asks of a
// sleep timer.
//
// The spoken form is built from the same branch rather than beside it, so a
// state cannot be added to one and forgotten in the other — and it stays a
// sentence rather than the pill's own string, because a screen reader saying
// "sleep timer middle dot twenty four min left" is not what the pill means.
function drawSleep() {
  const choice = SLEEP_CHOICES[sleepChoice];
  let says = "off";
  let spoken = "off";
  if (fade?.thenSleep) {
    says = "fading";
    spoken = "fading out";
  } else if (choice === "chapter") {
    says = "chapter end";
    spoken = "at the end of this chapter";
  } else if (sleepLeftMs !== null && sleepLeftMs < 60_000) {
    // Under the last minute it counts in seconds. `1m` stood for everything
    // from fifty-nine seconds down, which is the stretch where the difference
    // is the only thing anybody wants from the control — the question at that
    // point is whether there is time for the rest of the chapter, and a whole
    // minute of the answer being the same number cannot answer it. The floor is
    // the fade rather than zero: at twenty seconds the timer hands over and the
    // pill reads `fading`, so nothing below that is ever drawn here.
    const seconds = Math.max(1, Math.ceil(sleepLeftMs / 1_000));
    says = `${seconds}s left`;
    spoken = `${seconds} seconds left`;
  } else if (sleepLeftMs !== null) {
    // Rounded up: what is left, not what it was set to. `30m` was ambiguous at
    // 1am in the one way that matters — total or remaining — and only remaining
    // is a question anybody asks of a sleep timer.
    const minutes = Math.ceil(sleepLeftMs / 60_000);
    says = `${minutes} min left`;
    spoken = `${minutes} minutes left`;
  }
  sleepButton.textContent = `sleep timer · ${says}`;
  sleepButton.setAttribute("aria-label", `Sleep timer, ${spoken}`);
  sleepButton.classList.toggle("armed", choice !== null);
}

// The timer counts listening time, not clock time. Someone who pauses to ask a
// question and then reads the answer meant to hear the rest of what they had
// asked for — and a timer that had run out while they read would answer them
// by ending the night, which is the opposite of what pressing play just said.
function countDownToSleep() {
  const now = Date.now();
  // Clamped: a gap this wide was a stall, a chapter arriving slowly or a
  // question being answered, and none of that was anybody listening.
  const spent = Math.min(now - sleepCountedAt, 2_000);
  sleepCountedAt = now;
  // Seeking fires timeupdate whether or not there is any sound, which is the
  // one way a paused book could otherwise be charged for the time.
  if (player.paused || fade || sleepLeftMs === null) return;
  sleepLeftMs -= spent;
  // Written down as it goes, not only when it is set: the tab can be discarded
  // between one timeupdate and the next, and a timer that came back with the
  // whole of its hour still to run would be an hour of book nobody asked for.
  if (now - sleepSavedAt >= SLEEP_SAVE_MS) saveSleep();
  if (sleepLeftMs > FADE_OUT_MS) return;
  // Spent: the fade is the last thing the timer does, and once it has started
  // the control reads as off again. Coming back afterwards is a decision to
  // set another one, which is one tap and takes no thinking about.
  clearSleep();
  startFade(0, FADE_OUT_MS, { thenSleep: true });
}

// How far back to go when they press play again, by how long the book was
// silent. A pause is three unlike things wearing the same name: a moment taken
// to hear something in the room, a question asked and answered, and falling
// asleep with the phone still in a hand. Only the last of them means the last
// thing they took in was well before where the sound stopped.
function rewindFor(silentMs) {
  if (silentMs < 30_000) return 0;
  if (silentMs < 5 * 60_000) return 8_000;
  if (silentMs < 60 * 60_000) return 20_000;
  return LONG_REWIND_MS;
}

function resumePoint() {
  // When the sound stopped, from whichever of the two knows it.
  //
  // `lastPauseAt` first, because it is the fuller answer: it is written at every
  // pause, whatever caused it, and it is this page's own memory of a night it
  // was awake for. What it is not is a memory that survives — it is a `let`, and
  // the night this rewind was written for is precisely the one that ends with
  // the tab discarded. So the ordinary morning arrived here with nothing at all
  // and gave back nothing, and the longest rung of the ladder above, which
  // exists for exactly that night, had never once been reached in the case it
  // was built for.
  const stoppedAt = lastPauseAt || faded?.at || 0;
  if (!stoppedAt) return positionMs;
  const back = rewindFor(Date.now() - stoppedAt);
  const target = Math.max(0, positionMs - back);
  // Only the longest rung snaps. The sentence was looked up half a minute
  // behind where they stopped, because that is where the long rewind lands, so
  // applying it to one of the shorter ones would quietly turn eight seconds
  // back into half a minute back — a rewind three times the size of the one
  // the silence asked for, and it would happen on the most ordinary pause
  // there is.
  if (back < LONG_REWIND_MS) return target;
  if (!sentenceHint || sentenceHint.from !== Math.round(positionMs)) {
    // Nothing was found out at the pause, or the book has been moved since and
    // what was found out is about somewhere else entirely.
    return target;
  }
  // Long enough that they were asleep: land on the start of the sentence
  // rather than in the middle of one. A clause with no beginning is worse than
  // the silence was, and after an hour they have the whole of it to place.
  const extra = target - sentenceHint.start_ms;
  return extra >= 0 && extra <= SENTENCE_REACH_MS ? sentenceHint.start_ms : target;
}

// Asked at the pause and spent at the resume, never the other way round.
// Pressing play has to make a sound now, and a phone that has been face down
// for an hour is the least likely thing on the tailnet to answer quickly.
async function rememberTheSentence() {
  sentenceHint = null;
  if (gid === null) return;
  const from = Math.round(positionMs);
  try {
    const response = await fetch(
      `api/sentence/${gid}/${Math.max(0, from - LONG_REWIND_MS)}`,
    );
    if (!response.ok) return;
    const body = await response.json();
    if (typeof body.start_ms === "number") {
      sentenceHint = { from, start_ms: body.start_ms };
    }
  } catch (error) {
    // Offline, most likely, which is where the night usually ends. The flat
    // rewind above is the whole answer then, and a perfectly good one.
    console.error(error);
  }
}

// ---------------------------------------------------------- the morning after

// What the fade leaves behind, so that the morning has something to go on.
//
// Everything else about a night survives it. The position is on the server, the
// timer is in `somnia-sleep`, the last places are in `somnia-places`. The one
// thing nothing wrote down was that the night had ended by itself: the timer
// clears itself on the way into the fade, and the fade then stops the book
// through the ordinary path, which reports `pause` — the same word a thumb
// sends, and the only word the server is ever told. So the morning could not
// tell a book put down at eleven from one that faded out at 1:47, and it needed
// to tell them apart twice over: once for the rewind, and once for the screen.
//
// localStorage, beside the timer and the places and for the reason the timer
// gives: the tab is the thing that does not survive the night. A backgrounded
// page is discarded whenever the phone wants the memory back, so the relaunch is
// the ordinary morning rather than an edge of one — which is exactly why
// `lastPauseAt`, held in a variable, could never have been this record.
const FADE_KEY = "somnia-fade";

// Older than this and the morning it belonged to is over. A fade lands between
// about ten at night and three in the morning; twelve hours past any of those is
// the middle of the afternoon, which is after every morning and before the next
// night. Someone opening the book then is starting a night, and a screen telling
// them the timer faded them out at 1:47 would be about a night they have already
// had the whole of a day since.
const FADE_STALE_MS = 12 * 3_600_000;

// The fade this page is still living with, or null. It holds two things and both
// of them are read: when the sound went, which is what sizes the rewind and what
// the morning screen says out loud, and where it stopped, which is what the
// third choice on that screen offers to keep.
let faded = null;

// Whether the morning is still owed the wake screen. Separate from the record
// because the two have different lives: the screen is answered by one press, and
// the record goes on standing until the book is playing again, which is what
// keeps the long rewind for somebody who chose to keep their place and then
// pressed play.
let waking = false;

function rememberTheFade() {
  faded = { at: Date.now(), positionMs: Math.round(positionMs) };
  try {
    localStorage.setItem(FADE_KEY, JSON.stringify(faded));
  } catch (error) {
    // Storage refused, or is full. The rewind still works for as long as this
    // page lives — that is what `lastPauseAt` is — and what is lost is the
    // screen the next launch would have opened on.
    console.error(error);
  }
}

// What the last page to be alive wrote down as it went quiet.
//
// Anything else in that key reads as a night that ended some other way, rather
// than as a reason to throw: this runs at boot, before there is a screen to say
// anything on, and the one thing the page opening at 2am has to do is open. It
// is the rule `somnia-places` already follows and for the same reason.
function restoreFade() {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(FADE_KEY) || "null");
  } catch (error) {
    console.error(error);
  }
  if (!saved || typeof saved.at !== "number") return;
  // Both halves or neither. A record with no position in it would draw a third
  // choice offering to keep the book at `NaN`, on the one screen where every
  // word is supposed to be a fact somnia actually holds.
  if (typeof saved.positionMs !== "number") return;
  const since = Date.now() - saved.at;
  // A record from the future is a clock that has been put back — a phone that
  // picked up the network's time in the night, or one carried across a
  // timezone. Nothing true can be said about how long ago that fade was, so
  // nothing is said: no rewind, and no screen naming a time that has not
  // happened yet.
  if (!(since >= 0 && since < FADE_STALE_MS)) return;
  faded = saved;
  waking = true;
  drawWake();
}

// The fade, spent. Either the morning has been answered by a press on it, or the
// book is playing again — which is the same answer said with a thumb — and
// either way the rewind it feeds has been given and there is no second night in
// it. A record left behind is a wake screen at eight o'clock for somebody who
// was listening to the book at half past seven.
function spendTheFade() {
  faded = null;
  try {
    localStorage.removeItem(FADE_KEY);
  } catch (error) {
    console.error(error);
  }
}

// Off the morning and back to the book, by the same three lines every other way
// back to the player goes through. It is called from the two choices that end on
// the player and from the book starting to play under the screen, which is what
// a press on the lock screen does: the transport is not drawn on this screen, so
// leaving it up over a playing book would be a book nothing on the page can
// stop.
function leaveTheMorning() {
  waking = false;
  backToTheBook();
}

// The wall clock, as the phone beside the bed shows it: `1:47`, `23:05`.
//
// Built by hand rather than asked of a locale, because the one this page runs in
// writes `01:47` and the leading zero on the hour is a digit doing nothing on
// the loudest line of the screen. Twenty-four hours and no am/pm for the same
// reason: this line is read at 2am, when it is either the time on the clock
// beside it or a word to be worked out.
function wallClock(ms) {
  const when = new Date(ms);
  return `${when.getHours()}:${String(when.getMinutes()).padStart(2, "0")}`;
}

// What the morning screen says, out of the record and nothing else.
function drawWake() {
  if (!faded) return;
  wakeSaid.textContent = `The timer faded you out at ${wallClock(faded.at)}.`;
  // Where it stopped, on the book's own clock, in the shape every other clock on
  // the page uses. It is written on the choice that keeps it so that keeping it
  // is a decision about a place rather than a shrug at a button.
  wakeKeep.textContent = `keep it where it stopped · ${timestamp(faded.positionMs)}`;
  // And the count under the first choice, which is drawPlaces' business. Asked
  // here as well as there because at this point the book is not open yet — the
  // manifest is a fetch away — so the answer is "none that are about this book"
  // until it lands, and this is what makes that the state the screen comes up
  // in rather than a slab that appears and then goes away again.
  drawPlaces();
}

// The screen, raised. Two moments call it: the page opening after a fade, which
// is the ordinary morning; and a page that happened to survive the night coming
// back into view still holding a record, which is the same morning on a phone
// that did not kill the tab. Which of the two it was is not something the reader
// can see, so it must not be something the app draws differently.
function raiseTheMorning() {
  if (!faded || waking) return;
  waking = true;
  // Whatever screen they left the phone on, they are not on it now. `asked` is
  // the remembered "they want the conversation", and left standing it would put
  // the chat back over the morning on the first resize after they pressed
  // anything here.
  stoppedAsking();
  drawWake();
  showScreen("wake");
}

// The three choices, in the order the screen draws them.
//
// Each of them is one press with nothing to confirm, and each ends somewhere
// that answers the question this screen asks. The fade is spent by all three:
// having been asked, the morning does not ask again.

wakePlaces.addEventListener("click", () => {
  spendTheFade();
  leaveTheMorning();
  // The same list the position line opens, raised the same way. There is no
  // second route to Places and this is not one: what is here is the press,
  // moved to the screen somebody is on at seven in the morning.
  showRemembered();
});

wakeAsk.addEventListener("click", () => {
  spendTheFade();
  waking = false;
  // Straight on to the conversation with the keyboard coming up, which is the
  // same arrival the dock makes and is said the same way — `asked` is what that
  // screen means, and a screen set without it would be undone by the first
  // resize. The focus is what raises the keyboard, and it can only do that from
  // inside the press that asked for it.
  asked = true;
  showScreen("chat");
  question.focus();
});

wakeKeep.addEventListener("click", () => {
  spendTheFade();
  leaveTheMorning();
});

// The listener waiting for a touch anywhere on the page, or null. Its
// truthiness is the whole of "armed" — a second flag is a second thing to keep
// in step with it, and the one that goes stale is the one that starts the book
// under somebody.
//
// It is a named function held in a variable rather than the anonymous
// once-listener this used to be, purely so it can be taken off again. The
// candidate list is why: a real 2am sequence is app backgrounded, play refused,
// question asked, list arrives, cancel pressed — and with an unremovable
// listener the press that was meant to change nothing starts the book. Cancel
// puts it back afterwards, because by then it is true again.
let tapToResume = null;

function armTapToResume() {
  if (tapToResume) return;
  setStatus("tap anywhere to carry on");
  tapToResume = () => {
    tapToResume = null;
    ensurePlaying();
  };
  document.addEventListener("pointerdown", tapToResume, { once: true });
}

function disarmTapToResume() {
  if (!tapToResume) return;
  document.removeEventListener("pointerdown", tapToResume);
  tapToResume = null;
}

function onPlayRejected(error) {
  // Two unlike failures arrive here. NotAllowedError is the autoplay policy:
  // the sound is welcome, it just wants a touch first, and offering that is
  // the difference between a book that stopped and a book that stopped with
  // nothing on the screen to say why.
  //
  // Everything else — a chapter that would not load, a play abandoned because
  // a newer seek replaced the source — has already been explained by whatever
  // caused it, and arming a tap-to-resume for it would start the book under
  // the next thing they touch, which at 2am is the question box.
  console.error(error);
  if (error?.name !== "NotAllowedError") return;
  armTapToResume();
}

// --------------------------------------------------------------- getting back

// Nothing below is hypothetical. Wifi power save, a DHCP renewal and a
// tailscale re-key each take the tailnet away for a few seconds in the middle
// of the night, and a media element comes back from none of them by itself:
// once it has taken a network error it will never fetch again, and a buffer
// that ran dry with nothing behind it sits there silently until something
// reloads it. With the screen locked, all of that looks the same from the
// outside — a notification that says paused — so the page has to be the thing
// that notices, and it has to say so where they can see it. At 2am a silent
// spinner is worse than a sentence.

function inTrouble(message) {
  troubled = true;
  setStatus(message);
}

// The book is arriving again. Only the network's own message is cleared:
// "goodnight" and "tap anywhere to carry on" are about something else.
//
// A standing failure goes with it, and that is not the same test as `troubled`.
// "that chapter didn't arrive" is said about a book that had been put down, so
// nothing was retrying and `troubled` was never set — and until the red it was
// harmless to leave a stale sentence there, because amber on this line is only
// somnia talking. A red says a person is needed, and sound coming out of the
// phone is proof that they are not. The one thing that must not happen is a
// book playing under a red line nobody can take down.
function outOfTrouble() {
  clearTimeout(stallTimer);
  clearTimeout(retryTimer);
  stallTimer = 0;
  retryTimer = 0;
  retryDelay = RETRY_MIN_MS;
  if (troubled || statusLine.classList.contains("failed")) setStatus("");
  troubled = false;
}

// A source failed to load. Whether that says anything about the source itself,
// as against about the network underneath it, is what this decides — and after
// JOIN_TRIES failures of a join nobody has ever heard, spread over half a minute
// so that they are two answers rather than one outage, the page stops asking for
// it and reads the book a file at a time instead.
//
// This is the half of issue 31 that the blink was not. Both sentences reported
// off the handset came from the ladder below, and under the design this branch
// replaced every rung of it assigned src again: each attempt to get the book
// back first threw away the notification that was the only thing on the locked
// screen saying anything about the book at all. A boundary does not come down
// here any more, so what is left is a network that really went — and a URL that
// is never going to answer, which is what this is for. Left unbounded, that one
// is a night that never comes back.
//
// Nothing counts against a chapter file. That is already the fallback and there
// is nowhere further to fall: a page that gave up on those would be a page with
// nothing left to play.
function countAgainstTheJoin() {
  if (holdingOneChapter || fellBackToChapters) return;
  // The one that does the work: this URL has played, so the file is there and
  // what failed is the wire. See joinThatArrived for why that is the whole of
  // the distinction the fallback rests on.
  if (sourceUrl === joinThatArrived) return;
  // A URL the count is not about — the frontier reached for a longer join, or
  // the manifest named one while this was going on. Nothing learned about the
  // last one is evidence about this one, so the count starts again.
  if (sourceUrl !== joinThatFailed) {
    joinThatFailed = sourceUrl;
    joinsThatFailed = 0;
  }
  // Too soon after the failure before it to be a second answer: this is the
  // ladder finding the same outage again, and waiting it out is what the ladder
  // is for. See joinThatArrived.
  const now = Date.now();
  if (joinsThatFailed > 0 && now - joinFailedAt < RETRY_MAX_MS) return;
  joinFailedAt = now;
  joinsThatFailed += 1;
  if (joinsThatFailed < JOIN_TRIES) return;
  fellBackToChapters = true;
  // Nothing is said about it. The listener cannot act on which URL the sound is
  // arriving down, the ladder's own sentence is already on the screen, and it
  // comes off the moment the first chapter file loads — which is the only thing
  // about any of this they can hear.
  //
  // The wait the ladder has climbed was earned by a question nobody is asking
  // any more, so it is given back: the next attempt is a different URL on a box
  // that is answering. It can only climb again if the chapters fail too, which
  // is the network, which is what the climbing is for.
  retryDelay = RETRY_MIN_MS;
}

// Put the book back under them, from where they had got to rather than from the
// top of what was loaded. Reloading is the whole of the way back — assigning
// src is what makes an element try the network again — and going through
// locate(positionMs) is what makes a five-second drop cost five seconds instead
// of making them hear the last ten minutes again.
//
// This is a teardown like any other: the element is emptied and the lock screen
// panel goes with it. Route 2 does not remove that, it removes the reasons for
// it — a chapter boundary no longer comes down here, so what is left is a
// network that really went, which is rarer and is the case the ladder above was
// written for.
function reloadTheSource() {
  if (!manifest || !current) return;
  inTrouble("still trying to reach the book");
  loadSource(locate(positionMs), { play: wantsSound });
}

// Wait, then try again, waiting longer each time. Bounded at both ends for the
// reason given at RETRY_MIN_MS. Never while they are the ones who stopped it: a
// page that reloaded chapters under a book somebody had put down would be
// spending the battery on nobody.
function retryLater() {
  if (retryTimer || !wantsSound) return;
  // Whatever grace a stall was being given is spent: `waiting` fires just
  // before the error that follows it, so without this every failure leaves two
  // chains reloading the chapter and the backoff below is capped at whichever
  // of them is shorter — which at 4am is a request every eight seconds until
  // the battery goes.
  clearTimeout(stallTimer);
  stallTimer = 0;
  retryTimer = setTimeout(() => {
    retryTimer = 0;
    reloadTheSource();
  }, retryDelay);
  retryDelay = Math.min(retryDelay * 2, RETRY_MAX_MS);
}

// A buffer that has run dry, or a download that has stopped arriving. Given a
// few seconds before anything is done about it: most of these refill by
// themselves and nobody hears more than a gap, and announcing every ordinary
// rebuffer would put a line on the screen — and in a screen reader's ear,
// through the live region — for something that is already over.
//
// `suspend` and `abort` are deliberately not wired here however much they look
// like they belong: suspend is a full buffer, which a five-hour file reaches
// whenever the network is doing well, and abort is a source being replaced,
// which is the one thing this ladder is allowed to do.
function stalling() {
  if (!wantsSound || stallTimer || retryTimer) return;
  // The grace is for a buffer that is going to refill, and there is nothing
  // left of that story once the page is already fighting for the chapter: a
  // reload that stalls again goes straight onto the ladder instead. Without
  // this the two of them interleave — eight seconds of grace, then the wait,
  // then eight seconds of grace — and the cadence never falls below a request
  // every nineteen seconds however long the night's outage lasts.
  if (troubled) {
    retryLater();
    return;
  }
  stallTimer = setTimeout(() => {
    stallTimer = 0;
    reloadTheSource();
    // That reload was an attempt like any other, so the next one waits longer.
    // A server that takes the connection and never answers — a proxy black
    // hole, a re-key caught mid-handshake — fires no `error` at all, so
    // nothing else here would ever grow the wait: the new source stalls, this
    // fires again on the same eight seconds, and that is the request every
    // eight seconds until the battery goes that the backoff exists to prevent.
    // Never below the grace this waited out, so the ladder can only be more
    // patient than the stall was, never less.
    retryDelay = Math.max(retryDelay, STALL_GRACE_MS);
    retryLater();
  }, STALL_GRACE_MS);
}

// Something happened that might mean the network is back: the browser said so,
// or the page came back in front of them. Whatever is waiting out a backoff is
// worth trying now — the wait was only ever a guess about a network nobody can
// see, and being wrong about it in this direction costs one request.
function tryAgainNow() {
  bootDelay = RETRY_MIN_MS;
  retryDelay = RETRY_MIN_MS;
  if (bootTimer) {
    clearTimeout(bootTimer);
    bootTimer = 0;
    openTheBook();
  }
  if (retryTimer) {
    clearTimeout(retryTimer);
    retryTimer = 0;
    reloadTheSource();
  }
  if (awaiting) {
    awaiting.delay = RENDER_ASK_MS;
    askForMore();
  }
}

player.addEventListener("waiting", stalling);
player.addEventListener("stalled", stalling);
// The sound is really coming out, which is the only proof worth having. A stall
// that refilled by itself never reloads anything, so this is the one thing that
// says so.
player.addEventListener("playing", outOfTrouble);

// `online` is a hint and never a replacement for the backoff above: the wifi
// coming back is not the tailnet coming back, and a tailscale re-key does not
// touch this event at all. All it means is that there is no point waiting out
// the rest of a wait that was a guess.
window.addEventListener("online", tryAgainNow);

player.addEventListener("loadedmetadata", () => {
  // The server answered with audio, which is as much as this page ever knows
  // about the network being back.
  outOfTrouble();
  // And this particular URL is really there, which is a longer-lived fact than
  // that and a different one. It is what keeps an outage on a good join off the
  // fallback path however long the outage lasts — see joinThatArrived. Only for
  // a join: a chapter file is already the fallback and nothing is decided by
  // whether one of those arrives.
  if (!holdingOneChapter) {
    joinThatArrived = sourceUrl;
    joinsThatFailed = 0;
  }
  if (pendingOffsetMs !== null) {
    player.currentTime = toElementSeconds(pendingOffsetMs, player.duration);
    pendingOffsetMs = null;
  }
  swapping = false;
  // A new source, so the last sample was taken off a clock that is no longer
  // running. Whatever the load stepped over was not listened to, and counting
  // it would be the only listening a page ever got for free.
  playedFrom = null;
  drawPlayer();
  publishPosition();
  // A source landing is a good place to be interrupted at: it is the boot, or
  // the far side of a reload the network forced, and either way the position
  // either side of it can differ by a whole chapter. At boot this says nothing,
  // because opening the app has not moved anything. It is no longer once a
  // chapter — nothing is loaded at a boundary any more — so the fifteen-second
  // heartbeat is what carries the position across one.
  sendPosition("chapter");
});

player.addEventListener("timeupdate", () => {
  // While a source is arriving currentTime can still be reading from the one
  // being left, which would report a position they are no longer at.
  if (swapping || !current) return;
  positionMs = whereTheSoundIs();
  // Sound came out between the last sample and this one, and this is the only
  // place in the page where that is true: the media clock moves by itself here
  // and is moved by hand everywhere else. Forwards only, and only from a
  // sample left behind by the source still loaded — a rewind is not negative
  // listening, and a baseline that was set aside by a seek or a load is not a
  // distance anybody heard.
  if (playedFrom !== null && positionMs > playedFrom) {
    playedMs += positionMs - playedFrom;
  }
  playedFrom = positionMs;
  // Both of these are here rather than above the guard so that neither can
  // land in the middle of a source arriving: a fade that finished then would
  // pause an element that is between two sources, and the pause it caused would
  // be swallowed as the spurious one a src assignment fires.
  stepFade();
  countDownToSleep();
  // The render frontier: the sound is about to run off the end of what this
  // source holds, and there is more book than that. Stopping a fraction short of
  // it is what keeps the lock screen panel up for the wait — see
  // reachTheFrontier, which is also where a night asked to end at this chapter
  // is ended, because at the frontier the two are the same moment and the check
  // below is four hundred milliseconds too late to see it.
  //
  // Only while there is sound to stop. A paused element still gets a timeupdate
  // out of a seek, and coming back through here would be the page pausing what
  // is already paused and asking again for a chapter it is already waiting on.
  //
  // KNOWN: timeupdate comes off the media pipeline and goes on firing with the
  // screen off, which is what the fade and the sleep timer already rest on.
  // ASSUMED: that it keeps to something near four a second there. If a phone
  // ever throttles it past the four hundred milliseconds this leaves, the next
  // sample lands the far side of the end, the element ends, and the panel goes
  // with it — and `ended` picks the wait up from exactly here, so the book still
  // carries on when the chapter lands. What a throttled handler costs is the
  // panel, not the night.
  if (
    !player.paused &&
    sourceIsShortOfTheBook() &&
    player.currentTime >= frontierSeconds()
  ) {
    reachTheFrontier();
    return;
  }
  // The way the timer ends a night with a time to arrive at: they asked for the
  // end of this chapter, and the book's own clock has reached it. What ends the
  // night is that time and not the file underneath happening to run out — with
  // the whole book down one URL a chapter ends in the middle of a file with
  // hours left in it, and nothing but this marks the place.
  //
  // Above the crossing below, and that ordering is the whole of it: once the
  // page has entered the next chapter, `current` names a chapter whose end is
  // an hour away and this can never fire. A night asked to end here would end
  // at the end of the next one instead, which is the sleep timer doing the
  // opposite of what it was set for.
  //
  // Stopped rather than faded, for the reason `ended` gives further down: ingest
  // leaves half a second of silence at the end of every chapter, and the last
  // words of one are a place a book means to be put down. Twenty seconds of
  // fading out from here would be a fade over silence that nobody hears.
  if (sleepsAtChapterEnd() && positionMs >= current.chapter.end_ms) {
    clearSleep();
    fallAsleep();
    return;
  }
  // The chapter boundary, and all it is now.
  //
  // Idempotent by the index, because this runs four times a second for the
  // whole night: a boundary is the one sample where the answer changes, and
  // every other sample must leave the notification alone. Reassigning
  // `session.metadata` at 4 Hz would be the page shouting at the platform all
  // night for nothing.
  //
  // Nothing here touches the element. That is the point — see enterChapter.
  //
  // Only where the element holds more than one chapter. Played a file at a
  // time it is what was loaded that says which chapter this is, and the last
  // sample of such a file reads as the first millisecond of the next one —
  // toGlobalMs clamps to the chapter's own end, and locate calls that end the
  // chapter after. So this would enter the next chapter a quarter of a second
  // before `ended` loaded it, and `ended` would then step over it into the one
  // after: a chapter skipped, silently, at every boundary of the fallback path.
  if (!holdingOneChapter) {
    const at = locate(positionMs);
    if (at.idx !== current.idx) enterChapter(at);
  }
  drawPlayer();

  // At most once a second. The platform interpolates between these from the
  // playback rate it was given, so telling it more often buys nothing and
  // every one of them is a hop out of the page.
  const now = Date.now();
  if (now - lastPublishedAt >= 1000) {
    lastPublishedAt = now;
    publishPosition();
  }
  if (!player.paused && now - lastSentAt >= HEARTBEAT_MS) sendPosition("tick");
});

player.addEventListener("seeked", () => {
  if (swapping || !current) return;
  positionMs = whereTheSoundIs();
  drawPlayer();
  publishPosition();
  // A jump is the one thing the fifteen-second heartbeat cannot approximate:
  // between one tick and the next they may be an hour away.
  sendPosition("seek");
});

player.addEventListener("play", () => {
  untouched = false;
  // From here the sound is meant to be on, and anything that takes it away is
  // something to get back from rather than something that happened.
  wantsSound = true;
  // And it is not stopped at the end of what has been read, whatever started it
  // — the wait's own reload, or a thumb on the play button while the render is
  // still going. The second of those is the one that needs saying: it plays the
  // last fraction of a second again and comes straight back to the frontier, and
  // it can only be stopped there a second time if this has been given up first.
  atFrontier = false;
  // The timer measures listening, so it starts counting from here and not from
  // whenever it was last looked at.
  sleepCountedAt = Date.now();
  // Belt and braces on the invariant that a paused player is at full volume:
  // whatever route the sound came back by, it must not come back inaudible.
  if (!fade && player.volume < 1) startFade(1, FADE_IN_MS);
  reportPlaybackState("playing");
  drawPlayer();
  publishPosition();
  // Where the sound came back on, which is the beginning of a stretch of
  // listening. The spoiler guard advances on time that really elapsed with the
  // sound on, so a stretch with no beginning gives it nothing to measure the
  // first heartbeat against and it stops for the rest of the book. Not while a
  // source is arriving: the position is between two things there, and the report
  // at the far side of the load says the same thing a moment later.
  if (!swapping) sendPosition("play");
});

// Nothing changes the rate yet. The handler is here because the platform
// interpolates the scrubber from the rate it was last given, so the one thing
// that must never happen is a rate change it never hears about.
player.addEventListener("ratechange", publishPosition);

player.addEventListener("pause", () => {
  // A pause means four different things and only one of them is theirs.
  // Assigning src runs the media element load algorithm, which fires one;
  // reaching the end of what is loaded fires one before `ended`, per spec; and
  // a source that fails to load fires `error` and then a pause after it.
  // Treating any of those as the listener stopping announces that something
  // took the sound, and writes that over the true reason in the one case where
  // there is a true reason to give.
  //
  // Three of those four used to happen at every chapter boundary all night.
  // They do not any more — a boundary loads nothing and ends nothing — which
  // makes this guard rare rather than unnecessary: a reload the network forced
  // is still a real load with a real spurious pause, and reporting "paused" for
  // it is the platform's cue that the book stopped, after which it redraws the
  // button or decides the page is finished with the sound.
  if (swapping || player.ended || player.error) return;
  // A pause that got this far is one somebody made — a thumb, the lock screen,
  // the sleep timer, or an alarm taking the sound. None of them is a network to
  // fight, and the retry above stops for all of them.
  wantsSound = false;
  outOfTrouble();
  // How long the sound has been off is the whole of what the resume knows, so
  // it is written down before anything else can take time over it.
  lastPauseAt = Date.now();
  endFade();
  reportPlaybackState("paused");
  drawPlayer();
  publishPosition();
  // Someone who pauses at 2am may not touch the phone again for a week, so
  // this is the position that has to be right, and it is worth a request of
  // its own however recently the last one went.
  sendPosition("pause");
  // While the connection is still warm. If this pause turns out to have been
  // the end of the night, the answer is what stops the morning starting in the
  // middle of a sentence.
  rememberTheSentence();
  if (!weArePausing) {
    // Audio focus went elsewhere: a call, an alarm, another app. Do not
    // resume. An alarm should stop the book, not be talked over.
    //
    // Amber, not red: nothing is broken here. The phone did the right thing and
    // this line only explains why the book stopped, so that a silence with a
    // reason is not mistaken for one without.
    setStatus("something else took the sound");
  }
  weArePausing = false;
});

player.addEventListener("ended", () => {
  // The source ran out. What that means depends on what the source was, and
  // there are exactly two answers: a chapter file ended, which is a boundary
  // and is how boundaries are crossed when the book is played a file at a time;
  // or the whole book ran out, which is either the end of it or the end of what
  // has been read of it so far.
  //
  // `ended` decides that a file is over, never the clock: a truncated encode
  // becomes a skip rather than a book that hangs at 2am.
  //
  // Unless the sound was already meant to be off, in which case there is
  // nothing left here to decide: whatever stopped it has said what happens
  // next. The chapter-end sleep above is the one that does, and on a file of
  // exactly the length the database gives its chapter it stops a few
  // milliseconds ahead of this. An `ended` arriving behind it would read a
  // timer that had just been spent, find it off, and start the next chapter
  // over a book that was deliberately put down for the night.
  if (swapping || !current || !wantsSound) return;
  positionMs = current.chapter.end_ms;
  const next = manifest.chapters[current.idx + 1];
  const goodnight = sleepsAtChapterEnd();
  if (next && !goodnight) {
    // A chapter at a time: the next file, which is the ordinary boundary there.
    // Under one URL per book it means the stream stopped short of a book that
    // has grown since it was built — the render frontier, reached without the
    // pause a fraction before it having had a sample to fire on — and the way
    // on is the longer stream the manifest is now naming. Both are the same call
    // because both are "load whatever holds the place we are going to".
    loadSource(locate(next.start_ms), { play: true });
    return;
  }
  // The sound has stopped, whichever of the three reasons it was. A chapter
  // ending is its own fade — ingest leaves half a second of silence at the end
  // of every one, and the last words of a chapter are a place a book means to
  // be put down — so this way of stopping needs no fading at all.
  //
  // The pause that came with this was swallowed as spurious, quite rightly, so
  // everything that pause would have done has to happen here instead: writing
  // down when the sound stopped, because the morning's rewind is measured from
  // it, and saying so, because otherwise the lock screen goes on offering a
  // pause button for a book that is not playing.
  endFade();
  lastPauseAt = Date.now();
  rememberTheSentence();
  reportPlaybackState("paused");
  sendPosition("ended");
  // gid is null for a book the server has said is gone: there is nothing left
  // to ask about it, and the answer would never change.
  if (!next && !goodnight && gid !== null && manifest.status === "rendering") {
    // Not the end of the book — the end of what has been read of it so far.
    // Saying otherwise here is the lie somebody would act on: they added the
    // book at eleven, chapter one was playable in minutes, and the night ends
    // three chapters into forty-nine with the sleep timer thrown away.
    //
    // This is where a chapter file always runs out, and where the whole book
    // runs out when the pause a fraction short of the frontier had no sample to
    // fire on. The flag says the same thing either way — the sound is stopped
    // at the end of what has been read — and askForMore asks it rather than
    // asking `player.ended`, which is only true on one of the two.
    atFrontier = true;
    awaitMore(gid, { play: true, at: current.idx });
    drawPlayer();
    return;
  }
  // Not rendering, and not all here either: a render that was stopped, or that
  // died, or that a deploy shot in the head. Nothing is coming while nobody
  // asks for it, so there is nothing to wait for — but this is still not the
  // end of the book, and saying it was would end the night on a lie somebody
  // would act on. The sleep timer and the fight to keep the sound going are
  // left exactly as they are, because neither has anything to do with the
  // render having stopped.
  if (!next && !goodnight && moreToCome()) {
    setStatus("the rest of this book hasn't been read yet");
    drawPlayer();
    return;
  }
  setStatus(goodnight ? "goodnight" : "that is the end of the book");
  // The one way the timer ends a night that does not go through fallAsleep: the
  // file ran out before the book's clock reached the end of the chapter it was
  // asked to stop at — a truncated encode, or a join that came up short — so the
  // check that watches for that end never fired and this is where the night
  // actually ended. The morning is owed the same record either way, and a
  // morning that had one on some nights and not others would be worse than one
  // that never came at all.
  if (goodnight) rememberTheFade();
  // Nothing is coming. Anything still trying to get the book back is trying for
  // nobody now.
  wantsSound = false;
  clearSleep();
  drawPlayer();
});

player.addEventListener("error", () => {
  // Whatever went wrong, the state machine must not be left mid-load: with
  // `swapping` stuck on, every later tick of the media clock would be ignored.
  swapping = false;
  pendingOffsetMs = null;
  // Same reason as at the end of the book: the pause that follows an error is
  // swallowed, and a notification still showing a pause button for silence is
  // a lie they would have to unlock the phone to see through.
  reportPlaybackState("paused");
  drawPlayer();
  console.error(player.error);
  // Counted before anything below decides what to do about it. Whether this URL
  // is ever going to answer is true whether or not there is somebody listening
  // for it, and a book that was put down is exactly where a bad join sits
  // quietly until it is pressed at 2am.
  countAgainstTheJoin();
  // Nobody can tell from here whether this is the night ending or five seconds
  // of it, so the page assumes the kinder one for as long as the sound was
  // meant to be on, and keeps trying. A book they had already put down is left
  // where they put it.
  if (!wantsSound) {
    setStatus("that chapter didn't arrive", true);
    return;
  }
  // Not red, and the difference is the retry. Everything inTrouble says is the
  // page still working on it — "still trying", "trying again", and this, which
  // retryLater is about to act on. Nobody is needed while something is being
  // done, and a red that came on for every tailnet re-key would be red for the
  // second most common event of the night after the frontier.
  inTrouble("the book stopped arriving");
  retryLater();
});

playpause.addEventListener("click", () => {
  if (player.paused) ensurePlaying({ rewind: true });
  else pauseHere();
});
const nudge = (seconds) => seekGlobal(positionMs + seconds * 1000);
// Read at the moment of the press, not captured when the listener was added:
// Workshop can change what a skip is while the page is up, and a closure over
// the old value would leave the button saying `−15` and moving thirty.
back30.addEventListener("click", () => nudge(-jumpStep));
fwd30.addEventListener("click", () => nudge(jumpStep));

// Five seconds in, "previous" means the start of this chapter — what it means
// on every music player anyone has used, and the more forgiving of the two
// answers for a thumb that missed. On the first chapter it is the only answer
// there is, which is why the check is for a previous chapter existing and not
// for the index being zero.
function toPreviousChapter() {
  if (!current) return;
  const previous = manifest.chapters[current.idx - 1];
  const into = positionMs - current.chapter.start_ms;
  seekGlobal(
    into > CHAPTER_RESTART_MS || !previous
      ? current.chapter.start_ms
      : previous.start_ms,
  );
}

function toNextChapter() {
  const next = current && manifest.chapters[current.idx + 1];
  if (next) seekGlobal(next.start_ms);
}

// The same two functions the lock screen and a Bluetooth remote call, so the
// button on the page and the button on a pillow speaker cannot drift apart.
prevChapter.addEventListener("click", toPreviousChapter);
nextChapter.addEventListener("click", toNextChapter);

// All eight of them, whether or not this phone has anything to press. Android
// only surfaces the buttons it has a handler for, so an unregistered nexttrack
// is a pillow speaker whose skip button does nothing at all, and finding that
// out means being awake enough to test it.
function listenForRemoteControls() {
  if (!session?.setActionHandler) return;
  const handle = (action, fn) => {
    try {
      session.setActionHandler(action, fn);
    } catch {
      // A browser that has never heard of this action refuses to take it.
      // That is one button that will not appear, not a reason to stop.
    }
  };
  // The lock screen and a button on a pillow speaker are the same press as the
  // one on this page, made by the same person, and get the same few seconds
  // back — most of the night this is the only one of the two they can reach.
  handle("play", () => ensurePlaying({ rewind: true }));
  handle("pause", () => pauseHere());
  // Stop pauses, and does nothing else. The obvious reading — release the
  // sound, clear the element — is the documented way to dismiss the media
  // notification, and dismissing it face down in a pocket is the one state
  // this page cannot recover from.
  handle("stop", () => pauseHere());
  // The platform says how far it wants to go, and only falls back to our idea
  // of "a bit" when it has no opinion. Both go through the global timeline, so
  // a nudge back from the first seconds of a chapter lands in the one before,
  // which is what "back a bit" means to someone who is listening to a book and
  // not to a pile of files.
  // The setting, where the platform has not said how far. A lock screen that
  // skipped a different distance from the two buttons on the page would be the
  // app disagreeing with itself about what a skip is, in the one place nobody
  // can see the labels to check.
  handle("seekbackward", (d) => nudge(-(d?.seekOffset ?? jumpStep)));
  handle("seekforward", (d) => nudge(d?.seekOffset ?? jumpStep));
  // seekTime comes back on the scale we published, which is this chapter's.
  // This is the one place it is put back on the book's clock.
  handle("seekto", (d) => {
    if (!current || typeof d?.seekTime !== "number") return;
    seekGlobal(current.chapter.start_ms + d.seekTime * 1000);
  });
  handle("previoustrack", toPreviousChapter);
  handle("nexttrack", toNextChapter);
}

listenForRemoteControls();

// ------------------------------------------------------- where they have got to

// The page is the only thing that knows where the sound is while it plays, so
// saying so is not bookkeeping — it is the whole of somnia's memory of the
// night. Everything below is driven by media events for the reason given at
// HEARTBEAT_MS: with the screen off, they are the only events still arriving.

function positionBody(reason) {
  return {
    // Not authentication — there is none here by design. It is so the journal
    // can say which page wrote what.
    token,
    gid,
    position_ms: Math.round(positionMs),
    seq,
    // How much of the book has really played since the last report the server
    // took, which is what the spoiler guard measures this one against. A
    // stretch they listened to moves this by as much as it moves the position;
    // a skip, an agent move or a scrub moves the position and not this. Saying
    // it rather than leaving the server to infer it from the clock is the
    // whole of the difference between the two: the server cannot see a phone
    // that spent four minutes asleep with the sound off, and this page cannot
    // help seeing it.
    played_ms: Math.max(0, Math.round(playedMs - playedTaken)),
    reason,
  };
}

function postPosition(body, { keepalive = false } = {}) {
  return fetch("api/position", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    keepalive,
  });
}

// One at a time, and never retried. A retry delivers a stale position over a
// newer one, and the next heartbeat carries better truth anyway; what must not
// happen is the LAST position being the one that got dropped, which is what
// `owed` is for. It remembers only that something is owed, and the body is
// built afresh when it goes out, so what lands is where they are now.
function sendPosition(reason) {
  if (untouched || !manifest || gid === null) return;
  if (sending) {
    owed = reason;
    return;
  }
  sending = true;
  // Counted from when it went out, not from when it came back: gating the
  // heartbeat on the reply would turn a phone with no signal into a request
  // every few hundred milliseconds, which is the one thing a battery cannot
  // afford at 4am.
  lastSentAt = Date.now();
  // What this report is about to claim, held while it is in flight. Playback
  // that goes out and is not taken has to still be owed when the answer comes
  // back, and by then more of it may have happened.
  const claimed = playedMs;
  // Backgrounded, and the page may be frozen a moment later. keepalive is what
  // lets the request finish without one.
  postPosition(positionBody(reason), { keepalive: reason === "hidden" })
    .then((response) => response.json())
    .then((body) => {
      // Never backwards. A seek gives up whatever was owed at the moment it
      // happens, and an acknowledgement for a report that went out before it
      // would otherwise put that playback back and hand it to the jump.
      if (body?.accepted) playedTaken = Math.max(playedTaken, claimed);
      applyReply(body);
    })
    .catch((error) => console.error(error))
    .finally(() => {
      sending = false;
      const next = owed;
      owed = null;
      if (next) sendPosition(next);
    });
}

// The last word on a book the page is about to stop being on, sent while gid
// is still that book's. Nothing else would ever say it: the pause a load fires
// is swallowed as spurious, quite rightly, so a book left behind would keep
// whatever position its last heartbeat happened to catch — up to fifteen
// seconds of a book they were listening to a moment ago.
//
// It goes round sendPosition rather than through it. That one holds a report
// back while another is in flight and builds the body when its turn comes, and
// by then this body would be the book they left written against the gid of the
// one they are now on. Its reply is dropped for the same reason: a refusal
// here is about a book the page has already left, and following it would take
// them straight back to it.
//
// It carries the playback that belongs to this book with it, which is the last
// chance to say it: the stretch between the last heartbeat and here was really
// listened to, and a mark left behind the position they were left at would
// refuse everything they play the next time they open this book. Nothing here
// can hear it being taken, so openBook gives it up on this page's behalf a
// moment later rather than letting the next book claim it too.
function sendPartingPosition() {
  if (untouched || !manifest || gid === null) return;
  postPosition(positionBody("switch")).catch((error) => console.error(error));
}

function applyReply(body) {
  if (!body || body.accepted) return;
  // A refusal answers the report that asked, and that report may be about a
  // book the page has since left: switching books leaves one in flight, and
  // reading its refusal as "go here" would re-open the book they were just
  // taken out of. Only a refusal about the book the page is on has anything to
  // say to it.
  if (body.gid !== gid) return;
  // The agent moved the book while this page was not looking. That is the only
  // thing that can refuse a report, and the refusal says where to go.
  if (body.reason === "moved") follow(body);
  if (body.reason === "gone") {
    // The book is not in the database any more. Whatever is still in the
    // element can play out, but there is nothing left to write to.
    setStatus("that book isn't here any more", true);
    // And a list of places in it is a list of promises the page can no longer
    // keep: every row would go and fetch a book that has been deleted and come
    // back with "couldn't reach that book". Only when it is that book's list —
    // an offer about some other book is still perfectly good.
    if (offered?.gid === body.gid) closeCandidates();
    gid = null;
  }
}

// The agent decided where the book should be. It arrives by two routes — the
// reply to the question that caused it, and the refusal of the next report —
// and they are the same function because whichever gets here first should win
// and losing either should cost nothing.
function follow(move) {
  if (!move || typeof move.seq !== "number") return;
  if (move.gid !== gid) {
    // A different book. The move was written before the answer came back, so
    // that book's manifest already carries the new position and the new count:
    // opening it *is* following it, and there is nothing else to apply.
    openBook(move.gid, { play: true }).catch((error) => {
      setStatus("couldn't reach that book", true);
      console.error(error);
    });
    return;
  }
  // Our own book. Our reports never raise the count, so a number higher than
  // the one we hold can only be a move this page has not applied — and one that
  // is not higher has already been applied by the other route.
  if (move.seq <= seq) return;
  seq = move.seq;
  if (typeof move.position_ms !== "number") return;
  // They asked to be taken somewhere, so take them there and play it.
  // Reproducing "now press play yourself" in JavaScript would be a joke.
  seekGlobal(move.position_ms, { play: true });
}

// ------------------------------------------------------ places you might be

// Some questions have more than one answer, and the old way of saying so was a
// conversation: "did you mean the one an hour in, or the one at four hours?"
// read in the dark, by someone half asleep, and answered by typing. This is
// that conversation as a list of times a thumb can point at.
//
// It is an overlay and not a screen. The book plays underneath the whole time,
// nothing has been moved, nothing has been written, and every way out leaves
// the page in a state it was already able to be in. Choosing a row is a seek —
// the same code path as −30, made by the same person — and not a request to the
// server: a chosen row bumps no position_seq, so routing it through follow()
// with an invented count would either do nothing at all or leave this page
// holding a number the database has never had, after which every report for the
// rest of the night is refused and the refusal drags them backwards. The server
// finds out at once anyway, by the route every other seek takes: the element
// fires `seeked` and sendPosition("seek") goes out behind it.
//
// The words matter more than the times. Half of the point of a list rather than
// a sentence is that they read the book's own sentence and recognise it — but a
// place they have not reached yet cannot show its words, or its chapter title
// ("How Ginger Died" is as much of a spoiler as the paragraph under it), so
// those rows say only when they are and that they are ahead, and offer a press
// to find out more.
//
// Going somewhere and finding out what is there are different decisions, and a
// row is two targets rather than one: the reading, which is the whole left of
// the row, and `goto`, which is a pill on the right. Which of the two is the
// bigger one is the ruling this list turns on. It used to be the jump — the row
// itself was the button and the reveal was a small dashed thing under it — and
// that is the wrong way round for a screen read at 2am. The press wanted most
// often is "what is there?", it is the one that can be taken back, and the one
// that cannot be taken back is the one that should have to be aimed at. So the
// reveal is the row and `goto` is the pill beside it. Nothing about that
// changes what either press does: revealing still moves no playback and tells
// nobody, and it is still not possible to arrive somewhere by asking what is
// there.
//
// What the design asked for and this list does not have: a reason per row
// ("most likely · fits what you said") and a source per row ("you paused here,
// awake", "sleep timer faded out here"). The agent returns neither and there is
// nowhere in somnia either could be read from, so neither is drawn. A list of
// places is the one screen on this page where a plausible sentence nobody has
// evidence for is a lie a thumb then acts on.

// The offer currently on screen, or null. It holds the only copy in the page of
// the words of a place they have not heard yet, which is why it is a variable
// and not a rendered thing: those words are never written into the DOM until
// the reveal press, never logged, never passed to say(), and are gone from the
// page entirely the moment the list closes.
//
// It used to be the only copy anywhere, and the comment here used to say so — a
// page discarded with the list up came back with no list, and asking again was
// one press. Asking again is a question put to a model over a tailnet at 2am,
// which is the thing this page exists to spare somebody, so the list is written
// down as well now: see PLACES_KEY below. What closes still forgets what was on
// the screen; what a night keeps is the answer, not the overlay.
let offered = null;

// The last places somnia offered, kept where a discarded tab cannot take them.
//
// Places is the set of places from the last query and nothing else. It is not a
// store of pause points or fade points: somnia already produces exactly this
// list, once, in answer to a question asked in the dark — and until now it
// lived as long as the overlay did, so getting back to the third of four places
// meant asking the same question again.
//
// localStorage, beside the sleep timer and the dim level, and for the same
// reason as the timer: the tab is the thing that does not survive the night. A
// backgrounded page is discarded whenever the phone wants the memory back, and
// the list went with it.
//
// One entry, carrying the gid of the book it is about. A list about a book that
// is not the one open is no places at all — which is what keeps this from
// growing without bound, and what keeps the screen scoped to the book somebody
// is listening to.
//
// It holds the words of places they have not heard yet, and that is worth
// saying out loud. Those words came down with the answer, to this phone, on
// this night; what changes is that they now rest in a key between sessions
// rather than dying with the tab. No new exposure — same device, same answer —
// and whether they ever reach the screen is still the reveal press's decision
// and nobody else's.
const PLACES_KEY = "somnia-places";

// What would be put back on the screen, or null. `offered` is what is on it
// now: the two are the same list while Places is up, and different the moment
// it closes, because closing forgets the screen and this outlives the night.
let remembered = null;

// `start over` throws away the conversation, and the places are an answer to a
// question in it — so they go with it. The comment over startOver draws the line
// this side of: the questions, not the night. The book keeps playing, keeps its
// position and keeps its timer; what is forgotten is everything that was said.
//
// Without this the position line goes on saying `4 places found` after the
// server has been told to forget the question that found them, and pressing it
// opens a list somebody can no longer see the reason for. That is not the same
// case as a confident move, which leaves the list standing on purpose: there the
// conversation is still there to explain it.
function forgetPlaces() {
  remembered = null;
  drawPlaces();
  try {
    localStorage.removeItem(PLACES_KEY);
  } catch (error) {
    console.error(error);
  }
}

function rememberPlaces(list) {
  remembered = list;
  // The position line says how many places there are, and this is the moment
  // there is a different number of them. Waiting for the next pass of
  // drawPlayer would be waiting for the book to play: a page that was only ever
  // opened to ask a question is paused, so nothing else would come, and closing
  // the screen would leave the line saying nothing about the list behind it.
  drawPlaces();
  try {
    localStorage.setItem(PLACES_KEY, JSON.stringify(list));
  } catch (error) {
    // Storage refused, or is full. Places is a convenience over a question that
    // can always be asked again, so nothing else here has to care.
    console.error(error);
  }
}

// What the last page to be alive put in front of somebody. Anything else in
// that key reads as no places rather than as a reason to throw: this runs at
// boot, before there is a screen to say anything on, and the one thing the page
// opening at 2am has to do is open.
function restorePlaces() {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(PLACES_KEY) || "null");
  } catch (error) {
    console.error(error);
  }
  if (!saved || typeof saved.gid !== "number") return;
  if (!Array.isArray(saved.places) || !saved.places.length) return;
  // Every row is drawn out of these three and a press acts on the first of
  // them, so a record missing any one is a screen of rows reading "Ch NaN" with
  // a goto that seeks to nowhere.
  const whole = saved.places.every(
    (place) =>
      place &&
      typeof place.start_ms === "number" &&
      typeof place.chunk_id === "number" &&
      typeof place.chapter_idx === "number",
  );
  if (whole) remembered = saved;
}

// The remembered list, but only where it is about the book that is open. A list
// about another book is not a wrong list to draw, it is the answer to a
// question about somewhere else, and there is nothing on the position line that
// could say so.
function placesHere() {
  return remembered && gid !== null && remembered.gid === gid
    ? remembered
    : null;
}

// The way back to the last query's places. It goes through showCandidates, the
// same path the answer that first raised them took, because a list restored
// straight into the DOM would be markup: the words of a place they have not
// reached are held in a closure by candidateRow, and chooseCandidate acts on
// `offered` rather than on rows — so a screen built any other way would look
// right and do nothing when pressed.
//
// Nothing here refreshes anything, and a stale `ahead` flag is why that is
// safe. The server decided it against its own mark when the offer was made, and
// that mark only ever rises: a place stored as ahead may since have been
// listened to, and one stored as heard can never have become unheard. So age
// can only over-warn, which costs a press — and the other direction is the one
// thing this page must never do.
function showRemembered() {
  const list = placesHere();
  if (list) showCandidates(list);
}

// The position line, which is the way in when there is anywhere to go and a
// plain readout when there is not.
//
// `disabled` on the nights there are no places, and that is the whole of the
// argument for putting this on a line that already exists rather than giving
// Places a control of its own: after a cold launch on a book nobody has asked
// about there is nothing to open, and a line wearing a rule and a target that
// answered a press by doing nothing is worse in the dark than no way in at all.
// The rule and the count are drawn from the same number, so "does it look
// pressable?" and "is there anything to press?" cannot come apart.
//
// The count is emptied as well as hidden, for the reason the toast is: "is
// anything being offered?" gets one answer and not two that can disagree.
function drawPlaces() {
  const list = placesHere();
  const found = list ? list.places.length : 0;
  // One place is not counted as though there were more, which is the rule the
  // screen this opens already follows: it is the same list said in fewer words.
  const said = found ? `${found} ${found === 1 ? "place" : "places"} found` : "";
  placesFound.textContent = said;
  placesFound.hidden = found === 0;
  placesOpen.disabled = found === 0;
  placesOpen.classList.toggle("openable", found > 0);
  // The same sentence, on the morning screen's first choice, out of the same
  // number and literally the same string. The design has had this wrong twice —
  // a chat pill saying "see all 7 places" over a player line saying "4 places
  // found" over a list of four — and both times it was a count worked out in two
  // places. There is one here.
  wakeFound.textContent = said;
  // And on the mornings there is nothing to open, the choice is not drawn at
  // all. Places is the last query's answer and nothing else, so on most mornings
  // that list is empty; the position line can afford to sit there disabled
  // because it is a readout either way, and a 92dp amber slab at the top of the
  // morning cannot. What is left is two choices, the first of which is how the
  // list gets made in the first place.
  wakePlaces.hidden = found === 0;
}

// Pressed, it puts the last query's places back on the screen. It is the same
// screen an answer raises and every way out of it is the one that was already
// there — including close, which now leaves the count standing behind it,
// because the places did not stop existing when the screen was put away.
placesOpen.addEventListener("click", showRemembered);

// Whether cancel owes the page a tap-to-resume listener, because showing the
// list took one away. See cancelCandidates.
let rearmOnCancel = false;

// Where the book is on this book's clock, read once per list and then written
// into it — showCandidates stamps `here_ms` from this and every later rendering
// uses the stamp. So this answers "where are they now", and the list answers
// "where were they when they asked", and those stopped being the same question
// the moment the rule became something to press.
//
// It is drawn into the list so that a glance says which rows are behind them
// and which are ahead. That is the whole point of the row: "ahead" as a word is
// a claim, and a time among other times is something anyone can check.
//
// For the book that is open it is this page's own number, because the page is
// the player and the server's copy is up to fifteen seconds stale; for a book
// that is not, it is whatever the server last wrote down. Null means nobody has
// ever started that book, and then there is no row at all — "never started" and
// "at 0:00:00" are different answers, and only one of them would be true. A
// book that is open but untouched reads 0:00:00 here, which is what the clock
// under the transport says as well, so at worst the two agree.
function hereTime(list) {
  return list.gid === gid && manifest ? positionMs : list.position_ms;
}

function chapterLabel(place, { title }) {
  const chapter = `Ch ${place.chapter_idx + 1}`;
  // Ingest numbers chapters from one and so does everybody counting them; the
  // index in the row is zero-based. A book whose chapters were never titled
  // gets the number and nothing else rather than a trailing separator.
  const parts = [chapter];
  if (title && place.chapter_title) parts.push(place.chapter_title);
  if (place.ahead) parts.push("ahead");
  return parts.join(" · ");
}

// What the list is, said in one line above it, and out of nothing but the
// payload that drew the rows. It counts what is on the screen and names the
// first and last time on it — no denominator, because somnia has no idea how
// many places in this book would have fitted the question, and "4 of 7" with a
// 7 nobody counted is a number that would be read and believed.
function candidatesSummary(places) {
  if (!places.length) return "";
  const first = timestamp(places[0].start_ms);
  if (places.length === 1) return `1 place, at ${first}`;
  const last = timestamp(places[places.length - 1].start_ms);
  return `${places.length} places between ${first} and ${last}`;
}

// The press that uncovers a row's words, and the press that puts them back.
// One function because both rows on this screen that have words to hide have
// to hide them the same way: the invitation is worded here, the state lives in
// one class, and a row that drifted from the other would be two controls that
// look identical and answer differently.
//
// It used to be a one-way door, and the argument was that a reveal which
// toggled is a control whose meaning depends on how many times it has been
// pressed, read by somebody who is not counting. What that argument missed is
// that the row itself says which press it is about to be — the line under the
// words reads "tap to hide" once they are up — so nobody has to count anything;
// they read it. And a screen that can only ever grow is the wrong shape for
// this one: four places with their passages open is the column of book at 2am
// that this list exists to spare somebody, and until now the only way to fold
// one back was to close the whole screen and open it again.
//
// `shut` is remembered from the hint the row arrived wearing rather than
// recomputed, so the row that warns goes back to warning and the row that does
// not goes back to not — the guard is never re-derived at the moment it is
// being put back, which is the one moment it could be got wrong.
//
// `words` is a function and not a string because the "you are here" row learns
// its words after it is built: the press has to read whatever is in hand when
// it happens, and a row with nothing in hand does not get a press at all.
function reveals(li, show, what, hint, { words, open, shut }) {
  const closed = hint.textContent;
  show.addEventListener("click", () => {
    if (li.classList.contains("revealed")) {
      // Not merely hidden. The words go out of the document the way they came
      // in, which is what the covered state has always meant on this screen —
      // see candidateRow: text a screen reader, a selection or a screenshot can
      // still reach is text that was never really put away.
      what.textContent = "";
      what.hidden = true;
      hint.textContent = closed;
      li.classList.remove("revealed");
      shut?.();
      return;
    }
    what.textContent = words();
    what.hidden = false;
    // The offer has been taken. What the line says now is how to undo it, in
    // the same place the invitation was — and never the warning again, because
    // whatever it was going to cost has already been spent.
    hint.textContent = "tap to hide";
    li.classList.add("revealed");
    open?.();
  });
}

function candidateRow(place) {
  const li = document.createElement("li");
  li.className = place.ahead ? "candidate ahead" : "candidate";

  // Everything known about the place, and the whole left of the row. Every row
  // is a button now, because every row has something to ask for.
  //
  // It used to be a button only on the places ahead of them, and the argument
  // was that a target which answers a press by doing nothing is worse in the
  // dark than no target: behind the mark the words leak nothing, so they were
  // simply printed and there was nothing left to press for. That reading of the
  // design was too narrow. "Text stays hidden until you ask for it" is a rule
  // about the list, said once in the subhead over all of it, and half a list
  // obeying it is a screen with two kinds of row that look like one kind.
  //
  // What is bought is not privacy on the heard rows — there is none to buy —
  // but a list that can be read at all. Four places with their passages printed
  // is four paragraphs of book in a column at 2am, which is the thing somebody
  // opened this screen to avoid reading; four times and four chapters is a list
  // you can look down. The words are one press away on the row you actually
  // mean, and that press is now how this screen is read rather than a warning
  // gate on the half of it that could spoil something.
  const show = document.createElement("button");
  show.type = "button";
  show.className = "candidate-show";
  show.id = `candidate-show-${place.chunk_id}`;

  // Nothing on this row sits beside anything else. A time, a chapter and a
  // pill shared one line until this pass, and at 360dp that line could not hold
  // them: the chapter was cut to "Ch 2 · 02 The Hu…" on the row whose name was
  // the point, and the words underneath were squeezed into the column left over
  // beside the pill and clipped mid-sentence. Each is its own full-width line
  // now, so the only thing deciding where a chapter's name ends is the chapter's
  // name.
  const when = document.createElement("p");
  when.className = "candidate-when";
  when.textContent = timestamp(place.start_ms);

  const where = document.createElement("p");
  where.className = "candidate-where";
  where.textContent = chapterLabel(place, { title: !place.ahead });

  const what = document.createElement("p");
  what.className = "candidate-what";
  // Every row starts with nothing in it at all — not hidden text, no text.
  // Held in the closure below instead, so that a screen reader cannot read it
  // out, a selection cannot catch it, a screenshot cannot contain it and a
  // scroll cannot bring it into view.
  //
  // On the rows ahead of them that is the spoiler guard and the reason the
  // closure exists; on the rows behind them it is the same mechanism used for a
  // smaller reason, and it is used rather than merely imitated with CSS on
  // purpose. Two ways of not showing text on one list — one that withholds and
  // one that only hides — is one refactor away from the withholding row being
  // rewritten to match the hiding one, by somebody who can see they do the same
  // thing on a screen. They do not.
  what.hidden = true;

  show.append(when);
  show.append(where);
  show.append(what);

  // What pressing offers, on every row, and it says two different things. Both
  // are an invitation to read; only one of them is a warning, and after this
  // change that difference is the only thing making an `ahead` row look
  // different from a closed row it is safe to open. So the words differ and the
  // colour differs: cream at .3 is the list telling you how it is read, amber
  // is the row telling you what the press will cost. Amber because on this page
  // amber is the warm thing and a warning is one, and said in the row rather
  // than under the list, because whether the words are worth uncovering is a
  // question about this place and not about the screen.
  const hint = document.createElement("p");
  hint.className = "candidate-hint";
  hint.textContent = place.ahead ? "tap to reveal · may spoil" : "tap to reveal";
  show.append(hint);
  // Six writes to this row's own DOM and nothing else in the whole page: no
  // request, no seek, no report, nothing touched that the spoiler guard
  // measures. The words came down with the answer and were already in hand,
  // which is why there is no endpoint here to fetch them from — a general
  // /api route handing back unheard book text for any chunk id would be a
  // spoiler oracle one guessed integer wide, sitting there for the life of
  // the deployment, and it would put a tailnet round trip on the one press
  // where a control that does nothing for three seconds reads as broken and
  // gets pressed again — with a list on screen, into a row.
  reveals(li, show, what, hint, {
    words: () => place.text,
    // The title arrives at the same press and never before it on a row ahead of
    // them, where the chapter's own name is itself a spoiler. On a row behind
    // them it was already there and this writes it again unchanged: one path
    // through the reveal rather than two, because the branch would be a branch
    // on the guard.
    //
    // And it goes back with the words. A hide that left the chapter's own name
    // standing would be a row that had been half un-revealed — the press says
    // "put that away", and half of what it was asked to put away is the name.
    open: () => {
      where.textContent = chapterLabel(place, { title: true });
    },
    shut: () => {
      where.textContent = chapterLabel(place, { title: !place.ahead });
    },
  });
  li.append(show);

  // The other target, and the last line of the row: the press that cannot be
  // taken back, on its own line, ranged right.
  //
  // It used to sit beside the reading rather than under it, and the argument
  // for that was that nothing else was then in the column a low miss would fall
  // into. That is no longer true and was not kept: the reading is the full
  // width of the row now, so its bottom edge is this pill's top edge, and a
  // reach for the words that lands low lands here. It is a deliberate trade for
  // the row being legible at all — the alternative was the chapter's own name
  // truncated and the book's own words clipped, on the screen whose whole
  // promise is that the words are the book's.
  //
  // What is still true is the fall from one row's pill to the next: 42px of
  // list that listens for nothing, which is `.candidate`'s padding either side
  // of the hairline. That is the miss that moves the book to the wrong place;
  // this one only moves it to the place they were already reading about.
  const go = document.createElement("button");
  go.type = "button";
  go.className = "candidate-go";
  go.id = `candidate-go-${place.chunk_id}`;
  // Not "jump": at this size and in this position "jump" reads like the ±30
  // below, and this moves the whole book.
  go.textContent = "goto";
  go.addEventListener("click", () => chooseCandidate(place));
  li.append(go);
  return li;
}

// The rule drawn across the list at the point they have got to — and a place
// now, which is the one place on this screen that goes nowhere new.
//
// It was a rule and nothing else for a long time, and the argument was that the
// listener's position is not a mark in this list: the places are search hits,
// so where they are is normally between two rows and inside none, and the
// design's `here` — a row of the list wearing the word — assumes a partition
// that somnia's four results do not make. That is still true of the *ordering*
// and it is why the rule keeps a line of its own. It was never a reason for the
// row under the rule to be shaped differently from every other row on the
// screen, which is what it had become: a list of times you can read down, and
// then the one entry that is about you, in type too small to read.
//
// So it is a place now, drawn the way places are drawn — the time large and
// first, the words one press away, the pill at the foot ranged right — and the
// only things that mark it out are its own: the label on the rule above it, and
// amber on the two things a thumb goes for.
//
// What the pill is for is the move before it. Press a place, hear it is the
// wrong one, press `here`: it is the way back, and the only one there is, since
// the position it discarded is not written down anywhere else and finding it
// again means asking a model the same question over a tailnet. That is the
// whole of why the time it holds is frozen — see showCandidates. A `here` that
// followed the playhead would name the place the last press landed on, and
// pressing it would be a no-op offered as an undo.
//
// `more` is whether there is anything under the rule. The sentence beneath it
// is about what follows it, and printed with nothing following, it would be a
// warning about an empty screen.
function hereRow(list, ms, { more, back }) {
  const li = document.createElement("li");
  li.className = "candidate here";
  li.setAttribute("aria-current", "true");
  // The label on the rule, and only the label now. The time came out of it in
  // the same change that gave this row a time of its own at the size every
  // other row states its time in — one line saying it twice, once at 9px, was
  // the old row's whole problem in one string.
  const mark = document.createElement("p");
  mark.className = "section-label here-mark";
  mark.textContent = "you are here";
  li.append(mark);

  // The reading, in the shape candidateRow builds it: the same classes, so the
  // sheet has one rule for a time on this screen and one for a passage, and the
  // wash under a press is the same wash.
  const show = document.createElement("button");
  show.type = "button";
  show.className = "candidate-show";
  show.id = "candidate-show-here";

  const when = document.createElement("p");
  when.className = "candidate-when here-when";
  when.textContent = timestamp(ms);

  const what = document.createElement("p");
  what.className = "candidate-what";
  what.hidden = true;
  show.append(when);
  show.append(what);

  // The invitation, and it arrives late or not at all — which is why it starts
  // hidden and why the press is wired at the same moment it appears.
  //
  // Every other row on this screen carries its words down with the answer that
  // named it. This one names no passage, so its words have to be asked for, and
  // a control that is on the screen before there is anything behind it is a
  // control that does nothing at 2am — pressed again, and again, into a list.
  // So there is no offer until the words are in hand: until then this row is
  // exactly what it was before any of this, a time and a way back.
  //
  // Never the warning wording. What is at `here` is by definition the last
  // thing they heard, and /api/passage cannot hand back anything further on
  // than that however it is asked — see Player.passage_at.
  const hint = document.createElement("p");
  hint.className = "candidate-hint";
  hint.textContent = "tap to reveal";
  hint.hidden = true;
  show.append(hint);
  li.append(show);

  // Asked for now, read at the press. The round trip happens while the list is
  // being looked at rather than while a thumb is waiting on it, which is the
  // same trade the smart-rewind sentence makes: fetch it while the connection
  // is warm and hold it for later.
  hereWords(list).then((text) => {
    if (!text) return;
    hint.hidden = false;
    reveals(li, show, what, hint, { words: () => text });
  });

  // Drawn as a `goto` and not as anything of its own: it sits in a list where
  // every other row's press is a seek, and a press that seeks has one shape on
  // this screen. What is different is the word and the colour — `here` in
  // amber, which is the design's own marking for the current row and is doing
  // the work of saying this one is not a move outward.
  //
  // Only on a list about the book that is playing. On a list about another
  // book, `here` is that book's own stored position — a place they are not, in
  // a book they cannot hear — and a press would be a book switch wearing the
  // word "here". The rule is still drawn there, because where they are in that
  // book is what makes the rest of the list legible; it is only not a target.
  if (back) {
    const go = document.createElement("button");
    go.type = "button";
    go.className = "candidate-go here-go";
    go.id = "candidate-go-here";
    go.textContent = "here";
    go.addEventListener("click", () => returnHere(ms));
    li.append(go);
  }

  // The sentence the whole screen is arranged around, and the last thing in
  // this row rather than the first.
  //
  // It sat directly under the mark until the rule became a place, which is
  // where the design puts it and where it belonged while there was nothing
  // between it and the rows it warns about. There is now: a time, an offer of
  // words and a pill, all of them about a moment they have certainly heard. A
  // warning with its own counter-example printed underneath it is a warning
  // read wrongly at 2am — the amber time directly beneath it is precisely the
  // one thing on this screen it is not about.
  //
  // Last, it is the line immediately above the first row it is true of, which
  // is what it always meant.
  if (more) {
    const caveat = document.createElement("p");
    caveat.className = "here-caveat";
    caveat.textContent = "anything below this line you may not have heard";
    li.append(caveat);
  }
  return li;
}

// The words at the point the rule is drawn, fetched once per list and then kept
// in it.
//
// Kept in the list rather than in a variable beside it because the list is what
// outlives the screen: it goes into localStorage with everything else the last
// question turned up, so a second opening of the same places — after the phone
// has thrown the tab away, on a tailnet that is now asleep — has the words
// already and asks nothing. That is the same promise every other row on this
// screen makes, arrived at a different way.
//
// Storing them is not a new exposure. These are words the sound has already
// said out loud in this room; the route cannot return any others.
//
// Null on anything that is not a passage: no such book, a book whose text was
// never indexed, a book nobody has played a second of, or a tailnet that did
// not answer. Every one of those is the same answer to the row — there is
// nothing to offer — and none of them is worth a message on a screen somebody
// opened to find their place.
async function hereWords(list) {
  if (typeof list.here_text === "string") return list.here_text;
  try {
    const response = await fetch(`api/passage/${list.gid}/${list.here_ms}`);
    if (!response.ok) return null;
    const body = await response.json();
    if (typeof body.text !== "string" || !body.text) return null;
    list.here_text = body.text;
    // Written down where the rest of the answer already is, so the next opening
    // of these places is as offline as this one was not.
    if (remembered === list) rememberPlaces(list);
    return body.text;
  } catch (error) {
    console.error(error);
    return null;
  }
}

// The way back, and the only press on this screen that ends where it started.
//
// It is the same three steps a row's `goto` takes and in the same order — the
// list goes first, so nothing can leave a screen of places over a book that has
// already moved — and it needs none of what that one guards against: `ms` is a
// position this page has already played through, so it cannot be past a
// frontier the manifest has not caught up with, and there is no other book to
// open.
//
// The toast says what happened rather than where it went. A time is what every
// other press here reports, and it would be a strange thing to read after a
// press whose whole promise is that nothing has changed.
//
// It is the same sentence stepBack says, because they are the same act reached
// two ways: this one is the way back that is still there in the morning, found
// by opening the list again, and stepBack is the one offered for six seconds
// beside the press it undoes. The row can undo a `goto` made an hour ago; the
// toast can undo one made while the thumb is still on the screen.
function returnHere(ms) {
  if (!offered || offered.gid !== gid || !manifest) return;
  closeCandidates();
  seekGlobal(ms, { play: true });
  toast("back where you were");
}

function showCandidates(list) {
  offered = list;
  // Where they were when they asked, written into the record the first time
  // this list reaches a screen and never touched again.
  //
  // It used to be computed on every rendering, and the comment on the rule said
  // so approvingly: the line goes where the book has got to tonight. That is
  // the right answer for a rule and the wrong one for a control, and it is now
  // both. The row's press exists to undo a `goto`, and a `goto` closes this
  // screen — so the only way to reach the press is to open the list again,
  // which under the old rule recomputed `here` as the place the `goto` had just
  // landed on. The one press that had to remember was the one that could not.
  //
  // Frozen, the whole screen is one photograph of the moment the question was
  // asked, which is what the rest of it already was: `ahead` was decided by the
  // server against its own mark at that moment and has never been refreshed
  // either. The cost is that the rule can be older than the sound — they may
  // have listened past a row that still sits below the line — and that is the
  // direction this list is allowed to be wrong in. It over-warns. It cannot
  // print a sentence somebody has not heard.
  //
  // Unstamped rather than stamped with a lie when there is no number: a book
  // nobody has ever started has no position, and "never started" and "at
  // 0:00:00" are different answers. A record written by a page older than this
  // one arrives without the field and is stamped on its first showing, which is
  // exactly the old behaviour, once.
  if (typeof list.here_ms !== "number") {
    const at = hereTime(list);
    if (typeof at === "number") list.here_ms = at;
  }
  // Written down here rather than where the answer arrives, so that what a
  // night remembers is what was actually put in front of somebody: an answer
  // that knew where they meant moved the book and offered nothing, and it
  // leaves the last real list standing.
  rememberPlaces(list);
  candidateList.replaceChildren();

  // Which book, but only when it is not the one playing.
  const elsewhere = list.gid !== gid;
  candidatesBook.textContent = elsewhere ? `in ${list.title}` : "";
  candidatesBook.hidden = !elsewhere;
  summaryLine.textContent = candidatesSummary(list.places);

  const rows = list.places.map(candidateRow);
  const here = list.here_ms;
  if (typeof here === "number") {
    // Spliced in among them in book order, which is the only arrangement that
    // answers the question the list is for without reading a word: everything
    // below this line has not happened yet. The server sorted the places; this
    // is the one row the page decides the place of, and it lands where the
    // stamped time puts it — so the rule sits among the same rows on every
    // showing of this list, however long the book has run between two of them.
    const at = list.places.findIndex((place) => place.start_ms > here);
    const mark = at < 0 ? rows.length : at;
    rows.splice(
      mark,
      0,
      hereRow(list, here, {
        more: mark < rows.length,
        // Pressable only where going there means anything: the book this list
        // is about is the book making the sound. See hereRow.
        back: list.gid === gid && Boolean(manifest),
      }),
    );
  }
  for (const row of rows) candidateList.append(row);

  candidates.hidden = false;
  // Giving focus up, never taking it. Half the screen being keyboard is how the
  // close button ends up somewhere a thumb cannot reach. Nothing here calls
  // focus() on anything: this page does not move the cursor around under people.
  //
  // Through the named way back rather than a bare blur(), because what this
  // press really is is an arrival on the player with a list over it. The old
  // comment here said the keyboard is up on exactly the turns that produce a
  // list, "they just typed a question" — which was never true of the microphone,
  // and that is how this list came to sit over two different screens depending
  // on how the question was asked. Typed, the blur landed on the player by
  // accident; spoken, there was no focus to give up and the list stood over the
  // conversation. Now it is one screen either way, which is also what makes
  // `close` answerable: it changes nothing, so it leaves them wherever the list
  // was raised over, and that has to be somewhere that does not depend on
  // whether they used their voice.
  backToTheBook();
  // A book waiting for a touch before it will make a sound would otherwise
  // start on the first press anywhere on this overlay — a row, a reveal, or
  // cancel. Cancel especially: the one control that promises to change nothing
  // would have started the night. Taken off while the list is up and given back
  // by cancel, which is the only way out that leaves the page as it found it.
  rearmOnCancel = tapToResume !== null;
  disarmTapToResume();
}

// The inert close. Everything that takes the list down goes through here, and
// it does nothing but forget: no seek, no report, no request, nothing said, and
// nothing touched that the spoiler guard or the sleep timer can see.
function closeCandidates() {
  candidates.hidden = true;
  // The rows, and with them any words a reveal press put on the screen.
  candidateList.replaceChildren();
  // The line that counted them goes with them. It is only times and a number,
  // but a subhead left standing over an empty list is the page describing
  // something that is not there.
  summaryLine.textContent = "";
  // And the words it did not: the only other copy in the page.
  offered = null;
}

// Cancel, and only cancel. It is three assignments and at most one listener put
// back, and that is the whole of it: no move, no report, no seq bump, no write
// to Audiobookshelf, and nothing said on the status line.
//
// The button says `close` now and this still is the cancel. `cancel` was the
// word while the list read as a question with an answer owed; it is a screen of
// places now, and a screen is left rather than called off. Nothing under the
// word changed — it is still the one way out that gives back the tap the list
// took, and still the only one that has to.
//
// What it deliberately does not undo, because none of it was the list's doing:
// a sleep fade running underneath keeps running, and if it finishes the book
// still goes quiet and still says goodnight — the night was already ending and
// a question about where to go did not change that, so putting the question
// away must not either. Nor does it give back the countdown, which has been
// running the whole time the list was up because the book was playing and they
// were listening to it. A list left up long enough ends the night by itself.
// That looks like a bug and is not one.
function cancelCandidates() {
  const rearm = rearmOnCancel;
  rearmOnCancel = false;
  closeCandidates();
  // True before the list went up and true again now: the book is still paused,
  // still waiting for a touch, and the line that said so was taken down with
  // the listener rather than left lying.
  if (rearm) armTapToResume();
}

candidatesCancel.addEventListener("click", cancelCandidates);

// A row is a seek somebody made, in the book they made it in.
async function chooseCandidate(place) {
  const list = offered;
  if (!list) return;
  // First, so that nothing between here and the seek can leave a list of places
  // over a book that has already gone to one of them.
  closeCandidates();
  // And the screen this list was raised over, which is the conversation whenever
  // the question that raised it was asked out loud — the microphone takes no
  // focus, so nothing about it ever put the page back on the player. `goto` is
  // the one press on this list that moves the book, so it is the one press that
  // owes them the sight of it: without this the seek lands behind a transcript,
  // and the only evidence a nine-hour book went anywhere is a toast.
  //
  // Before the seek rather than after, so that the same press cannot be two
  // frames — the book moving on one and the screen catching up on the next.
  backToTheBook();
  if (list.gid === gid && manifest) {
    // Where they are, read before anything is done about where they asked to
    // be. This is the whole of what `goto` throws away and the whole of what
    // the way back restores — taken here rather than after the refresh below,
    // because the book goes on playing across that await and what somebody
    // means by "back" is where they were when they pressed.
    const from = positionMs;
    if (place.start_ms > manifest.total_ms) {
      // The manifest is older than the render: this book grew while the page
      // was holding a photograph of it, and seeking would clamp them to the
      // frontier instead. Only in that case — an unconditional refresh would
      // put a network round trip in front of every press, which is the one
      // thing a transport action on this page never does. The seek happens
      // either way: a refresh that failed leaves them where the page thinks
      // the book ends, which is still nearer than not moving at all.
      await refreshManifest().catch(() => {});
    }
    seekGlobal(place.start_ms, { play: true });
    // On the line after the seek, and never on a timer. The design's prototype
    // waits ~900ms and then says this, which on a real page is a sentence that
    // can outlive what it describes: the agent can move the book by the other
    // route — the refusal of the next report — inside that window, and a toast
    // fired afterwards would be telling them about a press whose effect has
    // been overwritten. Said here it is true when it is written, or it is not
    // written.
    //
    // A receipt now, rather than the old "moved · playing". Both sentences are
    // true and only one of them is worth keeping: what the reader cannot see
    // is where nine hours of book have gone, and what they can already hear is
    // that it is playing. It names where it landed and not the row's own
    // `start_ms`, which are the same number except at the end of a book that
    // has grown — seekGlobal clamps, and a toast must not report a millisecond
    // the book was not taken to.
    toast(`moved to ${timestamp(positionMs)}`, () => stepBack(from, list.gid));
    return;
  }
  // Another book, which has had nothing written to it: `at` is what carries the
  // chosen place through the switch. If that book is still rendering, openBook
  // waits for its first chapter and the chosen place is lost — said plainly on
  // the status line rather than engineered around, because threading a position
  // through a wait that can last a quarter of an hour is a promise this page
  // cannot keep.
  try {
    await openBook(list.gid, { play: true, at: place.start_ms });
  } catch (error) {
    setStatus("couldn't reach that book");
    console.error(error);
    return;
  }
  // Hung off the book having really opened, for the same reason as above, and it
  // really can not happen: a book whose first chapter has not been rendered yet
  // comes back from openBook having changed nothing but the status line, and
  // the page is still on the book it was on. A time over a book that did not
  // move is the one thing a toast must never say.
  //
  // The same receipt and no way back. What this press overwrote is the other
  // book's own stored position, which openBook read and did not keep, so undoing
  // it means restoring a number this function was never handed — a different
  // piece of work from the one above, and one that has to reach into openBook to
  // get it. It is not built. Left as it is, this press is still recoverable the
  // way it always was: the position it replaced is a per-book number, and the
  // book they came from kept its own.
  if (gid === list.gid) toast(`moved to ${timestamp(positionMs)}`);
}

// The way back from a `goto`, and the shortest-lived control on the page.
//
// It is the same seek the row made, in reverse, and it needs none of what that
// one guards against: `ms` is a position this page was sitting at moments ago,
// so it is inside a manifest this page already holds and cannot be past a
// frontier the render has not reached.
//
// The book is checked anyway. Nothing should be able to reach this press after
// the page has changed books — openBook withdraws the offer — but the cost of
// being wrong about that is a seek to a millisecond that means nothing in the
// book it lands in, and the cost of the check is a line.
function stepBack(ms, book) {
  if (gid !== book || !manifest) return;
  seekGlobal(ms, { play: true });
  // What it did, rather than where it went. A second time on the screen would
  // read as a third move; this press is the one thing on the page whose promise
  // is that nothing has changed, and it is the same sentence the `here` row says
  // for the same reason.
  toast("back where you were");
}

// Told once, as the page dies. fetch does not survive teardown — the document
// is gone before the connection is made — but a beacon is the browser's promise
// to deliver after the page has stopped existing. It is JSON in a Blob because
// that is the only way to give a beacon a content type, and it can read no
// reply at all, which is the other reason a refusal is a 200 with a body.
//
// Nothing can tell this page the beacon landed, so the playback it carries
// stays owed. A page that dies here never sends it again; a page frozen and
// then restored sends it twice, which is the cheaper way round — a stretch
// counted twice lets a jump of a few seconds through once, and a stretch
// dropped leaves the mark behind the position for the rest of the book.
window.addEventListener("pagehide", () => {
  if (untouched || !manifest || gid === null) return;
  const body = JSON.stringify(positionBody("unload"));
  navigator.sendBeacon?.(
    "api/position",
    new Blob([body], { type: "application/json" }),
  );
});

document.addEventListener("visibilitychange", () => {
  // Backgrounded, which on a phone is most of the night. Say so now: from here
  // on the page can be frozen or discarded without warning, and this is the
  // last moment a normal request is certain to be allowed out.
  if (document.visibilityState === "hidden") {
    sendPosition("hidden");
    saveSleep();
    // Nobody is looking at the books panel either, and a poll in a pocket is
    // both throttled to uselessness and a radio wake beside somebody asleep.
    stopQueuePoll();
    return;
  }
  // Back in front of them, and the phone may have been asleep for hours.
  //
  // If a fade happened while it was, this is the morning: the page is here to be
  // looked at and the last thing it did was go quiet by itself. The tab
  // surviving the night is luck rather than a different night — the ordinary
  // case is a relaunch, which is the boot path — and which of the two happened
  // is not something the reader can see, so it must not be something the app
  // draws differently.
  raiseTheMorning();
  // Two things could have changed while nothing here was running: the network,
  // and the book — a render that was three chapters in when the screen went off
  // can be twenty by now. Both are cheap to ask, and neither answers by itself.
  tryAgainNow();
  if (!awaiting && manifest?.status === "rendering") {
    refreshManifest().catch((error) => console.error(error));
  }
  // And whatever screen they left up is as old as the sleep was. Asked now
  // rather than in five seconds, for the same reason as the two above: coming
  // back to the app is the moment somebody is looking, and for the shelf it is
  // one of only two such moments.
  //
  // The screen in front is the one asked, and only that one. Workshop being up
  // means Books is up behind it — it is an overlay over Books, not a route away
  // from it — so `!queuePanel.hidden` is true on both screens and on its own it
  // would fetch the shelf every time the phone came back to Workshop, for a
  // list nobody can see under the screen they are looking at. Books has no
  // queue on it and Workshop has no shelf, so each screen asks for its own one
  // thing and neither asks for the other's.
  if (!queuePanel.hidden && workshop.hidden) askForTheShelf();
  if (!workshop.hidden) pollQueue();
});

// `play` is false at boot and true only when the agent has just moved this
// book: opening the app at 2am to ask a question must not start the book, but
// being taken to a passage in a book that was not even open must.
//
// `at` is where in that book to land, and it exists for exactly one caller: a
// candidate chosen in a book that is not the one open. Everywhere else the
// position comes from the manifest, because by the time openBook is called the
// server has already written it — follow() gets away with opening a book and
// applying nothing for precisely that reason. A chosen row has had nothing
// written anywhere, so without this it would land wherever that book was last
// left. It is applied before the source is loaded rather than seeked to
// afterwards: a seek onto an element whose src was assigned a moment ago finds
// readyState 0 and loads it a second time, which is two source assignments and
// the media notification built twice for one press.
async function openBook(id, { play = false, at = null } = {}) {
  const response = await fetch(`api/book/${id}`);
  if (!response.ok) throw new Error(`no book ${id}`);
  // Held to one side until it is known to be playable. Adopting it before the
  // check below left the element playing one book while every clock, seek and
  // boundary read another book's rows: the time said "of 0:00:00", locate()
  // threw on the next press of anything for the rest of the night, and the
  // chapter they were in ended with "that is the end of the book".
  const opening = await response.json();
  if (!opening.chapters.length) {
    // Rows but no audio: the book is still rendering, or the render died.
    // Whatever was playing is still playing, and still the book this page is
    // on, which is the only place left to be.
    if (opening.status === "rendering") {
      // The first chapter is minutes away. Left at that one sentence with the
      // player bar hidden, the page stayed that way for ever, on a book that
      // was playable a quarter of an hour later.
      awaitMore(id, { play });
    } else {
      // Nothing is running, so nothing is coming: the render died, or it never
      // started. Asking again all night would answer the same thing all night.
      stopAwaiting();
      setStatus("nothing to play yet");
    }
    return;
  }
  stopAwaiting();
  // This book is really being adopted now, so whichever book the list was drawn
  // against, it is not the one about to be open — and if it is, the position
  // those rows were drawn around is about to change. Either way the rows are
  // stale and the list goes with them.
  //
  // It is here and not at the top of the function on purpose. openBook is
  // called by the two ladders that ask again on a timer — the boot retry and
  // the wait for a book that is still being read — and neither of those is
  // somebody doing something. A page booted onto a rendering book holds no book
  // at all, which is exactly the state a list about some *other* book can be
  // raised in; from the top of the function, the five-second poll that found
  // nothing new tore that list out from under a thumb with nothing said, and
  // then did it again at ten seconds, and twenty, and on every unlock. A call
  // that adopts nothing must leave the screen alone, and a fetch that failed
  // must too.
  closeCandidates();
  // The way back goes too, and here rather than in seekGlobal below, because a
  // book switch does not always reach it: openBook sets the position itself and
  // hands it to loadSource. A position in the book they have just left is not
  // somewhere the undo can take them, and pressing it would move the wrong
  // book to a millisecond that means nothing in it.
  withdrawUndo();
  if (gid !== null && gid !== opening.gid) sendPartingPosition();
  // Another book, so another join, and it gets its own chance at it. Giving up
  // is a judgement about one concatenation; carried across, one book whose build
  // failed would have every book opened after it played a file at a time, and
  // the blink would outlive the reason for it by the whole night.
  //
  // The same book opened again is not that. This is called by the two ladders
  // that ask on a timer as well as by a thumb, and a page that forgot on each of
  // those would ask for a missing join over and over all night.
  if (gid !== opening.gid) {
    fellBackToChapters = false;
    joinsThatFailed = 0;
  }
  // Playback belongs to the book it happened in, and this page is starting
  // again from the server's own record of where that book is — which is what
  // the last report it took said, and so what the mark was raised to. Both
  // clocks restart together or neither does: carried across, the first report
  // of the new book would claim the last seconds of the old one as listening
  // in it, and thrown away without the position it goes with, the mark would
  // be left behind and refuse everything they played afterwards.
  playedTaken = playedMs;
  manifest = opening;
  gid = opening.gid;
  seq = opening.seq ?? 0;
  positionMs = at ?? opening.position_ms ?? 0;
  // Somebody chose this place, which is the same kind of act as a seek and is
  // worth writing down. Opening a book on its own is still not listening, so
  // this stays where it is rather than moving up to the top of the function.
  if (at !== null) untouched = false;
  playerBar.hidden = false;
  loadSource(locate(positionMs), { play });
}

async function openTheBook() {
  clearTimeout(bootTimer);
  bootTimer = 0;
  try {
    const response = await fetch("api/books");
    if (!response.ok) throw new Error("no book list");
    const listing = await response.json();
    const chosen = listing.last_gid ?? listing.books[0]?.gid;
    if (chosen === undefined) {
      // The state that most needs the panel, and the one with no book, no
      // manifest and no gid — so the nudge has to name the control rather than
      // relying on anything on the screen to be about a book. Two presses now
      // rather than one, and it says so: adding a book is Workshop's job, and
      // Workshop is behind Books.
      setStatus("nothing yet — press books, then Workshop, to add one");
      return;
    }
    await openBook(chosen);
    // Reached the server and got a book out of it, so the next thing to go
    // wrong starts its waiting again from the short end.
    bootDelay = RETRY_MIN_MS;
  } catch (error) {
    console.error(error);
    // The service worker serves the shell from cache when the server cannot be
    // reached — on purpose, and it is the right call — so what somebody lands
    // on here is a page that looks perfectly alive with no book in it. Said
    // once and never tried again, it stayed that way until they thought to kill
    // the app and open it afresh, and the 2am screen took away the pull to
    // refresh that was the one gesture that would have fixed it by hand.
    inTrouble("couldn't reach the book — trying again");
    bootTimer = setTimeout(openTheBook, bootDelay);
    bootDelay = Math.min(bootDelay * 2, RETRY_MAX_MS);
  }
}

// ------------------------------------------------------------------- books

// The second overlay, and the one that had to argue hardest for itself.
//
// A book gets added by asking — "add me Treasure Island" — and that still
// works and is still the shortest way to do it. What asking could never do is
// show the answer: a render takes hours, it happens in another process on
// another unit, and until now the only evidence that it was happening at all
// was whether the chapter count was still moving. So this panel exists to watch
// one, and to stop one, and to start one when somebody would rather point than
// speak.
//
// It also opens books now, which it did not, and that is a decision rather than
// a drift: ADR 3 said "the page opens the book they were last listening to;
// changing books is done by asking", and its amendment says what that sentence
// was really protecting against — browsing a library to find something new. The
// search at the foot of this panel is that, and it is still a separate act from
// tapping one of the three books you already have, which is what `on the shelf`
// is. A shelf row is a book whose position somnia has kept all along; the press
// makes it the most recent one and opens it where it was left.
//
// `reading now` at the top of it names the book the panel is standing over and
// offers it back, and that press is the play button pressed from up here rather
// than from behind. What both presses cost is that `close` is no longer the only
// way out, and the listener at the foot of this section has to give the borrowed
// tap-to-resume up rather than hand it back.
//
// It costs nothing when it is shut. No request is made before it is opened, its
// poll stops the moment it is closed or the phone goes in a pocket, and what it
// holds — the queue's rows, the last search, and the shelf — is forgotten by
// close rather than kept. So none of the six places that take the candidate
// list down has a twin here, and nothing else on the page has to know it
// exists. The one thing on it that can go stale under somebody is a shelf row
// for the book the agent has just moved them to, and that is dealt with by the
// press rather than by a redraw; see openShelved.
//
// And it is separate from the ladder that watches THIS book grow, on purpose.
// `awaiting`/`askForMore` conflate "has this book got longer" with "is the
// listener stranded", and when a status stops being 'rendering' they clear
// wantsSound and throw the sleep timer away. Sharing them would end somebody's
// night because a book they queued for tomorrow finished rendering.

// How often the panel asks, while somebody is looking at it. Five seconds is
// slow enough to be nothing on a tailnet and fast enough that a press feels
// answered — and it stops dead the moment nobody is looking, which is the part
// that matters at 2am.
const QUEUE_POLL_MS = 5000;

// How long the first press of `stop reading this` stands before the button
// forgets it was ever asked. Long enough to read the label and decide, short
// enough that a panel left open does not have a live stop on it.
const STOP_CONFIRM_MS = 5000;

// The two states a job can be stopped in, which are also the two that go in the
// top list. Everything else has already happened.
const QUEUE_LIVE = ["queued", "rendering"];

// What somnia already has, said as something to read rather than as a status.
// A book on 'pending' is a render that died or was stopped, and it is the one
// marked state that is still worth offering: retrying it was impossible until
// the queue existed, and it is now the ordinary way to pick a book back up.
const HAVE_WORDS = {
  done: "already here",
  rendering: "being read now",
  queued: "in the queue",
  pending: "part rendered",
};
const HAVE_ALREADY = ["done", "rendering", "queued"];

// Which library a result came from, named only when it is the second one.
// Every row saying "Project Gutenberg" would be a column of noise on a list
// where all four lines have to earn their place; an Australian book is the
// exception and reads as one. It matters enough to say because the two
// libraries clear their books against different countries' law — Australia's,
// which is not the law here — and because that is the whole reason a title
// missing from the other catalog can be found in this one.
const SOURCE_WORDS = { australia: "PG Australia" };

// Which stage a row is at, in one word, in the corner of the row. It is the
// design's status column, and there is one entry here for each state the queue
// actually has and not one more. In particular there is no "fetching text":
// the design drew a pipeline with a fetch step in it, and somnia's queue has no
// such state to report. A book whose text has not been parsed is still
// `rendering` to the server, and what it is doing is said in the line under the
// name, where it can be honest about not knowing the count.
//
// The word and the line under it are two different things on purpose. This says
// which stage the row is at and does not change while it is at that stage; the
// line says what is actually happening inside it — which chapter, how much can
// be listened to, whether anything has been heard from it in five minutes.
const JOB_STAGE = {
  queued: "queued",
  rendering: "narrating",
  done: "ready",
  failed: "failed",
  cancelled: "stopped",
};

let queuePoll = 0; // the wake this panel is waiting on, or 0 for none
let queueRows = []; // the last list the server gave us, drawn as it stands
let queueFound = []; // the last search, and what has since been done about it
// Every book somnia has, as of the last time somebody arrived at this panel.
// Not polled with the queue: a shelf changes when a render finishes, which is
// hours, and the queue changes while you watch it, which is why only one of the
// two is worth a request every five seconds.
let shelved = [];
// The progress hairline of each row that has one, kept by job id across
// redraws. The list is rebuilt from scratch every five seconds, and a bar
// created a moment ago has no width to move from — so a fill that was made
// fresh each time would jump, and the 500ms the design asks for would be a
// transition that never once runs. Reusing the element is the whole of what
// makes it slide.
let jobFills = new Map();
// Which stop control is asking for its second press, and the wake that will
// make it forget. It lives here rather than on the button because the list is
// redrawn under it every five seconds, and a confirmation that a poll can
// cancel is a confirmation that expires at random.
let stopArmed = null;
let submitting = 0; // one submit in flight at a time, by gid

// ------------------------------------------------------------ which voice reads it

// The roster comes from the server rather than being written down here, so the
// list this page draws and the list the server will accept cannot come apart —
// a pill offering a voice the route refuses is a press that does nothing. Asked
// for once and kept: it changes when somnia is deployed and not otherwise.
//
// null means "not asked yet or the ask failed", and that is a state with a
// deliberate behaviour rather than an error: with no roster the add press does
// what it always did and submits at once, and the render uses whatever the
// renderer is set to. A picker is the improvement; adding a book is the job.
let voiceRoster = null;
// Which gid has its picker open. One at a time, because two open pickers is two
// sets of pills on the same screen with one chosen in each, and the question
// "which voice will this book be read in" then has two answers on it.
let voicePicking = 0;
// The block itself, and the pills inside it, held rather than looked up. The
// page keeps hold of everything it has to redraw — jobFills does the same for
// the progress hairlines — because a query selector is a second description of
// a tree this file already built and can simply remember.
let voiceOpen = null;
let voicePills = [];
// The last voice chosen, kept in localStorage beside the dim level and the skip
// size and for the same reason: it is a fact about how this person listens, not
// about tonight. It is what the picker opens on, so the second book of an
// evening is two presses — open, add — and the choice is still in front of you.
const VOICE_KEY = "somnia-voice";
let chosenVoice = "";
// One element for every sample, made on the first press rather than at load:
// six Audio objects built for a screen nobody may open is six decoders held all
// night on a phone.
let sampler = null;

function restoreVoice() {
  try {
    chosenVoice = localStorage.getItem(VOICE_KEY) || "";
  } catch (error) {
    console.error(error);
  }
}

restoreVoice();

async function loadVoices() {
  if (voiceRoster) return voiceRoster;
  try {
    const response = await fetch("api/voices");
    if (!response.ok) throw new Error("no voices");
    const body = await response.json();
    voiceRoster = body.voices || [];
  } catch (error) {
    // Left null on purpose, and not retried on a timer. The press below falls
    // back to adding the book without naming a voice, which is exactly what
    // this page did before there was a choice.
    console.error(error);
    voiceRoster = null;
  }
  return voiceRoster;
}

// Which of the roster is in force. Not stored as an index: the roster can
// change under a page left open across a deploy, and an index would then point
// at a different voice than the one somebody chose.
function voiceInForce() {
  if (!voiceRoster?.length) return "";
  const kept = voiceRoster.find((voice) => voice.id === chosenVoice);
  // The first of the roster is the default, and the server's is the same one.
  // A stored voice that has left the roster is forgotten rather than sent: it
  // would be refused, and the refusal would arrive as the answer to a press
  // about a book, which is a confusing place to be told about a voice.
  return (kept || voiceRoster[0]).id;
}

// Play one sample, and stop whatever else was playing.
//
// The book is paused first if it is playing, through the app's own pauseHere so
// that the fade, the media session and the position report all see it happen —
// two things reading aloud at once is the one outcome worth any amount of care
// to avoid. It is deliberately not started again afterwards: resuming a book
// over somebody who is still choosing is worse than leaving the play button
// where they can find it, and the automatic version of that is where all the
// hard bugs in this file live.
function playSample(id, said) {
  if (!player.paused) {
    pauseHere();
    said.textContent = "the book is paused while you listen.";
  }
  if (!sampler) sampler = new Audio();
  sampler.pause();
  sampler.src = `voice/${id}.m4a`;
  sampler.play().catch((error) => {
    // A missing clip is not a reason to refuse the voice: the samples are
    // rendered by hand on the box that has Kokoro and committed, so a voice
    // added without one is the ordinary way this fails. The choice still works;
    // only the audition is gone.
    console.error(error);
    said.textContent = "no sample for that one — it will still read the book.";
  });
}

function drawVoicePills(said) {
  const inForce = voiceInForce();
  for (const pill of voicePills) {
    const chosen = pill.dataset.voice === inForce;
    // Said twice, once in amber and once in the accessibility tree, exactly as
    // the skip-size pills on Settings are: a reader who cannot see the amber
    // had a row of identical-looking buttons and no way to tell which of them
    // was already true.
    pill.classList.toggle("chosen", chosen);
    pill.setAttribute("aria-pressed", String(chosen));
    if (chosen) said.textContent = pill.dataset.says || "";
  }
}

function chooseVoice(id, said) {
  chosenVoice = id;
  try {
    localStorage.setItem(VOICE_KEY, id);
  } catch (error) {
    console.error(error);
  }
  drawVoicePills(said);
  // One press does both: it says which voice, and it plays it. Selecting and
  // auditioning are the same intention here — nobody presses a name they have
  // never heard in order to *not* hear it — and splitting them would put a
  // second press between somebody and the only information on the screen.
  playSample(id, said);
}

// The picker, built under the row whose press opened it.
//
// Under rather than over: it belongs to one book, and a book is a row. It is
// also why there is no cancel on it — the press that opened it closes it, so
// the way out is the control the hand is already on.
function voiceBlock(entry, button) {
  const block = document.createElement("div");
  block.className = "voices";
  block.id = `voices-${entry.gid}`;
  const label = document.createElement("p");
  label.className = "voices-label";
  label.textContent = "read in";
  block.append(label);
  const row = document.createElement("div");
  row.className = "voice-row";
  row.setAttribute("role", "group");
  row.setAttribute("aria-label", "Which voice reads this book");
  const said = document.createElement("p");
  said.className = "voices-note";
  voicePills = [];
  for (const voice of voiceRoster) {
    const pill = document.createElement("button");
    pill.type = "button";
    pill.className = "voice";
    pill.id = `voice-${entry.gid}-${voice.id}`;
    pill.dataset.voice = voice.id;
    pill.dataset.says = voice.says;
    pill.textContent = voice.name;
    pill.addEventListener("click", () => chooseVoice(voice.id, said));
    row.append(pill);
    voicePills.push(pill);
  }
  block.append(row);
  block.append(said);
  const confirm = document.createElement("button");
  confirm.type = "button";
  // Warm, and the only warm press on this panel besides picking a dead render
  // back up: by this point the book has been chosen and the voice has been
  // chosen, and this is the press that spends six hours of the box on both.
  confirm.className = "found-add again voices-add";
  confirm.id = `queue-confirm-${entry.gid}`;
  confirm.textContent = "add it";
  confirm.addEventListener("click", () => addBook(entry, button, voiceInForce()));
  block.append(confirm);
  drawVoicePills(said);
  return block;
}

function closeVoices() {
  if (sampler) sampler.pause();
  voiceOpen?.remove();
  voiceOpen = null;
  voicePills = [];
  voicePicking = 0;
}

// The add press. It opens the picker rather than submitting, except when there
// is no picker to open.
async function pressAdd(entry, button) {
  const open = voicePicking === entry.gid;
  closeVoices();
  if (open) return;
  // Claimed before the first await, not after it. The first press of the night
  // waits on a real fetch of the roster, and a thumb that presses twice inside
  // that wait used to get two blocks under the one row — the second overwrote
  // `voiceOpen`, so close could only ever remove one of them, and two buttons
  // were left answering to `queue-confirm-<gid>`.
  voicePicking = entry.gid;
  await loadVoices();
  // A press that landed during the fetch has taken the claim back. That press
  // was the one that closes this picker, so there is nothing left to open.
  if (voicePicking !== entry.gid) return;
  if (!voiceRoster?.length) {
    // No roster, so no choice to offer and nothing to wait for. This is the
    // whole of the page's behaviour before voices existed, and it is the right
    // fallback: the book is what somebody came here for.
    voicePicking = 0;
    await addBook(entry, button, "");
    return;
  }
  const li = document.getElementById(`found-${entry.gid}`);
  if (!li) {
    voicePicking = 0;
    return;
  }
  voiceOpen = voiceBlock(entry, button);
  li.append(voiceOpen);
}
// One shelf press in flight at a time, by gid. Not `opening`, which is what
// openBook already calls the manifest it is deciding whether to adopt — a
// module-level name shadowed inside the one function this guard wraps is a
// trap for whoever fixes the next thing in here.
let picking = 0;
// Whether close owes the page a tap-to-resume listener, because opening the
// panel took one away. Exactly the borrow cancelCandidates makes, for exactly
// the same reason: with the listener still armed the first press anywhere on
// this overlay starts the book, and close — the one control that promises to
// change nothing — is where a thumb goes first.
//
// `pick it up` is the one press that clears this instead of spending it: that
// press is itself the touch the platform was waiting for, so what close would
// hand back is a listener over a book that is already sounding.
let rearmOnQueueClose = false;
// And the same borrowing for Settings, which is its own flag rather than a
// share of that one because the two screens can be opened from different
// corners of different screens and a single flag would have one of them handing
// back a listener the other had already spent. Nothing on Settings starts the
// book, so unlike the panel's this is only ever spent by the way out.
let rearmOnSettingsClose = false;

function ordinal(n) {
  const tens = n % 100;
  const suffix =
    tens > 3 && tens < 21 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th";
  return `${n}${suffix}`;
}

// How much of a book can be listened to now, in the units somebody thinking
// about bedtime thinks in. Empty under a minute, because "0m read so far" reads
// as a stall and a render that has just started is not stalled.
function howMuch(ms) {
  const minutes = Math.floor(Math.max(0, ms) / 60_000);
  if (minutes < 1) return "";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours ? `${hours}h${String(rest).padStart(2, "0")}m` : `${rest}m`;
}

function bookName(row) {
  // A book that has been through nothing but the local catalog may have no name
  // at all, and "book 1342" is a good deal better than an empty pair of quotes
  // in a sentence read at 2am. The server says the same thing in its own
  // readout, from queue._name.
  const name = row.title || `book ${row.gid}`;
  return row.authors ? `${name} — ${row.authors}` : name;
}

// -------------------------------------------------- what is playing under it

// Who wrote it, out of the one field the catalog has.
//
// Gutenberg's `authors` is already `Surname, Forename, dates`, so one name needs
// nothing done to it at all. Several arrive as one string with semicolons in it,
// and printed as they come that is a run of commas and semicolons with nothing
// in it to say where one person ends and the next begins:
// `Collins, Wilkie, 1824-1889; Reade, Charles, 1814-1884` is two people and
// reads as one long list of somethings. Split on the semicolon and set between
// them the separator this page already uses to hold two unlike things apart on
// one line, and the eye has somewhere to stop.
//
// Empties are dropped rather than trimmed away afterwards, because the field
// comes with a trailing semicolon often enough to matter and a name followed by
// a lone separator reads as a second author whose name is missing.
//
// It is used in Workshop and nowhere else now, which is the answer to a question
// this split made somebody look at. Books used to name every book
// `Title — Surname, Forename, dates`, at 21dp, on a screen that had to be small
// enough to hold eight blocks. At the night scale that screen is set at now, the
// same string is three lines of a shelf row — a render of it was what settled
// this — and two of those three lines are catalogue metadata about a book
// somebody already owns and chose. What the shelf is for is recognising one of
// three or four titles in the dark, and the title alone is what does that.
//
// Where the author does its work is choosing among seventy thousand books
// nobody owns yet, which is a search result, which is Workshop.
function whoWrote(authors) {
  return String(authors || "")
    .split(";")
    .map((one) => one.trim())
    .filter(Boolean)
    .join(" · ");
}

// What to call a book of somnia's own — the block at the top of Books and every
// row of the shelf under it, out of one function so the two cannot drift.
//
// The fallback is the one drawPlayer uses for its headline: a book that has been
// through nothing but the local catalog may have no title at all, and
// "book 1342" is a good deal better than an empty line where the name goes.
function titleOf(title, id) {
  return title || `book ${id}`;
}

// The block at the top of the books panel: which book is playing under it, how
// far in, and — being the press itself — the way back to it.
//
// Everything here comes off the manifest and the position this page is already
// holding. Nothing is fetched, nothing is stored, and nothing on the server
// knows this block exists — which is what lets it be redrawn on every pass of
// drawPlayer without costing anything, and what makes it impossible for it to
// disagree with the player behind the panel.
//
// Nothing at all while the panel is shut. drawPlayer runs four times a second
// with the sound on and most of that is spent with nobody looking at this.
function drawReadingNow() {
  if (queuePanel.hidden) return;
  // No book open — a somnia that has never rendered anything, or a book still
  // waiting on its first chapter. The whole block goes, label and all, which is
  // the rule the card of live rows already follows: a heading over nothing is a
  // claim that something should be there, and at 2am that is a reason to get up
  // and look for it.
  if (!manifest || !current) {
    readingNow.hidden = true;
    return;
  }
  readingNow.hidden = false;
  readingTitle.textContent = titleOf(manifest.title, gid);
  // The player's own count, drawn again here rather than read off the screen:
  // 0 means nobody wrote the total down — every book rendered before that
  // column existed — so it says `chapter 4` and stops, and never `4 of 0`.
  const total = manifest.chapters_total || 0;
  const number = current.idx + 1;
  const which = total ? `chapter ${number} of ${total}` : `chapter ${number}`;
  // And where the press will land, in the book's own clock — the same string
  // the player's position readout shows, so the panel and the screen behind it
  // name one place. This is what the pill above the shelf used to say, and it
  // reads better here: on the button it was the label of a control, and in the
  // line it is a fact about the book, beside the chapter it belongs with.
  //
  // A book already sounding has nothing to start, so it says that instead of
  // offering a time — which on a playing book is out of date by the moment it
  // is read, and names a place nothing is going to move to.
  //
  // Not `1h12m in`, which this line said while the block had a pill under it.
  // That was the only honest thing the line could hold once `listened` was
  // ruled out — ADR 3 dropped Audiobookshelf's session history at the pivot and
  // nothing stores how long anybody has listened for — but distance travelled
  // is the lesser reading of the two, and the place is now free to be said here.
  const where = player.paused ? `picks up at ${timestamp(positionMs)}` : "playing";
  readingMeta.textContent = `${which} · ${where}`;
  // And the label over it, which is the same fact read at a glance from the top
  // of the screen rather than from the end of a line.
  readingLabel.textContent = player.paused ? "reading now" : "playing now";
  // The same fraction drawn rather than stated — and nothing at all while the
  // book is still arriving. total_ms is how much audio exists, which on a
  // finished book is how long the book is and on one still being read is not:
  // a bar drawn from it reaches the end at chapter five of thirty-seven and
  // then walks backwards as the rest lands. Both halves of "still arriving"
  // count, because a render that was stopped part way leaves exactly the same
  // short timeline as one that is still going.
  const arriving = manifest.status === "rendering" || moreToCome();
  const whole = !arriving && manifest.total_ms > 0;
  readingTrack.hidden = !whole;
  if (whole) {
    const through = Math.min(1, positionMs / manifest.total_ms);
    // One decimal place, as the job rows use, so that a redraw of the same
    // position is the same string and the bar does not shiver on a rounding
    // error four times a second.
    readingFill.style.width = `${Math.round(through * 1000) / 10}%`;
  }
}

// ------------------------------------------------------------ on the shelf

// The books somnia already has, each one a press that resumes it where it was
// left. Everything a row says is already in /api/books — positions have always
// been per book — so this is a readout of state that existed before the panel
// did, and the press writes one column on the server.
//
// What that press cannot do is the reason it is allowed to exist at all.
// Opening a book moves nothing, plays nothing of it that has not been played,
// and leaves the book being left behind at its own position to the millisecond.
// A wrong press costs one press back, which is what makes a list of books
// something a thumb may land on in the dark.

// Where a book was left, and what is happening to it, in the line under its
// name. A book with nothing to play at all says only that, in the page's own
// two sentences for it, because there is no press on that row and the line has
// to say why.
function shelfWords(entry) {
  if (!entry.chapters) {
    return entry.status === "rendering"
      ? "the first chapter is still being read"
      : "nothing to play yet";
  }
  // "never started" and "at 0:00:00" are different answers and only one of them
  // is true of a book nobody has opened — the same distinction the manifest's
  // null position carries, said in words here.
  const where =
    entry.position_ms === null
      ? "not started"
      : `${timestamp(entry.position_ms)} in`;
  // And whether the whole of it is there to be listened to, in the words the
  // search results below use for the same two states: a book somnia is still
  // reading, and one whose render stopped part way and left what it had. A
  // finished book says nothing, because "already here" is what every other row
  // on this list is as well.
  const state = entry.status === "done" ? "" : HAVE_WORDS[entry.status];
  return state ? `${where} · ${state}` : where;
}

function shelfRow(entry) {
  const li = document.createElement("li");
  li.className = "shelved";
  li.id = `shelf-${entry.gid}`;
  // The row is the press, and the whole of it is: name, line and hairline
  // inside one target rather than a reading with a pill on the end of it. Four
  // pills down a list are four controls to aim at where the question is only
  // which book, and at this screen's type scale the pill and the title were
  // fighting over the same row. Tapping the book is the one gesture Books has —
  // the block above works the same way — so there is nothing on this list to
  // learn that was not already learnt at the top of the screen.
  //
  // A book with no audio behind it is not a press at all. It is marked rather
  // than offered and then refused, which is the rule the search results already
  // follow and the same rule the server keeps: it answers 404 for a book there
  // is nothing to play of. So the parts go inside a button or inside a plain
  // div, and only one of the two can be pressed — where before the difference
  // was a pill that was there or was not.
  const press = document.createElement(entry.chapters ? "button" : "div");
  press.className = "shelved-open";
  if (entry.chapters) {
    press.type = "button";
    // Set at creation, as candidateRow does, or nothing in a test can reach it.
    press.id = `shelf-open-${entry.gid}`;
    press.addEventListener("click", () => openShelved(entry, press));
  }
  // Spans rather than paragraphs, and the same for the hairline below: a
  // <button> takes phrasing content, and a <p> or a <div> inside one is invalid
  // even where a browser draws it. The sheet gives each of them a block display
  // back. `reading now` above is built the same way, in index.html.
  const name = document.createElement("span");
  name.className = "shelved-name";
  name.textContent = titleOf(entry.title, entry.gid);
  press.append(name);
  const meta = document.createElement("span");
  meta.className = "shelved-meta";
  meta.textContent = shelfWords(entry);
  press.append(meta);
  // How far through, drawn rather than stated, and only where the whole book is
  // here: the same guard drawReadingNow carries, for the same reason. While a
  // render is going total_ms is how much audio exists rather than how long the
  // book is, so a bar drawn from it reaches the end at chapter five of
  // thirty-seven and then walks backwards as the rest lands. A book nobody has
  // started gets none either — there is nothing to draw, and an empty track
  // where every other row has a fill reads as a book at zero rather than as a
  // book at nothing.
  //
  // Inside the press with the words above it, because the press is the row now.
  // The divider between one book and the next is still on the <li>, so a rule
  // that stopped where the text stops is still not a thing this list can show.
  if (entry.status === "done" && entry.total_ms > 0 && entry.position_ms) {
    const track = document.createElement("span");
    track.className = "shelved-track";
    const fill = document.createElement("span");
    fill.className = "shelved-fill";
    const through = Math.min(1, entry.position_ms / entry.total_ms);
    fill.style.width = `${Math.round(through * 1000) / 10}%`;
    track.append(fill);
    press.append(track);
  }
  li.append(press);
  return li;
}

function drawShelf() {
  // Never the book playing underneath. That one is the block above — the same
  // shape as one of these rows, in amber, with the time it would land at in its
  // line — and a second row for it here would be two entries for one book, with
  // this one being the worse of them, because it would adopt the server's copy
  // of the position, which is up to fifteen seconds behind the sound.
  const others = shelved.filter((entry) => entry.gid !== gid);
  shelf.replaceChildren(...others.map(shelfRow));
  // A label over nothing is a claim that something should be there, which is
  // the rule the card of live rows and the ended list both follow.
  shelfLabel.hidden = !others.length;
}

// Asked when somebody arrives at the panel, and not on the poll with the queue.
// The queue moves while it is being watched; the shelf changes when a render
// finishes, which is hours, so the two moments worth asking are opening the
// panel and coming back to a phone that has been in a pocket.
async function askForTheShelf() {
  let listing = null;
  try {
    const response = await fetch("api/books");
    if (!response.ok) throw new Error("no book list");
    listing = await response.json();
  } catch (error) {
    // Whatever was last drawn stays on the screen, exactly as the queue rows
    // do: emptying the list would be this screen's one available lie, because
    // an empty shelf and an unreachable server look identical and mean opposite
    // things.
    //
    // And the doubt is written under it, which it did not use to be. While the
    // queue was on this panel the poll owned the one line for "couldn't reach
    // somnia" and this request went to the same box on the same press, so that
    // line was true of the shelf as well and a second writer would only have
    // raced it. The queue is on another screen now. A failure here that said
    // nothing would be a shelf that had quietly stopped being a list of books.
    console.error(error);
  }
  // The panel may have gone while this was in flight — one press to open it and
  // one to leave is an ordinary thing to do in the time a tailnet takes. Close
  // forgets the shelf on purpose, so an answer that arrived afterwards and
  // adopted itself anyway would put a shelf from a night that is over back in
  // the DOM, to be found at the next opening. Nothing here is drawn while
  // nobody is looking, which is the same rule drawReadingNow keeps — and it is
  // why the line of doubt is written here rather than in the catch above.
  if (queuePanel.hidden) return;
  shelfNote.textContent = listing ? "" : "couldn't reach somnia";
  if (listing) shelved = listing.books || [];
  drawShelf();
}

// The press that changes which book the night is about, in a fixed order.
async function openShelved(entry, button) {
  // One at a time, and the guard is set before the first await: two presses a
  // frame apart are the ordinary way a thumb double-taps something that has not
  // answered yet.
  if (picking) return;
  // The book already open, which this list holds only for a moment — the agent
  // can move the night to another book while somebody is reading the panel, and
  // the row drawn a second ago is then the book that is playing. Opening it
  // again would adopt the server's position, which is up to fifteen seconds
  // behind the sound, so this press is the one above it instead.
  if (entry.gid === gid) {
    pickItUp();
    return;
  }
  picking = entry.gid;
  button.disabled = true;
  try {
    // The server first, because this is the half that outlives the tab: it
    // makes this book the most recent one, which is the whole of what a cold
    // launch reads, so a page discarded a second later comes back on the book
    // they chose rather than on the one they left. It writes nothing else — no
    // position, no count, no mark — so the page is not being moved, it is being
    // pointed somewhere.
    const response = await fetch(`api/book/${entry.gid}/open`, {
      method: "POST",
    });
    if (!response.ok) throw new Error(`no book ${entry.gid} to open`);
    // And then the same call the agent's move takes when it lands in another
    // book, which is what makes this one line rather than a second way of
    // switching: the parting position of the book being left, the played clock
    // that belongs to it, the seq, the manifest and the first chapter are all
    // handled where they already are.
    await openBook(entry.gid, { play: true });
  } catch (error) {
    console.error(error);
    // Said in the page's second voice, and it has to be that one. #status is
    // under the panel; #queue-said is the foot of a scroller that runs past the
    // card, the ended rows, the label and the search box — at 360x780 a shelf
    // press is at the top of the panel and that line is three screens down, so
    // a failure written there is a press that did nothing and said nothing.
    // The toast is over both overlays, at the bottom by the thumb that caused
    // it, and it is already where the same press says `opened` when it works.
    // The same sentence follow() uses for the same failure, for the same
    // reason: the switch did not happen, and the press is still there.
    toast("couldn't reach that book");
    button.disabled = false;
    picking = 0;
    return;
  }
  picking = 0;
  // openBook adopts nothing when there is no audio to play, and leaves the page
  // on the book it was on. The server refuses those before this gets that far,
  // so this is the belt to that braces — and it is here rather than nowhere
  // because "opened" over a book that did not open is the one thing a toast
  // must never say. The press comes back with the panel it is still standing
  // on, exactly as it does when the request itself failed: a row that did
  // nothing and cannot be pressed again is worse than either.
  if (gid !== entry.gid) {
    button.disabled = false;
    return;
  }
  // This press is itself the touch a refused play was waiting for, so the panel
  // gives the borrowed listener up rather than handing it back. Then the panel
  // goes, because the question it was opened with has just been answered.
  rearmOnQueueClose = false;
  hideQueue();
  // On the line after the switch and never on a timer, for the reason
  // chooseCandidate gives: what a toast says has to be true when it is written.
  toast(`opened · ${entry.title || `book ${entry.gid}`}`);
}

// One job, in one line, for somebody who wants to know whether to wait up.
//
// Two of these are not states at all. A render whose heartbeat has gone quiet
// says so, because "rendering" would be a claim about a process that may have
// died with the box; and one that has been asked to stop says it is stopping,
// because it stays 'rendering' until the child reaches the end of its sentence
// and saying "rendering" there looks like the press was ignored.
//
// No percentage and no time remaining, in words. Chapters differ in length by
// an order of magnitude, so a number drawn from 4 of 39 is not a fraction of
// the work and reading it as one is how a render looks stalled, and the only
// honest denominator for a time estimate does not exist until the last chapter
// has been encoded. The hairline under this line is the same fraction drawn
// rather than stated, which is as much as it can honestly claim: something is
// moving, and this is roughly where it has got to.
// Which voice a job named, in the short form the picker draws — `bm_george` is
// a filename and this is a caption. Stripped rather than looked up in the
// roster, because the queue is drawn the moment the panel opens and the roster
// is only fetched when somebody reaches for the add press.
//
// Empty for a row that named no voice, and that is right: the renderer's own
// is a thing this page cannot see, and guessing at it would put a name on the
// screen that the book might not be read in.
function voiceWords(row) {
  return (row.voice || "").replace(/^[a-z]{2}_/, "");
}

function jobWords(row) {
  if (row.state === "queued") {
    const place = row.place > 0 ? `${ordinal(row.place)} in line` : "waiting its turn";
    // Said here, on the row a press has just made, because this is the last
    // moment the choice costs nothing to change: a book in the line can be
    // taken out of it with the control on the same row.
    const voice = voiceWords(row);
    return voice ? `${place} · ${voice}` : place;
  }
  if (row.state === "rendering") {
    if (row.stopping) return "stopping at the end of this sentence";
    if (!row.responding) return "not responding";
    // 0 means nobody has written the number down yet — the fetch and the parse
    // are what produce it — and it is what every book rendered before that
    // column existed says as well. "chapter 1 of 0" is the sentence this
    // prevents.
    if (!row.chapters_total) return "fetching the text";
    // The chapter being worked on, not the count that is finished: the same
    // number, and the same meaning, as the "rendering chapter 4/39" line the
    // renderer writes to the journal, so the two can be read side by side.
    const chapter = Math.min(row.chapters_done + 1, row.chapters_total);
    const words = `chapter ${chapter} of ${row.chapters_total}`;
    const ready = howMuch(row.rendered_ms);
    return ready ? `${words} · ${ready} read so far` : words;
  }
  if (row.state === "failed") return row.error || "something went wrong";
  if (row.state === "cancelled") {
    // Two quite different things end up here. A book taken out of the line
    // never started and nothing of it exists; a render stopped at chapter four
    // left four chapters that play perfectly well, and somebody deciding
    // whether to ask for it again needs to know which of those they have.
    return row.chapters_done
      ? "stopped part way — what was read still plays"
      : "taken out of the queue";
  }
  return "all of it is here";
}

function stopControl(row) {
  const armed = stopArmed?.id === row.id;
  const button = document.createElement("button");
  button.type = "button";
  button.className = armed ? "job-stop armed" : "job-stop";
  // Set at creation, as candidateRow does, or nothing in a test can reach it.
  button.id = `queue-stop-${row.id}`;
  // Two presses, and the button itself is the question. Not a confirm dialog:
  // that is an overlay over an overlay, which is a route wearing a hat, and it
  // would be the first thing on this page to take focus from anybody.
  button.textContent = armed ? "really stop?" : "stop reading this";
  button.addEventListener("click", () => pressStop(row));
  return button;
}

// How far through the chapters this row is, drawn as a hairline — and nothing
// at all when nobody has written the total down.
//
// That guard is the whole reason this is a function. chapters_total is 0 until
// the parse has run, and it is 0 for ever on every book rendered before the
// column existed, so a bar drawn from it would sit at 0% on a render that is
// working perfectly well. An empty track is a lie somebody acts on at 2am; no
// track at all is the truth, and the line above says what is going on instead.
//
// It is a hairline and not a percentage for the reason `jobWords` gives no
// percentage either: chapters differ in length by an order of magnitude, so
// this creeps and lurches. As a 2dp rule that is a thing moving, which is all
// it is claiming to be; as a number it would be a promise about time.
function jobProgress(row) {
  if (!row.chapters_total) return null;
  const track = document.createElement("div");
  track.className = "job-track";
  // Kept from the last redraw where there was one, so the width animates
  // instead of appearing. See jobFills.
  let fill = jobFills.get(row.id);
  if (!fill) {
    fill = document.createElement("div");
    fill.className = "job-fill";
  }
  jobFills.set(row.id, fill);
  const done = Math.min(row.chapters_done, row.chapters_total);
  // One decimal place, so that a chapter landing moves it by a number rather
  // than by a rounding error, and so that two renders of the same row are the
  // same string.
  fill.style.width = `${Math.round((done / row.chapters_total) * 1000) / 10}%`;
  track.append(fill);
  return track;
}

function jobRow(row) {
  const live = QUEUE_LIVE.includes(row.state);
  const li = document.createElement("li");
  li.className = live ? "job" : "job gone";
  li.id = `job-${row.id}`;
  // The name, and in the corner of the same line the stage it is at. One line
  // and two ends of it, because the question this panel is opened with is "is
  // anything happening", and the answer to that is a single word beside a
  // title.
  const line = document.createElement("p");
  line.className = "job-line";
  const name = document.createElement("span");
  name.className = "job-name";
  name.textContent = bookName(row);
  const stage = document.createElement("span");
  // Amber only while it is really being read. A render whose heartbeat has
  // gone quiet, or one that has been asked to stop, is still `rendering` to
  // the server and still says `narrating` here — but it is no longer the warm
  // thing on the panel, because the line under it is about to say something
  // that is not good news.
  const warm = row.state === "rendering" && row.responding && !row.stopping;
  stage.className = warm ? "job-stage now" : "job-stage";
  stage.textContent = JOB_STAGE[row.state] || row.state;
  line.append(name);
  line.append(stage);
  const state = document.createElement("p");
  state.className = "job-state";
  state.textContent = jobWords(row);
  // No listener on the row itself. A row is a readout, so the only pressable
  // thing on it is its own action and there is nothing to mis-hit into.
  li.append(line);
  li.append(state);
  const track = jobProgress(row);
  if (track) li.append(track);
  if (live) li.append(stopControl(row));
  return li;
}

function drawQueue() {
  const live = queueRows.filter((row) => QUEUE_LIVE.includes(row.state));
  const over = queueRows.filter((row) => !QUEUE_LIVE.includes(row.state));
  // Whatever is on the screen after this, and nothing else. A bar kept for a
  // row that has left the list is a bar that would slide from somebody else's
  // progress if that id ever came back.
  const kept = new Map();
  for (const row of queueRows) {
    if (jobFills.has(row.id)) kept.set(row.id, jobFills.get(row.id));
  }
  jobFills = kept;
  queueLive.replaceChildren(...live.map(jobRow));
  // The card holds the live rows and goes with them. A heading over nothing is
  // a claim that something should be there.
  queueWorking.hidden = !live.length;
  // What went wrong, under what is happening. There is no dismiss control for
  // these and no count of them: `view` drops a terminal row after a day, which
  // is when a failure stops being news and becomes something the journal has.
  queueGone.replaceChildren(...over.map(jobRow));
  queueEnded.hidden = !over.length;
}

// A book the catalog found: what it is called, who wrote it, and the one press
// that can be made about it.
//
// The title and the author are two lines rather than one string. The design asks
// for `Author · year · formats` under the title and somnia's catalog has the
// first of those three and neither of the others, so what is under the title is
// the author and whatever this screen already knows about the book — and no
// cover art, here or anywhere: a cover is a bright rectangle in a dark room, and
// four lines of text are read faster half asleep.
//
// This is the only list in the app that names an author, and it is the only one
// that has to: it is a list of books nobody owns yet, several of them likely by
// the same person, being read in daylight. Books names none of its own — see
// whoWrote for why the shelf gave the author up.
function foundRow(entry) {
  const li = document.createElement("li");
  li.className = "found";
  li.id = `found-${entry.gid}`;
  const text = document.createElement("div");
  text.className = "found-text";
  const name = document.createElement("p");
  name.className = "found-name";
  name.textContent = titleOf(entry.title, entry.gid);
  text.append(name);
  const meta = document.createElement("p");
  meta.className = "found-meta";
  const by = document.createElement("span");
  by.className = "found-by";
  // Through whoWrote, which used to be spent on the shelf and is spent here
  // instead: two authors arrive from the catalog as one semicolon-joined string,
  // and this is the list where that shape actually turns up.
  by.textContent = whoWrote(entry.authors);
  meta.append(by);
  const where = SOURCE_WORDS[entry.source];
  if (where) {
    const library = document.createElement("span");
    library.className = "found-where";
    library.textContent = where;
    meta.append(library);
  }
  const already = HAVE_WORDS[entry.have];
  if (already) {
    // Why there is no press to make, in the line that already exists rather
    // than as a pill on the right: a pill that cannot be pressed is a button
    // that does nothing, which is the one thing this row is arranged to avoid.
    const mark = document.createElement("span");
    mark.className = "found-have";
    mark.textContent = already;
    meta.append(mark);
  }
  text.append(meta);
  li.append(text);
  // A book that is already here, or already coming, is marked rather than
  // offered and then refused: a press that was never available cannot be a
  // press that did nothing, and at 2am those two feel completely different.
  if (HAVE_ALREADY.includes(entry.have)) return li;
  const add = document.createElement("button");
  add.type = "button";
  // The one warm press on the panel, and only for a render that died: picking
  // a half-read book back up is the thing somebody came here having already
  // decided to do, and it was impossible from this page until the queue
  // existed. Adding something new is a plain pill.
  const resume = entry.have === "pending";
  add.className = resume ? "found-add again" : "found-add";
  add.id = `queue-add-${entry.gid}`;
  add.textContent = resume ? "finish this one" : "add this book";
  // Opens the voice picker under this row; the press that opened it closes it,
  // and `add it` inside it is what actually submits. A book somnia part
  // rendered is the exception: it already has a voice, every timestamp in it
  // was measured in that voice, and finishing it in another would move all of
  // them — so `finish this one` is still one press and names no voice at all,
  // which leaves the renderer's own to carry on with.
  add.addEventListener("click", () =>
    resume ? addBook(entry, add, "") : pressAdd(entry, add),
  );
  li.append(add);
  return li;
}

function drawResults() {
  // Before the rows are replaced, not after: the picker lives inside one of
  // them, so a redraw takes it off the screen either way — and without this the
  // page would go on believing it was open, and the press that should reopen it
  // would read as the press that closes it.
  closeVoices();
  queueResults.replaceChildren(...queueFound.map(foundRow));
}

// ------------------------------------------------------------- asking about it

async function pollQueue() {
  clearTimeout(queuePoll);
  queuePoll = 0;
  try {
    const response = await fetch("api/queue");
    if (!response.ok) throw new Error("no queue");
    const body = await response.json();
    queueRows = body.items || [];
    queueNote.textContent = "";
    drawQueue();
  } catch (error) {
    // Whatever was last drawn stays on the screen and the doubt is written
    // under it. Emptying the list would be the one lie this panel can tell: an
    // empty queue and an unreachable server look identical and mean opposite
    // things, and only one of them is a reason to go to sleep.
    console.error(error);
    queueNote.textContent = "couldn't reach somnia";
  }
  scheduleQueuePoll();
}

// Only while somebody is looking, and only while Workshop is up — which is now
// a daytime screen two presses from the player, so this is a poll that cannot
// run at night at all. A hidden page's timers are throttled to roughly one wake
// a minute, so a poll left running in a pocket is both untimely and a radio
// wake beside somebody asleep — worst of both. It is asked again in full when
// the page comes back.
function scheduleQueuePoll() {
  clearTimeout(queuePoll);
  queuePoll = 0;
  if (workshop.hidden || document.visibilityState === "hidden") return;
  queuePoll = setTimeout(pollQueue, QUEUE_POLL_MS);
}

function stopQueuePoll() {
  clearTimeout(queuePoll);
  queuePoll = 0;
}

// ------------------------------------------------------------------ stopping

function forgetStop() {
  if (!stopArmed) return;
  clearTimeout(stopArmed.timer);
  stopArmed = null;
}

function pressStop(row) {
  if (stopArmed?.id !== row.id) {
    forgetStop();
    stopArmed = {
      id: row.id,
      timer: setTimeout(() => {
        stopArmed = null;
        drawQueue();
      }, STOP_CONFIRM_MS),
    };
    // Redrawn rather than relabelled in place, so that the label a poll paints
    // and the label a press paints come from the same line of code.
    drawQueue();
    return;
  }
  forgetStop();
  askToStop(row.id);
}

async function askToStop(id) {
  try {
    const response = await fetch(`api/queue/${id}/stop`, { method: "POST" });
    // Read whatever came back, whatever the status was. A job that ended a
    // second ago is answered 200 with a sentence and a job that never existed
    // is answered 404 with the same shape, and the sentence is the point of
    // both.
    const body = await response.json();
    queueSaid.textContent = body.said || "";
  } catch (error) {
    console.error(error);
    queueSaid.textContent = "couldn't reach somnia — nothing has been stopped";
    return;
  }
  // A stop takes about twenty seconds to land — one heartbeat plus the sentence
  // in flight — so this is not the answer, it is the row starting to say
  // "stopping".
  await pollQueue();
}

// ------------------------------------------------------------------- adding

async function findBooks() {
  const wanted = queueQuery.value.trim();
  if (!wanted) return;
  queueSaid.textContent = "";
  try {
    // One request per press. A round trip per keystroke would be fifteen
    // requests for one answer over a tailnet, and the search is an offline FTS5
    // query on the server's own disk, so there is nothing to be gained by
    // starting it early.
    const response = await fetch(`api/catalog?q=${encodeURIComponent(wanted)}`);
    if (!response.ok) throw new Error("no catalog");
    const body = await response.json();
    queueFound = body.entries || [];
    drawResults();
    if (!queueFound.length) queueSaid.textContent = "nothing in the catalog";
  } catch (error) {
    console.error(error);
    queueSaid.textContent = "couldn't reach somnia";
  }
}

async function addBook(entry, button, voice) {
  // One at a time, and the guard is set before the first await: two presses a
  // frame apart are the ordinary way a thumb double-taps something that has not
  // answered yet.
  if (submitting) return;
  submitting = entry.gid;
  button.disabled = true;
  // Whatever happens to the request, the choosing is over: the picker names a
  // voice for a press that has now been made, and leaving it up would offer to
  // change something already sent.
  closeVoices();
  try {
    const response = await fetch("api/queue", {
      method: "POST",
      headers: { "content-type": "application/json" },
      // The rule is: send exactly what was on the screen. A picker that drew a
      // pill in amber has said which voice this book will be read in, so that
      // is what goes — including when nobody pressed anything, because the
      // default was still shown as chosen. Only a press with no picker at all
      // behind it sends nothing, and then nothing was claimed either.
      //
      // Left out rather than sent as "": absent means "the renderer's own",
      // which is a different request from naming one, and the route tells the
      // two apart.
      body: JSON.stringify(voice ? { gid: entry.gid, voice } : { gid: entry.gid }),
    });
    const body = await response.json();
    // Taken or refused, the server said a sentence and the sentence is the
    // answer — the same string the agent's add_book returns, from the same
    // function, so the panel and the voice cannot disagree about what happened.
    queueSaid.textContent = body.said || "";
    if (body.ok) {
      entry.have = "queued";
      drawResults();
    } else {
      button.disabled = false;
    }
  } catch (error) {
    // Nothing landed, and no optimistic row is drawn: a queue entry that never
    // existed on the server is exactly the state a wrong press must not be able
    // to leave behind. The press comes back, because trying again is the whole
    // of what there is to do about it.
    console.error(error);
    queueSaid.textContent = "couldn't reach somnia — nothing has been added";
    button.disabled = false;
    submitting = 0;
    return;
  }
  submitting = 0;
  // So the row it just made is on the screen now rather than in five seconds.
  await pollQueue();
}

// ------------------------------------------------------- opening and closing

function showQueue() {
  if (!queuePanel.hidden) return;
  queuePanel.hidden = false;
  // Giving focus up, never taking it. There is no text input on this screen any
  // more — the search left with the rest of the daytime work — but the composer
  // behind it is one blur away from putting a keyboard over a panel that has
  // just measured itself against a screen with none.
  question.blur?.();
  rearmOnQueueClose = tapToResume !== null;
  disarmTapToResume();
  // Before the first request comes back, so the answer to "which book is this
  // standing over?" is on the screen the moment the panel is, rather than a
  // round trip later. It is drawn from what this page already holds, so there
  // is nothing to wait for.
  drawReadingNow();
  // The shelf is asked for once, here. Nothing about it is worth a wake every
  // five seconds — a book appears on it when a render finishes — and this is
  // the moment somebody is looking at it.
  askForTheShelf();
  // No queue poll. That belongs to Workshop now, which is the screen the rows
  // are on: a panel that polled for a list it does not draw would be a radio
  // waking every five seconds to answer a question nobody has asked.
}

// The inert close. It forgets everything the panel was holding and gives back
// the one thing it borrowed, and that is the whole of it: no seek, no report,
// no seq bump, nothing said on the status line, and nothing touched that the
// spoiler guard or the sleep timer can see. A fade running underneath keeps
// running and the countdown keeps counting, for the same reason cancel leaves
// them alone — the night was already ending and looking at a list of books did
// not change that.
function hideQueue() {
  if (queuePanel.hidden) return;
  // Workshop is over this and cannot outlive it. Nothing on the page opens
  // Workshop without opening Books first, so this can only be reached with
  // Workshop already down — but a screen left standing over a panel that has
  // gone would be the one state on this page with no way out of it, and one
  // line is a cheaper guarantee than the argument that it cannot happen.
  hideWorkshop();
  queuePanel.hidden = true;
  shelved = [];
  shelf.replaceChildren();
  shelfLabel.hidden = true;
  shelfNote.textContent = "";
  const rearm = rearmOnQueueClose;
  rearmOnQueueClose = false;
  // True before the panel went up and true again now: the book is still paused,
  // still waiting for a touch, and the line that said so came back with the
  // listener rather than being left lying.
  if (rearm) armTapToResume();
}

// Workshop, over Books rather than instead of it. Books stays exactly as it was
// underneath — same shelf, same block at the top, same scroll position — so
// `‹ books` is a close and not a second opening, and nothing is re-fetched to
// come back to a screen that never left.
//
// It owns the queue poll, and that ownership is the whole of why the split is
// worth anything at runtime as well as on screen: the rows are only asked for
// while the screen that draws them is up, so a night spent on Books is a night
// with no five-second wake in it at all.
function showWorkshop() {
  if (!workshop.hidden) return;
  workshop.hidden = false;
  // The dim layer comes off with it, and goes back on at `‹ books`. drawDim
  // reads the screen rather than being told a level, so these two calls cannot
  // leave the layer disagreeing with which screen is up.
  drawDim();
  // Never focusing the search box. Focusing it pops the keyboard, and the
  // keyboard changes the geometry the fixed overlay just measured itself
  // against, so the screen would arrive with its way out under the letters.
  queueQuery.blur?.();
  pollQueue();
}

// And the way back, which changes nothing about the book and nothing about
// Books. What it forgets is what this screen was holding — the rows, the
// search, what the server last said — for the reason the panel below it forgets
// the shelf: a photograph taken five seconds ago is not worth keeping, and one
// taken last night is a lie.
function hideWorkshop() {
  if (workshop.hidden) return;
  workshop.hidden = true;
  // And the room goes back to whatever darkness was set for it, on the screen
  // that set it.
  drawDim();
  stopQueuePoll();
  forgetStop();
  // The picker goes with the screen, and so does whatever sample was playing:
  // a voice reading a line from Black Beauty out of a page that has been shut
  // is a sound with nothing on screen to explain it.
  closeVoices();
  queueRows = [];
  queueFound = [];
  jobFills = new Map();
  queueLive.replaceChildren();
  queueWorking.hidden = true;
  queueGone.replaceChildren();
  queueEnded.hidden = true;
  queueResults.replaceChildren();
  queueNote.textContent = "";
  queueSaid.textContent = "";
  queueQuery.value = "";
}

// Settings, from the player's other corner. The quietest open and close on the
// page: nothing is fetched, nothing is polled, nothing is forgotten on the way
// out — both controls on it write straight through to localStorage, so there is
// no state here that a close could drop or a re-open could bring back stale.
//
// The dim layer stays exactly where it is. This is a night screen and is read
// through it like everything else but Workshop, which is the whole reason the
// dim control can live here: a press moves the darkness of the screen doing the
// pressing.
function showSettings() {
  if (!settingsPanel.hidden) return;
  settingsPanel.hidden = false;
  // The same borrowing Books does. A page that could not start its sound is
  // waiting for a touch anywhere, and every control on this screen is a touch —
  // so the first press on `+` would start the book as well as darken the room,
  // which is a thing nobody asked for at the moment they are trying to make the
  // screen quieter. It goes back on the way out, where it is true again.
  rearmOnSettingsClose = tapToResume !== null;
  disarmTapToResume();
}

function hideSettings() {
  if (settingsPanel.hidden) return;
  settingsPanel.hidden = true;
  const rearm = rearmOnSettingsClose;
  rearmOnSettingsClose = false;
  if (rearm) armTapToResume();
}

booksButton.addEventListener("click", showQueue);
queueClose.addEventListener("click", hideQueue);
toWorkshop.addEventListener("click", showWorkshop);
workshopClose.addEventListener("click", hideWorkshop);
toSettings.addEventListener("click", showSettings);
settingsClose.addEventListener("click", hideSettings);

// The press that starts the book already open, and one of the two ways out of
// this panel that are not `close`. It is the whole `reading now` block — title,
// line and hairline — rather than a pill under it: see the block's own comment
// in index.html for why that pill is gone.
//
// The order of the three lines matters and the first of them is the whole of
// why this is not just a call to hideQueue. showQueue borrows the tap-to-resume
// listener a refused play left armed, and close hands it back, because after
// close the book really is still paused and still waiting for a touch. This
// press is not close: it *is* that touch. Handed back here, the listener would
// be sitting over a book that is now sounding, and the next thing pressed
// anywhere on the page — the question box, the transport, the microphone —
// would start it a second time.
//
// Then the panel goes, because the question it was opened with has just been
// answered and a panel left standing over a book that has started playing is
// one more thing to get out of in the dark.
//
// Then the sound, by exactly the route the play button takes: the same rewind
// for the same silence, the same fade up from nothing, the same landing on the
// start of a sentence after an hour. A second kind of resume is a second thing
// to reason about at 2am, and this one would be the one nobody tested. Only
// when it is really stopped — the block's own line already said `· playing`
// rather than a time, and there is nothing there to start.
//
// A shelf row for the book that is already open lands here too, rather than
// opening it again; see openShelved.
function pickItUp() {
  rearmOnQueueClose = false;
  hideQueue();
  if (player.paused) ensurePlaying({ rewind: true });
}

readingOpen.addEventListener("click", pickItUp);
queueSearch.addEventListener("submit", (event) => {
  event.preventDefault();
  findBooks();
});

// -------------------------------------------- a book that is still being read

// somnia renders a book chapter by chapter and the whole point of that is that
// listening can start when chapter one is ready. So a manifest is a photograph
// of a book that is still arriving: ingest writes each chapter row as it
// finishes and bumps total_ms with it. Fetched once at boot and never again,
// chapter three of forty-nine ended the night with "that is the end of the
// book", the sleep timer thrown away and the phone silent — and a book opened
// before its first chapter landed showed no player at all, for ever.
//
// Only the timeline is taken. position_ms and seq in the reply are the server's
// record of what this page last told it, which is up to fifteen seconds behind
// where the sound actually is, so adopting them mid-chapter would drag the
// listener backwards every time the book grew.
// Whether this book has chapters that have not been read yet — as against
// being over.
//
// `status === 'rendering'` answers the live case and nothing else: a render
// that was stopped, or killed by a reboot, or that failed at chapter four of
// thirty-nine leaves a book that is not growing and is not finished either, and
// before there was a denominator the page had nothing to tell that from the end
// of a novel. It would say "that is the end of the book", clear wantsSound and
// throw the sleep timer away, three chapters into thirty-nine.
//
// 0 means nobody wrote the number down — which is every book rendered before
// the column existed, including every book on the box this runs on — so it is
// read as "don't know" and the old sentence stands.
function moreToCome() {
  const total = manifest?.chapters_total || 0;
  return total > 0 && manifest.chapters.length < total;
}

async function refreshManifest() {
  if (gid === null || !manifest) return false;
  const response = await fetch(`api/book/${gid}`);
  if (!response.ok) throw new Error(`no book ${gid}`);
  const fresh = await response.json();
  // The page moved to another book while this was in flight, or the answer has
  // fewer chapters in it than the page is already playing — a book somebody is
  // re-rendering, say. Neither is something to adopt underneath a listener: the
  // chapter the element is holding might not be in it.
  if (fresh.gid !== gid || fresh.chapters.length < manifest.chapters.length) {
    return false;
  }
  const grew = fresh.chapters.length > manifest.chapters.length;
  // The timeline is adopted and the element is left holding the join it was
  // given, however much longer a join this manifest names. That deferral is the
  // whole of what keeps a night to one load or none: nuc2 reads a chapter every
  // three and a quarter minutes, so taking each new join as it landed would be a
  // hundred and fifteen loads between eleven and morning — a hundred and fifteen
  // elements emptied, and a hundred and fifteen chances for the lock screen
  // panel not to come back — for audio the listener will not reach for hours.
  // `streamMs` goes on saying how much book the element really holds, and the
  // load happens if and when they reach it.
  manifest = fresh;
  // The element is holding a chapter object from the manifest just replaced.
  // Pointing it at the row of the same index in the new one keeps every clock
  // on the page reading off one manifest — the numbers are the same today, but
  // a page holding rows from two fetches at once is a bug waiting for the day
  // they are not.
  if (current) {
    current = { idx: current.idx, chapter: fresh.chapters[current.idx] };
  }
  drawPlayer();
  return grew;
}

// Wait for the book to grow, and carry on when it does. `at` is the chapter the
// audio ran out after, or null when there was no audio at all yet.
//
// The same book and the same chapter is the same question, already being asked,
// and it is left alone: the two callers that arrive here on a timer — the boot
// retry, and a press of play at the frontier that comes straight back to it —
// would otherwise put the ladder back on its bottom rung every time, which is a
// request every five seconds until morning.
//
// A different chapter is a different question, and this is where a night used
// to be lost. The listener reaches one frontier, is moved past it — a place
// chosen in the chapter that has just landed refreshes the manifest and seeks
// without this wait hearing about it — and reaches the next one an hour later.
// Returning here left the wait naming the chapter before last, so the chapter
// that finally arrived was not recognised as the one the sound was stopped in
// front of: the resume was skipped, the wait took its own timer down as it went,
// and the book stayed paused with the audio for it already on the disk.
function awaitMore(id, { play = false, at = null } = {}) {
  const saying =
    at === null
      ? "the first chapter is still being read"
      : "waiting for the next chapter to be read";
  if (awaiting?.gid === id && awaiting.at === at) {
    awaiting.play = play;
    // Said again rather than assumed to be still on the screen. The status line
    // is shared — a question asked and answered takes it for itself — and the
    // sentence belongs to the sound being stopped here, which it still is.
    setStatus(saying);
    return;
  }
  stopAwaiting();
  awaiting = { gid: id, delay: RENDER_ASK_MS, play, at, timer: 0 };
  setStatus(saying);
  // Asked at once where the sound has run out, rather than five seconds from
  // now. Two reasons, and the second is the one that matters. With the screen
  // off nothing else refreshes the manifest — visibilitychange is the only
  // caller a night has, and a phone in a pocket never fires one — so the audio
  // being waited for is quite often already on the disk and the page is the
  // last to know. And the page has just paused, which makes it inaudible, and
  // an inaudible backgrounded page has its timers throttled to roughly one wake
  // a minute: this ask goes out from inside the timeupdate that found the
  // frontier, which is the one place it is certain to go out at all.
  //
  // Not for a book with no audio yet. Its manifest arrived seconds ago, from
  // openBook, and asking again in the same breath would only ask the same
  // question twice.
  if (at !== null) {
    askForMore();
    return;
  }
  awaiting.timer = setTimeout(askForMore, awaiting.delay);
}

// Whoever stops the waiting takes the message down with it — the chapter has
// either arrived or is never going to, and either way the page is not waiting
// for it any more. Anything with something else to say says it afterwards.
function stopAwaiting() {
  if (!awaiting) return;
  clearTimeout(awaiting.timer);
  awaiting = null;
  setStatus("");
}

async function askForMore() {
  const waiting = awaiting;
  if (!waiting) return;
  // It may have been called early — by the network coming back, or by the page
  // coming back in front of them — so whatever was scheduled is stale.
  clearTimeout(waiting.timer);
  try {
    if (gid === waiting.gid && manifest) {
      const grew = await refreshManifest();
      // Only if they are still standing where the audio ran out. If they went
      // somewhere else in the meantime, the longer timeline was all they
      // needed: the frontier at the end of wherever they are now will take them
      // into the new chapter by itself.
      //
      // `atFrontier` and not `player.ended`. The element does not end any more
      // — it is stopped a fraction of a second short of the end of what it
      // holds, so that the panel is suspended rather than taken down — and a
      // guard on `ended` would sit here all night beside a chapter that had
      // already arrived. The flag is set on both routes, so this still covers
      // the element that really did end: a chapter file always does, and the
      // whole book does when no timeupdate fell inside the pause's window.
      if (atFrontier && current?.idx === waiting.at) {
        // What there is to go to, asked of the manifest rather than of this
        // one answer. A book that grew while they were still listening to the
        // chapter in front of the frontier grew on an earlier ask, and a page
        // that only ever acted on the ask that found it would leave them
        // stopped in front of audio that was already here — for another minute,
        // and then another.
        const next = manifest.chapters[waiting.at + 1];
        if (next) {
          stopAwaiting();
          // From where the sound stopped, not from the top of the new chapter.
          // The two are the same place for a chapter file, which ends where its
          // chapter does; under one URL per book the stop is a fraction short of
          // the join, and that fraction is the silence ingest leaves at the end
          // of every chapter — heard twice rather than lost.
          loadSource(locate(positionMs), { play: waiting.play });
          return;
        }
      }
      if (grew) {
        stopAwaiting();
        return;
      }
      if (manifest.status !== "rendering") {
        stopAwaiting();
        // The render stopped without finishing the book — cancelled, killed, or
        // failed — and the chapters it did not get to are still missing. That is
        // not the end of the book, so nothing here ends the night: the sleep
        // timer is left running and the page is left wanting the sound back.
        if (moreToCome()) {
          setStatus("the rest of this book hasn't been read yet");
          return;
        }
        // The render finished, and there was nothing more in it after all.
        setStatus("that is the end of the book");
        wantsSound = false;
        clearSleep();
        return;
      }
    } else {
      // Nothing of this book is open yet, so there is no timeline to extend:
      // the first chapter arriving is the page opening the book at last.
      await openBook(waiting.gid, { play: waiting.play });
      if (awaiting !== waiting) return;
    }
  } catch (error) {
    // The tailnet, most likely. Asking again is already the plan.
    console.error(error);
  }
  waiting.delay = Math.min(waiting.delay * 2, RENDER_ASK_MAX_MS);
  waiting.timer = setTimeout(askForMore, waiting.delay);
}

restoreSleep();
// Before the book, because the book is what decides whether the places are
// about it: openBook draws the player the moment a manifest lands, and a list
// read out of storage a turn later would be a count that appeared on the
// position line after somebody had already looked at it.
restorePlaces();
// And after the places, because the morning screen draws their count: it is the
// same one line on the position line, and reading the fade first would draw the
// screen with the count of a list nobody had read yet.
//
// Before the book for a second reason of its own. This is what decides which
// screen the app comes up on, and the screens block further down asks it as the
// page is laid out — so a fade found here is a page that opens on the morning,
// rather than one that opens on the player and jumps a frame later.
restoreFade();
openTheBook();

// ------------------------------------------------------------------ speaking

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (!Recognition) {
  // No Web Speech API here — the phone keyboard's own dictation still works.
  talk.hidden = true;
} else {
  const recognition = new Recognition();
  recognition.lang = navigator.language || "en-GB";
  recognition.interimResults = true;
  recognition.continuous = false;
  let listening = false;
  let heard = "";

  recognition.addEventListener("result", (event) => {
    let interim = "";
    heard = "";
    for (const result of event.results) {
      if (result.isFinal) heard += result[0].transcript;
      else interim += result[0].transcript;
    }
    question.value = (heard + interim).trim();
  });

  recognition.addEventListener("end", () => {
    listening = false;
    talk.classList.remove("listening");
    setStatus("");
    buzz(10);
    const said = (heard || question.value).trim();
    heard = "";
    ask(said);
  });

  recognition.addEventListener("error", (event) => {
    // "no-speech" and "aborted" are just a held button that heard nothing.
    if (event.error !== "no-speech" && event.error !== "aborted") {
      console.error(event.error);
    }
    heard = "";
    question.value = "";
    setStatus("");
  });

  const start = (event) => {
    event.preventDefault();
    if (listening) return;
    heard = "";
    question.value = "";
    try {
      recognition.start();
      listening = true;
      talk.classList.add("listening");
      setStatus("listening…");
      buzz(15);
    } catch {
      // Already starting — the previous session hasn't finished releasing.
    }
  };

  const stop = () => {
    if (listening) recognition.stop();
  };

  talk.addEventListener("pointerdown", start);
  talk.addEventListener("pointerup", stop);
  talk.addEventListener("pointercancel", stop);
  talk.addEventListener("pointerleave", stop);
  talk.addEventListener("contextmenu", (event) => event.preventDefault());
}

// ------------------------------------------------------------------- screens

// Which of the three screens the page is on, said out loud on <body> so the
// sheet can ask.
//
// There is one document and there always was. The player and the chat are the
// same elements shown and hidden — no route, no history, nothing to come back
// from — and what is new here is only that the page *knows* which of the two it
// is showing instead of the sheet working it out from the height of the window.
//
// The sheet used to ask `@media (max-height: 34rem)` and mean two things at
// once: "is there room to draw the reading?", which is a fair question to ask a
// height, and "is the keyboard up?", which is not. The second guess was wrong
// twice over. A window dragged short has no keyboard in it, and 34rem is 34
// times a root that is the OS text scale on purpose — so turning the text up,
// which is the one setting this whole page is sized around, eventually put the
// threshold above the height of the phone and left the player unreachable for
// the rest of the night. The larger the reader's type, the sooner they lost the
// book. The first question is still a height query in the sheet; this is the
// second one, and it is a measurement.
//
// It is a named screen rather than a `keyboard-up` boolean because the keyboard
// is a route in and not the thing itself: the design's dock is a portal to this
// same screen, and the header is drawn differently on each of the two.
//
// The keyboard used to be the only route, and that was the second half of this
// bug rather than the end of the first. A measurement is a fine way to notice
// that somebody has arrived on the chat screen and a terrible way to decide
// whether they may be there at all: a keyboard that overlays the page instead of
// shrinking it, an `unobscured` height taken a moment too early, a phone turned
// on its side mid-question — each of them is a night where the composer takes
// letters and the conversation is on the other screen, and the reader is left
// typing into a box whose answers they cannot see.
//
// So the press is the route now and the measurement only adds to it, which is
// what the warning that used to be in this comment asked for. `asked` below is
// the remembered "they want the conversation", it is set by a press on the dock
// and cleared by a press on the way out, and no resize can overrule either.
const SCREENS = ["player", "chat", "wake"];

// The book and its controls, until something takes them off it.
//
// This is the page's own answer to "which screen?"; the class below is only how
// the sheet gets told. It is a name rather than a boolean, and the third screen
// the design described has now taken the room that left: `wake` is the morning
// after a fade, and it is the one of the three that is neither a measurement nor
// a press — it is a fact about last night, read out of storage before any of
// this runs.
//
// `whichScreen` and not `screen`: `screen` is a browser global, and a top-level
// `let screen` would quietly shadow it for the whole file.
let whichScreen = "player";

// Written every time rather than only on a change: this is also what puts the
// first class on <body>, and a page that only wrote when the screen changed
// would spend the whole of its first night carrying neither of them.
function showScreen(name) {
  const arriving = name !== whichScreen;
  whichScreen = name;
  for (const each of SCREENS) {
    document.body.classList.toggle(`${each}-screen`, each === name);
  }
  // Arriving on the conversation puts you at the end of it, which is where the
  // last thing said is. It used to come free: the only way here was a keyboard,
  // and the resize that keyboard fired ran fit(), which scrolls. A press does
  // not resize anything — and the turns that landed while this screen was off
  // scrolled a box that was display:none, which scrolls nothing at all — so
  // without this somebody pressing the dock after a long night would open the
  // conversation at the top and have to scroll down to what they just asked.
  if (arriving && name === "chat") {
    transcript.scrollTop = transcript.scrollHeight;
  }
}

// Said before anything can ask, and before a keyboard can have an opinion. The
// morning is the one thing that can already be true this early — restoreFade has
// run — and it is said here rather than a turn later so that a page opening
// after a fade opens on the wake screen, instead of drawing the player and
// replacing it a frame afterwards.
showScreen(waking ? "wake" : whichScreen);

// ------------------------------------------------------------------ keyboard

// Not every browser shrinks the page for the on-screen keyboard, and the ones
// that do disagree about when. Following the visual viewport keeps the
// composer above the keyboard and the transcript scrollable to both ends.
//
// It is also where the keyboard is *measured*, which is the whole of how the
// screen above is decided. `visualViewport.height` is what is left of the page
// after whatever the platform has put over it; the same page's height with
// nothing over it is the other half of the sum, and the difference between them
// is the keyboard. Nothing there has to be inferred from anything.

// How much of the page something has to take before it counts as a keyboard
// rather than the address bar sliding in. A keyboard is between a third and a
// half of a phone; the chrome that comes and goes is a tenth of it at most. A
// fraction and not a number of pixels, because what it has to clear scales with
// the screen — a tablet's keyboard is a smaller share of a taller page.
const KEYBOARD_TAKES = 0.25;

// The two boxes on this page anybody types into. A keyboard cannot be up over a
// page with focus in neither of them, and that is what tells a window dragged
// short from a keyboard arriving: nothing about a desktop resize implies
// somebody is typing. A third field added to this page has to be added here as
// well, or its keyboard is the one the page cannot see.
const typingFields = [question, queueQuery];

// Which of them is being typed into, or null. The element rather than a
// boolean, because the composer's keyboard is the chat screen while the books
// panel's keyboard is a keyboard over an overlay with the player still behind
// it.
let typing = null;

// Somebody asked for the conversation, and the page stays on it until somebody
// asks to leave. Nothing about the size of the window is allowed near this.
let asked = false;

// Whether a keyboard has been seen over the composer since they asked. It is the
// one thing the measurement is still trusted with, and it buys the way out that
// nobody presses: Android's back button closes the keyboard and leaves the box
// focused, so there is no blur to hear and the only evidence that they are done
// is the room coming back. A keyboard that was never up cannot go away again,
// which is what keeps the microphone — and a desktop, and any phone whose
// keyboard covers the page rather than shrinking it — on the screen they asked
// for.
let hadKeyboard = false;

const viewport = window.visualViewport;

// What the page is when nothing is over it, and the only number here that is
// remembered rather than read. It can only be taken while nothing has focus:
// measured with a keyboard up it would teach the page that the short screen is
// the whole screen, and the keyboard would never be seen again.
let unobscured = viewport ? viewport.height : 0;

const fit = () => {
  if (!viewport) return;
  document.body.style.height = `${viewport.height}px`;
  transcript.scrollTop = transcript.scrollHeight;
};

// The two facts the sheet reads, from the two above.
function readKeyboard() {
  // Without a visual viewport there is nothing to measure, so focus has to be
  // taken at its word. Every engine that can run this page has one; the arm is
  // here so that an engine that does not can still reach the conversation,
  // which is what the height query used to give it.
  const shrunk =
    !viewport || viewport.height < unobscured * (1 - KEYBOARD_TAKES);
  const up = Boolean(typing) && shrunk;
  // A keyboard over an overlay is still a keyboard: the list of places and the
  // books panel both shrink their rows for one, and either can be up with the
  // player rather than the chat behind it. So this is a separate fact from the
  // screen and not a second name for it.
  document.body.classList.toggle("keyboard-up", up);
  // The keyboard closing under a finger that asked for this screen is the way
  // back to the book, and it is the only way back that costs no press at all.
  // It has to be a keyboard that was really up and has really gone — not simply
  // one that is not up — or the press that opens this screen would be undone by
  // the same measurement a beat later, on every engine slow to raise a keyboard
  // and on every engine that never raises one.
  if (asked && typing === question) {
    if (up) hadKeyboard = true;
    else if (hadKeyboard) stoppedAsking();
  }
  // The morning outranks both of the others, and nothing measurable may take it
  // off the screen: it is not a screen somebody asked for, it is a screen the
  // page owes them until one of its three presses answers it. A keyboard coming
  // up under it — a restored focus, a phone unlocked with the box still live —
  // would otherwise put the conversation over an unanswered morning.
  showScreen(
    waking ? "wake" : asked || (up && typing === question) ? "chat" : "player",
  );
}

viewport?.addEventListener("resize", () => {
  // With nothing focused, nothing is over the page: whatever it is now is what
  // "not obscured" means from here on. A window dragged shorter, a phone turned
  // on its side, a text scale changed under a page left open all night — all of
  // them arrive here, and none of them is a keyboard.
  if (!typing) unobscured = viewport.height;
  fit();
  readKeyboard();
});

// The way ON to the chat screen, and the whole of it: a press on the dock.
//
// Both halves of the dock, because both of them are somebody starting to ask
// something. The box is the obvious one. The microphone is the one that was
// missing entirely — it takes no focus and raises no keyboard, so nothing about
// it could ever be measured, and holding it dictated a question into a
// transcript that was on the other screen. What that looked like was a
// microphone that did nothing at all.
//
// `pointerdown` and not `click`: the finger going down is the moment the page
// should have already changed, and it is before the focus and the keyboard that
// follow it rather than after them, so there is no beat where the screen and
// the finger disagree. It is also what keeps a focus nobody asked for out of
// this — see the focus handler below.
for (const way of [question, talk]) {
  way.addEventListener("pointerdown", () => {
    asked = true;
    hadKeyboard = false;
    readKeyboard();
  });
}

// Nobody is asking any more, whoever said so, and the counterpart of the press
// above. Kept apart from stoppedTyping(): the books panel's box losing focus is
// a keyboard leaving and nothing to do with which screen the page is on.
function stoppedAsking() {
  asked = false;
  hadKeyboard = false;
}

// The way back to the player, as one thing with a name. Three lines, in this
// order, and every route off the chat screen goes through them: forget that they
// asked, give the keyboard back, and say so.
//
// It is a function because the routes are no longer only presses. `‹ controls`
// and the thread are somebody leaving; the two below are the book moving, which
// is the same arrival at the player and must not be a second, slightly different
// copy of these lines — a way back that forgot one of them is a page that goes
// to the book and comes back to the conversation on the next resize.
function backToTheBook() {
  stoppedAsking();
  question.blur?.();
  stoppedTyping();
}

for (const field of typingFields) {
  field.addEventListener("focus", () => {
    // A focus nobody asked for is not a request for anything, which is the same
    // rule the press above is: only somebody's own press means they want this
    // screen. A box can take focus without anybody having touched the page —
    // a browser restoring a document it had put away is the usual way — and the
    // page that carried the book off the screen in that case would be a page
    // that came up on the conversation for somebody who had done nothing but
    // unlock their phone. Nothing here has to be believed about any particular
    // engine for that to be the wrong page to open on.
    //
    // It costs nothing on the way in: pointerdown is what makes a page
    // activated, and it lands before the focus it causes. Engines that cannot
    // say are taken at their word.
    //
    // (This is a guard and not a diagnosis. The reader really did lose the
    // player this way — see the top of this section — but that was a page still
    // deciding the screen from `@media (max-height: 34rem)`, served from a phone
    // cache long after the fix for it had shipped. No restored focus was ever
    // observed doing it, and the way to see whether a page is old rather than
    // wrong is whether the serve log shows it fetching app.js at boot.)
    if (navigator.userActivation?.hasBeenActive === false) return;
    typing = field;
    readKeyboard();
    // The keyboard animates in, so measure again after it has settled.
    setTimeout(() => {
      fit();
      readKeyboard();
    }, 250);
  });
  field.addEventListener("blur", () => {
    // Decided at once rather than waited on. The keyboard animates out over the
    // next fifth of a second and the viewport does not come back until it has,
    // so the player is drawn for that long in a window still short of the room
    // it wants — which is worth it, because a page that waited for a resize
    // that never came on an engine that does not send them would leave somebody
    // stranded on the chat screen, which is the whole of this issue.
    //
    // The composer only. Focus leaving the books panel's search box is a
    // keyboard going down over an overlay, and the page was never on the chat
    // screen for it to be taken off.
    if (field === question) stoppedAsking();
    stoppedTyping();
    setTimeout(() => {
      fit();
      readKeyboard();
    }, 250);
  });
}

// Nobody is typing any more, whoever said so. The box losing focus is one way
// of saying it and the header's `‹ controls` pill is the other, and they have to
// mean the same thing or the page has two ideas of which screen it is on.
function stoppedTyping() {
  typing = null;
  readKeyboard();
}

// The way off the chat screen that is a press rather than a keyboard leaving.
//
// Giving the keyboard back is most of it: on the phone, blurring the composer
// is what takes those letters off the bottom half of the screen, and there is
// no other way to ask for that. But the screen is set here as well rather than
// left to the blur that follows, because a press whose result waits on the
// platform answering is a press that does nothing on the platform that does
// not — and this is the press that exists so that somebody who cannot get the
// keyboard down still has a way back to the book. Both paths end in
// stoppedTyping(), so pressing this and dismissing the keyboard by hand are the
// same event twice and not two states.
//
// It also forgets that they asked, and that is the half that has to be said
// here rather than left to the blur: the screen is a remembered press now, and a
// way out that only gave the keyboard back would hand it straight to a page that
// still believed it was wanted.
toControls.addEventListener("click", backToTheBook);

// The same way out, made out of the biggest thing on the screen.
//
// The thread is a target as well as something to read, which is what the design
// has asked for since the first handoff and what this page never built — because
// while the transport was at the foot of the chat screen there were four ways
// back and this was the least of them. The transport is gone from that screen
// now, and this is the one way back that needs no aiming: a thumb anywhere in
// the top two thirds of the phone.
//
// Through the same three lines as the pill, in the same order, so that pressing
// the corner and pressing the words are one event and not two states.
//
// A drag is not a click, so scrolling back through the conversation does not
// land on the player. And the guard on the screen class is belt to the sheet's
// braces: #transcript is drawn on the chat screen and nowhere else, so on the
// player there is nothing here to press in the first place.
transcript.addEventListener("click", () => {
  if (!document.body.classList.contains("chat-screen")) return;
  backToTheBook();
});

// And neither corner of that screen may take the composer's focus, which is the
// one thing standing between both of them and being pressable at all.
//
// The chain is short and it runs entirely downhill. Focus leaving the box is a
// blur; a blur is stoppedTyping(); stoppedTyping() is the player screen; and the
// player screen is the one the sheet draws neither of these pills on. So a press
// that let the focus move would take the button out of the page between the
// finger going down and the click coming out, and a browser with nothing left
// under the finger hands that click to whatever is behind it. Chrome does
// exactly this, by mouse and by finger alike, and what it looked like was `start
// over` putting the keyboard away and throwing no conversation away at all —
// while every test of it passed, because a test fires the click at the element
// itself and cannot lose it on the way.
//
// Cancelling the mousedown is the whole of the cure: moving the focus is that
// event's default action, on the touch path as well, since the tap's focus
// arrives with the mouse events the phone synthesises after the finger lifts.
// `‹ controls` then blurs the box itself, above, in the order it chooses.
// `start over` leaves the keyboard up and the screen where it was, which is what
// it should do anyway — a thread cleared is a thread about to be asked something
// else.
for (const corner of [toControls, restart]) {
  corner.addEventListener("mousedown", (event) => event.preventDefault());
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
