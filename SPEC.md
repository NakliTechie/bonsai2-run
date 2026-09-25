# bonsai2-run spec

Tier: **Tool**. One image, one deploy script, one bench. Unity sentence (Mono): a scale-to-zero OpenAI-compatible
endpoint for Ternary-Bonsai-2-27B with the DFlash2 drafter, driven by one script whose every verb prints one line.

## §0 Agent contract (DRIVER.md pass, 2026-09-24)

The driver is an agent with a shell, `gcloud`, and no memory of the last session. It has to answer three questions
fast: is the endpoint up and what does it cost, what is missing, what is the next command.

1. **One perception act.** `./deploy.sh status` prints one JSON line: service URL, ready revision, image, GPU type,
   min/max instances, bucket objects with sizes, and whether each expected GGUF is present. No other read is needed
   to decide the next move.
2. **Closed verdict vocabulary.** Every `deploy.sh` verb ends with exactly one line `verdict=<CODE> next=<command>`
   and a matching exit code. Codes: `OK` 0 · `NO_GCLOUD` 10 · `NO_PROJECT` 11 · `NO_BUCKET` 12 · `WEIGHTS_MISSING` 13 ·
   `DEPLOY_FAILED` 14 · `UNHEALTHY` 15 · `NOT_DEPLOYED` 16 · `BUILD_FAILED` 17. One code per distinct next action.
3. **Bounded output.** One line per step, plus the verdict line. Output grows with the number of steps, never with
   log size. Failures print the last 20 lines of the relevant log, no more.
4. **Every failure names its remedy.** `next=` is a literal command (for example `./deploy.sh stage`).
5. **Idempotent and crash-safe.** `stage` skips an object whose size already matches. `deploy` is `gcloud run deploy`,
   which converges to the declared state. Re-running any verb after a kill is safe.
6. **The tool holds the memory.** `bench.py run` writes JSONL rows to `results/`; `results/` is append-only and
   committed. The README table is built from those rows, so a claim in the README resolves to a file.
7. **Accretion mechanism.** Each measurement run appends a dated results folder. A new GPU type or quant adds rows;
   it never overwrites old ones.
8. **The tower** (each layer consumes only the one below):
   - GGUFs in a GCS bucket (`stage`)
   - image: `llama-server` from PrismML's fork + `patches/` (Dockerfile)
   - boot: FUSE → `/dev/shm` staging → `llama-server` flags (entrypoint.sh, all knobs are env vars)
   - service: Cloud Run GPU, min 0 / max 1 (`deploy`)
   - API: OpenAI `/v1/chat/completions`, `/health`, `/metrics`
   - evaluator: `scripts/bench.py` (tok/s, draft acceptance, greedy parity)
9. **Evaluator outside the loop, fail closed.** `bench.py diff` compares two independent runs byte for byte and exits
   non-zero on any difference. A missing `timings` field is reported as `None`, never as a number.

## Knobs (entrypoint env)

`MODEL_DIR` `/mnt/gcs` · `TARGET` PQ2_0 GGUF · `DRAFT` drafter GGUF (empty = plain decode) · `COPY_TO_SHM` 1 ·
`COPY_STREAMS` 8 · `CTX` 16384 · `PARALLEL` 1 · `DRAFT_N_MAX` 7 · `NGRAM` 1 (ngram-mod stacked before DFlash2; 0 = DFlash2 only) · `EXTRA_ARGS` passed through to `llama-server`.
