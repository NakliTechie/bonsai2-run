#!/usr/bin/env python3
"""Share image (1600x900 PNG) for the n-gram + DFlash2 stacking run: speedup over the fastest plain config, DFlash2
alone vs stacked, per set. Numbers come from RESULTS_DIR/summary.json.

  chart_stack.py RESULTS_DIR OUT.png
"""
import json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

res, out = sys.argv[1:3]
S = {(s["config"], s["set"]): s for s in json.load(open(f"{res}/summary.json")) if s["think"] == "off"}
SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8983", "#e6e5e0"
BLUE, AQUA = "#2a78d6", "#1baf7a"
plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 15, "axes.edgecolor": GRID,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})
sets = [("humaneval", "HumanEval"), ("codeedit", "Code edit"), ("math500", "MATH-500"), ("gsm8k", "GSM8K"),
        ("mbpp", "MBPP"), ("mtbench_t2", "MT-Bench\nturn 2"), ("mtbench", "MT-Bench"), ("sb_rag", "RAG"),
        ("sb_sum", "Summarize")]
sp = lambda c, k: S[(c, k)]["tps"] / S[("PTQ1_0-plain", k)]["tps"]

fig = plt.figure(figsize=(16, 9), dpi=100, facecolor=SURF)
fig.text(0.055, 0.92, "Prompt lookup + DFlash2: +28-33% on code that copies", fontsize=30, fontweight="bold")
fig.text(0.055, 0.865, "Speedup over the fastest plain setup, one NVIDIA L4, decode tok/s. "
         "Stacked = try an n-gram match first, fall back to DFlash2.", fontsize=16.5, color=INK2)
fig.text(0.055, 0.035, "llama.cpp (PrismML fork + DFlash2, PR #261) · --spec-type ngram-mod,draft-dflash (ngram-mod defaults) · "
         "greedy, batch 1, thinking off · Ternary Bonsai 2 27B PQ2_0", fontsize=11.5, color=MUTED)
ax = fig.add_axes([0.075, 0.2, 0.905, 0.59]); ax.set_facecolor(SURF)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.tick_params(length=0)
w = 0.38
for i, (k, _) in enumerate(sets):
    a, b = sp("PQ2_0-dflash", k), sp("PQ2_0-stack", k)
    ax.bar(i - w / 2, a, w * 0.92, color=BLUE, edgecolor=SURF, linewidth=2, zorder=3)
    ax.bar(i + w / 2, b, w * 0.92, color=AQUA, edgecolor=SURF, linewidth=2, zorder=3)
    ax.text(i - w / 2, a + 0.04, f"{a:.2f}x", ha="center", va="bottom", fontsize=13, color=INK2)
    ax.text(i + w / 2, b + 0.04, f"{b:.2f}x", ha="center", va="bottom", fontsize=13, color=INK, fontweight="bold")
    d = b / a - 1
    if abs(d) >= 0.1:
        ax.text(i, b + 0.32, f"{d:+.0%}", ha="center", va="bottom", fontsize=20, fontweight="bold", color=INK)
ax.axhline(1.0, color=INK2, lw=1.5, ls=(0, (4, 3)), zorder=4)
ax.set_xticks(range(len(sets)), [n for _, n in sets], fontsize=15, color=INK)
ax.set_ylim(0, 4.3); ax.set_yticks([0, 1, 2, 3, 4], ["0", "1x plain", "2x", "3x", "4x"])
ax.grid(axis="y", color=GRID, zorder=0)
ax.legend(handles=[Patch(color=BLUE, label="DFlash2 alone"), Patch(color=AQUA, label="stacked: prompt lookup + DFlash2")],
          loc="upper right", frameon=False, fontsize=15)
fig.text(0.975, 0.075, "Other sets: within 1.4%, except MBPP -4.5%. Accuracy within 2 problems per set.", fontsize=12.5,
         color=MUTED, ha="right")
fig.savefig(out, facecolor=SURF)
print("wrote", out)
