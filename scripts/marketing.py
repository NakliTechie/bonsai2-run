#!/usr/bin/env python3
"""Launch creatives: marketing/social.png (1280x640 repo card) and marketing/launch.png (1600x900 post image).
Every number on them is measured: results/cloudrun-nvidia-l4-2026-09-25-0856/NOTES.md, results/bench-stack-2026-09-24.

  marketing.py [OUT_DIR]      # default: marketing/
"""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

out = sys.argv[1] if len(sys.argv) > 1 else "marketing"
os.makedirs(out, exist_ok=True)
SURF, INK, INK2, MUTED, LINE, BLUE, TILE = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8983", "#e6e5e0", "#2a78d6", "#f1f0ec"
plt.rcParams.update({"font.family": "Helvetica Neue", "text.color": INK})
STATS = [("9 min 38 s", "new project to live URL"), ("23 s", "idle to first answer"),
         ("$0", "GPU cost while idle"), ("148 tok/s", "code edit, one L4")]


PAIRS = []   # (text artist, (x0, y0, x1, y1) box in data coords, name) checked before saving


def check(fig, ax):  # fail if any registered text leaves its box (12 px inside) or the canvas (40 px margin)
    fig.canvas.draw(); r = fig.canvas.get_renderer(); bad = []
    for t, (x0, y0, x1, y1), name in PAIRS:
        pad = 40 if "canvas" in name else 12
        bb = t.get_window_extent(r).transformed(ax.transData.inverted())
        if bb.x0 < x0 + pad - 1 or bb.x1 > x1 - pad + 1 or bb.y0 < y0 + (pad if "canvas" in name else 4) - 1 or bb.y1 > y1 - 4 + 1:
            bad.append(f"{name}: text [{bb.x0:.0f},{bb.x1:.0f}]x[{bb.y0:.0f},{bb.y1:.0f}] vs box [{x0},{x1}]x[{y0},{y1}]")
    PAIRS.clear()
    if bad:
        sys.exit("OVERFLOW\n" + "\n".join(bad))


def canvas(w, h):
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100, facecolor=SURF)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis("off")
    return fig, ax


def tile(ax, x, y, w, h, big, small, big_size, small_size):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=14", fc=TILE, ec=LINE, lw=1.5))
    for t in (ax.text(x + 22, y + h - 24, big, fontsize=big_size, fontweight="bold", va="top", color=INK),
              ax.text(x + 22, y + 22, small, fontsize=small_size, va="bottom", color=INK2)):
        PAIRS.append((t, (x, y, x + w, y + h), f"tile {big}"))


# 1. Repo social card, 1280x640: one sentence, the name, the numbers. Readable at thumbnail size.
fig, ax = canvas(1280, 640)
ax.add_patch(FancyBboxPatch((0, 0), 16, 640, boxstyle="square,pad=0", fc=BLUE, ec="none"))
ax.text(70, 560, "bonsai2-run", fontsize=30, color=BLUE, fontweight="bold", va="top")
ax.text(70, 490, "A 27B model on one Cloud Run GPU.", fontsize=46, fontweight="bold", va="top")
ax.text(70, 418, "No GPU bill when nobody uses it.", fontsize=46, fontweight="bold", va="top", color=BLUE)
for i, (big, small) in enumerate(STATS):
    tile(ax, 70 + i * 290, 120, 270, 150, big, small, 32, 16)
ax.text(70, 62, "One script from Cloud Shell · Ternary Bonsai 2 27B + DFlash2 · OpenAI + Anthropic APIs · MIT",
        fontsize=16, color=MUTED, va="center")
for t in ax.texts:
    PAIRS.append((t, (0, 0, 1280, 640), "social canvas"))
check(fig, ax)
fig.savefig(f"{out}/social.png", facecolor=SURF); plt.close(fig)

# 2. Launch image, 1600x900: the four steps a reader takes, with measured times.
fig, ax = canvas(1600, 900)
ax.text(80, 820, "From Cloud Shell to a live GPU endpoint", fontsize=40, fontweight="bold", va="top")
ax.text(80, 752, "Ternary Bonsai 2 27B with DFlash2 on one NVIDIA L4, scale-to-zero, on your own Google Cloud project.",
        fontsize=19, color=INK2, va="top")
steps = [("1", "Open Cloud Shell", "Already signed in.\nNothing to install."),
         ("2", "Paste one line", "curl -fsSL …/\n  bonsai2-cloudrun.sh\n  | bash"),
         ("3", "Script does the rest", "billing · APIs · L4 quota\n· model into your bucket\n· deploy"),
         ("4", "Call it", "OpenAI API\n/v1/chat/completions\nAnthropic API\n/v1/messages")]
for i, (n, head, body) in enumerate(steps):
    x = 80 + i * 370
    ax.add_patch(FancyBboxPatch((x, 330), 340, 330, boxstyle="round,pad=0,rounding_size=16", fc=TILE, ec=LINE, lw=1.5))
    for t in (ax.text(x + 28, 628, n, fontsize=44, fontweight="bold", color=BLUE, va="top"),
              ax.text(x + 28, 540, head, fontsize=21, fontweight="bold", va="top"),
              ax.text(x + 28, 480, body, fontsize=16 if n == "2" else 16.5, color=INK2, va="top", linespacing=1.5,
                      family="Menlo" if n == "2" else "Helvetica Neue")):
        PAIRS.append((t, (x, 330, x + 340, 660), f"step {n}"))
    if i < 3:
        ax.annotate("", xy=(x + 369, 495), xytext=(x + 341, 495), arrowprops=dict(arrowstyle="-|>,head_width=0.5,head_length=0.8", color=BLUE, lw=3))
PAIRS.append((ax.text(80 + 2 * 370 + 28, 352, "measured: 9 min 38 s\nfrom an empty project", fontsize=14.5, color=BLUE,
                      va="bottom", fontweight="bold", linespacing=1.4), (80 + 2 * 370, 330, 80 + 2 * 370 + 340, 660), "step 3 note"))
for i, (big, small) in enumerate(STATS[1:] + [("~2.2x", "on math & code vs plain")]):
    tile(ax, 80 + i * 370, 100, 340, 170, big, small, 34, 16)
ax.text(80, 50, "About $1.42 per active hour · model files about 17¢ a month · github.com/NakliTechie/bonsai2-run",
        fontsize=15, color=MUTED, va="center")
for t in ax.texts:
    PAIRS.append((t, (0, 0, 1600, 900), "launch canvas"))
check(fig, ax)
fig.savefig(f"{out}/launch.png", facecolor=SURF); plt.close(fig)
print("wrote", f"{out}/social.png", f"{out}/launch.png")
