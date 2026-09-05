#!/usr/bin/env python3
"""
One-off generator for static/icon.png, the app icon used by the Chromebook
desktop launcher (jeopardy.desktop.template) and as the browser favicon for
game.html/editor.html.

Not a runtime dependency of the server -- run this manually only when you
want to regenerate or tweak the icon's look:

    python3 make_icon.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BASE_DIR = Path(__file__).resolve().parent
OUT_PATH = BASE_DIR / "static" / "icon.png"

# Match the palette in static/css/style.css.
BOARD_BLUE = "#060ce9"
GOLD = "#ffd700"
WHITE = "#ffffff"

SIZE_PX = 256
DPI = 128


def main():
    fig = plt.figure(figsize=(SIZE_PX / DPI, SIZE_PX / DPI), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Rounded blue tile with a gold border, echoing the board's .cell style.
    tile = FancyBboxPatch(
        (0.06, 0.06), 0.88, 0.88,
        boxstyle="round,pad=0,rounding_size=0.14",
        linewidth=SIZE_PX * 0.02,
        edgecolor=GOLD,
        facecolor=BOARD_BLUE,
    )
    ax.add_patch(tile)

    # A dollar sign, like an uncovered board value tile.
    ax.text(0.5, 0.5, "$", color=GOLD, fontsize=95,
             fontweight="bold", ha="center", va="center",
             family="Arial")

    OUT_PATH.parent.mkdir(exist_ok=True)
    fig.savefig(OUT_PATH, dpi=DPI, transparent=False, facecolor=WHITE)
    plt.close(fig)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
