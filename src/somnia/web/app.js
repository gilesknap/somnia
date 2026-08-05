// The 2am client. Push to talk, let go, get taken back to the passage.
//
// Speech recognition is push-to-talk rather than always-listening on purpose:
// a bedroom is full of speech that was not meant for somnia, and holding a
// button is the one gesture that survives being half asleep.

const transcript = document.getElementById("transcript");
const composer = document.getElementById("composer");
const question = document.getElementById("question");
const talk = document.getElementById("talk");
const restart = document.getElementById("restart");
const statusLine = document.getElementById("status");

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

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
