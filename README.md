# bonsai2-run

> One-command, scale-to-zero Google Cloud Run deploy of Ternary-Bonsai-2-27B with our re-fitted DFlash 2 drafter. $0 at rest.

Tier: **Tool**. Serve PrismML's Ternary-Bonsai-2-27B (1.72 bpw, ~6 GB GGUF) plus the NakliTechie re-fitted DFlash 2 drafter as an OpenAI-compatible endpoint on Cloud Run, with `--min-instances=0` so an idle deployment costs nothing. The recipe follows [taeold/djev-run](https://github.com/taeold/djev-run), which serves DiffusionGemma-Jev the same way and cut its cold start from 4 m 05 s to 47.5 s.

## Install

<!-- Install comes before Why (README-DOCTRINE). Fill the moment there is a run path. -->
_TODO: two commands, as in djev-run — (1) stage the GGUFs in a GCS bucket, (2) `gcloud beta run deploy … --image=ghcr.io/naklitechie/bonsai2-run:latest --gpu-type=nvidia-l4 --min-instances=0`._

## Why

- **Zero at rest.** Cloud Run bills a GPU instance only while it is up; `--min-instances=0` scales to $0 when idle. Bursty, low-duty-cycle use pays per active hour.
- **The model is small.** The PTQ1_0 GGUF is 5.95 GB and the drafter Q4_K_M is a few GB, so the whole stack fits one **NVIDIA L4 (24 GB)**, the cheapest Cloud Run GPU. djev-run needs an RTX PRO 6000 for 17.5 GB of weights.
- **Less to stream, faster cold start.** Under half of djev's bytes to pull from GCS.

## Serving path

CUDA, not MLX. The Apple-Silicon fork ([dflash-mlx-bonsai2](https://github.com/NakliTechie/dflash-mlx-bonsai2)) cannot run on Cloud Run's NVIDIA GPUs.

- Engine: PrismML's llama.cpp fork with DFlash 2 speculative decoding — our `~/Code/llama.cpp-prism` carries the DFlash2 spec (`8f29f159c`) and the `prism.hadamard` transform fix for the borrowed tok_embd / lm_head (`cbe495c59`). Stock llama.cpp cannot run the Bonsai GGUF.
- Target: [prism-ml/Ternary-Bonsai-2-27B-gguf](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf) (PTQ1_0 5.95 GB, or PQ2_0 7.21 GB).
- Drafter: [naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2](https://huggingface.co/naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2) `Qwen3.8-27B-DFlash2-r3-Q4_K_M.gguf`.
- API: `llama-server` OpenAI-compatible `/v1/chat/completions`; speculation engages on greedy (`temperature: 0`) requests.
- GPU: Cloud Run `nvidia-l4`; `nvidia-rtx-pro-6000` as fallback.

## Cold-start recipe (ported from djev-run)

- Weights in GCS, mounted by Cloud Storage FUSE with `enable-buffered-read=true`; VPC egress `all-traffic` (djev measured ~1.05 GiB/s).
- Background copy of the GGUFs into `/dev/shm` while the server binary starts.
- No CUDA-graph / warm-up passes that cost startup time.
- `--no-cpu-throttling`; no `--cpu-boost` (djev measured it slower).
- Startup probe on `/health`.

## Next steps

- Build llama.cpp-prism for CUDA (sm_89 for L4, sm_120 for RTX PRO 6000) in a container; confirm DFlash2 + Bonsai GGUF runs on a CUDA box.
- Entrypoint script: shm staging + `llama-server` with target + drafter.
- `deploy.sh`: bucket upload + `gcloud beta run deploy`.
- Measure: cold start from zero, tok/s plain vs DFlash2, $/active-hour on L4.

## Context

Prior art in the knowledge vault: `sources/2026-09-20-taeold-djev-run-repo.md` (the recipe), `sources/2026-09-17-ternary-bonsai-2-27b-model-card.md` (GGUF sizes, RTX 5090 129.9 tok/s tg128), `sources/2026-09-19-bonsai-2-27b-cmp170hx-dflash2.md` (vLLM W4A16 + DFlash2 on SM80: 155.7–251.6 tok/s, 4.17 tok/draft — an alternative serving path).
