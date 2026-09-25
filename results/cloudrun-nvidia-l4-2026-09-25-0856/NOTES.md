# Cloud Run L4, asia-southeast1 — first deploy, 2026-09-25 08:54 IST

Revision bonsai2-00001-w5k, image `bonsai2-run:40c9578` (PrismML prism + DFlash2), 8 vCPU / 32 GiB / 1x L4,
min 0 / max 1, GCS FUSE (enable-buffered-read) + Direct VPC egress, `NGRAM=1` default.

- Deploy (revision create incl. first instance + /health probe): 2 min 30 s (08:54:01 -> 08:56:30).
- In-container startup (Cloud Run log): /dev/shm staging 7.8 GB in 12.0 s (~650 MB/s), llama-server load 5.7 s,
  listening at +17.8 s after the entrypoint started.
- Warm bench (`bench.jsonl`, leg9 prompts, greedy, thinking off): email 29.3, code 60.9, story 26.9 tok/s;
  code 410/703 drafts accepted, same as the AWS L4 PQ2_0 DFlash2 run.
- Stacking live check (`codeedit-request.json`: add type hints, keep the rest): 297 tokens at 148.0 tok/s,
  319 drafted / 286 accepted in ~11 verify steps = 29 drafted and 27 tokens per step (DFlash2 alone caps at 7),
  so ngram-mod is active.
- Cold start from zero: see `cold.txt` of the next bench run.

## Cold start from zero (2026-09-25 10:38 IST)

Service idle for 25 min (no instance). One request (`max_tokens` 8, thinking off), timed with curl from Bengaluru:
`http=200 ttfb=23.32 s`. Cloud Run log: instance start 05:08:52.6Z, FUSE mount +1.3 s, staging 7.8 GB in 12.7 s,
`llama-server` listening +7.0 s, `/health` probe passed 05:09:14.9Z (22.3 s), answer 0.7 s. Warm repeat: 0.66 s.
Proxy check: `gcloud run services proxy` + OpenAI Python SDK (`/v1`) and Anthropic Python SDK (base URL, any key) both answered.
