# n-gram + DFlash2 stacking (leg 1), 2026-09-24/25 — NVIDIA L4, llama.cpp, thinking off

Same image as `results/bench-2026-09-24` (PrismML `prism` + DFlash2). Stacking = `--spec-type ngram-mod,draft-dflash`:
llama.cpp tries ngram-mod first each cycle (match >= n_match tokens, draft n_min..n_max) and falls back to DFlash2.
- stack      = ngram-mod defaults (n_match 24, n_min 48, n_max 64)
- stackloose = n_match 12, n_min 8, n_max 32
Speedup = decode tok/s vs fastest plain (PTQ1_0). DFlash2 and both stacks ran on the same box in the same session
(plain PTQ1_0 on the original five sets is from bench-2026-09-24, other box, ~2-3 % offset). Full table: `summary.md`.

| set | DFlash2 | stack | stack vs DFlash2 | stackloose | pass@1 DFlash2 -> stack |
|---|---|---|---|---|---|
| HumanEval (164) | 2.69x | **3.58x** | **+33 %** | 3.27x | 0.933 -> 0.921 |
| code-edit (80, HumanEval refactors) | 2.46x | **3.15x** | **+28 %** | 2.88x | 0.975 -> 0.963 |
| MT-Bench turn 1 (80) | 1.39x | 1.39x | 0 % | 1.36x | – |
| MT-Bench turn 2 (80) | 1.44x | 1.45x | +0 % | 1.40x | – |
| Spec-Bench RAG (80) | 1.56x | 1.55x | -1 % | 1.47x | – |
| Spec-Bench summarization (80) | 1.30x | 1.29x | -1 % | 1.24x | – |
| MATH-500 (100) | 2.20x | 2.19x | -0.3 % | 2.12x | 0.75 -> 0.75 |
| GSM8K (100) | 2.17x | 2.14x | -1.4 % | 2.08x | 0.93 -> 0.93 |
| MBPP (100) | 2.17x | 2.07x | **-4.5 %** | 2.00x | 0.80 -> 0.80 |

- Gains come from drafts longer than DFlash2's 8-token block on output that copies the prompt (tau 10.2 on HumanEval).
- ngram-mod alone: 0.93-0.95x everywhere except code (code-edit 1.57x, HumanEval 1.68x). The model paraphrases
  RAG/summarization sources, so 24-token matches rarely fire there.
- MBPP regresses 4.5 % (median 2.26 -> 2.09x): MBPP prompts include the test asserts; echoed names trigger long
  matches with wrong continuations that displace DFlash2 drafts.
- MLX (CopySpec, block 5) and WebGPU (in-block n-gram, block <= 8): correct (output identical to plain greedy) but no
  measurable gain; both cap copy drafts at the block and lose their fast ternary kernel past 8 rows. Branches
  `stack-ngram` / `stack-ngram-web` on NakliTechie/dflash-mlx-bonsai2.
