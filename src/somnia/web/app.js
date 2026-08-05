// The 2am client. Push to talk, let go, get taken back to the passage.
//
// Speech recognition is push-to-talk rather than always-listening on purpose:
// a bedroom is full of speech that was not meant for somnia, and holding a
// button is the one gesture that survives being half asleep.
//
// The book plays here as well. somnia rendered it one file per chapter, but
// nobody listens to a chapter — they listen to a book — so everything below
// counts in global milliseconds, the same clock the search results and the
// agent speak, and which file that lands in is an implementation detail kept
// to three functions.

const transcript = document.getElementById("transcript");
const composer = document.getElementById("composer");
const question = document.getElementById("question");
const talk = document.getElementById("talk");
const restart = document.getElementById("restart");
const statusLine = document.getElementById("status");
const player = document.getElementById("player");
const playerBar = document.getElementById("player-bar");
const chapterTitle = document.getElementById("chapter-title");
const clock = document.getElementById("clock");
const playpause = document.getElementById("playpause");
const back30 = document.getElementById("back30");
const fwd30 = document.getElementById("fwd30");

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

// Answers are read, never spoken. Nothing here makes a sound: the phone is on
// a bedside table next to someone who may be asleep again by the time the
// answer lands.
function setStatus(text) {
  statusLine.textContent = text;
}

// A short buzz confirms the button caught the press, for a listener who can't
// see much and shouldn't be listening for a beep. Android honours this; iOS
// ignores it, which is why the button also changes colour and pulses.
function buzz(ms) {
  navigator.vibrate?.(ms);
}

async function ask(text) {
  if (!text) return;
  say(text, "you");
  question.value = "";
  const pending = say("…", "agent pending");
  const asked = token;
  setStatus("thinking…");
  try {
    const response = await fetch("api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token, question: text }),
    });
    const body = await response.json();
    // They started over while this was in flight: the answer belongs to a
    // conversation that no longer exists, and appearing now would be a reply
    // to a question no longer on the screen.
    if (token !== asked) return;
    if (!response.ok) throw new Error(body.error || "no answer");
    pending.className = "said agent";
    pending.textContent = body.reply || "…nothing to say.";
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

restart.addEventListener("click", async () => {
  const stale = token;
  token = crypto.randomUUID();
  sessionStorage.setItem("somnia-token", token);
  fetch("api/forget", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token: stale }),
  }).catch(() => {});
  transcript.replaceChildren();
  setStatus("");
  say("Where do you want to be?", "agent");
  question.focus();
});

// ------------------------------------------------------------------- playing

// How early to start the next chapter. Ingest leaves 500ms of rendered silence
// at the end of every one, so a swap that begins 400ms out is spent inside a
// pause the book already had: the gap between chapters comes out shorter than
// it was written to be rather than longer. Raise this only if the silence
// ingest appends rises with it.
const SWAP_LEAD_S = 0.4;

// What "back a bit" means, in the absence of anyone able to say.
const SEEK_STEP_S = 30;

let manifest = null;
let current = null; // {idx, chapter} — which file the element is holding
let positionMs = 0;
// Where to land once the file has a duration to clamp against. It stays set
// until it is applied, so a loadedmetadata that arrives four minutes late —
// after the tailnet came back — still lands in the right place instead of
// starting the chapter from nothing.
let pendingOffsetMs = null;
let swapping = false; // a chapter change is in flight
let weArePausing = false; // tell our own pause from the platform's

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
  // fires `ended` at once, which silently skips a whole chapter. The render
  // clock can legitimately exceed the container clock, so this is not
  // hypothetical.
  return Math.min(s, duration - 0.05);
}

// Where the element is, on the book's clock. Clamped to this chapter's own
// span: a decoder that ignores the edit list runs up to one AAC frame past what
// was rendered, and a position reported from inside that padding would claim to
// be in the next chapter.
function toGlobalMs(chapter, currentTime) {
  const t = chapter.start_ms + Math.round(currentTime * 1000);
  return Math.max(chapter.start_ms, Math.min(t, chapter.end_ms));
}

// h:mm:ss, the same shape format_timestamp gives the agent, so what is on the
// screen and what somnia says out of the model agree to the second.
function timestamp(ms) {
  const seconds = Math.floor(Math.max(0, ms) / 1000);
  const mm = String(Math.floor(seconds / 60) % 60).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${Math.floor(seconds / 3600)}:${mm}:${ss}`;
}

function drawPlayer() {
  if (!manifest || !current) return;
  chapterTitle.textContent = current.chapter.title;
  const whole = timestamp(manifest.total_ms);
  clock.textContent = `${timestamp(positionMs)} of ${whole}`;
  playpause.textContent = player.paused ? "▶" : "⏸";
  playpause.setAttribute("aria-label", player.paused ? "Play" : "Pause");
}

// A chapter boundary and a seek into another chapter are the same thing, so
// they are the same code path.
function showChapter({ idx, chapter, offset_ms }, { play }) {
  swapping = true;
  current = { idx, chapter };
  pendingOffsetMs = offset_ms; // applied at loadedmetadata, when there is
  player.src = chapter.url; // a duration to clamp against
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
  const at = locate(ms);
  positionMs = Math.max(0, Math.min(ms, manifest.total_ms));
  if (current && at.idx === current.idx && player.readyState > 0) {
    // Within the file already loaded. This branch is what keeps autoplay policy
    // out of the common case: a seek on a live element needs no permission at
    // all, so it does not ask for any.
    player.currentTime = toElementSeconds(at.offset_ms, player.duration);
    if (play === true && player.paused) player.play().catch(onPlayRejected);
  } else {
    showChapter(at, { play: play ?? !player.paused });
  }
  drawPlayer();
}

function ensurePlaying() {
  player.play().catch(onPlayRejected);
}

function pauseHere() {
  weArePausing = true;
  player.pause();
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
  setStatus("tap anywhere to carry on");
  document.addEventListener("pointerdown", () => ensurePlaying(), {
    once: true,
  });
}

player.addEventListener("loadedmetadata", () => {
  if (pendingOffsetMs !== null) {
    player.currentTime = toElementSeconds(pendingOffsetMs, player.duration);
    pendingOffsetMs = null;
  }
  swapping = false;
  drawPlayer();
});

player.addEventListener("timeupdate", () => {
  // While a swap is in flight currentTime can still be reading from the
  // chapter being left, which would report a position they are no longer at.
  if (swapping || !current) return;
  positionMs = toGlobalMs(current.chapter, player.currentTime);
  drawPlayer();

  const next = manifest.chapters[current.idx + 1];
  const left = player.duration - player.currentTime;
  if (next && !player.paused && Number.isFinite(left) && left <= SWAP_LEAD_S) {
    showChapter(locate(next.start_ms), { play: true });
  }
});

player.addEventListener("seeked", () => {
  if (swapping || !current) return;
  positionMs = toGlobalMs(current.chapter, player.currentTime);
  drawPlayer();
});

player.addEventListener("play", drawPlayer);

player.addEventListener("pause", () => {
  // A pause means four different things and only one of them is theirs.
  // Assigning src runs the media element load algorithm, which fires one;
  // reaching the end of a chapter fires one before `ended`, per spec; and a
  // chapter that fails to load fires `error` and then a pause after it.
  // Treating any of those as the listener stopping announces that something
  // took the sound at every chapter boundary, and writes that over the true
  // reason in the one case where there is a true reason to give.
  if (swapping || player.ended || player.error) return;
  drawPlayer();
  if (!weArePausing) {
    // Audio focus went elsewhere: a call, an alarm, another app. Do not
    // resume. An alarm should stop the book, not be talked over.
    setStatus("something else took the sound");
  }
  weArePausing = false;
});

player.addEventListener("ended", () => {
  // The backstop. The lead above normally takes the boundary first; this is
  // for a chapter whose duration never became a number, or a file that runs
  // out sooner than the database says it should. `ended` decides that a
  // chapter is over, never the clock: a truncated encode becomes a skip rather
  // than a book that hangs at 2am.
  if (swapping || !current) return;
  positionMs = current.chapter.end_ms;
  const next = manifest.chapters[current.idx + 1];
  if (next) {
    showChapter(locate(next.start_ms), { play: true });
    return;
  }
  setStatus("that is the end of the book");
  drawPlayer();
});

player.addEventListener("error", () => {
  // Whatever went wrong, the state machine must not be left mid-swap: with
  // `swapping` stuck on, every later boundary would be ignored.
  swapping = false;
  pendingOffsetMs = null;
  setStatus("that chapter didn't arrive");
  drawPlayer();
  console.error(player.error);
});

playpause.addEventListener("click", () => {
  if (player.paused) ensurePlaying();
  else pauseHere();
});
const nudge = (seconds) => seekGlobal(positionMs + seconds * 1000);
back30.addEventListener("click", () => nudge(-SEEK_STEP_S));
fwd30.addEventListener("click", () => nudge(SEEK_STEP_S));

async function openBook(id) {
  const response = await fetch(`api/book/${id}`);
  if (!response.ok) throw new Error(`no book ${id}`);
  manifest = await response.json();
  if (!manifest.chapters.length) {
    // Rows but no audio: the book is still rendering, or the render died.
    setStatus("nothing to play yet");
    return;
  }
  positionMs = manifest.position_ms ?? 0;
  playerBar.hidden = false;
  // Never play on load. Opening the app at 2am to ask a question must not
  // start the book.
  showChapter(locate(positionMs), { play: false });
}

async function openTheBook() {
  try {
    const response = await fetch("api/books");
    if (!response.ok) throw new Error("no book list");
    const listing = await response.json();
    const chosen = listing.last_gid ?? listing.books[0]?.gid;
    if (chosen === undefined) {
      setStatus("nothing rendered yet");
      return;
    }
    await openBook(chosen);
  } catch (error) {
    setStatus("couldn't reach the book");
    console.error(error);
  }
}

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

// ------------------------------------------------------------------ keyboard

// Not every browser shrinks the page for the on-screen keyboard, and the ones
// that do disagree about when. Following the visual viewport keeps the
// composer above the keyboard and the transcript scrollable to both ends.
const viewport = window.visualViewport;
if (viewport) {
  const fit = () => {
    document.body.style.height = `${viewport.height}px`;
    transcript.scrollTop = transcript.scrollHeight;
  };
  viewport.addEventListener("resize", fit);
  // The keyboard animates in, so measure after it has settled.
  question.addEventListener("focus", () => setTimeout(fit, 250));
  question.addEventListener("blur", () => setTimeout(fit, 250));
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
