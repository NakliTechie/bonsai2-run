#!/usr/bin/env python3
"""Score and aggregate a benchmark results dir. Generated code runs inside `docker run --network none`.

  score.py SETS_DIR RESULTS_DIR          # writes RESULTS_DIR/summary.md and summary.json
RESULTS_DIR/<config>/<think>/<set>.jsonl, config = <quant>-<plain|dflash>, think = off|on.
"""
import glob, json, os, re, subprocess, sys, tempfile

sets_dir, res = sys.argv[1], sys.argv[2]
SETS = {n: {r["id"]: r for r in map(json.loads, open(f"{sets_dir}/{n}.jsonl"))} for n in ("humaneval", "mbpp", "gsm8k", "mtbench")}


def code_of(text):
    m = re.findall(r"```(?:python|py)?\n(.*?)```", text, re.S)
    return max(m, key=len) if m else text


def program(set_name, item, content):
    code = code_of(content)
    if set_name == "humaneval":
        if f"def {item['entry_point']}" not in code:
            code = item["code_prompt"] + code
        return f"{code}\n\n{item['test']}\n\ncheck({item['entry_point']})\n"
    return "\n".join(item["test_imports"]) + f"\n{code}\n\n" + "\n".join(item["tests"]) + "\n"


def run_programs(progs):  # {key: source} -> {key: passed}
    with tempfile.TemporaryDirectory(dir=os.path.expanduser("~")) as d:
        for i, (k, src) in enumerate(progs.items()):
            open(f"{d}/{i}.py", "w").write(src)
        runner = ("import subprocess,sys,glob,json\nr={}\nfor p in sorted(glob.glob('/w/*.py')):\n"
                  "  try: r[p]=subprocess.run([sys.executable,p],capture_output=True,timeout=15).returncode==0\n"
                  "  except Exception: r[p]=False\nprint(json.dumps(r))\n")
        out = subprocess.run(["docker", "run", "--rm", "--network", "none", "--memory", "2g", "-v", f"{d}:/w:ro",
                              "python:3.12-slim", "python", "-c", runner], capture_output=True, text=True, check=True).stdout
        ok = json.loads(out)
        return {k: ok[f"/w/{i}.py"] for i, k in enumerate(progs)}


def num(s):
    s = s.replace(",", "").replace("$", "").strip().rstrip(".")
    try:
        return float(s)
    except ValueError:
        return None


def gsm_ok(item, content):
    m = re.findall(r"####\s*\$?(-?[\d,]*\.?\d+)", content) or re.findall(r"-?[\d,]*\.?\d+", content)
    return bool(m) and num(m[-1]) is not None and num(m[-1]) == num(item["answer"])


summary = []
for path in sorted(glob.glob(f"{res}/*/*/*.jsonl")):
    config, think, set_name = path.split("/")[-3], path.split("/")[-2], os.path.basename(path)[:-6]
    rows = [json.loads(l) for l in open(path)]
    if not rows:
        continue
    items = SETS[set_name]
    if set_name in ("humaneval", "mbpp"):
        correct = run_programs({r["id"]: program(set_name, items[r["id"]], r["content"]) for r in rows})
    elif set_name == "gsm8k":
        correct = {r["id"]: gsm_ok(items[r["id"]], r["content"]) for r in rows}
    else:
        correct = {}
    tok = sum(r["completion_tokens"] for r in rows)
    ms = sum(r["predicted_ms"] or 0 for r in rows)
    dn = sum(r["draft_n"] or 0 for r in rows); da = sum(r["draft_accepted"] or 0 for r in rows)
    summary.append({"config": config, "think": think, "set": set_name, "n": len(rows), "tokens": tok,
                    "tps": round(tok / (ms / 1000), 2) if ms else None,
                    "accept": round(da / dn, 3) if dn else None,
                    "tau": round(tok / (tok - da), 2) if dn and tok > da else None,   # tokens per target forward pass
                    "truncated": sum(r["finish"] == "length" for r in rows),
                    "score": round(sum(correct.values()) / len(correct), 3) if correct else None,
                    "correct_ids": sorted(k for k, v in correct.items() if v)})

json.dump(summary, open(f"{res}/summary.json", "w"), indent=1)
base = {(s["think"], s["set"], s["config"].split("-")[0]): s for s in summary if s["config"].endswith("plain")}
with open(f"{res}/summary.md", "w") as f:
    f.write("| think | set | config | n | tok/s | vs plain same quant | accept | tau | score | truncated |\n|---|---|---|---|---|---|---|---|---|---|\n")
    for s in sorted(summary, key=lambda s: (s["think"], s["set"], s["config"])):
        b = base.get((s["think"], s["set"], s["config"].split("-")[0]))
        sp = f"{s['tps'] / b['tps']:.2f}x" if b and s["tps"] and b["tps"] and b is not s else ""
        f.write(f"| {s['think']} | {s['set']} | {s['config']} | {s['n']} | {s['tps']} | {sp} | {s['accept'] or ''} | "
                f"{s['tau'] or ''} | {'' if s['score'] is None else s['score']} | {s['truncated']} |\n")
print(open(f"{res}/summary.md").read())
