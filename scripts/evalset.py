#!/usr/bin/env python3
"""Build the benchmark prompt sets as JSONL: HumanEval, MBPP (sanitized), GSM8K, MT-Bench turn 1.
Subsets use a seed-0 shuffle, so every config sees the same ids. Needs `datasets`.

  evalset.py OUT_DIR [SET ...]            # default: all sets
Writes OUT_DIR/{humaneval,mbpp,gsm8k,mtbench,math500,sb_sum,sb_rag,codeedit}.jsonl (mtbench_t2 needs a turn-1 run; see evalset_t2.py) with fields: id, prompt, plus what the scorer needs.
"""
import json, os, random, sys, urllib.request
from datasets import load_dataset

out, only = sys.argv[1], set(sys.argv[2:])
os.makedirs(out, exist_ok=True)
FENCE = "```"


def want(name):
    return not only or name in only


def dump(name, rows):
    random.Random(0).shuffle(rows)
    with open(f"{out}/{name}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(name, len(rows))


if want("humaneval"):
    he = load_dataset("openai/openai_humaneval", split="test")
    dump("humaneval", [{"id": r["task_id"], "entry_point": r["entry_point"], "code_prompt": r["prompt"], "test": r["test"],
                        "prompt": "Complete the following Python function. Reply with the complete function, including the "
                                  f"signature and any imports, in a single {FENCE}python code block.\n\n{FENCE}python\n{r['prompt']}{FENCE}"}
                       for r in he])

if want("mbpp"):
    mb = load_dataset("google-research-datasets/mbpp", "sanitized", split="test")
    dump("mbpp", [{"id": f"mbpp/{r['task_id']}", "test_imports": r["test_imports"], "tests": r["test_list"],
                   "prompt": f"{r['prompt']}\nYour code should pass these tests:\n" + "\n".join(r["test_list"])
                             + f"\nReply with the Python code in a single {FENCE}python code block."}
                  for r in mb])

if want("gsm8k"):
    gs = load_dataset("openai/gsm8k", "main", split="test")
    dump("gsm8k", [{"id": f"gsm8k/{i}", "answer": r["answer"].split("####")[-1].strip(),
                    "prompt": f"{r['question']}\nSolve it step by step, then give the final answer on the last line as: #### <number>"}
                   for i, r in enumerate(gs)])

if want("mtbench"):
    url = "https://raw.githubusercontent.com/lm-sys/FastChat/main/fastchat/llm_judge/data/mt_bench/question.jsonl"
    mt = [json.loads(l) for l in urllib.request.urlopen(url).read().decode().splitlines() if l.strip()]
    dump("mtbench", [{"id": f"mtbench/{q['question_id']}", "category": q["category"], "prompt": q["turns"][0]} for q in mt])

if want("math500"):
    ma = load_dataset("HuggingFaceH4/MATH-500", split="test")
    dump("math500", [{"id": r["unique_id"], "answer": r["answer"], "level": r["level"],
                      "prompt": f"{r['problem']}\nReason step by step, and put your final answer within \\boxed{{}}."}
                     for r in ma])

SPECBENCH = "https://raw.githubusercontent.com/hemingkx/Spec-Bench/main/data/spec_bench/question.jsonl"
if want("sb_sum") or want("sb_rag"):
    sb = [json.loads(l) for l in urllib.request.urlopen(SPECBENCH).read().decode().splitlines() if l.strip()]
    for cat, name in (("summarization", "sb_sum"), ("rag", "sb_rag")):
        if want(name):
            dump(name, [{"id": f"{name}/{q['question_id']}", "prompt": q["turns"][0]} for q in sb if q["category"] == cat])

if want("codeedit"):  # copy-heavy code task: rewrite a given, correct function; behaviour checked with HumanEval's tests
    he = load_dataset("openai/openai_humaneval", split="test")
    rows = [{"id": f"codeedit/{r['task_id']}", "entry_point": r["entry_point"], "code_prompt": "", "test": r["test"],
             "prompt": "Refactor the following Python function for readability: use descriptive variable names and add brief "
                       "comments, but keep its behaviour exactly the same. Reply with the complete function, including the "
                       f"signature and docstring, in a single {FENCE}python code block.\n\n{FENCE}python\n{r['prompt']}{r['canonical_solution']}{FENCE}"}
            for r in he]
    random.Random(1).shuffle(rows)
    dump("codeedit", rows[:80])
