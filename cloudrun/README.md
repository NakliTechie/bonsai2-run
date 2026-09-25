# Ternary Bonsai 2 27B + DFlash2 on Cloud Run: one script

A 27B open-weight model behind OpenAI- and Anthropic-compatible APIs on one Google Cloud Run **NVIDIA L4**, with DFlash2
speculative decoding and prompt lookup. **$0 while idle**, about **$1.4 per active hour**.

## Run it

**Step 1. Get a Google Cloud account with billing** at [cloud.google.com](https://cloud.google.com). A Free Trial
account must be **upgraded to paid** first: Google keeps the unused credit, but GPUs are blocked during the trial.

**Step 2. Open [Cloud Shell](https://shell.cloud.google.com)** and select or create a project. It is already signed in.

**Step 3. Paste this line.** Wait seven to ten minutes (9 min 38 s measured on a new project).

```bash
curl -fsSL https://raw.githubusercontent.com/NakliTechie/bonsai2-run/main/cloudrun/bonsai2-cloudrun.sh | bash
```

**Step 4. Copy the URL line it prints** and paste it back into the shell:

```text
== Your endpoint is live
  export URL=https://bonsai2-xxxxxxxxxx-as.a.run.app
```

**Step 5. Call it.** The endpoint is private to your Google account, so every call carries an identity token.

```bash
curl -s $URL/v1/chat/completions -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"Write a palindrome check in Python."}]}'
```

## Options

| To | Do |
|---|---|
| Get faster answers (no thinking) | Add `"chat_template_kwargs": {"enable_thinking": false}` to the request body |
| Use the Anthropic Messages API | POST to `$URL/v1/messages` with the same token; `max_tokens` is required |
| Use an OpenAI or Anthropic SDK | Run `gcloud run services proxy bonsai2 --region <region> --port 8080`; base URL `http://localhost:8080/v1` (OpenAI) or `http://localhost:8080` (Anthropic), any API key |
| Tune for chat and prose | `curl -fsSL … \| PROFILE=chat bash` |
| Choose the region | `curl -fsSL … \| REGION=europe-west4 bash` |
| Remove everything | `curl -fsSL … \| DOWN=1 bash` deletes the service and the bucket |

The first call after an idle spell starts a GPU instance: 23 s from zero to the first answer (measured). On math and code it decodes about 2.2x faster
than plain decoding on the same L4; a copy-heavy code edit ran at 148 tok/s.

Full source, benchmarks and method: **[NakliTechie/bonsai2-run](https://github.com/NakliTechie/bonsai2-run)**.
Model: [prism-ml/Ternary-Bonsai-2-27B](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf) ·
drafter: [naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2](https://huggingface.co/naklitechie/Qwen3.8-27B-DFlash2-ternary-bonsai2).
