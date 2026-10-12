"""A generated financial model, independent of layout: periods, lines and inputs, and a plain
Python evaluator (the independent check of what LibreOffice calculates from the compiled
workbook).

A line holds, per period, either a typed number or an expression (expr.py). Annual lines run
over `Model.periods` (actual years, then forecast years); quarterly lines over
`Model.quarters` (the last actual year's quarters, then the forecast years'). Inputs are
scalars (one cell) or series (one cell per forecast year). Scalar lines are single formula
cells such as enterprise value.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

from fin_model_edits.gen.expr import (
    Across,
    Bin,
    Expr,
    Fn,
    In,
    Neg,
    Num,
    QSum,
    Ref,
    Sum,
    YRef,
)

Cell = float | Expr


@dataclass
class Line:
    key: str
    label: str
    block: str
    """Where the line belongs: inputs, cases, qtr, is, bs, cf, dcf, val."""
    kind: str = "line"
    """line (a value per period), series (an input per forecast year), scalar_input, scalar."""
    freq: str = "Y"
    cells: dict[str, Cell] = field(default_factory=dict)
    """Period -> typed number or expression. Scalars use the key "" (one cell)."""
    fmt: str = "num"
    """num, pct, days, x (multiple), int, text."""
    note: str = ""
    """Shown next to the line (a notes column, or appended to the label)."""
    text: str | None = None
    """Text-only lines (policy notes): the text, no numbers."""


@dataclass
class Model:
    company: str
    sector: str
    units: str
    """For example "$ in millions"."""
    periods: list[str]
    n_actual: int
    quarters: list[str] = field(default_factory=list)
    quarter_year: dict[str, str] = field(default_factory=dict)
    lines: dict[str, Line] = field(default_factory=dict)
    modules: set[str] = field(default_factory=set)
    cases: list[str] = field(default_factory=list)
    """Scenario case names (empty without a scenario switch)."""
    tax_sign: str = "negative"
    """DCF tax line: "negative" (shown negative, added) or "positive" (shown positive, subtracted)."""
    discounting: str = "end"
    """Valuation policy: "end" (end-of-year) or "mid" (mid-year) discounting."""

    @property
    def actual(self) -> list[str]:
        return self.periods[: self.n_actual]

    @property
    def forecast(self) -> list[str]:
        return self.periods[self.n_actual :]

    def add(self, line: Line) -> Line:
        if line.key in self.lines:
            raise ValueError(f"duplicate line {line.key}")
        self.lines[line.key] = line
        return line

    def line(self, key: str) -> Line:
        return self.lines[key]

    def periods_of(self, key: str) -> list[str]:
        line = self.lines[key]
        return self.quarters if line.freq == "Q" else self.periods

    def copy(self) -> Model:
        return copy.deepcopy(self)


class EvalError(ValueError):
    pass


class Evaluator:
    """Evaluate every cell of a model in Python, memoized. Raises on a reference to a period
    a line has no value for, and on cycles."""

    def __init__(self, model: Model):
        self.m = model
        self.memo: dict[tuple[str, str], float] = {}
        self.active: set[tuple[str, str]] = set()

    def value(self, key: str, period: str) -> float:
        k = (key, period)
        if k in self.memo:
            return self.memo[k]
        if k in self.active:
            raise EvalError(f"circular: {key} {period}")
        line = self.m.lines.get(key)
        if line is None:
            raise EvalError(f"unknown line {key}")
        if period not in line.cells:
            raise EvalError(f"{key} has no value for {period!r}")
        self.active.add(k)
        try:
            cell = line.cells[period]
            out = float(cell) if not isinstance(cell, Expr) else self.eval(cell, key, period)
        finally:
            self.active.discard(k)
        self.memo[k] = out
        return out

    def _shift(self, key: str, period: str, shift: int, from_key: str) -> str:
        line, src = self.m.lines[key], self.m.lines[from_key]
        if line.freq != src.freq:
            raise EvalError(f"{from_key} -> {key}: frequency mismatch")
        periods = self.m.periods_of(key)
        i = periods.index(period) + shift
        if not 0 <= i < len(periods):
            raise EvalError(f"{key}: shift {shift} from {period} is out of range")
        return periods[i]

    def eval(self, e: Expr, key: str, period: str) -> float:
        if isinstance(e, Num):
            return e.value
        if isinstance(e, Ref):
            target = e.at if e.at is not None else self._shift(e.key, period, e.shift, key)
            return self.value(e.key, target)
        if isinstance(e, In):
            return self.value(e.key, "")
        if isinstance(e, YRef):
            return self.value(e.key, self.m.quarter_year[period])
        if isinstance(e, QSum):
            return sum(self.value(e.key, q) for q in self.m.quarters if self.m.quarter_year[q] == period)
        if isinstance(e, Sum):
            return sum(self.value(k, period) for k in e.keys)
        if isinstance(e, Across):
            return sum(self.value(e.key, p) for p in self.m.forecast)
        if isinstance(e, Neg):
            return -self.eval(e.a, key, period)
        if isinstance(e, Bin):
            a, b = self.eval(e.a, key, period), self.eval(e.b, key, period)
            if e.op == "+":
                return a + b
            if e.op == "-":
                return a - b
            if e.op == "*":
                return a * b
            if e.op == "/":
                if b == 0:
                    raise EvalError(f"division by zero in {key} {period}")
                return a / b
            if e.op == "^":
                return math.pow(a, b)
        if isinstance(e, Fn):
            args = [self.eval(a, key, period) for a in e.args]
            if e.name == "MIN":
                return min(args)
            if e.name == "MAX":
                return max(args)
            if e.name == "CHOOSE":
                i = int(args[0])
                if not 1 <= i < len(args):
                    raise EvalError(f"CHOOSE index {i} out of range in {key}")
                return args[i]
            if e.name == "ROUND":
                return _excel_round(args[0], int(args[1]))
        raise EvalError(f"can't evaluate {e!r}")

    def all_values(self) -> dict[tuple[str, str], float]:
        for key, line in self.m.lines.items():
            if line.text is not None:
                continue
            for period in line.cells:
                self.value(key, period)
        return dict(self.memo)


def _excel_round(x: float, digits: int) -> float:
    q = 10.0**digits
    return math.copysign(math.floor(abs(x) * q + 0.5) / q, x)
