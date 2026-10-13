"""A small expression language for model lines, independent of any cell layout.

Each line of a generated model defines its value for a period as an expression over other
lines and inputs. The same expression is compiled into an Excel formula for a given layout
(layout.py) and evaluated directly in Python (model.py). The two are written separately, so
a compiler mistake (a wrong cell, a missing `$`) shows up as a difference between LibreOffice
and Python in the validation.

    Ref("revenue", -1)           the line in the previous period (same frequency)
    Ref("growth")                a series input in the same period
    Ref("cash", at="FY2025A")    a fixed period
    Ref("capex_pct", at="FY2026E", absolute=True)  a `$`-anchored cell (the anchoring bug)
    In("tax_rate")               a scalar input (always `$`-anchored)
    YRef("growth")               from a quarterly line: the annual line in the quarter's year
    QSum("rev_q")                on an annual line: the four quarters of the same year
    Sum(("sga", "rnd"))          lines added in the same period (SUM(range) when contiguous)
    Across("pv_fcf")             a scalar: the line summed over the forecast periods
    Fn("MIN", a, b), Fn("CHOOSE", In("case"), a, b)
    Fn("IF", Cmp(">", a, b), x, y)   a comparison is only used as IF's condition
"""

from __future__ import annotations

from dataclasses import dataclass


class Expr:
    def __add__(self, other):
        return Bin("+", self, lift(other))

    def __radd__(self, other):
        return Bin("+", lift(other), self)

    def __sub__(self, other):
        return Bin("-", self, lift(other))

    def __rsub__(self, other):
        return Bin("-", lift(other), self)

    def __mul__(self, other):
        return Bin("*", self, lift(other))

    def __rmul__(self, other):
        return Bin("*", lift(other), self)

    def __truediv__(self, other):
        return Bin("/", self, lift(other))

    def __rtruediv__(self, other):
        return Bin("/", lift(other), self)

    def __pow__(self, other):
        return Bin("^", self, lift(other))

    def __neg__(self):
        return Neg(self)


def lift(value) -> Expr:
    return value if isinstance(value, Expr) else Num(float(value))


@dataclass(frozen=True, eq=True)
class Num(Expr):
    value: float


@dataclass(frozen=True, eq=True)
class Ref(Expr):
    key: str
    shift: int = 0
    at: str | None = None
    absolute: bool = False


@dataclass(frozen=True, eq=True)
class In(Expr):
    key: str


@dataclass(frozen=True, eq=True)
class YRef(Expr):
    key: str


@dataclass(frozen=True, eq=True)
class QSum(Expr):
    key: str


@dataclass(frozen=True, eq=True)
class Sum(Expr):
    keys: tuple[str, ...]


@dataclass(frozen=True, eq=True)
class Across(Expr):
    key: str


@dataclass(frozen=True, eq=True)
class Bin(Expr):
    op: str
    a: Expr
    b: Expr


@dataclass(frozen=True, eq=True)
class Neg(Expr):
    a: Expr


@dataclass(frozen=True, eq=True)
class Cmp(Expr):
    op: str
    """One of >, >=, <, <=."""
    a: Expr
    b: Expr

    def __post_init__(self):
        object.__setattr__(self, "a", lift(self.a))
        object.__setattr__(self, "b", lift(self.b))


@dataclass(frozen=True, eq=True)
class Fn(Expr):
    name: str
    args: tuple[Expr, ...]

    def __init__(self, name: str, *args):
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "args", tuple(lift(a) for a in args))


PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2, "^": 3}


def refs(expr: Expr) -> list[Expr]:
    """Every leaf reference in the expression."""
    if isinstance(expr, Ref | In | YRef | QSum | Sum | Across):
        return [expr]
    if isinstance(expr, Bin | Cmp):
        return refs(expr.a) + refs(expr.b)
    if isinstance(expr, Neg):
        return refs(expr.a)
    if isinstance(expr, Fn):
        return [r for a in expr.args for r in refs(a)]
    return []


def replace(expr: Expr, old: Expr, new: Expr) -> Expr:
    """The expression with every occurrence of `old` replaced by `new`."""
    if expr == old:
        return new
    if isinstance(expr, Bin):
        return Bin(expr.op, replace(expr.a, old, new), replace(expr.b, old, new))
    if isinstance(expr, Cmp):
        return Cmp(expr.op, replace(expr.a, old, new), replace(expr.b, old, new))
    if isinstance(expr, Neg):
        return Neg(replace(expr.a, old, new))
    if isinstance(expr, Fn):
        return Fn(expr.name, *(replace(a, old, new) for a in expr.args))
    return expr
