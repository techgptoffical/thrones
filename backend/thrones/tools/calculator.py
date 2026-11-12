"""Exact arithmetic evaluated by Python, not by the language model.

Expressions are parsed to an AST and only whitelisted nodes are evaluated,
so no names, attributes or calls outside the table below can run.
"""
from __future__ import annotations

import ast
import math
import operator
import statistics
from fractions import Fraction
from typing import Any

from .registry import Tool

_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CMP = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
}
_FUNCS: dict[str, Any] = {
    "sqrt": math.sqrt, "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
    "exp": math.exp, "log": math.log, "ln": math.log, "log2": math.log2, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos,
    "atan": math.atan, "atan2": math.atan2, "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "degrees": math.degrees, "radians": math.radians, "hypot": math.hypot,
    "floor": math.floor, "ceil": math.ceil, "trunc": math.trunc, "round": round, "abs": abs,
    "factorial": math.factorial, "comb": math.comb, "perm": math.perm, "gcd": math.gcd, "lcm": math.lcm,
    "min": min, "max": max, "sum": lambda *a: sum(a[0] if len(a) == 1 and isinstance(a[0], (list, tuple)) else a),
    "mean": lambda *a: statistics.fmean(a[0] if len(a) == 1 and isinstance(a[0], (list, tuple)) else a),
    "median": lambda *a: statistics.median(a[0] if len(a) == 1 and isinstance(a[0], (list, tuple)) else a),
    "stdev": lambda *a: statistics.stdev(a[0] if len(a) == 1 and isinstance(a[0], (list, tuple)) else a),
    "pstdev": lambda *a: statistics.pstdev(a[0] if len(a) == 1 and isinstance(a[0], (list, tuple)) else a),
    "fraction": Fraction, "isqrt": math.isqrt,
}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf}
_MAX_POW_BITS = 20000


def _eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError("only numbers are allowed")
    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"unknown name '{node.id}'")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and isinstance(left, int) and isinstance(right, int):
            if right > 0 and left.bit_length() * right > _MAX_POW_BITS:
                raise ValueError("result too large")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
        return _CMP[type(node.ops[0])](_eval(node.left), _eval(node.comparators[0]))
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e) for e in node.elts]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        fn = _FUNCS.get(node.func.id)
        if fn is None:
            raise ValueError(f"unknown function '{node.func.id}'")
        args = [_eval(a) for a in node.args]
        if node.func.id == "factorial" and args and args[0] > 3000:
            raise ValueError("factorial argument too large")
        return fn(*args)
    raise ValueError(f"unsupported syntax: {type(node).__name__}")


def evaluate(expression: str) -> str:
    expr = expression.strip().replace("^", "**").replace("×", "*").replace("÷", "/").replace("−", "-")
    if "(" not in expr:
        expr = expr.replace(",", "")  # thousands separators such as 1,250,000
    if len(expr) > 500:
        raise ValueError("expression too long")
    value = _eval(ast.parse(expr, mode="eval"))
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.12g}"
    return str(value)


async def _handler(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    expression = str(args.get("expression", ""))
    if not expression.strip():
        return "Error: no expression given."
    return f"{expression.strip()} = {evaluate(expression)}"


calculator = Tool(
    name="calculator",
    label="Calculating",
    description=(
        "Evaluate a numeric expression exactly. Use this for any arithmetic you are not certain of. "
        "Supports + - * / // % **, parentheses, and functions: sqrt, exp, log(x[, base]), log10, sin, cos, tan, "
        "factorial, comb, perm, gcd, lcm, round, floor, ceil, abs, min, max, sum, mean, median, stdev, fraction. "
        "Constants: pi, e. Example: (1.07 ** 12) * 1500"
    ),
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "The expression to evaluate."}},
        "required": ["expression"],
    },
    handler=_handler,
    timeout_s=5,
)
