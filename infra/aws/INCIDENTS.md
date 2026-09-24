# Incidents — AWS / SkyPilot GPU runs (bonsai2-run)

One line of cause, one line of fix per incident. Times are approximate (from logs and session notes). General lessons are also in `~/Code/infra/aws/README.md`.

## 2026-09-24

| # | UTC | Where | What happened | Cause | Fix / rule |
|---|---|---|---|---|---|
| 1 | 01:20 | smoke box | Driver 535.216 (CUDA 12.2) on the AMI, image built for CUDA 12.8 | SkyPilot's AWS image ships an older driver than Cloud Run (580) | Ran fine (L4 is a datacenter part, forward-compat). No action; don't assume the AMI driver matches the target. |
| 2 | 01:45 | tool calls | `ssh box 'nohup cmd & ...'` hung the local call until its timeout | ssh waits for the backgrounded process's inherited fds | `setsid -f nohup cmd > log 2>&1 < /dev/null` |
| 3 | 06:03 | bench box 1 (g6.12xlarge) | Box `sky down`-ed mid-benchmark at 99 % GPU | Autostop counts SkyPilot jobs only; MATH-500/top-up/control passes ran over ssh outside the job; 120-min idle timer ran from the main job's end | Every pass inside the job (`run:` or `sky exec`); else `sky autostop --cancel`. Watchdog alerts on "autostop armed + no job + GPUs busy". S3 mirroring kept the loss to unfinished rows. |
| 4 | 06:08 | relaunch | `VcpuLimitExceeded` (64 G vCPU) | The torn-down instance was still `shutting-down` and counted against the quota | Wait for `terminated` before relaunching the same shape |
| 5 | 06:10 | relaunch | `InsufficientInstanceCapacity` for g6.12xlarge in every us-east-2 and us-west-2 AZ | No on-demand 4xL4 capacity at that hour | Keep 3+ regions in `any_of`; eu-south-2 had capacity |
| 6 | 06:20 | watchdog | Watchdog silent while the job ran | This SkyPilot version writes job logs to `~/sky_logs/<id>-<name>/run.log`, not `sky-*/run.log` | Glob both, or read `sky queue`'s LOG column |
| 7 | 06:30 | watchdog | Replayed old runs' milestones as new events | The workdir sync carries earlier `results/bench-*` folders; the glob matched all of them | `RES=<folder glob>` scopes the watchdog to one run |
| 8 | 07:00 | watchdog | Edited `watch-bench.sh` while it ran | bash reads scripts incrementally; an in-place edit can corrupt the running copy | Write `x.new`, `mv` over (new inode), restart the monitor |
| 9 | 09:40 | verify box (g6.2xlarge) | Build rc=127 in 0 s | SkyPilot AMI has no `cmake`; `nvcc` is installed but not on PATH (`/usr/local/cuda/bin`) | Install cmake + build-essential; `export PATH=/usr/local/cuda/bin:$PATH`. The public post lists these as prerequisites. |
| 10 | 10:00 | verify box | Job `FAILED_DRIVER` after 22 min, load avg 296 | `cmake --build -j` (no number) spawned hundreds of nvcc/cicc; RAM hit 95 %, Ray's OOM monitor killed the job. CMake 3.22 has no CUDA `native`, so it also compiled every arch (`compute_50`...) | `-DCMAKE_CUDA_ARCHITECTURES=<arch>` and a bounded `-j` |
| 11 | 10:10 | verify box | Build ran serially (`-j 1`), 40 min | SkyPilot/Ray sets `OMP_NUM_THREADS=1`; GNU `nproc` honours it | Inside SkyPilot jobs pass an explicit `-j N` (or `nproc --all`) |
| 12 | 10:10 | verify box | Hard-shutdown deadline had to be extended 3 times | Deadline sized for a parallel build | Size `shutdown -h +N` for the worst case, extend with `shutdown -c` first |
| 13 | 16:41 | stack box | Docker build failed; every server then "died" | Ubuntu security mirror returned 404 for `libexpat1` mid-sync; SkyPilot `setup:` does not stop on a failed command, so `run:` started without an image | Dockerfile retries apt 3x (`--fix-missing`, fails if all fail); `run:` builds if the image is missing and exits on failure |
| 14 | 16:45 | stack box | Resubmitted job would have started with empty queues | The aborted run left `$OUT/.queue-*` files, consumed | `rm -f $OUT/.queue*` at the start of a fresh run |
| 15 | 07:10 | analysis | Thinking-on speedups jumped (MT-Bench 1.38x -> 1.77x) after the 16k top-up | Prompts that hit 16k were greedy repetition loops; loops are trivial to draft | Drop ids still truncated at the higher limit from every config (paired) |
| 16 | 10:40 | local | Writing `plan/` from the worktree session was blocked by a hook | `plan/` is gitignored and lives only in the main checkout; the hook guards the main checkout | Chirag approved writing `plan/` in the main checkout via Bash for windup |
| 17 | 14:10 | local | `hf auth whoami`: "Not logged in" | `HF_TOKEN` is exported in `~/.zshrc`; the tool's non-interactive shell doesn't source it | Run hf via `zsh -ic '...'` |

"Server died" in `evalbox*.log` means the `llama-server` container exited before `/health` answered; check `docker logs` saved as `<config>/<think>/server.log` first, then whether the image exists.
