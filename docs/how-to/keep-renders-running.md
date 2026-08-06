# Keep a long render running

`somnia add` is hours of work in the foreground. Close the terminal and it dies
with the session, and a render that dies is expensive: there is no resume, so
starting it again starts it at chapter one
([#11](https://github.com/gilesknap/somnia/issues/11)).

Before starting one, check the machine can actually finish it:

```bash
bash somnia-doctor.sh
```

ffmpeg, espeak-ng and a CPU torch all have to be there, and a book needs roughly
30MB of disk an hour at the default bitrate.

## As a systemd user service

A render is a job with an end, not a daemon, so it wants a **template** unit —
one file, any book, named by its Gutenberg id:

```ini
# ~/.config/systemd/user/somnia-render@.service
[Unit]
Description=somnia render of Gutenberg book %i
After=network-online.target

[Service]
Type=oneshot
EnvironmentFile=%h/somnia.env
ExecStart=%h/somnia-venv/bin/somnia add %i
# A oneshot unit is killed after 90 seconds by default, and this one runs for
# hours. Without this line the render is shot in the head just after it starts
# on chapter one, and systemd calls that a timeout rather than a failure.
TimeoutStartSec=infinity
```

```bash
loginctl enable-linger $USER            # survive logging out
systemctl --user daemon-reload
systemctl --user start --no-block somnia-render@271
journalctl --user -u somnia-render@271 -f
```

`--no-block` matters: starting a oneshot unit otherwise waits for it to finish,
which here is most of the night.

**Do not add `Restart=`.** A render that failed part way and is restarted
automatically begins again at chapter one and adds a second copy of every
passage to the index — the same [#11](https://github.com/gilesknap/somnia/issues/11).
Until that is fixed, a failed render is something to look at, not something to
retry blindly.

## Or in tmux

```bash
tmux new -s render 'somnia add 271'
tmux attach -t render
```

Fine for one book you are watching. The unit is better for anything you want a
journal of afterwards.

## Renders the agent starts

When `serve` is running, the agent can start a render itself: asked for a book
that is not there, it spawns the same `somnia add` in the background, detached,
and answers immediately. Two things follow from how it is spawned.

Its output goes nowhere — not the journal, not a file — so an agent-started
render leaves no trace beyond one line in the server's own log saying it began.
If you want a log of a particular render, start it yourself with the unit above.

And it refuses to start a book somnia already has, in any state, so an agent
cannot be talked into the duplicate-index problem by being asked twice.

## Watching one

```bash
journalctl --user -u somnia-render@271 -f
somnia find 271 "any phrase from an early chapter"
```

The second is the real check, and the more interesting one: it only answers once
a chapter has been rendered *and* indexed, so it tells you the pipeline is
working end to end rather than that a process is alive. The page will already be
playing chapter one by then — a book is listenable while the rest of it is still
being read.
