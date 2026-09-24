#!/usr/bin/env python3
"""Build the benchmark prompt sets as JSONL: HumanEval, MBPP (sanitized), GSM8K, MT-Bench turn 1.
Subsets use a seed-0 shuffle, so every config sees the same ids. Needs `datasets`.

  evalset.py OUT_DIR
Writes OUT_DIR/{humaneval,mbpp,gsm8k,mtbench}.jsonl with fields: id, prompt, plus what the scorer needs.
"""
import json, os, random, sys, urllib.request
from datasets import load_dataset

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
FENCE = "```"


def dump(name, rows):
    random.Random(0).shuffle(rows)
    with open(f"{out}/{name}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(name, len(rows))


he = load_dataset("openai/openai_humaneval", split="test")
dump("humaneval", [{"id": r["task_id"], "entry_point": r["entry_point"], "code_prompt": r["prompt"], "test": r["test"],
                    "prompt": "Complete the following Python function. Reply with the complete function, including the "
                              f"signature and any imports, in a single {FENCE}python code block.\n\n{FENCE}python\n{r['prompt']}{FENCE}"}
                   for r in he])

mb = load_dataset("google-research-datasets/mbpp", "sanitized", split="test")
dump("mbpp", [{"id": f"mbpp/{r['task_id']}", "test_imports": r["test_imports"], "tests": r["test_list"],
               "prompt": f"{r['prompt']}\nYour code should pass these tests:\n" + "\n".join(r["test_list"])
                         + f"\nReply with the Python code in a single {FENCE}python code block."}
              for r in mb])

gs = load_dataset("openai/gsm8k", "main", split="test")
dump("gsm8k", [{"id": f"gsm8k/{i}", "answer": r["answer"].split("####")[-1].strip(),
                "prompt": f"{r['question']}\nSolve it step by step, then give the final answer on the last line as: #### <number>"}
               for i, r in enumerate(gs)])

url = "https://raw.githubusercontent.com/lm-sys/FastChat/main/fastchat/llm_judge/data/mt_bench/question.jsonl"
mt = [json.loads(l) for l in urllib.request.urlopen(url).read().decode().splitlines() if l.strip()]
dump("mtbench", [{"id": f"mtbench/{q['question_id']}", "category": q["category"], "prompt": q["turns"][0]} for q in mt])
