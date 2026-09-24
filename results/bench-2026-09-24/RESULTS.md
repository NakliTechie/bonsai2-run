# Ternary Bonsai 2 27B + DFlash2 on one NVIDIA L4 — benchmark, 2026-09-24

Engine: `llama-server` from PrismML-Eng/llama.cpp `prism` @ `ee8ad0ef6` + the DFlash2 cherry-pick (PrismML-Eng/llama.cpp#261),
CUDA 12.8, image built from this repo's `Dockerfile`. GPU: NVIDIA L4 24 GB (AWS g6.12xlarge, one server per GPU), driver 535.
Greedy (`temperature 0`), one request at a time, `-np 1`. Target GGUF `prism-ml/Ternary-Bonsai-2-27B-gguf`.
Drafter r3 = `naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2` Q4_K_M; stock = `z-lab/Qwen3.8-27B-DFlash2-GGUF` Q4_K_M.
Draft length 7 unless stated. Every speedup is against the **fastest plain configuration** (PTQ1_0, no speculation).
Full tables: `summary.md` (capped limits), `summary-extended.md` (thinking-on re-run to 16k). Raw rows: `*/*/*.jsonl`.

## Headline (thinking off, max 1024 tokens; MATH-500 2048)

| set | n | plain PTQ1_0 tok/s | DFlash2 PQ2_0 tok/s | speedup (aggregate) | per-prompt median [IQR] | tau | accuracy plain -> DFlash2 |
|---|---|---|---|---|---|---|---|
| GSM8K | 100 | 31.4 | 67.6 | **2.15x** | 2.19x [2.05-2.35] | 5.71 | 0.94 -> 0.93 (PQ2_0 plain) |
| MBPP (sanitized) | 100 | 31.6 | 68.4 | **2.16x** | 2.24x [2.06-2.47] | 5.74 | 0.80 -> 0.80 |
| MATH-500 | 100 | 30.6 | 67.8 | **2.22x** | 2.32x [2.14-2.45] | 5.81 | 0.76 -> 0.75 |
| MT-Bench turn 1 | 80 | 31.3 | 42.9 | 1.37x | 1.51x [1.12-2.00] | 3.63 | not scored |
| HumanEval* | 164 | 31.5 | 83.8 | 2.66x | 2.81x [2.69-2.89] | 7.03 | 0.927 -> 0.933 |

\*64% of each HumanEval answer (by characters) is verbatim prompt text (signature + docstring); treat it as an upper bound.
Accuracy compares PQ2_0 plain with PQ2_0 + DFlash2 (same weights). Speed is decode tok/s; end to end (with prefill) MBPP is 1.87x.

## Thinking on (re-run to 16,384 tokens; prompts still truncated at 16k in any config dropped from all, n shown)

| set | n | speedup (aggregate) | per-prompt median | tau | accuracy plain -> DFlash2 |
|---|---|---|---|---|---|
| GSM8K | 40 | 1.57x | 1.85x | 4.18 | 0.95 -> 0.95 |
| MATH-500 | 39 | 1.63x | 1.95x | 4.24 | 0.949 -> 0.923 (1 problem) |
| HumanEval | 34 | 1.49x | 1.64x | 3.94 | 0.971 -> 0.941 (1 problem) |
| MBPP | 36 | 1.36x | 1.43x | 3.54 | 0.972 -> 0.972 |
| MT-Bench | 34 | 1.25x | 1.34x | 3.32 | not scored |

17 prompts hit 16k in some config; most end in greedy repetition loops in every config (a model behaviour under greedy
decoding). Loops are trivial to draft, so keeping them would inflate speculative tok/s. The capped (4096) numbers agree:
1.57 / 1.61 / 1.52 / 1.38 / 1.38x.

## Controls (thinking off)

| control | GSM8K | MBPP | MATH-500 | MT-Bench | HumanEval |
|---|---|---|---|---|---|
| `ngram-mod` prompt-lookup speculation, no drafter | 0.93x | 0.92x | 0.95x | 0.94x | 1.68x |
| stock z-lab drafter (same box as r3 repeat) | 63.1 tok/s | 63.4 | 63.0 | 38.7 | 79.2 |
| r3 drafter, repeat run (same box) | 66.5 tok/s | 66.9 | 66.4 | 41.9 | 81.1 |
| r3 over stock | +5% | +5% | +5% | +8% | +2% |
| DFlash2 draft length 3 | 1.83x | 1.84x | 1.89x | **1.49x** | 1.99x |

- Prompt lookup gains nothing where the prompt holds no answer; DFlash2's 2.15x there is drafting, not copying.
- The r3 re-fit (trained on UltraChat) helps most on chat: MT-Bench writing is 0.84x with the stock drafter, 0.98x with r3.
- Draft length 3 is the better chat setting: MT-Bench per category, draft 7 -> 3: writing 0.98 -> 1.26x, humanities
  1.08 -> 1.33x, roleplay 1.08 -> 1.28x; coding 1.94 -> 1.76x, math 2.27 -> 1.91x (10 prompts per category).
- Reproducibility: the r3 repeat ran on a second machine (eu-south-2 vs us-east-2). Acceptance and tau are identical to
  3 decimals on every set (same greedy drafts); decode speed differs by 1.7-3.2%.

## Limits

- One GPU type (L4), batch 1. Serving throughput under concurrency is not measured.
- Greedy DFlash2 output is not byte-identical to plain decode (batched-verify rounding flips near-tied tokens, top-2 gap
  <= 0.024 nats in the smoke run); accuracy differs by at most one problem per set.
- MT-Bench turn 1 only, not judged. Thinking-on sets are 40 prompts each (seed-0 subset).
- Thinking-off truncation: MT-Bench 14-17/80 at 1024 (FastChat convention), MATH-500 20-22/100 at 2048, equal across configs.

## Reproduce

`CONFIRM_GPU_SPEND=1 CLUSTER=bonsai2-run-bench TASK=infra/aws/bench.sky.yaml bash infra/aws/launch.sh`, then
`python3 scripts/score.py <sets> results/bench-2026-09-24 [--extended]`. Prompt sets: `scripts/evalset.py`.
