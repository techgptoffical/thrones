"""Licensed reasoning problem sets with verifiable answers, shared by evaluation and teacher distillation.

  GSM8K  (openai/gsm8k, MIT)                 grade-school maths, numeric answers
  MATH   (EleutherAI/hendrycks_math, MIT)    competition maths; only integer-answer problems are used
  MBPP   (google-research-datasets/mbpp, CC-BY-4.0)  Python tasks graded by their own unit tests

Train splits feed distillation; test splits are used only for evaluation.
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "training" / "datasets" / "raw"
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "backend"))

from items import _num  # noqa: E402
from thrones.tools.calculator import calculator, evaluate  # noqa: E402

MATH_SUFFIX = "\n\nSolve it step by step. Finish with a final line in the form 'Answer: <number>'."
CODE_SUFFIX = ("\n\nWrite the Python function. Put the complete code in one ```python code block, "
               "then briefly explain it.")
TOOLS = [calculator.schema()]


# ------------------------------------------------------------------------------ loaders
def _boxed(solution: str) -> str | None:
    i = solution.rfind("\\boxed{")
    if i < 0:
        return None
    depth, j, out = 0, i + len("\\boxed{"), []
    while j < len(solution):
        ch = solution[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                break
            depth -= 1
        out.append(ch)
        j += 1
    return "".join(out).strip()


def gsm8k(split: str) -> list[dict[str, Any]]:
    from datasets import load_dataset

    ds = load_dataset("openai/gsm8k", "main", split=split, cache_dir=str(RAW))
    out = []
    for i, r in enumerate(ds):
        gold = r["answer"].split("####")[-1].strip().replace(",", "")
        out.append({"id": f"gsm8k-{split}-{i}", "kind": "gsm8k", "prompt": r["question"] + MATH_SUFFIX,
                    "gold": float(gold), "source": "openai/gsm8k", "license": "MIT"})
    return out


def math_int(split: str) -> list[dict[str, Any]]:
    from datasets import load_dataset

    out = []
    for cfg in ("algebra", "counting_and_probability", "geometry", "intermediate_algebra", "number_theory",
                "prealgebra", "precalculus"):
        ds = load_dataset("EleutherAI/hendrycks_math", cfg, split=split, cache_dir=str(RAW))
        for i, r in enumerate(ds):
            ans = _boxed(r["solution"])
            if ans is None:
                continue
            ans = ans.replace("\\!", "").replace(",", "").replace("$", "").strip()
            if re.fullmatch(r"-?\d+", ans):
                out.append({"id": f"math-{split}-{cfg}-{i}", "kind": "math", "level": r["level"],
                            "prompt": r["problem"] + MATH_SUFFIX, "gold": float(ans),
                            "source": f"EleutherAI/hendrycks_math ({cfg})", "license": "MIT"})
    return out


def mbpp(splits: tuple[str, ...]) -> list[dict[str, Any]]:
    from datasets import load_dataset

    out = []
    for split in splits:
        ds = load_dataset("google-research-datasets/mbpp", "full", split=split, cache_dir=str(RAW))
        for r in ds:
            tests = "\n".join(r["test_list"])
            prompt = (f"{r['text']}\nYour function must pass these tests:\n```python\n{tests}\n```" + CODE_SUFFIX)
            out.append({"id": f"mbpp-{r['task_id']}", "kind": "mbpp", "prompt": prompt,
                        "tests": (r.get("test_setup_code") or "") + "\n" + tests,
                        "source": "google-research-datasets/mbpp", "license": "CC-BY-4.0"})
    return out


def sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    rows = list(rows)
    random.Random(seed).shuffle(rows)
    return rows[:n]


# ------------------------------------------------------------------------------ grading
def code_block(text: str) -> str | None:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.DOTALL)
    return blocks[0] if blocks else None


def run_tests(code: str, tests: str) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.py"
        p.write_text(code + "\n\n" + tests + "\nprint('ALL_OK')\n", encoding="utf-8")
        for attempt in range(8):
            try:
                r = subprocess.run([sys.executable, "-I", str(p)], capture_output=True, text=True, timeout=10,
                                   cwd=tmp)
                break
            except subprocess.TimeoutExpired:
                return False
            except OSError:
                # Windows can briefly refuse to start a process when memory is nearly exhausted
                # ("paging file is too small"); wait and retry instead of losing the whole run.
                if attempt == 7:
                    raise
                time.sleep(10)
    return "ALL_OK" in r.stdout


def grade(item: dict, text: str) -> bool:
    if item["kind"] == "mbpp":
        code = code_block(text)
        return bool(code) and run_tests(code, item["tests"])
    v = _num(text)
    return v is not None and abs(v - item["gold"]) <= max(1e-6, abs(item["gold"]) * 1e-6)


# ------------------------------------------------------------------- tool-using solve loop
def solve(post, messages: list[dict], tools: list | None, max_tokens: int = 1500,
          temperature: float = 0.0) -> tuple[list[dict], str]:
    """Run the model with the real calculator for up to 6 rounds.

    `post(body) -> choice dict`. Returns (assistant/tool messages produced, final text).
    """
    produced: list[dict] = []
    msgs = list(messages)
    for _ in range(6):
        body = {"messages": msgs, "max_tokens": max_tokens, "temperature": temperature,
                "top_k": 1 if temperature == 0 else 20, "top_p": 1.0 if temperature == 0 else 0.95,
                "chat_template_kwargs": {"enable_thinking": False}}
        if tools:
            body["tools"] = tools
        choice = post(body)
        msg = choice["message"]
        tcs = msg.get("tool_calls") or []
        if not tcs:
            final = msg.get("content") or ""
            produced.append({"role": "assistant", "content": final})
            return produced, final
        turn = {"role": "assistant", "content": msg.get("content") or "", "tool_calls": []}
        results = []
        for k, tc in enumerate(tcs):
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
                expr = str(args["expression"])
                out = f"{expr} = {evaluate(expr)}"
            except Exception as exc:
                args, out = {"expression": str(tc["function"].get("arguments", ""))}, f"Error: {type(exc).__name__}: {exc}"
            cid = tc.get("id") or f"call_{len(produced)}_{k}"
            turn["tool_calls"].append({"id": cid, "type": "function",
                                       "function": {"name": tc["function"]["name"], "arguments": args}})
            results.append({"role": "tool", "tool_call_id": cid, "content": out})
        produced.append(turn)
        produced.extend(results)
        # The server wants OpenAI-style string arguments; the training rows keep a dict (what the template expects).
        wire = {**turn, "tool_calls": [{**t, "function": {**t["function"], "arguments": json.dumps(t["function"]["arguments"])}}
                                       for t in turn["tool_calls"]]}
        msgs = msgs + [wire] + results
    return produced, ""
