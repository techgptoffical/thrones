"""Build the Thrones SFT dataset v0.2.

Changes from v0.1:
  * + verified Qwen3.5 9B teacher solutions for GSM8K / MATH / MBPP train problems (distill_teacher.py)
  * tool-use: more phrasings per template
  * identity: several paraphrased answers instead of one memorised paragraph
  * held-out tool use has two parts: in-distribution (training templates, new numbers) and
    out-of-distribution (three question types that never appear in any training set)

    .venv-train\\Scripts\\python training\\build_dataset_v02.py
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "training"))

import build_dataset as v1  # noqa: E402  (reuses v0.1 generators and loaders)
from thrones.reasoning import prompts  # noqa: E402

VERSION = "0.2"
SEED = 20261113
OUT = v1.OUT
DISTILL = OUT / "distill_v0.2.jsonl"

ENTRY = {"id": "thrones-adapter-0.2-qwen3.5-4b", "name": "Thrones Adapter 0.2 (Qwen3.5 4B)",
         "base_name": "Qwen3.5 4B", "adapter": "Thrones Adapter 0.2", "quantization": "Q4_K_M",
         "publisher": "Alibaba Cloud (Qwen team)"}


def system() -> str:
    return prompts.system_prompt(ENTRY, v1.SETTINGS, "fast", []) + "\n\n" + prompts.TOOL_GUIDE


# Re-point the v0.1 helpers at the v0.2 identity and a fresh random stream.
v1.system = lambda mode="fast", with_tools=True: system()  # noqa: E731
v1.rng = random.Random(SEED)
rng = v1.rng


# ------------------------------------------------------- new tool templates (OOD: held-out only)
def gen_unit_convert(lang: str) -> list[dict]:
    kind = rng.choice(["kmh_ms", "c_f", "kg_lb", "inch_cm"])
    v = rng.choice([12.5, 36, 54, 72, 90, 108, 37.5, 68, 101.3, 154, 172.5])
    expr, unit_in, unit_out = {
        "kmh_ms": (f"{v} * 1000 / 3600", "km/h", "m/s"), "c_f": (f"{v} * 9 / 5 + 32", "°C", "°F"),
        "kg_lb": (f"{v} * 2.20462", "kg", "lb"), "inch_cm": (f"{v} * 2.54", "inches", "cm")}[kind]
    out = float(v1.evaluate(expr))
    if lang == "en":
        user = f"Convert {v} {unit_in} to {unit_out}."
        final = f"{v} {unit_in} = **{v1.num(round(out, 2))} {unit_out}**"
    else:
        user = f"{v} {unit_in} ko {unit_out} mein convert karo."
        final = f"{v} {unit_in} = **{v1.num(round(out, 2))} {unit_out}**"
    return v1.tool_turn(user, [(expr, "")], final, lang)


def gen_profit_loss(lang: str) -> list[dict]:
    cost = rng.choice([450, 1200, 2750, 3600, 8400, 15500, 42000])
    sell = round(cost * rng.choice([0.82, 0.9, 1.08, 1.15, 1.27, 1.4]))
    expr = f"({sell} - {cost}) / {cost} * 100"
    pct = float(v1.evaluate(expr))
    word = "profit" if pct >= 0 else "loss"
    if lang == "en":
        user = f"I bought something for ₹{v1.inr(cost)} and sold it for ₹{v1.inr(sell)}. What is my {word} percentage?"
        final = f"That is a {word} of **{v1.num(round(abs(pct), 2))}%** on the cost price."
    else:
        user = f"Maine ₹{v1.inr(cost)} mein kharida aur ₹{v1.inr(sell)} mein becha. {word.title()} kitne percent hua?"
        final = f"Cost price par **{v1.num(round(abs(pct), 2))}%** ka {word} hua."
    return v1.tool_turn(user, [(expr, "")], final, lang)


def gen_split_bill(lang: str) -> list[dict]:
    bill = rng.choice([1840, 2375, 3960, 5420, 7815, 12650])
    tip = rng.choice([5, 10, 12, 15])
    people = rng.choice([3, 4, 6, 7, 9])
    expr = f"{bill} * (1 + {tip}/100) / {people}"
    each = float(v1.evaluate(expr))
    if lang == "en":
        user = f"Our restaurant bill is ₹{v1.inr(bill)}. We add a {tip}% tip and split it equally among {people} people. How much does each person pay?"
        final = f"Each person pays **₹{v1.inr(round(each, 2))}**."
    else:
        user = f"Restaurant ka bill ₹{v1.inr(bill)} hai. {tip}% tip jodkar {people} logon mein barabar baantna hai. Har ek ko kitna dena hai?"
        final = f"Har ek ko **₹{v1.inr(round(each, 2))}** dene honge."
    return v1.tool_turn(user, [(expr, "")], final, lang)


OOD_GENERATORS = [gen_unit_convert, gen_profit_loss, gen_split_bill]


def tool_rows(gens: list, n: int, kind: str) -> list[dict]:
    rows = []
    for _ in range(n):
        gen = rng.choice(gens)
        lang = rng.choice(["en", "en", "hinglish"])
        rows.append(v1.row(gen(lang), "thrones-generated", "MIT (Thrones project)",
                           "code templates; every number computed by the Thrones calculator", gen.__name__, kind))
    return rows


# ------------------------------------------------------------------------- identity (varied)
IDENTITY_Q = {
    "en": ["Who are you?", "What model are you running on?", "Are you ChatGPT?", "Did TECH GPT train you from scratch?",
           "What are you, exactly?", "Which company made you?", "Are you Claude or Gemini?", "Introduce yourself briefly."],
    "hinglish": ["Tum kaun ho?", "Tum kis model par chalte ho?", "Kya tum ChatGPT ho?", "Apne baare mein batao.",
                 "Tumhe kisne banaya?"],
    "hindi": ["आप कौन हैं?", "आप किस मॉडल पर चलते हैं?", "क्या आप ChatGPT हैं?"],
}
IDENTITY_A = {
    "en": [
        "I'm Thrones, an assistant that runs locally on your computer. My language model is Qwen3.5 4B from Alibaba Cloud's Qwen team, with a small Thrones fine-tune (Thrones Adapter 0.2) on top. Thrones didn't train the base model from scratch.",
        "I'm Thrones. Under the hood I run Qwen3.5 4B, an open-weight model made by Alibaba Cloud's Qwen team, plus a lightweight fine-tune trained by the Thrones project. Everything runs on your own PC.",
        "No — I'm Thrones, a local assistant. The model doing the thinking is Qwen3.5 4B by the Qwen team at Alibaba Cloud, adjusted with a small Thrones adapter. I'm not ChatGPT, Claude or Gemini.",
    ],
    "hinglish": [
        "Main Thrones hoon — aapke computer par chalne wala local assistant. Mera model Alibaba Cloud ki Qwen team ka Qwen3.5 4B hai, jiske upar Thrones ka ek chhota fine-tune (Thrones Adapter 0.2) laga hai. Base model Thrones ne zero se train nahi kiya.",
        "Main Thrones hoon. Andar se main Qwen3.5 4B model chalata hoon, jo Alibaba Cloud ki Qwen team ne banaya hai, aur upar se Thrones ka halka sa fine-tune hai. Sab kuch aapke PC par hi chalta hai.",
    ],
    "hindi": [
        "मैं Thrones हूँ — आपके कंप्यूटर पर चलने वाला लोकल असिस्टेंट। मेरा मॉडल Alibaba Cloud की Qwen टीम का Qwen3.5 4B है, जिस पर Thrones का एक छोटा फ़ाइन-ट्यून (Thrones Adapter 0.2) लगा है। मूल मॉडल Thrones ने शुरू से ट्रेन नहीं किया।",
        "मैं Thrones हूँ। मेरे अंदर Alibaba Cloud की Qwen टीम का Qwen3.5 4B मॉडल चलता है, साथ में Thrones का एक हल्का फ़ाइन-ट्यून। सब कुछ आपके अपने PC पर चलता है।",
    ],
}


def identity_rows() -> list[dict]:
    out = []
    for lang, qs in IDENTITY_Q.items():
        for q in qs:
            for a in rng.sample(IDENTITY_A[lang], k=min(2, len(IDENTITY_A[lang]))):
                out.append(v1.row([{"role": "system", "content": system()}, {"role": "user", "content": q},
                                   {"role": "assistant", "content": a}],
                                  "thrones-authored", "MIT (Thrones project)", "written by the Thrones team", "none",
                                  "identity"))
    return out


def distill_rows() -> list[dict]:
    rows = []
    for line in DISTILL.open(encoding="utf-8"):
        r = json.loads(line)
        if "messages" in r:
            rows.append(r)
    return rows


def write(path: Path, rows: list[dict]) -> str:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    train: list[dict] = []
    held: list[dict] = []
    train += tool_rows(v1.TOOL_GENERATORS, 900, "tool_use")
    held += tool_rows(v1.TOOL_GENERATORS, 120, "tool_use")            # in-distribution held-out
    held += tool_rows(OOD_GENERATORS, 120, "tool_use_ood")            # never trained on (0.1 or 0.2)
    train += identity_rows()
    # Hinglish test = v0.1's held-out pairs (never trained by 0.1), and kept out of 0.2's training too,
    # so base, 0.1 and 0.2 are compared on exactly the same unseen pairs.
    v01_held = [json.loads(l) for l in (OUT / "thrones_sft_v0.1.heldout.jsonl").open(encoding="utf-8")]
    hing_held = [r for r in v01_held if r["meta"]["kind"] == "hinglish"]
    held_texts = set()
    for r in hing_held:
        held_texts.add(r["messages"][-1]["content"].strip())
        held_texts.add(r["messages"][1]["content"].split(": ", 1)[-1].strip())
    hing_train, _ = v1.load_hinglish(800, 0)
    hing_train = [r for r in hing_train
                  if r["messages"][-1]["content"].strip() not in held_texts
                  and r["messages"][1]["content"].split(": ", 1)[-1].strip() not in held_texts][:700]
    train += hing_train
    held += hing_held
    train += v1.load_aya_hindi(600)
    train += v1.load_oasst(500, "en")
    distilled = distill_rows()
    train += distilled
    rng.shuffle(train)

    # No test prompt may appear in the training data of 0.2 or of 0.1.
    def user_text(r: dict) -> str:
        return r["messages"][1]["content"].strip()

    seen = {user_text(r) for r in train}
    seen |= {user_text(json.loads(l)) for l in (OUT / "thrones_sft_v0.1.train.jsonl").open(encoding="utf-8")}
    held = [r for r in held if user_text(r) not in seen]

    name = f"thrones_sft_v{VERSION}"
    sha_t = write(OUT / f"{name}.train.jsonl", train)
    sha_h = write(OUT / f"{name}.heldout.jsonl", held)
    manifest = {
        "version": VERSION, "seed": SEED,
        "files": {f"{name}.train.jsonl": {"rows": len(train), "sha256": sha_t},
                  f"{name}.heldout.jsonl": {"rows": len(held), "sha256": sha_h},
                  DISTILL.name: {"sha256": hashlib.sha256(DISTILL.read_bytes()).hexdigest()}},
        "train_by_kind": dict(Counter(r["meta"]["kind"] for r in train)),
        "heldout_by_kind": dict(Counter(r["meta"]["kind"] for r in held)),
        "train_by_source": dict(Counter(r["meta"]["source"] for r in train)),
        "licences": dict(Counter(r["meta"]["license"] for r in train)),
        "teacher": "Qwen/Qwen3.5-9B (Apache-2.0), Q4_K_M via llama.cpp, verified solutions only",
        "excluded": "No outputs from Claude, Fable or any proprietary model; no non-commercial datasets.",
    }
    (OUT / f"{name}.manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
