#!/usr/bin/env python3
"""Run one prompt set against a running endpoint, greedy, one request at a time. Resumable: ids already in OUT are skipped.

  evalrun.py URL SET.jsonl OUT.jsonl --limit N --max-tokens M [--think] [--ids FILE]   # --ids: only these ids
"""
import argparse, json, os, time, urllib.request

a = argparse.ArgumentParser()
a.add_argument("url"); a.add_argument("set"); a.add_argument("out")
a.add_argument("--limit", type=int, default=0); a.add_argument("--max-tokens", type=int, default=1024)
a.add_argument("--think", action="store_true"); a.add_argument("--ids")
a = a.parse_args()

rows = [json.loads(l) for l in open(a.set)]
rows = rows[: a.limit] if a.limit else rows
if a.ids:
    keep = set(open(a.ids).read().split())
    rows = [r for r in rows if r["id"] in keep]
done = {json.loads(l)["id"] for l in open(a.out)} if os.path.exists(a.out) else set()
url = a.url.rstrip("/") + "/v1/chat/completions"
with open(a.out, "a") as f:
    for r in rows:
        if r["id"] in done:
            continue
        body = {"messages": r.get("messages") or [{"role": "user", "content": r["prompt"]}], "temperature": 0, "max_tokens": a.max_tokens,
                "chat_template_kwargs": {"enable_thinking": a.think}}
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        t = time.time()
        resp = json.load(urllib.request.urlopen(req, timeout=1800))
        c, tm = resp["choices"][0], resp.get("timings", {})
        f.write(json.dumps({"id": r["id"], "think": a.think, "content": c["message"].get("content") or "",
                            "reasoning": c["message"].get("reasoning_content") or "", "finish": c.get("finish_reason"),
                            "completion_tokens": resp["usage"]["completion_tokens"], "wall_s": round(time.time() - t, 3),
                            "predicted_ms": tm.get("predicted_ms"), "draft_n": tm.get("draft_n"),
                            "draft_accepted": tm.get("draft_n_accepted")}) + "\n")
        f.flush()
