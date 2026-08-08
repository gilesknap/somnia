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
replaced: a window nobody was typing in, or an OS text scale one notch up, put
the page on the chat screen with the player gone. app.js measures the keyboard
now and writes the screen onto <body>, and app.js is exactly what a snapshot
drops. So `--height 470` alone photographs a squashed player, and the chat screen
is `--screen chat --height 470`.
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
