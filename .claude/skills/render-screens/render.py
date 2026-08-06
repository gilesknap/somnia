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
and its height media queries have fired.
"""

import argparse
import pathlib
import subprocess

WIDTH = 360
HEIGHT = 780
KEYBOARD_HEIGHT = 470
ROOT = 20


def render(src, out, width=WIDTH, height=HEIGHT, root=ROOT):
    src, out = pathlib.Path(src), pathlib.Path(out)
    # The root font is injected rather than edited into style.css: what is being
    # photographed has to stay byte-for-byte the page that ships.
    scaled = src.with_name(f".scaled-{src.name}")
    scaled.write_text(
        src.read_text().replace(
            "</head>", f"<style>html {{ font-size: {root}px; }}</style>\n</head>"
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
    a = ap.parse_args()
    print(render(a.src, a.out, a.width, a.height, a.root))
