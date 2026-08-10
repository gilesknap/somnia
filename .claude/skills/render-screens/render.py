"""Screenshot a page at the phone it is actually read on.

The measure is the whole point of this file. somnia is read on a Pixel 6 Pro
with the display size turned up, because it is read without glasses in the dark
— so the effective viewport is about 360x780 CSS px, not the 412x892 a stock
device emulation gives you. Every line is roughly a third wider in practice than
a default render shows, and a layout that fits at the stock measure can overflow
on the actual phone.

**The width is the setting; the root follows from it.** `style.css` takes its
root from the screen — `min(100vw, 460px) / 18`, because the design is 360 CSS
px across at a 20px root and 360/20 is 18 — so a render at a given width gets
the root the phone would have at that width, with nothing injected. This file
therefore injects **no root at all** unless `--root` is passed on purpose. It
used to inject 20px always, which was right at 360 and quietly wrong everywhere
else: it drew a phone with the design's type at a viewport the design's type was
never sized for.

`--root` survives for asking what-if, and `--text-size` models the reader's own
control on Settings, which multiplies that root.

The keyboard genuinely shrinks the viewport rather than covering it, because the
page asks for `interactive-widget=resizes-content`. So the page with a keyboard
up is not a crop of the page without one: it is the same document at 360x470,
on the other of the page's two screens.

Which screen has to be *said* here, and this is the part that changed. It used to
follow from the height alone — the sheet asked `@media (max-height: 34rem)` and
took a short window to mean a keyboard — and that guess is the bug this argument
replaced: a window nobody was typing in put the page on the chat screen with the
player gone. app.js measures the keyboard now and writes the screen onto <body>,
and app.js is exactly what a snapshot drops. So `--height 470` alone photographs
a squashed player, and the chat screen is `--screen chat --height 470`.

**Whether there is room for the reading is measured too, and this file derives
it.** app.js compares the height with nothing over it against 32 of the page's
own roots and writes `short-page`; the sheet hides the reading on that class. It
used to be a media query, and a media query's `rem` is the browser's 16px and
never the page's root, which is issue #65. There is no `--short` flag: the width,
the height, the root and the text size are all known here, so the class is worked
out from them. A short render that had forgotten a flag would photograph a player
the phone would never draw, and be believed. A keyboard render is judged by the
height with nothing over it, because that is what app.js judges by: `--keyboard
--height 470` is a picture of the design's phone with a panel over it, not a
picture of a phone with no room in it.
"""

import argparse
import pathlib
import subprocess

WIDTH = 360
HEIGHT = 780
KEYBOARD_HEIGHT = 470

# The design's own metric, and the only number here that came from the brief:
# 360 CSS px across at a 20px root is a page 18 rem wide. `style.css` divides by
# it, and anything in this skill that needs to know what root a width implies
# divides by it too, rather than keeping a second copy of the answer.
REM_WIDE = 18

# Past this the root stops growing with the window: `min(100vw, 460px)` in
# style.css, because 460 is about as wide as a phone gets and holding the size
# is kinder than honouring the ratio on a desktop.
ROOT_CAP = 460

# How many of its own roots the player needs to draw the reading without the
# book's title landing on the clock. `PLAYER_NEEDS_ROOTS` in app.js, which is
# where the class this derives is really written.
#
# Stamping the class is not the same as hiding the reading: style.css asks this
# only of a window under 460 across or under 540 tall, so a render of a laptop
# window carries the class and keeps the whole reading, exactly as the page does.
PLAYER_NEEDS_ROOTS = 32

# And how many it needs before the two headings give up their second line.
# `TITLE_NEEDS_ROOTS` in app.js. Under this the clamp goes to one line and the
# ellipsis lands where it can be seen; over it, and under `PLAYER_NEEDS_ROOTS`,
# the whole reading goes instead.
TITLE_NEEDS_ROOTS = 34


def effective_root(width, root=None, text_size=None):
    """The root the page would have at this width, or the one being forced."""
    if root is not None:
        return root
    return (text_size or 1) * min(width, ROOT_CAP) / REM_WIDE


def overrides(root=None, text_size=None):
    """The one <style> that makes a render ask a question the page would not.

    Empty by default, which is the point: the page works its own root out from
    the width, so a render with nothing injected is the phone at that width.
    """
    rules = []
    if root is not None:
        rules.append(f"html {{ font-size: {root}px; }}")
    if text_size is not None:
        # What `how big the words` writes. app.js sets it inline; a snapshot has
        # no app.js, and a later rule of equal specificity beats the sheet's own
        # default, so a plain block is the same thing said a different way.
        rules.append(f":root {{ --text-size: {text_size}; }}")
    return f"<style>{' '.join(rules)}</style>\n" if rules else ""


# What app.js would have put on <body>. The chat screen carries `keyboard-up` as
# well because that is the only route onto it: the two overlays read that class
# on its own, so a books panel with the keyboard up over the player is
# `--screen player --keyboard`.
#
# The morning is the third, and the one that is neither measured nor pressed:
# app.js reads the record the sleep timer's fade left and opens on this screen
# instead of the player. It carries no keyboard — there is nothing to type into,
# and the header is off it as well.
SCREENS = {
    "player": ["player-screen"],
    "chat": ["chat-screen", "keyboard-up"],
    "wake": ["wake-screen"],
}


def render(
    src,
    out,
    width=WIDTH,
    height=HEIGHT,
    root=None,
    screen="player",
    keyboard=False,
    text_size=None,
):
    src, out = pathlib.Path(src), pathlib.Path(out)
    classes = SCREENS[screen] + (["keyboard-up"] if keyboard else [])
    # And whether there is room to draw the reading in, which app.js measures and
    # a snapshot has no app.js to measure it with. Derived from the four numbers
    # this script already has rather than offered as a flag: a flag is a thing
    # that gets forgotten, and a short render that forgot it would photograph a
    # player with the whole reading in it that the phone would never draw — which
    # is the render that would have hidden issue #65 rather than found it.
    #
    # Against the height with nothing over it and not against `--height`, because
    # that is the height app.js judges by: it holds `unobscured` still while
    # anything has focus, so a keyboard shortens the window and moves this class
    # not at all. Derive it from `--height` instead and `--keyboard --height 470`
    # stamps `short-page` on a picture of a phone that has no such class — a
    # player with the reading gone that the phone would draw in full behind the
    # panel. That is the same conflation of a keyboard with a page out of room
    # that this whole pass exists to undo, in the only tool anyone has to check
    # the pass. The height with nothing over it is taken to be the design's own
    # phone, which is the only phone this skill knows the full height of.
    #
    # So a keyboard render is judged against 780 whatever `--height` says, and
    # that is a limit rather than an instruction: on a keyboard render `--height`
    # means the shortened window, and the full height it was shortened *from* is
    # a second number this script is never told. Photographing another device's
    # keyboard correctly would need that number as its own flag. There is no
    # such flag, and until there is, a keyboard render of anything but the
    # design's phone gets this class from the design phone's height.
    unobscured = HEIGHT if (keyboard or screen == "chat") else height
    roots = unobscured / effective_root(width, root, text_size)
    if roots < PLAYER_NEEDS_ROOTS:
        classes.append("short-page")
    # The step before that one: room for the headings but not for their second
    # line. Derived here for the same reason and with more force, because the
    # failure it prevents is one a render is the only way to see — a heading cut
    # horizontally through the letters looks like a broken font, and a picture
    # taken without this class is a picture of that bug rather than of the page.
    if roots < TITLE_NEEDS_ROOTS:
        classes.append("title-one-line")
    # Anything being forced is injected rather than edited into style.css: what
    # is being photographed has to stay byte-for-byte the page that ships.
    scaled = src.with_name(f".scaled-{src.name}")
    scaled.write_text(
        src.read_text()
        .replace("</head>", f"{overrides(root, text_size)}</head>")
        # Last thing in the body, so it lands after the snapshot's own fill
        # script has set the default screen rather than before it. The scroll
        # belongs here and not in the fill for the same reason: the conversation
        # is display:none until the screen is named, so a scroll taken before
        # this line is a scroll of a box with nothing in it, and the render comes
        # out showing the top of a thread the phone is showing the bottom of.
        # app.js scrolls it on every resize; app.js is what a snapshot drops.
        #
        # Scrolled twice, and the second one is the one that matters. Newsreader
        # arrives as a data URI and swaps in when it is ready, which changes how
        # tall the thread is — so a scroll taken before that lands on a height
        # that is about to be wrong, and the chat render comes out a line and a
        # half short. It was reproducible rather than random, which is worse:
        # adding any element to <head> shifted the moment and silently moved
        # every chat render with it. Waiting on `fonts.ready` makes the picture a
        # fact about the page instead of about what else was in the document.
        .replace(
            "</body>",
            f"<script>document.body.className = {' '.join(sorted(set(classes)))!r};"
            "const said = document.getElementById('transcript');"
            "const bottom = () => { if (said) said.scrollTop = said.scrollHeight; };"
            "bottom();"
            "if (document.fonts) document.fonts.ready.then(bottom);"
            "addEventListener('resize', bottom);"
            "setTimeout(bottom, 600);</script>\n</body>",
        )
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "google-chrome",
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--screenshot={out}",
                f"--window-size={width},{height}",
                # Retina, so the type in the PNG can be read and judged.
                "--force-device-scale-factor=2",
                # Long enough for layout and any injected fill script to settle.
                "--virtual-time-budget=1500",
                str(scaled),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        scaled.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--width", type=int, default=WIDTH)
    ap.add_argument(
        "--height",
        type=int,
        default=HEIGHT,
        help=f"{HEIGHT} with no keyboard, {KEYBOARD_HEIGHT} with one up",
    )
    ap.add_argument(
        "--root",
        type=float,
        default=None,
        help="force a root in px; omit and the page takes it from --width",
    )
    ap.add_argument(
        "--text-size",
        type=float,
        default=None,
        help="the reader's own control on Settings: 0.8-1.2, shipping at 1",
    )
    ap.add_argument(
        "--screen",
        choices=sorted(SCREENS),
        default="player",
        help="which screen the page is on; chat implies a keyboard",
    )
    ap.add_argument(
        "--keyboard",
        action="store_true",
        help="a keyboard up over whichever screen — what the overlays shrink for",
    )
    a = ap.parse_args()
    print(
        render(
            a.src, a.out, a.width, a.height, a.root, a.screen, a.keyboard, a.text_size
        )
    )
