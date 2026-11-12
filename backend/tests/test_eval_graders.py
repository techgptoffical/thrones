"""The eval graders decide what we publish as model scores, so they are tested too."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evals"))
import items  # noqa: E402


@pytest.mark.parametrize("text,value", [
    ("Answer: 3 3/5", 3.6), ("Answer: 18/5 hours", 3.6), ("Answer: \\frac{18}{5}", 3.6),
    ("Answer: 1,048,575", 1048575), ("Answer: ₹13,310", 13310), ("Answer: 5 cents", 5), ("Answer: -4", -4),
    ("work...\nAnswer: **476893754**", 476893754), ("no answer line\n42", 42),
])
def test_number_parser(text, value):
    assert items._num(text) == pytest.approx(value)


def test_every_item_has_a_grader_and_unique_id():
    all_items = items.ITEMS + items.HARD_ITEMS
    ids = [i["id"] for i in all_items]
    assert len(ids) == len(set(ids)) == 65
    assert all(callable(i["grade"]) and i["cat"] in items.CATEGORIES for i in all_items)


@pytest.mark.parametrize("item_id,good,bad", [
    ("math-10", "Answer: 476,893,754", "Answer: 476,893,755"),
    ("hm-08", "Answer: 0.5177", "Answer: 0.52"),
    ("logic-05", "Answer: Friday", "Answer: Thursday"),
    ("if-02", "YES", "Yes."),
    ("if-04", '{"name": "Ravi", "age": 31}', '{"name": "Ravi"}'),
    ("hi-03", "12 aur 15 ka jod 27 hota hai.", "१२ और १५ का जोड़ 27 है"),
    ("hi-h2", "2, 3, 5, 7, 11, 13", "2, 3, 5, 7, 11"),
    ("hi-h1", "Rain falls. Roofs drip. Rivers swell.", "Rain falls. It drips. Rivers swell."),
])
def test_graders_accept_correct_and_reject_wrong(item_id, good, bad):
    item = next(i for i in items.ITEMS + items.HARD_ITEMS if i["id"] == item_id)
    assert item["grade"](good)
    assert not item["grade"](bad)


def test_code_grader_runs_hidden_asserts():
    item = next(i for i in items.ITEMS if i["id"] == "code-01")
    good = "```python\nimport re\ndef is_palindrome(s):\n    t = re.sub(r'[^a-z0-9]', '', s.lower())\n    return t == t[::-1]\n```"
    bad = "```python\ndef is_palindrome(s):\n    return s == s[::-1]\n```"
    assert item["grade"](good)
    assert not item["grade"](bad)
