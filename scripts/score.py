#!/usr/bin/env python3
"""Score and aggregate a benchmark results dir. Generated code runs inside `docker run --network none`.

  score.py SETS_DIR RESULTS_DIR [--speed-only] [--extended]   # writes RESULTS_DIR/summary[-extended].{md,json}
--extended: rows from <set>.topup.jsonl (truncated thinking runs re-run with a higher token limit) replace the capped rows.
Speed is aggregate (total tokens / total time). Speedups are also given per prompt, paired by id, as median [p25-p75],
against the same-quant plain run and against the fastest plain run (PTQ1_0 plain).
RESULTS_DIR/<config>/<think>/<set>.jsonl, config = <quant>-<plain|dflash>, think = off|on.
"""
import difflib, glob, json, os, re, subprocess, sys, tempfile

sets_dir, res = sys.argv[1], sys.argv[2]
SPEED_ONLY = "--speed-only" in sys.argv
EXT = "--extended" in sys.argv
SUFFIX = "-extended" if EXT else ""
SETS = {n: {r["id"]: r for r in map(json.loads, open(f"{sets_dir}/{n}.jsonl"))}
        for n in ("humaneval", "mbpp", "gsm8k", "mtbench", "math500") if os.path.exists(f"{sets_dir}/{n}.jsonl")}


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


def boxed(text):  # contents of the last \boxed{...}, braces balanced
    i = text.rfind("\\boxed{")
    if i < 0:
        return None
    i += len("\\boxed{"); depth, j = 1, i
    while j < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[j], 0); j += 1
    return text[i:j - 1] if depth == 0 else None


def norm(a):  # light MATH answer normalisation (Hendrycks-style), string compare after it
    a = re.sub(r"\\text\{(.*?)\}", r"\1", a)
    for x in ("\\left", "\\right", "\\!", "\\,", "\\;", "$", " ", "^\\circ", "^{\\circ}", "\\%", "%"):
        a = a.replace(x, "")
    a = a.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac").rstrip(".")
    a = re.sub(r"\\frac(\d)(\d)", r"\\frac{\1}{\2}", a)
    return a[:-2] if a.endswith(".0") else a


def math_ok(item, content):
    b = boxed(content)
    if b is None:
        return False
    if norm(b) == norm(item["answer"]):
        return True
    x, y = num(norm(b)), num(norm(item["answer"]))
    return x is not None and x == y


def copied(item, content):  # share of the answer's chars that are verbatim runs (>= 20 chars) of the HumanEval prompt
    a, b = content, item["code_prompt"]
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    return sum(x.size for x in m if x.size >= 20) / max(1, len(a))


summary = []
for path in sorted(p for p in glob.glob(f"{res}/*/*/*.jsonl") if not p.endswith(".topup.jsonl")):
    config, think, set_name = path.split("/")[-3], path.split("/")[-2], os.path.basename(path)[:-6]
    rows = [json.loads(l) for l in open(path)]
    if EXT and os.path.exists(path[:-6] + ".topup.jsonl"):
        top = {r["id"]: r for r in map(json.loads, open(path[:-6] + ".topup.jsonl"))}
        rows = [top.get(r["id"], r) for r in rows]
    if not rows:
        continue
    items = SETS[set_name]
    if SPEED_ONLY:
        correct = {}
    elif set_name in ("humaneval", "mbpp"):
        correct = run_programs({r["id"]: program(set_name, items[r["id"]], r["content"]) for r in rows})
    elif set_name == "gsm8k":
        correct = {r["id"]: gsm_ok(items[r["id"]], r["content"]) for r in rows}
    elif set_name == "math500":
        correct = {r["id"]: math_ok(items[r["id"]], r["content"]) for r in rows}
    else:
        correct = {}
    tok = sum(r["completion_tokens"] for r in rows)
    ms = sum(r["predicted_ms"] or 0 for r in rows)
    dn = sum(r["draft_n"] or 0 for r in rows); da = sum(r["draft_accepted"] or 0 for r in rows)
    wall = sum(r["wall_s"] for r in rows)
    copy = round(sum(copied(items[r["id"]], r["content"]) for r in rows) / len(rows), 3) if set_name == "humaneval" else None
    summary.append({"config": config, "think": think, "set": set_name, "n": len(rows), "tokens": tok,
                    "tps": round(tok / (ms / 1000), 2) if ms else None, "e2e_tps": round(tok / wall, 2),
                    "per_id_tps": {r["id"]: r["completion_tokens"] / (r["predicted_ms"] / 1000) for r in rows if r["predicted_ms"]},
                    "accept": round(da / dn, 3) if dn else None,
                    "tau": round(tok / (tok - da), 2) if dn and tok > da else None,   # tokens per target forward pass
                    "truncated": sum(r["finish"] == "length" for r in rows), "prompt_copy": copy,
                    "score": round(sum(correct.values()) / len(correct), 3) if correct else None,
                    "correct_ids": sorted(k for k, v in correct.items() if v)})


def paired(s, b):  # median [p25-p75] of per-prompt speedup over ids present in both runs
    ids = sorted(set(s["per_id_tps"]) & set(b["per_id_tps"]))
    if not ids or s is b:
        return ""
    r = sorted(s["per_id_tps"][i] / b["per_id_tps"][i] for i in ids)
    q = lambda f: r[min(len(r) - 1, int(f * len(r)))]
    return f"{q(0.5):.2f}x [{q(0.25):.2f}-{q(0.75):.2f}] n={len(ids)}"


def agg(s, b):
    return f"{s['tps'] / b['tps']:.2f}x" if b and s is not b and s["tps"] and b["tps"] else ""


json.dump([{k: v for k, v in s.items() if k != "per_id_tps"} for s in summary], open(f"{res}/summary{SUFFIX}.json", "w"), indent=1)
idx = {(s["think"], s["set"], s["config"]): s for s in summary}
with open(f"{res}/summary{SUFFIX}.md", "w") as f:
    f.write("| think | set | config | n | decode tok/s | e2e tok/s | vs same-quant plain (agg; per-prompt median [IQR]) | vs PTQ1_0 plain (agg; per-prompt) | accept | tau | score | trunc | copied from prompt |\n")
    f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for s in sorted(summary, key=lambda s: (s["think"], s["set"], s["config"])):
        same = idx.get((s["think"], s["set"], s["config"].split("-")[0] + "-plain"))
        fast = idx.get((s["think"], s["set"], "PTQ1_0-plain"))
        c1 = f"{agg(s, same)}; {paired(s, same)}" if same and same is not s else ""
        c2 = f"{agg(s, fast)}; {paired(s, fast)}" if fast and fast is not s else ""
        f.write(f"| {s['think']} | {s['set']} | {s['config']} | {s['n']} | {s['tps']} | {s['e2e_tps']} | {c1} | {c2} | "
                f"{s['accept'] or ''} | {s['tau'] or ''} | {'' if s['score'] is None else s['score']} | {s['truncated']} | {'' if s['prompt_copy'] is None else s['prompt_copy']} |\n")
    # MT-Bench per category: DFlash2 vs the fastest plain run, paired per prompt (median), plus acceptance
    f.write("\n| think | MT-Bench category | n | DFlash2 vs PTQ1_0 plain (per-prompt median) | accept |\n|---|---|---|---|---|\n")
    cats = {i: it["category"] for i, it in SETS.get("mtbench", {}).items()}
    for th in ("off", "on"):
        d, b = idx.get((th, "mtbench", "PQ2_0-dflash")), idx.get((th, "mtbench", "PTQ1_0-plain"))
        if not d or not b:
            continue
        rows = {r["id"]: r for r in map(json.loads, open(f"{res}/PQ2_0-dflash/{th}/mtbench.jsonl"))}
        for c in sorted(set(cats.values())):
            ids = [i for i in d["per_id_tps"] if cats.get(i) == c and i in b["per_id_tps"]]
            if not ids:
                continue
            r = sorted(d["per_id_tps"][i] / b["per_id_tps"][i] for i in ids)
            dn = sum(rows[i]["draft_n"] or 0 for i in ids); da = sum(rows[i]["draft_accepted"] or 0 for i in ids)
            f.write(f"| {th} | {c} | {len(ids)} | {r[len(r) // 2]:.2f}x | {da / dn:.2f} |\n" if dn else "")
print(open(f"{res}/summary{SUFFIX}.md").read())
