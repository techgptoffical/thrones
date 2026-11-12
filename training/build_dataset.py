"""Build the Thrones SFT dataset v0.1 from licensed sources and code-generated examples.

Every row records: source, license, origin (how it was made) and transform.
No row is produced by Claude/Fable or any other proprietary model.

Outputs (training/datasets/):
  thrones_sft_v0.1.train.jsonl     training rows
  thrones_sft_v0.1.heldout.jsonl   held-out rows (never trained on)
  thrones_sft_v0.1.manifest.json   counts, licences, sha256 of each file

Run with the training environment:
  .venv-train\\Scripts\\python training\\build_dataset.py
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from thrones.reasoning import prompts  # noqa: E402
from thrones.tools.calculator import calculator, evaluate  # noqa: E402

OUT = ROOT / "training" / "datasets"
RAW = OUT / "raw"
VERSION = "0.1"
SEED = 20261112
rng = random.Random(SEED)

# Describes the model as it will exist after training, so the system prompt and the target answers agree.
BASE_ENTRY = {"id": "thrones-adapter-0.1-qwen3.5-4b", "name": "Thrones Adapter 0.1 (Qwen3.5 4B)",
              "base_name": "Qwen3.5 4B", "adapter": "Thrones Adapter 0.1", "quantization": "Q4_K_M",
              "publisher": "Alibaba Cloud (Qwen team)"}
SETTINGS = {"style": "balanced", "custom_instructions": ""}
TOOLS = [calculator.schema()]


def system(mode: str = "fast", with_tools: bool = True) -> str:
    text = prompts.system_prompt(BASE_ENTRY, SETTINGS, mode, [])
    if with_tools:
        text += "\n\n" + prompts.TOOL_GUIDE
    return text


def row(messages: list[dict], source: str, license_: str, origin: str, transform: str, kind: str,
        tools: bool = True) -> dict:
    return {"messages": messages, "tools": TOOLS if tools else None,
            "meta": {"kind": kind, "source": source, "license": license_, "origin": origin, "transform": transform}}


def inr(x: float) -> str:
    """Indian digit grouping: 1234567.5 -> 12,34,567.50"""
    neg = x < 0
    x = abs(x)
    whole, frac = f"{x:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    s = whole if frac == "00" else f"{whole}.{frac}"
    return ("-" if neg else "") + s


def num(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}"
    return f"{x:,.4f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------------ tool use (code-generated)
def tool_turn(user: str, steps: list[tuple[str, str]], final: str, lang: str) -> list[dict]:
    """steps: [(expression, short explanation)] each executed by the real calculator."""
    msgs: list[dict] = [{"role": "system", "content": system()}, {"role": "user", "content": user}]
    for i, (expr, _why) in enumerate(steps):
        result = evaluate(expr)
        call_id = f"call_{i}"
        msgs.append({"role": "assistant", "content": "",
                     "tool_calls": [{"id": call_id, "type": "function",
                                     "function": {"name": "calculator", "arguments": {"expression": expr}}}]})
        msgs.append({"role": "tool", "tool_call_id": call_id, "content": f"{expr} = {result}"})
    msgs.append({"role": "assistant", "content": final})
    return msgs


def gen_discount_gst(lang: str) -> list[dict]:
    price = rng.choice([1299, 2499, 3750, 4999, 8650, 12500, 18999, 24750, 48750, 65000])
    disc = rng.choice([5, 10, 12, 15, 18, 20, 25, 30])
    gst = rng.choice([5, 12, 18, 28])
    e1 = f"{price} * (1 - {disc}/100)"
    after = float(evaluate(e1))
    e2 = f"{after} * (1 + {gst}/100)" if after != int(after) else f"{int(after)} * (1 + {gst}/100)"
    final_v = float(evaluate(e2))
    if lang == "en":
        user = f"An item is listed at ₹{inr(price)}. There is a {disc}% discount, and then {gst}% GST is added on the discounted price. What do I pay?"
        final = (f"- Price after the {disc}% discount: ₹{inr(after)}\n- Adding {gst}% GST: ₹{inr(final_v)}\n\n"
                 f"You pay **₹{inr(final_v)}**.")
    else:
        user = f"Ek cheez ka price ₹{inr(price)} hai. {disc}% discount milta hai, phir discounted price par {gst}% GST lagta hai. Total kitna dena padega?"
        final = (f"- {disc}% discount ke baad: ₹{inr(after)}\n- {gst}% GST jodne par: ₹{inr(final_v)}\n\n"
                 f"Aapko **₹{inr(final_v)}** dene honge.")
    return tool_turn(user, [(e1, "discount"), (e2, "gst")], final, lang)


def gen_compound(lang: str) -> list[dict]:
    p = rng.choice([10000, 25000, 50000, 75000, 100000, 250000, 500000])
    r = rng.choice([6, 6.5, 7, 7.5, 8, 9, 10, 12])
    n = rng.choice([2, 3, 4, 5, 7, 10])
    expr = f"{p} * (1 + {r}/100) ** {n}"
    amount = float(evaluate(expr))
    e2 = f"{amount} - {p}"
    interest = float(evaluate(e2))
    if lang == "en":
        user = f"If I invest ₹{inr(p)} at {r}% interest compounded annually for {n} years, how much will I have, and how much of it is interest?"
        final = (f"Using A = P(1 + r)^n:\n\n- Amount after {n} years: **₹{inr(amount)}**\n"
                 f"- Interest earned: **₹{inr(interest)}**")
    else:
        user = f"₹{inr(p)} ko {r}% saalana compound interest par {n} saal ke liye lagaun to kitna milega, aur usme interest kitna hoga?"
        final = (f"Formula A = P(1 + r)^n se:\n\n- {n} saal baad amount: **₹{inr(amount)}**\n"
                 f"- Kul interest: **₹{inr(interest)}**")
    return tool_turn(user, [(expr, "amount"), (e2, "interest")], final, lang)


def gen_emi(lang: str) -> list[dict]:
    p = rng.choice([300000, 500000, 750000, 850000, 1200000, 2500000, 4000000])
    rate = rng.choice([7.5, 8.25, 8.5, 9, 9.5, 10.5, 11])
    years = rng.choice([3, 5, 7, 10, 15, 20])
    mr = f"({rate}/12/100)"
    n = years * 12
    expr = f"{p} * {mr} * (1 + {mr}) ** {n} / ((1 + {mr}) ** {n} - 1)"
    emi = float(evaluate(expr))
    e2 = f"{round(emi, 2)} * {n} - {p}"
    interest = float(evaluate(e2))
    if lang == "en":
        user = f"What is the monthly EMI on a loan of ₹{inr(p)} at {rate}% per year for {years} years? Also tell me the total interest."
        final = (f"EMI = P·r·(1+r)^n / ((1+r)^n − 1), with r = {rate}%/12 per month and n = {n} months.\n\n"
                 f"- Monthly EMI: **₹{inr(round(emi, 2))}**\n- Total interest over {years} years: **₹{inr(interest)}**")
    else:
        user = f"₹{inr(p)} ke loan par {rate}% saalana byaaj aur {years} saal ke liye monthly EMI kitni banegi? Total interest bhi batao."
        final = (f"EMI = P·r·(1+r)^n / ((1+r)^n − 1), jahan r = {rate}%/12 har mahine aur n = {n} mahine.\n\n"
                 f"- Monthly EMI: **₹{inr(round(emi, 2))}**\n- {years} saal mein total interest: **₹{inr(interest)}**")
    return tool_turn(user, [(expr, "emi"), (e2, "interest")], final, lang)


def gen_bigmul(lang: str) -> list[dict]:
    a, b = rng.randint(1000, 99999), rng.randint(100, 9999)
    c = rng.randint(10000, 2000000)
    op = rng.choice(["-", "+"])
    expr = f"{a} * {b} {op} {c}"
    v = float(evaluate(expr))
    if lang == "en":
        user = rng.choice([f"Compute {a} × {b} {op.replace('-', '−')} {c} exactly.", f"What is {a} times {b}, {'minus' if op == '-' else 'plus'} {c}?"])
        final = f"{a} × {b} {op.replace('-', '−')} {c} = **{num(v)}**"
    else:
        user = f"{a} ko {b} se guna karke {c} {'ghatao' if op == '-' else 'jodo'}. Exact answer chahiye."
        final = f"{a} × {b} {op.replace('-', '−')} {c} = **{num(v)}**"
    return tool_turn(user, [(expr, "")], final, lang)


def gen_average(lang: str) -> list[dict]:
    k = rng.randint(5, 9)
    vals = [rng.randint(35, 99) for _ in range(k)]
    expr = f"mean([{', '.join(map(str, vals))}])"
    v = float(evaluate(expr))
    shown = ", ".join(map(str, vals))
    if lang == "en":
        user = f"My test scores are {shown}. What's my average?"
        final = f"Your average score is **{num(round(v, 2))}** (sum {sum(vals)} ÷ {k} tests)."
    else:
        user = f"Mere marks hain {shown}. Average kitna hua?"
        final = f"Aapka average **{num(round(v, 2))}** hai (total {sum(vals)} ÷ {k} tests)."
    return tool_turn(user, [(expr, "")], final, lang)


def gen_speed(lang: str) -> list[dict]:
    km = rng.choice([45, 120, 180, 240, 315, 420, 560])
    h, m = rng.randint(1, 7), rng.choice([0, 10, 15, 20, 30, 40, 45, 50])
    expr = f"{km} / ({h} + {m}/60)"
    v = float(evaluate(expr))
    if lang == "en":
        user = f"A bus covers {km} km in {h} hours {m} minutes. What is its average speed in km/h?"
        final = f"Time = {h} h {m} min = {num(round(h + m / 60, 4))} h, so the average speed is **{num(round(v, 2))} km/h**."
    else:
        user = f"Ek bus {km} km {h} ghante {m} minute mein chalti hai. Average speed kitni hai km/h mein?"
        final = f"Samay = {h} ghante {m} minute = {num(round(h + m / 60, 4))} ghante, isliye average speed **{num(round(v, 2))} km/h** hai."
    return tool_turn(user, [(expr, "")], final, lang)


TOOL_GENERATORS = [gen_discount_gst, gen_compound, gen_emi, gen_bigmul, gen_average, gen_speed]


def tool_rows(n: int, kind: str = "tool_use") -> list[dict]:
    rows = []
    for _ in range(n):
        gen = rng.choice(TOOL_GENERATORS)
        lang = rng.choice(["en", "en", "hinglish"])
        rows.append(row(gen(lang), "thrones-generated", "MIT (Thrones project)",
                        "code templates; every number computed by the Thrones calculator", gen.__name__, kind))
    return rows


# --------------------------------------------------------------------------- identity (authored)
IDENTITY_Q = [
    ("en", "Who are you?"), ("en", "What model are you running on?"), ("en", "Are you ChatGPT?"),
    ("en", "Did TECH GPT train you from scratch?"), ("en", "What are you, exactly?"),
    ("hinglish", "Tum kaun ho?"), ("hinglish", "Tum kis model par chalte ho?"), ("hinglish", "Kya tum ChatGPT ho?"),
    ("hindi", "आप कौन हैं?"), ("hindi", "आप किस मॉडल पर चलते हैं?"),
]
IDENTITY_A = {
    "en": "I'm Thrones, a local assistant running the Qwen3.5 4B model made by Alibaba Cloud's Qwen team, here with a "
          "small Thrones fine-tune on top. Thrones is the app around the model; the underlying model was not trained "
          "from scratch by Thrones. Everything runs on your own computer.",
    "hinglish": "Main Thrones hoon — ek local assistant jo Alibaba Cloud ki Qwen team ke Qwen3.5 4B model par chalta hai, "
                "upar se Thrones ka chhota sa fine-tune hai. Thrones app hai; base model Thrones ne zero se train nahi kiya. "
                "Sab kuch aapke apne computer par chalta hai.",
    "hindi": "मैं Thrones हूँ — एक लोकल असिस्टेंट जो Alibaba Cloud की Qwen टीम के Qwen3.5 4B मॉडल पर चलता है, जिसके ऊपर "
             "Thrones का एक छोटा फ़ाइन-ट्यून है। Thrones ऐप है; मूल मॉडल Thrones ने शुरू से ट्रेन नहीं किया। सब कुछ आपके अपने "
             "कंप्यूटर पर चलता है।",
}


def identity_rows() -> list[dict]:
    out = []
    for lang, q in IDENTITY_Q:
        msgs = [{"role": "system", "content": system()}, {"role": "user", "content": q},
                {"role": "assistant", "content": IDENTITY_A[lang]}]
        out.append(row(msgs, "thrones-authored", "MIT (Thrones project)", "written by the Thrones team", "none",
                       "identity"))
    return out


# ------------------------------------------------------------------------- licensed datasets
def load_hinglish(n_train: int, n_held: int) -> tuple[list[dict], list[dict]]:
    from datasets import load_dataset

    ds = load_dataset("findnitai/english-to-hinglish", split="train", cache_dir=str(RAW))
    human = [r["translation"] for r in ds if int(r["translation"].get("source", 0)) == 1]
    human = [t for t in human if 20 <= len(t["en"]) <= 300 and 10 <= len(t["hi_ng"]) <= 300]
    rng.shuffle(human)
    rows = []
    for i, t in enumerate(human[: n_train + n_held]):
        if rng.random() < 0.7:
            q = rng.choice(["Translate into Hinglish (Roman script): ", "Isko Hinglish mein likho: ",
                            "Convert this to casual Hinglish: "]) + t["en"]
            a = t["hi_ng"]
        else:
            q = rng.choice(["Iska English translation do: ", "Translate this Hinglish into English: "]) + t["hi_ng"]
            a = t["en"]
        msgs = [{"role": "system", "content": system()}, {"role": "user", "content": q},
                {"role": "assistant", "content": a}]
        rows.append(row(msgs, "findnitai/english-to-hinglish (source=1, human-annotated rows only)", "Apache-2.0",
                        "aggregated public human-annotated corpora (Hinglish TOP, CMU DoG, HinGE, PHINC)",
                        "wrapped as a translation instruction", "hinglish"))
    return rows[:n_train], rows[n_train:]


def load_aya_hindi(n: int) -> list[dict]:
    from datasets import load_dataset

    ds = load_dataset("CohereLabs/aya_dataset", split="train", cache_dir=str(RAW))
    hi = [r for r in ds if r["language"] == "Hindi" and 20 <= len(r["targets"]) <= 1500]
    rng.shuffle(hi)
    return [row([{"role": "system", "content": system()}, {"role": "user", "content": r["inputs"]},
                 {"role": "assistant", "content": r["targets"]}],
                "CohereLabs/aya_dataset (language=Hindi)", "Apache-2.0",
                f"human-written by Aya contributors ({r['annotation_type']})", "none", "hindi") for r in hi[:n]]


def load_oasst(n: int, lang: str) -> list[dict]:
    from datasets import load_dataset

    ds = load_dataset("OpenAssistant/oasst2", split="train", cache_dir=str(RAW))
    by_parent: dict[str, list[dict]] = {}
    prompts_ = {}
    for r in ds:
        if r["lang"] != lang or r.get("deleted"):
            continue
        if r["parent_id"] is None and r["role"] == "prompter":
            prompts_[r["message_id"]] = r["text"]
        elif r["role"] == "assistant" and r["parent_id"]:
            by_parent.setdefault(r["parent_id"], []).append(r)
    pairs = []
    for mid, q in prompts_.items():
        replies = [x for x in by_parent.get(mid, []) if x.get("rank") == 0 and 80 <= len(x["text"]) <= 2500]
        if replies and 10 <= len(q) <= 1200:
            pairs.append((q, replies[0]["text"]))
    rng.shuffle(pairs)
    return [row([{"role": "system", "content": system()}, {"role": "user", "content": q},
                 {"role": "assistant", "content": a}],
                f"OpenAssistant/oasst2 (lang={lang}, first turn, rank-0 reply)", "Apache-2.0",
                "human-written conversations", "first turn only", f"general_{lang}") for q, a in pairs[:n]]


# ------------------------------------------------------------------------------------- main
def write(path: Path, rows: list[dict]) -> str:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    train: list[dict] = []
    held: list[dict] = []
    train += tool_rows(1100)
    held += tool_rows(150, kind="tool_use")
    train += identity_rows() * 3
    hing_train, hing_held = load_hinglish(700, 100)
    train += hing_train
    held += hing_held
    train += load_aya_hindi(600)
    train += load_oasst(550, "en")
    rng.shuffle(train)

    # Guard: no held-out user prompt may appear in training.
    seen = {json.dumps(r["messages"][1], ensure_ascii=False) for r in train}
    held = [r for r in held if json.dumps(r["messages"][1], ensure_ascii=False) not in seen]

    name = f"thrones_sft_v{VERSION}"
    sha_train = write(OUT / f"{name}.train.jsonl", train)
    sha_held = write(OUT / f"{name}.heldout.jsonl", held)
    licences = Counter(r["meta"]["license"] for r in train)
    manifest = {
        "version": VERSION, "seed": SEED,
        "files": {f"{name}.train.jsonl": {"rows": len(train), "sha256": sha_train},
                  f"{name}.heldout.jsonl": {"rows": len(held), "sha256": sha_held}},
        "train_by_kind": dict(Counter(r["meta"]["kind"] for r in train)),
        "heldout_by_kind": dict(Counter(r["meta"]["kind"] for r in held)),
        "train_by_source": dict(Counter(r["meta"]["source"] for r in train)),
        "licences": dict(licences),
        "excluded": "No outputs from Claude, Fable or any proprietary model; no non-commercial datasets.",
    }
    (OUT / f"{name}.manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
