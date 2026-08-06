[![CI](https://github.com/gilesknap/somnia/actions/workflows/ci.yml/badge.svg)](https://github.com/gilesknap/somnia/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/gilesknap/somnia/branch/main/graph/badge.svg)](https://codecov.io/gh/gilesknap/somnia)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

# somnia

Bedtime audiobook reader with semantic seek: TTS-rendered public-domain books plus a conversational agent that finds your place again

You fall asleep to an audiobook, wake at 2am somewhere unfamiliar, and have no
idea how far back the last thing you remember was. somnia renders Project
Gutenberg books to audio itself — which means it knows exactly which span of
audio every sentence occupies — and puts a conversation in front of that index.
Say *"go back to where the horse gets hurt"*, half asleep and in the dark, and
the book goes there and plays from there. Nothing to press afterwards.

It will not tell you anything from a part of the book you have not heard yet.
That bound is measured from audio that really came out of the speaker, so being
carried forward does not unlock the ending.

```bash
somnia add 271                      # render + index a Gutenberg book
somnia find 271 "the horse is beaten in the street"
somnia serve                        # the page that plays it, and the agent
```

The page is the player: an installable PWA served over your tailnet, with a
sleep timer, lock-screen controls and a rewind sized by how long the sound was
off. There is no login — reachability is the authentication.

What            | Where
:---:           | :---:
Source          | <https://github.com/gilesknap/somnia>
Docker          | `docker run ghcr.io/gilesknap/somnia:latest`
Documentation   | <https://gilesknap.github.io/somnia>
Releases        | <https://github.com/gilesknap/somnia/releases>

<!-- README only content. Anything below this line won't be included in index.md -->

See https://gilesknap.github.io/somnia for more detailed documentation.
