#!/usr/bin/env python3
"""At the first char where plain and DFlash2 greedy outputs split, how close was the plain run's top-2 logit race?
A small margin means the split is a batched-verify numeric tie flip, not a wrong verify path. Stdlib only.

  tie_margin.py URL PLAIN.jsonl DFLASH.jsonl      # URL = a running *plain* server
"""
import json, sys, urllib.request
sys.path.insert(0, __file__.rsplit("/", 1)[0])

url, pa, pb = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
A = {r["prompt"]: r for r in map(json.loads, open(pa))}
B = {r["prompt"]: r for r in map(json.loads, open(pb))}
from bench import PROMPTS  # noqa: E402

for name, prompt in PROMPTS.items():
    x, y = A[name]["content"], B[name]["content"]
    split = next((i for i, (p, q) in enumerate(zip(x, y)) if p != q), None)
    if split is None:
        print(f"{name:6s} identical"); continue
    body = {"messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": 400,
            "logprobs": True, "top_logprobs": 2, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=600))
    pos = 0
    for t in r["choices"][0]["logprobs"]["content"]:
        if pos + len(t["token"]) > split:
            top = t["top_logprobs"]
            gap = top[0]["logprob"] - top[1]["logprob"] if len(top) > 1 else float("nan")
            print(f"{name:6s} split@{split}: plain chose {top[0]['token']!r} ({top[0]['logprob']:.3f}) over "
                  f"{top[1]['token']!r} ({top[1]['logprob']:.3f}); gap {gap:.3f} nats; dflash wrote {y[split:split+12]!r}")
            break
        pos += len(t["token"])
