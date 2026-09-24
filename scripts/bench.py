#!/usr/bin/env python3
"""Greedy bench + parity check against a running bonsai2-run endpoint. Stdlib only.

  bench.py run URL OUT.jsonl [--max-tokens N] [--token T]   # 3 fixed prompts, temperature 0, thinking off
  bench.py diff A.jsonl B.jsonl                              # byte-compare outputs of two runs (plain vs DFlash2)
"""
import argparse, json, sys, time, urllib.request

PROMPTS = {  # leg9 prompts from dflash-mlx-bonsai2, so CUDA numbers line up with the Metal ones
    "email": "Write a warm, two-paragraph email to a friend describing a weekend hike in the hills, the weather, and what you cooked afterwards.",
    "code": "Write a Python module with a class LRUCache(capacity) supporting get(key) and put(key, value) in O(1), with docstrings, type hints, and a small pytest test file at the end.",
    "story": "Write a complete short story of about 1500 words: a lighthouse keeper on a remote island receives a letter that changes everything. Include dialogue, a turning point, and a resolution.",
}


def post(url, body, token):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def run(a):
    url = a.url.rstrip("/") + "/v1/chat/completions"
    with open(a.out, "w") as f:
        for name, prompt in PROMPTS.items():
            body = {"messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": a.max_tokens,
                    "chat_template_kwargs": {"enable_thinking": False}}
            t = time.time()
            r = post(url, body, a.token)
            wall = time.time() - t
            tm = r.get("timings", {})
            row = {"prompt": name, "content": r["choices"][0]["message"]["content"], "wall_s": round(wall, 3),
                   "completion_tokens": r["usage"]["completion_tokens"], "tg_tps": tm.get("predicted_per_second"),
                   "pp_tps": tm.get("prompt_per_second"), "draft_n": tm.get("draft_n"),
                   "draft_accepted": tm.get("draft_n_accepted")}
            f.write(json.dumps(row) + "\n")
            acc = f" accept {row['draft_accepted']}/{row['draft_n']}" if row["draft_n"] else ""
            print(f"{name:6s} {row['completion_tokens']:4d} tok  tg {row['tg_tps'] or 0:7.2f} tok/s  wall {wall:6.2f}s{acc}")


def diff(a):
    A = {r["prompt"]: r for r in map(json.loads, open(a.a))}
    B = {r["prompt"]: r for r in map(json.loads, open(a.b))}
    same = 0
    for k in A:
        x, y = A[k]["content"], B[k]["content"]
        if x == y:
            same += 1
            print(f"{k:6s} IDENTICAL ({len(x)} chars)")
        else:
            i = next((i for i, (p, q) in enumerate(zip(x, y)) if p != q), min(len(x), len(y)))
            print(f"{k:6s} DIFFERS at char {i}: {x[i:i+40]!r} vs {y[i:i+40]!r}")
    print(f"parity {same}/{len(A)}")
    sys.exit(0 if same == len(A) else 1)


p = argparse.ArgumentParser()
sp = p.add_subparsers(dest="cmd", required=True)
r = sp.add_parser("run"); r.add_argument("url"); r.add_argument("out")
r.add_argument("--max-tokens", type=int, default=512); r.add_argument("--token", default="")
d = sp.add_parser("diff"); d.add_argument("a"); d.add_argument("b")
a = p.parse_args()
run(a) if a.cmd == "run" else diff(a)
