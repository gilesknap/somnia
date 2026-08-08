"""Screenshot a page at the phone it is actually read on.

The measure is the whole point of this file. somnia is read on a Pixel 6 Pro
with Android's text scaling turned up, because it is read without glasses in the
dark — so the effective viewport is about 360x780 CSS px with a 20px root, not
the 412x892 at 16px a stock device emulation gives you. Every line is roughly a
third wider in practice than a default render shows, and a layout that fits at
the stock measure can overflow on the actual phone.

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
ROOT = 20

# What app.js would have put on <body>. The chat screen carries `keyboard-up` as
# well because that is the only route onto it: the two overlays read that class
# on its own, so a books panel with the keyboard up over the player is
# `--screen player --keyboard`.
SCREENS = {"player": ["player-screen"], "chat": ["chat-screen", "keyboard-up"]}


def render(
    src, out, width=WIDTH, height=HEIGHT, root=ROOT, screen="player", keyboard=False
):
    src, out = pathlib.Path(src), pathlib.Path(out)
    classes = SCREENS[screen] + (["keyboard-up"] if keyboard else [])
    # The root font is injected rather than edited into style.css: what is being
    # photographed has to stay byte-for-byte the page that ships.
    scaled = src.with_name(f".scaled-{src.name}")
    scaled.write_text(
        src.read_text()
        .replace("</head>", f"<style>html {{ font-size: {root}px; }}</style>\n</head>")
        # Last thing in the body, so it lands after the snapshot's own fill
        # script has set the default screen rather than before it. The scroll
        # belongs here and not in the fill for the same reason: the conversation
        # is display:none until the screen is named, so a scroll taken before
        # this line is a scroll of a box with nothing in it, and the render comes
        # out showing the top of a thread the phone is showing the bottom of.
        # app.js scrolls it on every resize; app.js is what a snapshot drops.
        .replace(
            "</body>",
            f"<script>document.body.className = {' '.join(sorted(set(classes)))!r};"
            "const said = document.getElementById('transcript');"
            "if (said) said.scrollTop = said.scrollHeight;</script>\n</body>",
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
    ap.add_argument("--root", type=int, default=ROOT)
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
    print(render(a.src, a.out, a.width, a.height, a.root, a.screen, a.keyboard))
