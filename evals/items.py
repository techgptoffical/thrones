"""Thrones evaluation set v1 — 39 items written for this project (not copied from any benchmark).

Every item has a deterministic grader. Small on purpose: it is a regression
and comparison tool for this machine, not a leaderboard. Scores from 39 items
carry roughly ±8 points of sampling noise, so small differences mean little.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ANSWER_SUFFIX = "\n\nFinish with a final line in the form 'Answer: <value>'."


def _answer(text: str) -> str:
    found = re.findall(r"answer\s*[:：]\s*(.+)", text, flags=re.IGNORECASE)
    return (found[-1] if found else text.strip().splitlines()[-1] if text.strip() else "").strip().strip("*").strip()


def _num(text: str) -> float | None:
    a = _answer(text).replace(",", "").replace("₹", "")
    m = re.findall(r"-?\d+(?:\.\d+)?", a)
    return float(m[0]) if m else None


def num(target: float, tol: float = 1e-6) -> Callable[[str], bool]:
    return lambda t: (v := _num(t)) is not None and abs(v - target) <= max(tol, abs(target) * 1e-9)


def word(*options: str) -> Callable[[str], bool]:
    return lambda t: any(o.lower() in _answer(t).lower() for o in options)


def contains(*options: str) -> Callable[[str], bool]:
    return lambda t: any(o.lower() in t.lower() for o in options)


DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _code_block(text: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.DOTALL)
    return blocks[-1] if blocks else text


def code(tests: str) -> Callable[[str], bool]:
    """Run the model's function against fixed asserts in a separate interpreter with a timeout."""
    def grade(text: str) -> bool:
        src = _code_block(text) + "\n\n" + tests + "\nprint('ALL_OK')\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.py"
            p.write_text(src, encoding="utf-8")
            try:
                r = subprocess.run([sys.executable, "-I", str(p)], capture_output=True, text=True, timeout=10, cwd=tmp)
            except subprocess.TimeoutExpired:
                return False
        return "ALL_OK" in r.stdout
    return grade


def lines_exactly(n: int) -> Callable[[str], bool]:
    return lambda t: len([ln for ln in t.strip().splitlines() if ln.strip()]) == n


def exact(s: str) -> Callable[[str], bool]:
    return lambda t: t.strip().strip(".").strip() == s


def word_count(n: int) -> Callable[[str], bool]:
    return lambda t: len(re.findall(r"[A-Za-z']+", t)) == n


def json_person(t: str) -> bool:
    raw = t.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return isinstance(obj, dict) and str(obj.get("name", "")).lower() == "ravi" and int(obj.get("age", -1)) == 31


def no_letter_e(t: str) -> bool:
    s = t.strip()
    return len(s.split()) >= 4 and "e" not in s.lower()


def roman_only(t: str) -> bool:
    return "27" in t and not DEVANAGARI.search(t)


ITEMS: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- maths
    {"id": "math-01", "cat": "math", "q": "A train leaves at 09:40 and arrives at 14:15 the same day. How many minutes long is the journey?" + ANSWER_SUFFIX, "grade": num(275)},
    {"id": "math-02", "cat": "math", "q": "What is the sum of all integers from 1 to 250?" + ANSWER_SUFFIX, "grade": num(31375)},
    {"id": "math-03", "cat": "math", "q": "A shirt costs 1,200 rupees after a 20% discount. What was the original price in rupees?" + ANSWER_SUFFIX, "grade": num(1500)},
    {"id": "math-04", "cat": "math", "q": "How many positive divisors does 360 have?" + ANSWER_SUFFIX, "grade": num(24)},
    {"id": "math-05", "cat": "math", "q": "Pipe A fills a tank in 6 hours and pipe B fills it in 9 hours. Working together, how many hours do they take?" + ANSWER_SUFFIX, "grade": num(3.6, 0.01)},
    {"id": "math-06", "cat": "math", "q": "What is 2^20 - 1?" + ANSWER_SUFFIX, "grade": num(1048575)},
    {"id": "math-07", "cat": "math", "q": "10,000 rupees is invested at 10% interest compounded annually. What is the amount after 3 years?" + ANSWER_SUFFIX, "grade": num(13310, 0.01)},
    {"id": "math-08", "cat": "math", "q": "What is the remainder when 7^100 is divided by 5?" + ANSWER_SUFFIX, "grade": num(1)},
    {"id": "math-09", "cat": "math", "q": "In how many different orders can 5 people stand in a line?" + ANSWER_SUFFIX, "grade": num(120)},
    {"id": "math-10", "cat": "math", "q": "Compute 48213 × 9917 − 1234567." + ANSWER_SUFFIX, "grade": num(476893754)},
    # ---------------------------------------------------------------- logic
    {"id": "logic-01", "cat": "logic", "q": "Asha is older than Bilal. Bilal is older than Chen. Who is the youngest?" + ANSWER_SUFFIX, "grade": word("chen")},
    {"id": "logic-02", "cat": "logic", "q": "All bloops are razzies and all razzies are lazzies. Are all bloops definitely lazzies? Answer yes or no." + ANSWER_SUFFIX, "grade": word("yes")},
    {"id": "logic-03", "cat": "logic", "q": "A bat and a ball cost 1.10 dollars in total. The bat costs 1.00 dollar more than the ball. How many cents does the ball cost?" + ANSWER_SUFFIX, "grade": num(5)},
    {"id": "logic-04", "cat": "logic", "q": "I have 3 apples. I eat one, buy 4 more, then give away half of what I have. How many apples do I have now?" + ANSWER_SUFFIX, "grade": num(3)},
    {"id": "logic-05", "cat": "logic", "q": "Today is Wednesday. What day of the week will it be 100 days from today?" + ANSWER_SUFFIX, "grade": word("friday")},
    {"id": "logic-06", "cat": "logic", "q": "How many times does the letter 'r' appear in the word 'strawberry'?" + ANSWER_SUFFIX, "grade": num(3)},
    {"id": "logic-07", "cat": "logic", "q": "Mary's father has five daughters: Nana, Nene, Nini and Nono. What is the name of the fifth daughter?" + ANSWER_SUFFIX, "grade": word("mary")},
    {"id": "logic-08", "cat": "logic", "q": "Which number is larger: 9.11 or 9.9?" + ANSWER_SUFFIX, "grade": num(9.9, 1e-9)},
    # ----------------------------------------------------------------- code
    {"id": "code-01", "cat": "code", "q": "Write a Python function is_palindrome(s) that returns True if s reads the same forwards and backwards, ignoring case and any non-alphanumeric characters. Return only the code in one python code block.",
     "grade": code("assert is_palindrome('A man, a plan, a canal: Panama')\nassert not is_palindrome('hello')\nassert is_palindrome('')\nassert is_palindrome('No lemon, no melon')")},
    {"id": "code-02", "cat": "code", "q": "Write a Python function second_largest(nums) that returns the second largest DISTINCT value in a list of numbers, or None if there is none. Return only the code in one python code block.",
     "grade": code("assert second_largest([3, 1, 4, 4, 2]) == 3\nassert second_largest([5, 5]) is None\nassert second_largest([]) is None\nassert second_largest([-1, -7]) == -7")},
    {"id": "code-03", "cat": "code", "q": "Write a Python function merge_intervals(intervals) that takes a list of [start, end] pairs and returns a sorted list of merged, non-overlapping [start, end] pairs. Intervals that touch (end == start) should merge. Return only the code in one python code block.",
     "grade": code("assert merge_intervals([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]\nassert merge_intervals([[1,4],[4,5]]) == [[1,5]]\nassert merge_intervals([]) == []\nassert merge_intervals([[5,7],[1,2]]) == [[1,2],[5,7]]")},
    {"id": "code-04", "cat": "code", "q": "Write a Python function roman_to_int(s) that converts a Roman numeral string (I, V, X, L, C, D, M, with subtractive forms like IV and CM) to an integer. Return only the code in one python code block.",
     "grade": code("assert roman_to_int('III') == 3\nassert roman_to_int('LVIII') == 58\nassert roman_to_int('MCMXCIV') == 1994\nassert roman_to_int('XLIX') == 49")},
    {"id": "code-05", "cat": "code", "q": "Write a Python function word_freq(text) that returns a dict mapping each lowercase word to its count. Words are runs of letters a-z (ignore digits and punctuation). Return only the code in one python code block.",
     "grade": code("assert word_freq('The cat and the hat.') == {'the': 2, 'cat': 1, 'and': 1, 'hat': 1}\nassert word_freq('') == {}\nassert word_freq('A1 a, b!') == {'a': 2, 'b': 1}")},
    # ---------------------------------------------------- instruction following
    {"id": "if-01", "cat": "instruction", "q": "List exactly three fruits, one per line, with no numbering and no other text.", "grade": lines_exactly(3)},
    {"id": "if-02", "cat": "instruction", "q": "Reply with only the word YES in uppercase and nothing else.", "grade": exact("YES")},
    {"id": "if-03", "cat": "instruction", "q": "In exactly five English words, say what colour a clear daytime sky is. Output only those five words.", "grade": word_count(5)},
    {"id": "if-04", "cat": "instruction", "q": "Output only a JSON object with the keys \"name\" and \"age\" for a person named Ravi who is 31 years old. No explanation.", "grade": json_person},
    {"id": "if-05", "cat": "instruction", "q": "Write one English sentence of at least four words that does not contain the letter 'e' anywhere. Output only the sentence.", "grade": no_letter_e},
    # ------------------------------------------------------- hindi / hinglish
    {"id": "hi-01", "cat": "hindi", "q": "भारत की राजधानी क्या है? केवल एक शब्द में उत्तर दीजिए।", "grade": contains("दिल्ली")},
    {"id": "hi-02", "cat": "hindi", "q": "Translate into Hindi using Devanagari script: 'I am going to the market.' Output only the translation.", "grade": lambda t: bool(DEVANAGARI.search(t)) and any(w in t for w in ("बाज़ार", "बाजार", "मार्केट"))},
    {"id": "hi-03", "cat": "hindi", "q": "Hinglish mein jawab do (Roman script mein, Devanagari nahi): 12 aur 15 ka jod kitna hota hai?", "grade": roman_only},
    {"id": "hi-04", "cat": "hindi", "q": "Ek saal mein kitne mahine hote hain? Sirf number likho.", "grade": contains("12", "बारह")},
    {"id": "hi-05", "cat": "hindi", "q": "हिंदी में बताइए: पानी का रासायनिक सूत्र क्या है?", "grade": lambda t: bool(DEVANAGARI.search(t)) and bool(re.search(r"H\s*(?:2|₂)\s*O", t))},
    # ------------------------------------------------------------- knowledge
    {"id": "know-01", "cat": "knowledge", "q": "What is the chemical symbol for gold?" + ANSWER_SUFFIX, "grade": word("au")},
    {"id": "know-02", "cat": "knowledge", "q": "Who wrote the novel 'Pride and Prejudice'?" + ANSWER_SUFFIX, "grade": word("austen")},
    {"id": "know-03", "cat": "knowledge", "q": "Which is the largest planet in our solar system?" + ANSWER_SUFFIX, "grade": word("jupiter")},
    {"id": "know-04", "cat": "knowledge", "q": "In which year did India become independent?" + ANSWER_SUFFIX, "grade": num(1947)},
    {"id": "know-05", "cat": "knowledge", "q": "What is the boiling point of water at sea level in degrees Fahrenheit?" + ANSWER_SUFFIX, "grade": num(212)},
    {"id": "know-06", "cat": "knowledge", "q": "What is the approximate speed of light in a vacuum, in kilometres per second?" + ANSWER_SUFFIX,
     "grade": lambda t: (v := _num(t)) is not None and (295000 <= v <= 300000 or 2.95 <= v <= 3.0)},
]

CATEGORIES = ["math", "logic", "code", "instruction", "hindi", "knowledge"]


def sentences_starting_with_r(t: str) -> bool:
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]
    return len(parts) == 3 and all(p[0].lower() == "r" for p in parts)


def lowercase_paris(t: str) -> bool:
    return "paris" in t and t == t.lower()


# Harder set (v1-hard, 26 items) — added after both 4B and 9B scored 37/39 on the base set,
# which was too easy to separate them. Answer keys were computed in Python, not by hand alone.
HARD_ITEMS: list[dict[str, Any]] = [
    {"id": "hm-01", "cat": "math", "q": "How many integers from 1 to 1000 inclusive are divisible by 3 or by 5 but NOT by 15?" + ANSWER_SUFFIX, "grade": num(401)},
    {"id": "hm-02", "cat": "math", "q": "What is the sum of the decimal digits of 2^50?" + ANSWER_SUFFIX, "grade": num(76)},
    {"id": "hm-03", "cat": "math", "q": "Find the smallest positive integer that leaves remainder 2 when divided by 3, remainder 3 when divided by 5, and remainder 2 when divided by 7." + ANSWER_SUFFIX, "grade": num(23)},
    {"id": "hm-04", "cat": "math", "q": "How many trailing zeros does 125! (125 factorial) have?" + ANSWER_SUFFIX, "grade": num(31)},
    {"id": "hm-05", "cat": "math", "q": "A committee of 3 is chosen from 12 people, but two particular people refuse to serve together. How many committees are possible?" + ANSWER_SUFFIX, "grade": num(210)},
    {"id": "hm-06", "cat": "math", "q": "A car goes from A to B at 60 km/h and returns along the same road at 40 km/h. What is its average speed for the whole round trip, in km/h?" + ANSWER_SUFFIX, "grade": num(48)},
    {"id": "hm-07", "cat": "math", "q": "With F1 = F2 = 1, what is the 30th Fibonacci number F30?" + ANSWER_SUFFIX, "grade": num(832040)},
    {"id": "hm-08", "cat": "math", "q": "What is the probability of rolling at least one six in four rolls of a fair six-sided die? Give a decimal rounded to 4 places." + ANSWER_SUFFIX, "grade": num(0.5177, 0.00011)},
    {"id": "hm-09", "cat": "math", "q": "Three consecutive even integers add up to 222. What is the largest of them?" + ANSWER_SUFFIX, "grade": num(76)},
    {"id": "hm-10", "cat": "math", "q": "An analogue clock shows 3:40. What is the smaller angle between the hour hand and the minute hand, in degrees?" + ANSWER_SUFFIX, "grade": num(130)},
    {"id": "hl-01", "cat": "logic", "q": "How many times does the letter 's' appear in the phrase 'mississippi assess'?" + ANSWER_SUFFIX, "grade": num(8)},
    {"id": "hl-02", "cat": "logic", "q": "Write the word 'kaleidoscope' backwards." + ANSWER_SUFFIX, "grade": word("epocsodielak")},
    {"id": "hl-03", "cat": "logic", "q": "What is the median of these numbers: 14, 3, 27, 8, 19, 3, 11?" + ANSWER_SUFFIX, "grade": num(11)},
    {"id": "hl-04", "cat": "logic", "q": "What day of the week is 1 March 2031?" + ANSWER_SUFFIX, "grade": word("saturday")},
    {"id": "hl-05", "cat": "logic", "q": "A is B's brother. C is A's mother. D is C's father. What is D's relationship to B?" + ANSWER_SUFFIX, "grade": word("grandfather")},
    {"id": "hl-06", "cat": "logic", "q": "In a race you overtake the runner in second place. What position are you in now?" + ANSWER_SUFFIX, "grade": word("second", "2nd", "2")},
    {"id": "hc-01", "cat": "code", "q": "Write a Python function longest_palindrome(s) that returns the longest palindromic substring of s (if several have the maximum length, return the one that starts first). Return only the code in one python code block.",
     "grade": code("assert longest_palindrome('babad') == 'bab'\nassert longest_palindrome('cbbd') == 'bb'\nassert longest_palindrome('a') == 'a'\nassert longest_palindrome('forgeeksskeegfor') == 'geeksskeeg'")},
    {"id": "hc-02", "cat": "code", "q": "Write a Python function is_balanced(s) that returns True if every bracket in s — (), [] and {} — is correctly matched and nested; other characters are ignored. Return only the code in one python code block.",
     "grade": code("assert is_balanced('a(b[c]{d}e)f')\nassert not is_balanced('([)]')\nassert not is_balanced('((')\nassert is_balanced('')\nassert not is_balanced('}{')")},
    {"id": "hc-03", "cat": "code", "q": "Write a Python function lis_length(nums) that returns the length of the longest strictly increasing subsequence of a list of integers. Return only the code in one python code block.",
     "grade": code("assert lis_length([10,9,2,5,3,7,101,18]) == 4\nassert lis_length([0,1,0,3,2,3]) == 4\nassert lis_length([7,7,7]) == 1\nassert lis_length([]) == 0")},
    {"id": "hc-04", "cat": "code", "q": "Write a Python function spiral_order(matrix) that returns the elements of a 2-D list in clockwise spiral order starting from the top-left. Return only the code in one python code block.",
     "grade": code("assert spiral_order([[1,2,3],[4,5,6],[7,8,9]]) == [1,2,3,6,9,8,7,4,5]\nassert spiral_order([[1,2,3,4],[5,6,7,8],[9,10,11,12]]) == [1,2,3,4,8,12,11,10,9,5,6,7]\nassert spiral_order([]) == []\nassert spiral_order([[1],[2],[3]]) == [1,2,3]")},
    {"id": "hc-05", "cat": "code", "q": "Write a Python function parse_duration(s) that converts strings like '1h30m15s', '45m', '2h' or '90s' into a total number of seconds (int). Return only the code in one python code block.",
     "grade": code("assert parse_duration('1h30m15s') == 5415\nassert parse_duration('45m') == 2700\nassert parse_duration('2h') == 7200\nassert parse_duration('90s') == 90")},
    {"id": "hi-h1", "cat": "instruction", "q": "Write exactly three sentences about rain. Every sentence must begin with the letter R. Output only the three sentences.", "grade": sentences_starting_with_r},
    {"id": "hi-h2", "cat": "instruction", "q": "Give the first six prime numbers as a comma-separated list and nothing else.",
     "grade": lambda t: re.sub(r"\s", "", t.strip().strip(".")) == "2,3,5,7,11,13"},
    {"id": "hi-h3", "cat": "instruction", "q": "Answer using only lowercase letters, with no capital letters anywhere: what is the capital of France?", "grade": lowercase_paris},
    {"id": "hh-01", "cat": "hindi", "q": "नीचे दिए वाक्य का अंग्रेज़ी में अनुवाद कीजिए, केवल अनुवाद लिखिए: 'कल सुबह बारिश हुई थी, इसलिए मैच रद्द हो गया।'",
     "grade": lambda t: "rain" in t.lower() and ("cancel" in t.lower() or "called off" in t.lower()) and not DEVANAGARI.search(t)},
    {"id": "hh-02", "cat": "hindi", "q": "Hinglish mein (Roman script) batao: agar ek shirt 800 rupaye ki hai aur 25% discount mile, to kitne ki padegi? Last line mein 'Answer: <number>' likho.", "grade": lambda t: num(600)(t) and not DEVANAGARI.search(t)},
]

SETS = {"base": ITEMS, "hard": HARD_ITEMS}
