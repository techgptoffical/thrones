import asyncio

import pytest

from thrones.tools.calculator import calculator, evaluate
from thrones.tools.registry import Tool, ToolSet


@pytest.mark.parametrize("expr,expected", [
    ("2 + 2", "4"),
    ("48213 * 9917 - 1234567", "476893754"),
    ("1,250,000 * 2", "2500000"),
    ("2^10", "1024"),
    ("sqrt(144)", "12"),
    ("round(850000 * (9.5/12/100) * (1 + 9.5/12/100)**84 / ((1 + 9.5/12/100)**84 - 1), 2)", "13892.38"),
    ("mean([2, 4, 6])", "4"),
    ("comb(10, 3)", "120"),
    ("log(8, 2)", "3"),
])
def test_calculator_values(expr, expected):
    assert evaluate(expr) == expected


@pytest.mark.parametrize("expr", [
    "__import__('os').system('echo hi')",
    "open('x')",
    "(1).__class__",
    "x + 1",
    "'a' * 3",
    "9 ** 9 ** 9",
    "factorial(100000)",
    "lambda: 1",
])
def test_calculator_rejects_unsafe_or_huge(expr):
    with pytest.raises((ValueError, SyntaxError)):
        evaluate(expr)


def _counting_tool():
    calls = []

    async def handler(args, ctx):
        calls.append(args)
        return "ok"

    return Tool("t", "test", {"type": "object", "properties": {}}, handler), calls


def test_toolset_refuses_duplicates_and_enforces_budget():
    tool, calls = _counting_tool()
    ts = ToolSet(max_calls=2)
    ts.add(tool)

    async def go():
        a = await ts.run("t", '{"x": 1}', {})
        b = await ts.run("t", '{"x": 1}', {})       # duplicate
        c = await ts.run("t", '{"x": 2}', {})
        d = await ts.run("t", '{"x": 3}', {})       # over budget
        return a, b, c, d

    a, b, c, d = asyncio.run(go())
    assert a.ok and c.ok
    assert "already made" in b.output and not b.ok
    assert "budget" in d.output and not d.ok
    assert len(calls) == 2


def test_toolset_handles_bad_json_and_unknown_tool():
    ts = ToolSet()
    ts.add(calculator)

    async def go():
        return await ts.run("calculator", "{not json", {}), await ts.run("nope", "{}", {})

    bad, unknown = asyncio.run(go())
    assert not bad.ok and "JSON" in bad.output
    assert not unknown.ok and "unknown tool" in unknown.output


def test_tool_timeout_is_reported_not_raised():
    async def slow(args, ctx):
        await asyncio.sleep(5)
        return "late"

    ts = ToolSet()
    ts.add(Tool("slow", "", {"type": "object"}, slow, timeout_s=0.1))
    r = asyncio.run(ts.run("slow", "{}", {}))
    assert not r.ok and "timed out" in r.output


def test_raw_tool_markup_is_detected():
    from thrones.reasoning.engine import has_raw_tool_markup
    assert has_raw_tool_markup("<tool_call>\n<function=calculator>\n<parameter=expression>\n1+1\n</parameter>")
    assert not has_raw_tool_markup("The EMI is **₹13,892.38**.")
    assert not has_raw_tool_markup("")
