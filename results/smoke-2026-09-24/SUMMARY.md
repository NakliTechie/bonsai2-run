# CUDA smoke, 2026-09-24 — AWS g6.4xlarge, NVIDIA L4 24 GB, driver 535.216.01

Image `bonsai2-run:dev` built on the box from commit cd7b85e (642 s, 3.53 GB). Weights on local NVMe, mounted at
`/mnt/gcs`, staged to `/dev/shm` by the entrypoint. Greedy (`temperature 0`), thinking off, `max_tokens 512`,
`-np 1`, `CTX 16384`, `DRAFT_N_MAX 7`, drafter `Qwen3.8-27B-DFlash2-r3-Q4_K_M.gguf`. Source: `smoke.log`, `*.jsonl`.

## Decode tok/s (server `timings.predicted_per_second`)

| target | mode | email | code | story |
|---|---|---|---|---|
| PTQ1_0 | plain | 32.9 | 32.8 | 32.7 |
| PTQ1_0 | DFlash2 | 18.6 (0.56×, 19% acc) | 40.7 (1.24×, 58% acc) | 18.8 (0.58×, 19% acc) |
| PQ2_0 | plain | 29.7 | 29.7 | 29.6 |
| PQ2_0 | DFlash2 | 29.2 (0.98×, 21% acc) | 61.2 (2.06×, 58% acc) | 27.1 (0.92×, 18% acc) |

- Acceptance matches the Metal leg9 run of the same drafter and prompts (email 21%, code 58%, story 17%;
  `dflash-mlx-bonsai2/lab/leg9/fork-*-r3.log`). The CUDA verify path behaves like Metal; low prose acceptance is the r3 drafter.
- PQ2_0 verifies 8-token blocks faster than PTQ1_0 on CUDA: same acceptance, 1.5× the speculative tok/s on code.
- VRAM: PTQ1_0 7.0 GB plain / 9.8 GB DFlash2; PQ2_0 8.1 / 11.0 GB. Fits the 24 GB L4 with room for more context.

## Start to /health 200 (local disk, not GCS)

5.5–7.5 s across the 4 runs; `/dev/shm` staging 2.6 s (PTQ1_0 + drafter) and 3.3 s (PQ2_0 + drafter), `llama-server`
load 2.5–4 s. Cloud Run cold start adds instance scheduling, image pull, and GCS FUSE reads; not measured here.

## Greedy parity: 0/6 byte-identical, 6/6 splits are near-ties

`*-tie-margin.txt`: at every first split, DFlash2 emitted the plain run's rank-2 token; top-2 logprob gap
0.001–0.024 nats. Batched verify and single-row decode run different CUDA kernels, and their rounding flips
near-tied argmaxes. No split lands on a token the plain run ranked below 2.
