#!/usr/bin/env python3
"""Share images (1600x900 PNG) from a benchmark results dir. Numbers come from summary.json and the raw rows.

  charts.py RESULTS_DIR SETS_DIR OUT_DIR
"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

res, sets_dir, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
S = {(s["config"], s["think"], s["set"]): s for s in json.load(open(f"{res}/summary.json"))}
X = {(s["config"], s["think"], s["set"]): s for s in json.load(open(f"{res}/summary-extended.json"))}

SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8983", "#e6e5e0"
BLUE, ORANGE, AQUA, VIOLET, PLAIN = "#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7", "#b9b8b1"
plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 15, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})
FOOT = ("NVIDIA L4 24 GB · llama.cpp (PrismML fork + DFlash2, PR #261) · greedy, batch 1 · decode tok/s · "
        "data: huggingface.co/datasets/naklitechie/bonsai2-dflash2-bench")


def frame(title, subtitle):
    fig = plt.figure(figsize=(16, 9), dpi=100, facecolor=SURF)
    fig.text(0.055, 0.92, title, fontsize=30, fontweight="bold", color=INK)
    fig.text(0.055, 0.865, subtitle, fontsize=17, color=INK2)
    fig.text(0.055, 0.035, FOOT, fontsize=11.5, color=MUTED)
    return fig


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)


# 1. Hero: decode tok/s per set, thinking off
sets = [("gsm8k", "GSM8K"), ("mbpp", "MBPP"), ("math500", "MATH-500"), ("mtbench", "MT-Bench")]
fig = frame("Ternary Bonsai 2 27B: ~2.2x faster on math & code",
            "Decode tok/s on one NVIDIA L4, thinking off. DFlash2 speculative decoding vs the fastest plain setup.")
ax = fig.add_axes([0.07, 0.17, 0.9, 0.62]); style(ax)
w = 0.25
for i, (k, name) in enumerate(sets):
    plain, ngram, df = (S[(c, "off", k)] for c in ("PTQ1_0-plain", "PQ2_0-ngram", "PQ2_0-dflash"))
    for dx, s, col in ((-w, plain, PLAIN), (0, ngram, ORANGE), (w, df, BLUE)):
        ax.bar(i + dx, s["tps"], w * 0.92, color=col, edgecolor=SURF, linewidth=2, zorder=3)
    ax.text(i + w, df["tps"] + 1.5, f"{df['tps'] / plain['tps']:.2f}x", ha="center", va="bottom", fontsize=22, fontweight="bold", color=INK)
    ax.text(i - w, plain["tps"] + 1.5, f"{plain['tps']:.0f}", ha="center", va="bottom", fontsize=14, color=INK2)
    ax.text(i, ngram["tps"] + 1.5, f"{ngram['tps']:.0f}", ha="center", va="bottom", fontsize=14, color=INK2)
    ax.text(i + w, df["tps"] / 2, f"{df['tps']:.0f}", ha="center", va="center", fontsize=14, color="white", fontweight="bold")
    base = S[("PQ2_0-plain", "off", k)]
    acc = f"accuracy, same weights: {base["score"]:.2f} -> {df["score"]:.2f}" if df["score"] is not None else "(not scored)"
    ax.text(i, -9.5, acc, ha="center", va="top", fontsize=13, color=MUTED)
ax.set_xticks(range(len(sets)), [n for _, n in sets], fontsize=19, color=INK)
ax.set_ylim(0, 80); ax.set_yticks([0, 20, 40, 60, 80]); ax.set_ylabel("decode tok/s", fontsize=15)
ax.grid(axis="y", color=GRID, zorder=0)
ax.legend(handles=[Patch(color=PLAIN, label="plain (fastest: PTQ1_0)"), Patch(color=ORANGE, label="prompt-lookup speculation (ngram-mod)"),
                   Patch(color=BLUE, label="DFlash2 (PQ2_0 + re-fit drafter)")], loc="upper right", frameon=False, fontsize=14, ncol=3,
          bbox_to_anchor=(1.0, 1.08))
fig.savefig(f"{out}/1-speedup.png", facecolor=SURF); plt.close(fig)

# 2. MT-Bench by category: draft length 7 vs 3 (same box), speedup vs fastest plain, per-prompt median
cat = {r["id"]: r["category"] for r in map(json.loads, open(f"{sets_dir}/mtbench.jsonl"))}
tps = lambda c: {r["id"]: r["completion_tokens"] / r["predicted_ms"] * 1000 for r in map(json.loads, open(f"{res}/{c}/off/mtbench.jsonl"))}
base, n7, n3 = tps("PTQ1_0-plain"), tps("PQ2_0-dflashrep"), tps("PQ2_0-dflashn3")
med = lambda v: sorted(v)[len(v) // 2]
rows = []
for c in sorted(set(cat.values())):
    ids = [i for i in base if cat[i] == c]
    rows.append((c, med([n7[i] / base[i] for i in ids]), med([n3[i] / base[i] for i in ids])))
rows.sort(key=lambda r: r[1])
fig = frame("Structured output flies, prose doesn't: pick the draft length",
            "MT-Bench (thinking off), speedup over the fastest plain setup by category. Median of 10 prompts each.")
ax = fig.add_axes([0.16, 0.13, 0.8, 0.68]); style(ax)
h = 0.36
for i, (c, a, b) in enumerate(rows):
    ax.barh(i + h / 2, a, h * 0.9, color=BLUE, edgecolor=SURF, linewidth=2, zorder=3)
    ax.barh(i - h / 2, b, h * 0.9, color=AQUA, edgecolor=SURF, linewidth=2, zorder=3)
    ax.text(a + 0.03, i + h / 2, f"{a:.2f}x", va="center", fontsize=13, color=INK2)
    ax.text(b + 0.03, i - h / 2, f"{b:.2f}x", va="center", fontsize=13, color=INK2)
ax.axvline(1.0, color=INK2, lw=1.5, ls=(0, (4, 3)), zorder=4)
ax.text(1.0, len(rows) - 0.35, " plain = 1.0x", fontsize=13, color=INK2, va="bottom")
ax.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=17, color=INK)
ax.set_xlim(0, 2.7); ax.set_xticks([0, 0.5, 1, 1.5, 2, 2.5], ["0", "0.5x", "1x", "1.5x", "2x", "2.5x"])
ax.grid(axis="x", color=GRID, zorder=0)
ax.legend(handles=[Patch(color=BLUE, label="draft length 7 (code / math default)"), Patch(color=AQUA, label="draft length 3 (chat)")],
          loc="lower right", frameon=False, fontsize=14)
fig.savefig(f"{out}/2-by-category.png", facecolor=SURF); plt.close(fig)

# 3. Thinking off vs on, speedup over fastest plain (aggregate); thinking-on from the 16k re-run with loops dropped
sets5 = sets + [("humaneval", "HumanEval*")]
fig = frame("Thinking on still gains 1.25-1.6x",
            "DFlash2 speedup over the fastest plain setup, aggregate decode tok/s. Thinking on: 16k-token re-run, looping prompts dropped.")
ax = fig.add_axes([0.07, 0.17, 0.9, 0.62]); style(ax)
w = 0.34
for i, (k, name) in enumerate(sets5):
    off = S[("PQ2_0-dflash", "off", k)]["tps"] / S[("PTQ1_0-plain", "off", k)]["tps"]
    on = X[("PQ2_0-dflash", "on", k)]["tps"] / X[("PTQ1_0-plain", "on", k)]["tps"]
    for dx, v, col in ((-w / 2, off, BLUE), (w / 2, on, VIOLET)):
        ax.bar(i + dx, v, w * 0.92, color=col, edgecolor=SURF, linewidth=2, zorder=3)
        ax.text(i + dx, v + 0.04, f"{v:.2f}x", ha="center", va="bottom", fontsize=16, color=INK, fontweight="bold")
ax.axhline(1.0, color=INK2, lw=1.5, ls=(0, (4, 3)), zorder=4)
ax.text(len(sets5) - 0.38, 1.03, "plain", fontsize=13, color=INK2, ha="left", va="bottom")
ax.set_xticks(range(len(sets5)), [n for _, n in sets5], fontsize=19, color=INK)
ax.set_xlim(-0.55, len(sets5) - 0.1); ax.set_ylim(0, 3); ax.set_yticks([0, 1, 2, 3], ["0", "1x", "2x", "3x"])
ax.grid(axis="y", color=GRID, zorder=0)
ax.legend(handles=[Patch(color=BLUE, label="thinking off"), Patch(color=VIOLET, label="thinking on")], loc="upper left", frameon=False, fontsize=15)
fig.text(0.97, 0.10, "*64% of each HumanEval answer copies the prompt: an upper bound", fontsize=12, color=MUTED, ha="right")
fig.savefig(f"{out}/3-thinking.png", facecolor=SURF); plt.close(fig)
print("wrote", sorted(os.listdir(out)))
