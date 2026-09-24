#!/usr/bin/env python3
"""MT-Bench turn 2 as a copy-heavy set: the turn-2 question follows a fixed turn-1 answer (taken from one reference
run, identical for every config), so the model can reuse turn-1 text.

  evalset_t2.py SETS_DIR TURN1_ROWS.jsonl     # writes SETS_DIR/mtbench_t2.jsonl
"""
import json, sys, urllib.request
sets_dir, t1 = sys.argv[1], sys.argv[2]
URL = "https://raw.githubusercontent.com/lm-sys/FastChat/main/fastchat/llm_judge/data/mt_bench/question.jsonl"
qs = {f"mtbench/{q['question_id']}": q for q in (json.loads(l) for l in urllib.request.urlopen(URL).read().decode().splitlines() if l.strip())}
ans = {r["id"]: r["content"] for r in map(json.loads, open(t1))}
order = [json.loads(l)["id"] for l in open(f"{sets_dir}/mtbench.jsonl")]
with open(f"{sets_dir}/mtbench_t2.jsonl", "w") as f:
    for i in order:
        q = qs[i]
        f.write(json.dumps({"id": i.replace("mtbench/", "mtbench_t2/"), "category": q["category"],
                            "messages": [{"role": "user", "content": q["turns"][0]}, {"role": "assistant", "content": ans[i]},
                                         {"role": "user", "content": q["turns"][1]}]}) + "\n")
print("mtbench_t2", len(order))
