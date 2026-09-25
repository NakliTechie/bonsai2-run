# Ternary Bonsai 2 27B + DFlash2 on Cloud Run: one script

A 27B open-weight model behind OpenAI- and Anthropic-compatible APIs on one Google Cloud Run **NVIDIA L4**, with DFlash2
speculative decoding and prompt lookup. **$0 while idle**, about **$1.4 per active hour**.

## Run it

1. Open **[Cloud Shell](https://shell.cloud.google.com)** (already signed in) and pick or create a project.
2. Paste:

```bash
curl -fsSL https://raw.githubusercontent.com/NakliTechie/bonsai2-run/main/cloudrun/bonsai2-cloudrun.sh | bash
```

Seven to ten minutes on a new project (measured: 9 min 38 s). It links billing, enables the APIs, requests one Cloud Run L4 in the first region that
grants it, copies the model files from Hugging Face into your bucket (inside Google Cloud), deploys
`ghcr.io/naklitechie/bonsai2-run`, and prints your URL with a ready `curl`.

**Needs:** a billing account. A Free Trial must be **upgraded to paid** first (Google keeps the unused credit;
GPUs and quota requests are blocked during the trial).

**Options:** `PROFILE=chat` (tuned for prose), `REGION=europe-west4` (skip the search), `DOWN=1` (delete the
service and bucket). Put them before `bash`: `curl -fsSL … | PROFILE=chat bash`.

## What you get

- ~2.2x decode on math and code vs plain decoding on the same L4; 148 tok/s on a copy-heavy code edit.
- OpenAI-compatible `/v1/chat/completions` and Anthropic-compatible `/v1/messages`. The model thinks by default;
  send `"chat_template_kwargs": {"enable_thinking": false}` to skip it.
- Private by default: calls need `Authorization: Bearer $(gcloud auth print-identity-token)`, or run
  `gcloud run services proxy bonsai2 --region <region> --port 8080` for a local, token-free endpoint.
- The first request after an idle spell waits for a GPU instance to start (tens of seconds).

Full source, benchmarks and method: **[NakliTechie/bonsai2-run](https://github.com/NakliTechie/bonsai2-run)**.
Model: [prism-ml/Ternary-Bonsai-2-27B](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf) ·
drafter: [naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2](https://huggingface.co/naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2).
