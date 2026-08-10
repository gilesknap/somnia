# Use the page at night

What the installed app does once it is on the phone: how to ask it things, how
the player behaves under a thumb in the dark, and the three screens behind the
corners. Getting the page onto the phone in the first place is
[Serve the page that plays the book](serve-the-chat-page.md).

## Asking it things

Type, or hold the button and speak — it listens only while held, because a
bedroom is full of speech that was not meant for somnia. Answers are read, not
spoken back: the only thing the page makes a sound with is the book.

The button glows and pulses while it is listening, and the phone buzzes when it
starts and stops. Android's own speech recogniser plays a start and stop tone
that no web page can turn off; silencing it means muting system sounds on the
phone.

Ask to be taken somewhere and the book goes there and plays from there. If the
passage is in a book that was not even open, that book opens. Nothing has to be
pressed afterwards — including nothing to get back to the book. A question is
asked on the conversation and answered by a book that moved, so the page puts
the player back in front of you rather than leaving the seek behind a
transcript. It does that whether you typed the question or held the microphone,
which it did not use to: typed, the keyboard going down took you back by
accident, and spoken there was no keyboard to go down.

Ask it a *question* instead — who Rob Roy is, what became of Ginger, why they
went to London — and it answers in a sentence and leaves the book exactly where
it is. Nothing moves, no list goes up, and the book carries on playing
underneath. It is worth saying because it did not use to be true: every question
was read as *take me somewhere*, so asking who somebody was either put a list of
places on the screen or moved the book to one of them, and cost you the hour you
were in.

When more than one place could be what you meant, it does not ask — it puts
them on the screen. The screen is headed *Places you might be*, with a line
under it saying how many there are and what they span, and each row is a
time, a chapter and the book's own words — its own, never a description of
them, so you recognise the moment rather than take somnia's word for it, and
never the words of a place you have not reached yet, which is the paragraph
after this one. Every row starts covered: press its reading and the words come
up, press it again and they go away, so the list can be read down without ending
up as four paragraphs of book on a phone at 2am. Sitting between the rows in
book order, so you can see which places are behind you and which are ahead,
there is a *you are here* line — and under it, in amber, where you were when you
asked: the time, the words being spoken there behind the same press, and a
*here* button that takes you back to it if you have gone somewhere and it was
wrong. If the book has moved on since — you pressed *goto*, or the sound simply
ran on — the line says *you were here* instead, and the amber time under it is
still the one the *here* button will take you back to. Pressing it takes you
back and starts the book playing there, so by the time you have opened the list
again to look, the sound has moved on and the line reads *you were here* once
more: the button gives the place back, not the tense.
Press *goto* on a row and the book goes there and plays, and the list
goes with it, leaving you on the player looking at where you have arrived. The
line at the foot of the screen names where you landed — *moved to 1:20:20* —
with *undo* beside it for six seconds, which puts you back exactly where the
press found you and says *back where you were*. It is there because *goto* is
the one press in the app that throws a position away, and without it the only
route back is asking again. Anything that moves the book inside those six
seconds takes the offer away and leaves the sentence: a way back holds a
position, not an intention, and after a press of *+30* it would be a fourth move
rather than a way back. After it has gone, the *here* button on the list is the
way back that is left — it remembers where you were when you asked, not where
the book has got to since. Press
*‹ controls* in the top left — the same corner and the same word as the way out
of everything else — and nothing whatever happens: the book carries on exactly
as it was, in the same place, with the same sleep timer running, on the player
the list was standing over. It stands over the player however the question was
asked, so what *‹ controls* gives back does not depend on whether you spoke it. Nothing has
moved while the list is up, so there is nothing to undo. The book keeps playing
underneath it the whole time, which also means a sleep timer left to run out
under a list still ends the night — the list is not a reason to keep the book
going.

It will not answer about a part of the book you have not heard. An answer can
come out of somnia's own reading of the book rather than only out of the passage
it just looked up, and that line is the whole of what bounds it: somebody who
has not turned up yet gets *he hasn't come up yet in what you've heard*, and
nothing after that — not who he is, and not that he arrives later. The bound is
the furthest point the page has actually *played through*, not where you are
now — so being taken back to chapter two does not un-hear chapter twenty, and
being taken forward does not unlock what you were carried over. What you get
instead is that place as a row on the list, marked *ahead*, showing its time
and its chapter number and nothing else — no words, and not even the chapter's
name, since a chapter called *How Ginger Died* gives away as much as the
sentence under it. What it says instead is *tap to reveal · may spoil*: press
anywhere on the row's reading and it uncovers, and you decide having read it;
press it again and it goes back under, name and all; press *goto* and you go
there without reading it at all. Two
things follow from measuring it that way. A book
somnia has never played is bounded at its opening minute, so if a book you have
been listening to for a fortnight puts everything on the list as *ahead*, the
listening happened in Audiobookshelf and somnia does not know about it — run
`somnia seed-positions`. And skipping forward while the sound is on stops the
mark where it was until you come back behind it, which is the price of one
press of *+30* not marking the rest of the book as heard.

Conversations are held in memory, keyed by a token the page mints when it
starts, and nothing is written to disk. *Start over* drops the history when the
agent has got the wrong end of a mumbled question; restarting the service drops
all of them.

## Playing the book

The page opens the book you last had open — the one you were listening to, or
the one you last pressed on the shelf — at the place you left it, or at its
beginning if you have not started it, and does not start it: opening the app at
2am to ask a question is not the same as asking for the book. Press play when
you want it.

To read something else, open *books* and press the book on the shelf — or ask,
which still works and is still the shortest way to say it. There is still no
library of things you do not have to browse: *Workshop*, behind the quiet
*workshop ›* pill in the top-right corner of *Books*, is where a book is
*added*, and its search goes to Gutenberg's catalog rather than to your shelf.

Those two are one screen each on purpose. **Books** is the night screen — which
book — and it is set at the same type size as the player, because it is read in
the same dark without glasses. **Workshop** is the daytime one — find a book,
have it read, watch it being made — and it is smaller and denser than anything
else in the app, because it is read sitting up with the lights on. The three
things you can change about how the app behaves are on a third, **Settings**,
which is a night screen and is reached from the player's top-right corner.

On the page there are three buttons: back thirty seconds, play/pause, forward
thirty seconds — or fifteen, or sixty, if you have said so in *Settings* under
*how far the skip buttons move*; the labels say which. Most nights you will use none of them,
because the screen is off. With the phone locked the book is driven from the
notification, the lock
screen and whatever is paired over Bluetooth: play, pause, back and forward,
previous and next chapter, and a scrubber. The scrubber covers the chapter, not
the book — three minutes to the pixel across a whole novel is no use for the
nudge you actually want, and one sleepy thumb from the ending.

Pressing play again gives you back a little of what you missed, sized by how
long the sound was off: nothing under half a minute, then eight seconds, twenty
after a few minutes, and half a minute after an hour — and that longest one
lands on the start of the sentence you were in rather than in the middle of it.

**The sleep timer is the word *sleep* next to the clock.** Tapping it walks
fifteen, thirty, forty-five and sixty minutes, then the end of the chapter,
then off again, and it always says which it is on. It counts listening time, so
pausing to ask a question does not spend it. It ends in a twenty-second fade
that reaches silence at the time it named; tapping the control during that fade
brings the sound back, on the grounds that anyone reaching for it is awake
enough to have changed their mind. It is written down as it counts, so a reload
— or the phone throwing the app out of memory while it is in the background —
brings it back with the minutes it had left on it. A timer more than six hours
old is not brought back: opening the book the next evening is starting a night,
not finishing one.

**The morning after a fade.** If the night ended in the sleep timer rather than
a thumb, the next launch shows this instead of the player, once. It says the
wall-clock time the sound went and that you were probably gone before that, and
offers three presses: the last query's places, when there were any; *tell me
what you remember*; and keeping the position, with the position written on the
button. There is no way off it but those three, on purpose. A fade more than
twelve hours old is not worth a morning for, and is not shown. The reasoning is
in [Design decisions](../explanations/design.md).

If something else takes the sound — a call, an alarm — the book stops and stays
stopped, and the page says so. If the phone refuses to start audio without
being touched first, the page says *tap anywhere to carry on*, and anywhere
means anywhere.

A book that is still being rendered grows underneath you, and the page keeps
up with it: while the render is running it asks again for the chapter list —
when the audio runs out, and whenever you come back to the app — and carries
on into whatever has landed since. Open one that is three chapters in and it
will play those three, say *waiting for the next chapter to be read*, and go
on when chapter four arrives. A book with nothing rendered at all says *the
first chapter is still being read*, and the player appears when that chapter
lands — already playing if the agent took you to that book, waiting to be
pressed if you only opened the app. A book whose render is not running and has
no audio at all says *nothing yet — press books, then Workshop, to add one*,
which is also
what a somnia with no books in it says.

When a render stopped part way — you stopped it, or a reboot did — the audio
runs out mid-book, and the page says *the rest of this book hasn't been read
yet* rather than *that is the end of the book*. It knows the difference because
the parse writes down how many chapters the book has, so a book three chapters
into thirty-nine is tellable from one that is over. Nothing ends: the sleep
timer keeps counting and the page keeps wanting the sound. Queue the book
again — from *Workshop*, or by asking — and it picks up at the chapter after the
last finished one.

When the tailnet goes — wifi power save and a tailscale re-key both do it for a
few seconds — the page says *the book stopped arriving* and keeps trying,
waiting longer between attempts up to half a minute, and puts the chapter back
where you had got to rather than at the top of it. Opening the app while the
server is unreachable says *couldn't reach the book — trying again*, and does.
It stops the moment you pause — nothing reloads chapters under a book somebody
has put down — and waking the phone, or the wifi coming back, makes it try
again at once, so there is nothing to press.

## Choosing a book: *Books*

*books*, in the top left corner, opens a panel over the page. The book keeps
playing underneath it, and *‹ controls* puts it away having changed nothing at
all. What does change something is tapping a book — the one at the top, which
starts the book already open, or one on the shelf, which opens that one. No book
on this screen carries a button of its own: opening one is the same gesture
wherever it is in the list.

It is a night screen, and everything on it is set at the player's own type size
for that reason: it is read in the same dark, at the same arm's length, by
somebody who has taken their glasses off. It asks one question — *what shall I
listen to* — and nothing that is not part of that answer is on it. It asks the
server for one thing, once, when it opens: which books there are. It schedules
no wake and polls nothing, so a night spent looking at it is a night with no
radio traffic in it.

At the top, under *reading now*, is the book that is playing underneath the
panel — *The Moonstone* in amber, the only amber title in the app, and under it
*chapter 4 of 37 · picks up at 1:12:08* over a hairline showing how far through
it you are. The time is where a tap would land you; while the book is actually
sounding the heading reads *playing now* and the line ends *· playing*, because
then there is nothing to start. The hairline is not drawn at all while the book
is still being rendered, because until the render is over the book's length is
only how much of it exists so far. Tapping the block starts it and puts the
panel away — the same press as the play button, made from up here.

Under it, *on the shelf* is every other book somnia has, each with where you
left it — *0:27:42 in*, or *not started*. Tapping a row opens that book at that
place and takes the panel away with it. Changing your mind costs one press back:
nothing is written to the book you left, so it is still exactly where it was,
and so is the one you looked at. A book still being rendered says so and is not
a press at all until its first chapter exists, because until then there is
nothing to play. A book whose render stopped part way says *part rendered* and
can still be opened — what was read plays. If the box cannot be reached, the
shelf you last saw stays on screen with *couldn't reach somnia* under it: an
empty shelf and an unreachable server look identical and mean opposite things.

The rows say the title and nothing else — no author, no dates, no cover. At this
size the catalogue's *Title — Surname, Forename, dates* is three lines of a
phone, and it is metadata about a book you already own and chose. The title is
what you recognise a book you own by. Who wrote it appears in *Workshop*, where
you are choosing among seventy thousand you do not.

The way to *Workshop* is a quiet *workshop ›* pill in this screen's own
top-right corner, opposite *‹ controls*. Nothing behind it is a job for 2am,
which is why it is drawn no louder than the way back — but it is not at the
bottom of the shelf either. It used to be, and on a twenty-book library that
meant scrolling past every book on the screen to reach the one thing on it that
is not about books.

*how dark* used to sit under the shelf. It is on *Settings* now, which is a
night screen too, so nothing it needed is lost — and this screen is back to
answering one question with nothing on its scroll but books.

## Adding a book, and watching it made: *Workshop*

*workshop ›*, in the top-right corner of *Books*, and reachable no other way. *‹ books* comes back, and *Books* is exactly where you left it.

This is the daytime screen and it is denser than anything else in the app,
because it is read sitting up with the lights on — denser, and brighter. It is
drawn in its own ink rather than the night palette: fuller cream, stronger
hairlines, a lifted amber, and the sheet of black the rest of the app is read
through comes off entirely while it is up. Every alpha in the night scale was
chosen for a dark room, and in daylight those same values are not quiet, they
are gone. Nothing on it goes below 16dp. It asks one question too: *get me a new
book, and tell me it worked*. The order down it is that sentence.

At the top, under *project gutenberg*, is the search. Under the results is what
is happening, in a box headed *the server is working* — on the same screen and
directly beneath them on purpose, because somebody who has just pressed *add
this book* wants to see it being made, and splitting the press from its
consequence is how the same book gets added twice. The box holds the book being
rendered, with *narrating* in the corner of its line
and, under the name, which chapter it is on and how much of it can be played
now — *chapter 4 of 39 · 1h12m read so far* — over a hairline that fills as the
chapters land. Under it is whatever is waiting, marked *queued*, saying how far
down the line it is. One book renders at a time, always, so a queue of three is
three books' worth of waiting and not three renders fighting over two cores.

The word in the corner is the stage — *queued*, *narrating*, *ready*, *failed*,
*stopped* — and the line under the name is what is actually going on inside it.
A book whose text has not been parsed yet has no hairline at all rather than one
sitting at nothing: until the parse has run, nobody has written down how many
chapters there are, and the line says *fetching the text* instead of counting.
The box is not drawn at all when nothing is rendering.

A render that has not been heard from for five minutes says *not responding*
instead of pretending. That is a real answer: it means the worker died, or the
box did, or nobody ever started `somnia-worker`. Check
`journalctl --user -u somnia-worker`.

Under those are the renders that ended in the last day, and a failed one says
why in a sentence — *Gutenberg has book 4321 but no HTML edition, so somnia
cannot read it*. They go away by themselves after a day. There is nothing to
dismiss and no badge or count anywhere: a book finishing at 3am is
not news to somebody asleep, and it is on a screen nobody opens at 3am.

Searching is the top of this screen, and it is what you came here for: type part
of a title or an author and press *find*. That searches
the copy of the Gutenberg catalog on this machine, so it answers in the time a
tap takes and works with the internet down — run `somnia catalog-update` if a
book you know exists is not in it. A book somnia already has, or already has
coming, is marked and offers no button; a render that died is marked *part
rendered* and offers *finish this one*, which picks it up at the chapter after
the last finished one.

*add this book* does not queue it. It opens *read in* under that row — the
voices somnia can read it in, one pill each, with *add it* underneath — and the
same press closes it again, so the way back is the button your thumb is already
on. Pressing a name plays a few seconds of it: the same line of *Black Beauty*
in every voice, so what you are comparing is the voice and not the sentence. If
the book is playing it is paused first, and stays paused — two things reading
aloud at once is the one thing worth avoiding here, and starting the book again
under somebody who is still choosing is worse than leaving the play button where
they can find it. The last voice you chose is the one the next book opens on, so
the second book of an evening is two presses.

It is asked here, and only here, because a book is read by one narrator and
cannot be re-read by another: every timestamp somnia holds — chapter marks,
index entries, the place you fell asleep — was measured against the audio that
was actually made. *finish this one* therefore offers no choice at all and picks
the book up in the voice it started in.

*add it* queues it, and the sentence underneath is the server's own — the same
sentence the agent says when you ask it out loud. The row it makes says which
voice, beside its place in the line, while taking it out again still costs
nothing.

*stop reading this* takes two presses, and the second one only asks. The render
stops at the end of the sentence it is reading, about twenty seconds later,
which is what keeps every chapter that was finished playable and stops the
index filling up with half a chapter. The row stays as the record of a render
somebody stopped.

*Workshop* asks the server how things are going every five seconds while it is
open, and stops the moment it is closed or the phone goes in a pocket. Nothing
about the queue is polled otherwise — and since this is the only screen the
queue is on, and it is two presses from the player behind a row that says
*daytime*, no night has a five-second wake in it.

*Workshop* holds no settings. They are all on *Settings*, below.

## Changing how it behaves at night: *Settings*

*settings ›* in the top-right corner of the player — the corner that had been
empty since *start over* moved to the chat screen. *‹ controls* comes back.

It is a night screen in the night palette, which is the point of it rather than
a default: all three controls on it are reached for in the dark with the book
playing, and none of them can be had from the phone's own settings.

*how big the words* moves the page's root size, so the words and the space
around them go together and the player's rhythm survives being resized. It
moves every screen, not only this one. It is somnia's answer to browser zoom,
which is several screens into Chrome and retunes every app on the phone — this
is one press from the player and moves nothing but somnia.

*how dark the room* takes the page darker than the phone's own minimum
brightness, by laying black over everything. Press *–* or *+* and the screen you
are looking at gets lighter or darker as you watch — the layer is over this
screen too, which is why it has to be set on a screen read in the dark. It goes
from nothing to rather dark in ten presses, and it cannot go dark enough to hide
itself.

*how far the skip buttons move* — fifteen, thirty or sixty seconds — is what the
two buttons either side of play mean, and what they say. It was in *Workshop*,
on the argument that a thing set once is daytime configuration. That is wrong
about when it is discovered: nobody decides thirty seconds is the wrong distance
sitting up in daylight, they decide it lying in the dark with a narrator who
leaves long gaps, having missed the same sentence twice.

All three are written down and outlive the page. The sleep timer is the one
setting that is not: it expires after six hours, because a timer is an intent
about one night.
