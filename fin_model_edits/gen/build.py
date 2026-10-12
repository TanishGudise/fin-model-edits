"""Sample a company profile and build its three-statement model and DCF (model.py).

Sectors set realistic ranges (growth, margins, cost lines, working capital, capital
intensity). Company names are made from syllables and assigned to a split by a hash, so no
name appears in two splits. Actual years are generated so that every year balances: cash is
whatever makes the balance sheet tie, and retained earnings roll forward with net income less
dividends.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from fin_model_edits.gen.expr import Across, Fn, In, QSum, Ref, Sum, YRef
from fin_model_edits.gen.model import Line, Model

SECTORS = {
    "software": {
        "growth": (0.08, 0.18),
        "gm": (0.70, 0.80),
        "opex": [
            ("Sales and marketing", (0.24, 0.32)),
            ("Research and development", (0.15, 0.21)),
            ("General and administrative", (0.08, 0.11)),
            ("Customer support", (0.04, 0.06)),
            ("Facilities and IT", (0.02, 0.04)),
        ],
        "dna": (0.03, 0.045),
        "capex": (0.02, 0.035),
        "dso": (55, 75),
        "dio": None,
        "dpo": (25, 40),
        "sbc": (0.04, 0.07),
        "segments": ["Subscriptions", "Professional services", "Licenses"],
        "noun": ["Software", "Systems", "Cloud", "Analytics", "Labs"],
    },
    "industrial": {
        "growth": (0.03, 0.07),
        "gm": (0.30, 0.38),
        "opex": [
            ("Selling, general and administrative", (0.12, 0.16)),
            ("Research and development", (0.03, 0.05)),
            ("Distribution", (0.03, 0.05)),
            ("Warranty", (0.005, 0.012)),
            ("Plant overhead", (0.02, 0.04)),
        ],
        "dna": (0.035, 0.05),
        "capex": (0.04, 0.06),
        "dso": (45, 65),
        "dio": (70, 110),
        "dpo": (40, 60),
        "sbc": (0.005, 0.015),
        "segments": ["Equipment", "Aftermarket parts", "Services"],
        "noun": ["Industries", "Manufacturing", "Machinery", "Components", "Engineering"],
    },
    "retail": {
        "growth": (0.02, 0.06),
        "gm": (0.32, 0.42),
        "opex": [
            ("Store operating expenses", (0.15, 0.19)),
            ("Selling, general and administrative", (0.06, 0.09)),
            ("Marketing", (0.02, 0.035)),
            ("Occupancy", (0.04, 0.06)),
            ("E-commerce fulfilment", (0.01, 0.025)),
        ],
        "dna": (0.025, 0.04),
        "capex": (0.03, 0.05),
        "dso": (3, 10),
        "dio": (55, 90),
        "dpo": (30, 50),
        "sbc": (0.003, 0.008),
        "segments": ["Stores", "Online", "Wholesale"],
        "noun": ["Stores", "Retail", "Outfitters", "Market", "Home"],
    },
    "healthcare services": {
        "growth": (0.04, 0.09),
        "gm": (0.30, 0.38),
        "opex": [
            ("Selling, general and administrative", (0.08, 0.11)),
            ("Facility costs", (0.03, 0.05)),
            ("Clinical support", (0.02, 0.035)),
            ("Information technology", (0.01, 0.02)),
            ("Professional liability insurance", (0.005, 0.01)),
        ],
        "dna": (0.03, 0.045),
        "capex": (0.035, 0.05),
        "dso": (40, 60),
        "dio": (8, 15),
        "dpo": (25, 40),
        "sbc": (0.004, 0.01),
        "segments": ["Outpatient clinics", "Home health", "Diagnostics"],
        "noun": ["Health", "Care", "Medical", "Clinics", "Health Partners"],
    },
    "consumer staples": {
        "growth": (0.02, 0.05),
        "gm": (0.36, 0.48),
        "opex": [
            ("Advertising and promotion", (0.10, 0.14)),
            ("General and administrative", (0.06, 0.08)),
            ("Distribution", (0.04, 0.06)),
            ("Research and development", (0.01, 0.02)),
            ("Brand royalties", (0.005, 0.015)),
        ],
        "dna": (0.03, 0.04),
        "capex": (0.03, 0.045),
        "dso": (30, 45),
        "dio": (50, 80),
        "dpo": (45, 70),
        "sbc": (0.003, 0.008),
        "segments": ["Beverages", "Snacks", "Household"],
        "noun": ["Foods", "Brands", "Consumer", "Provisions", "Goods"],
    },
    "logistics": {
        "growth": (0.03, 0.08),
        "gm": (0.20, 0.27),
        "opex": [
            ("Selling, general and administrative", (0.05, 0.07)),
            ("Technology", (0.008, 0.015)),
            ("Terminal operations", (0.015, 0.025)),
            ("Insurance and claims", (0.005, 0.01)),
            ("Fleet maintenance", (0.01, 0.02)),
        ],
        "dna": (0.035, 0.05),
        "capex": (0.04, 0.06),
        "dso": (35, 55),
        "dio": (3, 8),
        "dpo": (25, 40),
        "sbc": (0.003, 0.008),
        "segments": ["Freight brokerage", "Contract logistics", "Last mile"],
        "noun": ["Logistics", "Freight", "Transport", "Carriers", "Distribution"],
    },
}

SPLIT_SECTORS = {
    "train": ("software", "industrial", "retail"),
    "test_id": ("software", "industrial", "retail"),
    "test_ood": ("healthcare services", "consumer staples", "logistics"),
}

_FIRST = (
    "Al Bel Cal Dor El Fen Gar Hal Is Jor Kel Lor Mar Nor Or Pel Quin Ros Sel Tor Ul Var Wen Yor Zan".split()
)
_SECOND = (
    "bra cor dane fell gate holm ley mere more ridge stead ton vale wick worth brook crest field".split()
)
_SUFFIX = ["Inc.", "Corp.", "Group", "Holdings", "Co."]


def _split_of(stem: str) -> str:
    """Each name stem belongs to exactly one split."""
    h = int(hashlib.sha256(stem.encode()).hexdigest(), 16) % 3
    return ("train", "test_id", "test_ood")[h]


_REAL = set(
    """Alley Almere Alstead Alton Belfield Belton Calton Elmore Elton Fengate Fenton Fenwick Garfield
    Garton Haldane Halley Halstead Halton Isley Kelley Kelton Lorton Margate Marley Marton Norgate Norton
    Orton Pelton Quinton Selley Torridge Varley""".split()
)
"""Stems that are real brands, people or well-known places."""

NAME_STEMS = {
    split: [
        f"{a}{b}" for a in _FIRST for b in _SECOND if _split_of(f"{a}{b}") == split and f"{a}{b}" not in _REAL
    ]
    for split in ("train", "test_id", "test_ood")
}


@dataclass
class Profile:
    split: str
    company: str
    sector: str
    units: str
    scale: float
    first_actual_year: int
    n_actual: int
    n_forecast: int
    opex: list[tuple[str, tuple[float, float]]]
    modules: set[str] = field(default_factory=set)
    cases: list[str] = field(default_factory=list)
    segments: list[str] = field(default_factory=list)
    year_style: str = "FY{y}{s}"
    tax_sign: str = "positive"
    discounting: str = "end"


SIZES = {
    # n_forecast choices, opex lines, how many optional modules
    "S": {"n_forecast": (3, 4), "opex": (2, 3), "modules": (0, 1)},
    "M": {"n_forecast": (5, 5), "opex": (3, 3), "modules": (1, 2)},
    "L": {"n_forecast": (6, 7), "opex": (4, 5), "modules": (3, 4)},
}
OPTIONAL = ("scenario", "segments", "sbc", "dividends")


def sample_profile(rng: random.Random, split: str, size: str, layout: str) -> Profile:
    sector = rng.choice(SPLIT_SECTORS[split])
    spec = SECTORS[sector]
    stem = rng.choice(NAME_STEMS[split])
    company = f"{stem} {rng.choice(spec['noun'])} {rng.choice(_SUFFIX)}"
    thousands = rng.random() < 0.25
    units, scale = ("$ in thousands", 1000.0) if thousands else ("$ in millions", 1.0)
    sz = SIZES[size]
    n_forecast = rng.randint(*sz["n_forecast"])
    if layout == "E":
        n_forecast = min(n_forecast, 5)  # quarterly columns must fit in A..Z
    n_actual = rng.choice((2, 3))
    first_actual_year = rng.randint(2021, 2024) - n_actual + 1
    n_opex = rng.randint(*sz["opex"])
    opex = spec["opex"][:n_opex]
    allowed = [m for m in OPTIONAL if not (m == "scenario" and layout == "C")]
    if layout == "E":
        allowed = [m for m in allowed if m != "segments"]
    k = min(len(allowed), rng.randint(*sz["modules"]))
    modules = set(rng.sample(allowed, k))
    if layout == "D" and "scenario" not in modules and rng.random() < 0.7:
        modules.add("scenario")
    if spec["dio"] is not None:
        modules.add("inventory")
    if layout == "E":
        modules.add("quarterly")
    cases = []
    if "scenario" in modules:
        cases = ["Base", "Upside"] + (["Downside"] if rng.random() < 0.5 else [])
    segments = rng.sample(spec["segments"], rng.choice((2, 3))) if "segments" in modules else []
    return Profile(
        split=split,
        company=company,
        sector=sector,
        units=units,
        scale=scale,
        first_actual_year=first_actual_year,
        n_actual=n_actual,
        n_forecast=n_forecast,
        opex=list(opex),
        modules=modules,
        cases=cases,
        segments=segments,
        year_style=rng.choice(("FY{y}{s}", "FY{y}{s}", "{y}{s}", "FY{yy}{s}")),
        tax_sign=rng.choice(("positive", "negative")),
        discounting=rng.choice(("end", "mid")),
    )


def _r(x: float, nd: int = 1) -> float:
    return round(x, nd)


def _u(rng: random.Random, lo_hi: tuple[float, float], nd: int = 3) -> float:
    return round(rng.uniform(*lo_hi), nd)


def year_label(style: str, year: int, actual: bool) -> str:
    return style.format(y=year, yy=str(year)[2:], s="A" if actual else "E")


def build_model(p: Profile, rng: random.Random) -> Model:
    spec = SECTORS[p.sector]
    years = list(range(p.first_actual_year, p.first_actual_year + p.n_actual + p.n_forecast))
    periods = [year_label(p.year_style, y, i < p.n_actual) for i, y in enumerate(years)]
    m = Model(
        company=p.company,
        sector=p.sector,
        units=p.units,
        periods=periods,
        n_actual=p.n_actual,
        modules=set(p.modules),
        cases=list(p.cases),
        tax_sign=p.tax_sign,
        discounting=p.discounting,
    )
    A, F = m.actual, m.forecast
    S = p.scale
    nd = 0 if S > 1 else 1

    # --- drivers ---------------------------------------------------------------------------
    g0 = rng.uniform(*spec["growth"])
    fade = rng.uniform(0.002, 0.012)
    growth = [round(max(0.01, g0 - fade * i), 3) for i in range(len(F))]
    gm0 = rng.uniform(*spec["gm"])
    gm_step = rng.uniform(-0.002, 0.004)
    gm_path = [round(gm0 + gm_step * i + rng.uniform(-0.001, 0.001), 3) for i in range(len(F))]
    opex_pct = {f"opex{i}": _u(rng, rng_range) for i, (_, rng_range) in enumerate(p.opex, start=1)}
    sbc_pct = _u(rng, spec["sbc"]) if "sbc" in p.modules else 0.0
    dna_pct, capex_pct = _u(rng, spec["dna"]), _u(rng, spec["capex"])
    tax_rate = rng.choice((0.21, 0.23, 0.24, 0.25, 0.26, 0.27))
    int_rate = round(rng.uniform(0.045, 0.085), 3)
    dso = rng.randint(*spec["dso"])
    dio = rng.randint(*spec["dio"]) if "inventory" in p.modules else None
    dpo = rng.randint(*spec["dpo"])
    wacc = round(rng.uniform(0.075, 0.11), 3)
    tg = round(rng.uniform(0.015, 0.03), 3)
    payout = rng.choice((0.2, 0.25, 0.3, 0.35, 0.4)) if "dividends" in p.modules else 0.0

    # --- actual history --------------------------------------------------------------------
    rev0 = rng.uniform(150, 2500) * S if S == 1 else rng.uniform(25_000, 95_000)
    hist_g = [rng.uniform(*spec["growth"]) for _ in range(p.n_actual)]
    rev = []
    for i in range(p.n_actual):
        rev.append(_r(rev0 if i == 0 else rev[-1] * (1 + hist_g[i]), nd))
    noise = lambda: rng.uniform(0.97, 1.03)  # noqa: E731
    gm_hist = [gm0 - rng.uniform(-0.01, 0.015) for _ in range(p.n_actual)]
    cogs = [_r(r * (1 - g), nd) for r, g in zip(rev, gm_hist, strict=True)]
    opex_hist = {k: [_r(r * v * noise(), nd) for r in rev] for k, v in opex_pct.items()}
    sbc_hist = [_r(r * sbc_pct * noise(), nd) for r in rev] if "sbc" in p.modules else []
    dna = [_r(r * dna_pct * noise(), nd) for r in rev]
    debt0 = rev0 * rng.uniform(0.15, 0.45)
    repay = _r(debt0 * rng.uniform(0.04, 0.08), nd)
    debt = [_r(debt0 - repay * i, nd) for i in range(p.n_actual)]
    interest = [_r(int_rate * (debt[i - 1] if i else debt0 + repay) * noise(), nd) for i in range(p.n_actual)]
    taxes, ni = [], []
    for i in range(p.n_actual):
        opex_tot = sum(opex_hist[k][i] for k in opex_pct) + (sbc_hist[i] if sbc_hist else 0)
        ebt = rev[i] - cogs[i] - opex_tot - dna[i] - interest[i]
        taxes.append(_r(ebt * tax_rate, nd))
        ni.append(rev[i] - cogs[i] - opex_tot - dna[i] - interest[i] - taxes[-1])
    ar = [_r(r * dso * rng.uniform(0.93, 1.07) / 365, nd) for r in rev]
    inv = [_r(c * dio * rng.uniform(0.93, 1.07) / 365, nd) for c in cogs] if dio else []
    ap = [_r(c * dpo * rng.uniform(0.93, 1.07) / 365, nd) for c in cogs]
    ppe0, ppe_g = rev0 * rng.uniform(0.25, 0.5), rng.uniform(0.01, 0.04)
    ppe = [_r(ppe0 * (1 + ppe_g) ** i, nd) for i in range(p.n_actual)]
    gw = [_r(rev0 * rng.uniform(0.1, 0.3), nd)] * p.n_actual
    accrued_pct = rng.uniform(0.03, 0.05)
    accrued = [_r(r * accrued_pct * rng.uniform(0.98, 1.02), nd) for r in rev]
    accrued = [accrued[0]] * p.n_actual if rng.random() < 0.5 else accrued
    apic = [_r(rev0 * rng.uniform(0.15, 0.3), nd)]
    for i in range(1, p.n_actual):
        apic.append(_r(apic[-1] + (sbc_hist[i] if sbc_hist else 0), nd))
    re_ = [_r(rev0 * rng.uniform(0.1, 0.3), nd)]
    for i in range(1, p.n_actual):
        re_.append(_r(re_[-1] + ni[i] - (ni[i] * payout if payout else 0), nd))
    cash = []
    for i in range(p.n_actual):
        le = ap[i] + accrued[i] + debt[i] + apic[i] + re_[i]
        other = ar[i] + (inv[i] if inv else 0) + ppe[i] + gw[i]
        c = _r(le - other, nd)
        if c < rev[i] * 0.04:  # keep cash positive: more paid-in capital in every year
            bump = _r(rev[i] * 0.08 - c, nd)
            apic = [_r(a + bump, nd) for a in apic]
            cash = [_r(x + bump, nd) for x in cash]
            c = _r(c + bump, nd)
        cash.append(c)

    def actual(values):
        return dict(zip(A, values, strict=True))

    # --- inputs ----------------------------------------------------------------------------
    case_names = p.cases
    if case_names:
        sel = m.add(Line("case", "Active case", "cases", kind="scalar_input", cells={"": 1}, fmt="int"))
        sel.note = ", ".join(f"{i} = {c}" for i, c in enumerate(case_names, start=1))
        shift = {"Base": 0.0, "Upside": 0.02, "Downside": -0.025}
        mshift = {"Base": 0.0, "Upside": 0.006, "Downside": -0.008}
        for c in case_names:
            if p.segments:
                m.add(
                    Line(
                        f"upl_{c}",
                        f"Growth uplift: {c}",
                        "cases",
                        kind="series",
                        fmt="pct",
                        cells={pp: round(shift[c], 3) for pp in F},
                    )
                )
            else:
                m.add(
                    Line(
                        f"growth_{c}",
                        f"Revenue growth: {c}",
                        "cases",
                        kind="series",
                        fmt="pct",
                        cells={pp: round(g + shift[c], 3) for pp, g in zip(F, growth, strict=True)},
                    )
                )
            m.add(
                Line(
                    f"gm_{c}",
                    f"Gross margin: {c}",
                    "cases",
                    kind="series",
                    fmt="pct",
                    cells={pp: round(g + mshift[c], 3) for pp, g in zip(F, gm_path, strict=True)},
                )
            )
        if p.segments:
            m.add(
                Line(
                    "uplift",
                    "Growth uplift: active case",
                    "cases",
                    fmt="pct",
                    cells={pp: Fn("CHOOSE", In("case"), *(Ref(f"upl_{c}") for c in case_names)) for pp in F},
                )
            )
        else:
            m.add(
                Line(
                    "growth",
                    "Revenue growth: active case",
                    "cases",
                    fmt="pct",
                    cells={
                        pp: Fn("CHOOSE", In("case"), *(Ref(f"growth_{c}") for c in case_names)) for pp in F
                    },
                )
            )
        m.add(
            Line(
                "gm",
                "Gross margin: active case",
                "cases",
                fmt="pct",
                cells={pp: Fn("CHOOSE", In("case"), *(Ref(f"gm_{c}") for c in case_names)) for pp in F},
            )
        )
    else:
        if not p.segments:
            m.add(
                Line(
                    "growth",
                    "Revenue growth (assumption)",
                    "inputs",
                    kind="series",
                    fmt="pct",
                    cells=dict(zip(F, growth, strict=True)),
                )
            )
        m.add(
            Line(
                "gm",
                "Gross margin (assumption)",
                "inputs",
                kind="series",
                fmt="pct",
                cells=dict(zip(F, gm_path, strict=True)),
            )
        )
    if p.segments:
        for j, name in enumerate(p.segments, start=1):
            offset = rng.uniform(-0.02, 0.02)
            gseg = [round(max(0.005, g + offset + rng.uniform(-0.004, 0.004)), 3) for g in growth]
            m.add(
                Line(
                    f"seg_g{j}",
                    f"{name} growth (assumption)",
                    "inputs",
                    kind="series",
                    fmt="pct",
                    cells=dict(zip(F, gseg, strict=True)),
                )
            )
    for i, (name, _) in enumerate(p.opex, start=1):
        m.add(
            Line(
                f"opex{i}_pct",
                f"{name}, % of revenue",
                "inputs",
                kind="series",
                fmt="pct",
                cells={pp: opex_pct[f"opex{i}"] for pp in F},
            )
        )
    if "sbc" in p.modules:
        m.add(
            Line(
                "sbc_pct",
                "Stock-based compensation, % of revenue",
                "inputs",
                kind="series",
                fmt="pct",
                cells={pp: sbc_pct for pp in F},
            )
        )
    m.add(
        Line(
            "dna_pct",
            "D&A, % of revenue",
            "inputs",
            kind="series",
            fmt="pct",
            cells={pp: dna_pct for pp in F},
        )
    )
    m.add(
        Line(
            "capex_pct",
            "Capital expenditures, % of revenue",
            "inputs",
            kind="series",
            fmt="pct",
            cells={pp: capex_pct for pp in F},
        )
    )
    m.add(Line("repay", "Scheduled debt repayment", "inputs", kind="series", cells={pp: repay for pp in F}))
    m.add(Line("tax_rate", "Tax rate", "inputs", kind="scalar_input", cells={"": tax_rate}, fmt="pct"))
    m.add(
        Line(
            "int_rate",
            "Interest rate on beginning-of-year debt",
            "inputs",
            kind="scalar_input",
            cells={"": int_rate},
            fmt="pct",
        )
    )
    m.add(
        Line(
            "dso",
            "Days sales outstanding (on revenue)",
            "inputs",
            kind="scalar_input",
            cells={"": dso},
            fmt="days",
        )
    )
    if dio is not None:
        m.add(
            Line(
                "dio",
                "Days inventory outstanding (on COGS)",
                "inputs",
                kind="scalar_input",
                cells={"": dio},
                fmt="days",
            )
        )
    m.add(
        Line(
            "dpo",
            "Days payables outstanding (on COGS)",
            "inputs",
            kind="scalar_input",
            cells={"": dpo},
            fmt="days",
        )
    )
    if payout:
        m.add(
            Line(
                "payout",
                "Dividend payout, % of net income",
                "inputs",
                kind="scalar_input",
                cells={"": payout},
                fmt="pct",
            )
        )
    m.add(Line("wacc", "WACC", "inputs", kind="scalar_input", cells={"": wacc}, fmt="pct"))
    m.add(Line("tg", "Terminal growth rate", "inputs", kind="scalar_input", cells={"": tg}, fmt="pct"))
    share_unit = "thousands" if S > 1 else "millions"
    m.add(
        Line(
            "shares",
            f"Diluted shares outstanding ({share_unit})",
            "inputs",
            kind="scalar_input",
            cells={"": 1.0},
            fmt="shares",
        )
    )

    # --- quarterly build (layout E) --------------------------------------------------------
    opex_keys = [f"opex{i}" for i in range(1, len(p.opex) + 1)]
    if "quarterly" in p.modules:
        last = A[-1]
        m.quarters = [f"Q{q} {pp}" for pp in [last, *F] for q in range(1, 5)]
        m.quarter_year = {f"Q{q} {pp}": pp for pp in [last, *F] for q in range(1, 5)}
        seas = [rng.uniform(0.22, 0.28) for _ in range(3)]
        shares_q = [*seas, 1 - sum(seas)]
        lq = [f"Q{q} {last}" for q in range(1, 5)]

        def split_q(total):
            parts = [_r(total * s, nd) for s in shares_q[:3]]
            return [*parts, _r(total - sum(parts), nd)]

        rq = split_q(rev[-1])
        m.add(
            Line(
                "rev_q",
                "Revenue",
                "qtr",
                freq="Q",
                cells={
                    **dict(zip(lq, rq, strict=True)),
                    **{q: Ref("rev_q", -4) * (1 + YRef("growth")) for q in m.quarters[4:]},
                },
            )
        )
        m.add(
            Line(
                "cogs_q",
                "Cost of goods sold",
                "qtr",
                freq="Q",
                cells={
                    **dict(zip(lq, split_q(cogs[-1]), strict=True)),
                    **{q: Ref("rev_q") * (1 - YRef("gm")) for q in m.quarters[4:]},
                },
            )
        )
        m.add(
            Line(
                "gp_q",
                "Gross profit",
                "qtr",
                freq="Q",
                cells={q: Ref("rev_q") - Ref("cogs_q") for q in m.quarters},
            )
        )
        for i, k in enumerate(opex_keys, start=1):
            m.add(
                Line(
                    f"{k}_q",
                    p.opex[i - 1][0],
                    "qtr",
                    freq="Q",
                    cells={
                        **dict(zip(lq, split_q(opex_hist[k][-1]), strict=True)),
                        **{q: Ref("rev_q") * YRef(f"{k}_pct") for q in m.quarters[4:]},
                    },
                )
            )
        m.add(
            Line(
                "opex_q",
                "Total operating expenses",
                "qtr",
                freq="Q",
                cells={q: Sum(tuple(f"{k}_q" for k in opex_keys)) for q in m.quarters},
            )
        )
        m.add(
            Line(
                "ebitda_q",
                "EBITDA",
                "qtr",
                freq="Q",
                cells={q: Ref("gp_q") - Ref("opex_q") for q in m.quarters},
            )
        )

    # --- income statement ------------------------------------------------------------------
    if p.segments:
        seg_hist_share = [rng.uniform(0.2, 0.6) for _ in p.segments]
        tot = sum(seg_hist_share)
        for j, name in enumerate(p.segments, start=1):
            if j < len(p.segments):
                vals = [_r(r * seg_hist_share[j - 1] / tot, nd) for r in rev]
            else:
                vals = [
                    _r(r - sum(m.lines[f"seg{k}"].cells[pp] for k in range(1, j)), nd)
                    for r, pp in zip(rev, A, strict=True)
                ]
            growth_expr = Ref(f"seg_g{j}") + Ref("uplift") if case_names else Ref(f"seg_g{j}")
            m.add(
                Line(
                    f"seg{j}",
                    name,
                    "is",
                    cells={**actual(vals), **{pp: Ref(f"seg{j}", -1) * (1 + growth_expr) for pp in F}},
                )
            )
        m.add(
            Line(
                "revenue",
                "Total revenue",
                "is",
                cells={pp: Sum(tuple(f"seg{j}" for j in range(1, len(p.segments) + 1))) for pp in A + F},
            )
        )
    elif "quarterly" in p.modules:
        m.add(Line("revenue", "Revenue", "is", cells={**actual(rev), **{pp: QSum("rev_q") for pp in F}}))
    else:
        m.add(
            Line(
                "revenue",
                "Revenue",
                "is",
                cells={**actual(rev), **{pp: Ref("revenue", -1) * (1 + Ref("growth")) for pp in F}},
            )
        )
    m.add(
        Line(
            "rev_growth",
            "Revenue growth",
            "is",
            fmt="pct",
            cells={pp: Ref("revenue") / Ref("revenue", -1) - 1 for pp in (A + F)[1:]},
        )
    )
    if "quarterly" in p.modules:
        m.add(
            Line(
                "cogs", "Cost of goods sold", "is", cells={**actual(cogs), **{pp: QSum("cogs_q") for pp in F}}
            )
        )
    else:
        m.add(
            Line(
                "cogs",
                "Cost of goods sold",
                "is",
                cells={**actual(cogs), **{pp: Ref("revenue") * (1 - Ref("gm")) for pp in F}},
            )
        )
    m.add(Line("gp", "Gross profit", "is", cells={pp: Ref("revenue") - Ref("cogs") for pp in A + F}))
    m.add(
        Line(
            "gm_pct", "Gross margin", "is", fmt="pct", cells={pp: Ref("gp") / Ref("revenue") for pp in A + F}
        )
    )
    for i, (name, _) in enumerate(p.opex, start=1):
        k = f"opex{i}"
        fc = QSum(f"{k}_q") if "quarterly" in p.modules else Ref("revenue") * Ref(f"{k}_pct")
        m.add(Line(k, name, "is", cells={**actual(opex_hist[k]), **{pp: fc for pp in F}}))
    total_keys = list(opex_keys)
    if "sbc" in p.modules:
        m.add(
            Line(
                "sbc",
                "Stock-based compensation",
                "is",
                cells={**actual(sbc_hist), **{pp: Ref("revenue") * Ref("sbc_pct") for pp in F}},
            )
        )
        total_keys.append("sbc")
    m.add(Line("opex", "Total operating expenses", "is", cells={pp: Sum(tuple(total_keys)) for pp in A + F}))
    m.add(Line("ebitda", "EBITDA", "is", cells={pp: Ref("gp") - Ref("opex") for pp in A + F}))
    m.add(
        Line(
            "ebitda_pct",
            "EBITDA margin",
            "is",
            fmt="pct",
            cells={pp: Ref("ebitda") / Ref("revenue") for pp in A + F},
        )
    )
    m.add(
        Line(
            "dna",
            "Depreciation and amortization",
            "is",
            cells={**actual(dna), **{pp: Ref("revenue") * Ref("dna_pct") for pp in F}},
        )
    )
    m.add(Line("ebit", "EBIT", "is", cells={pp: Ref("ebitda") - Ref("dna") for pp in A + F}))
    m.add(
        Line(
            "interest",
            "Interest expense",
            "is",
            cells={**actual(interest), **{pp: In("int_rate") * Ref("debt", -1) for pp in F}},
        )
    )
    m.add(Line("ebt", "Pre-tax income", "is", cells={pp: Ref("ebit") - Ref("interest") for pp in A + F}))
    m.add(
        Line(
            "tax",
            "Income tax expense",
            "is",
            cells={**actual(taxes), **{pp: Ref("ebt") * In("tax_rate") for pp in F}},
        )
    )
    m.add(Line("ni", "Net income", "is", cells={pp: Ref("ebt") - Ref("tax") for pp in A + F}))

    # --- balance sheet ---------------------------------------------------------------------
    m.add(Line("cash", "Cash", "bs", cells={**actual(cash), **{pp: Ref("cf_end") for pp in F}}))
    m.add(
        Line(
            "ar",
            "Accounts receivable",
            "bs",
            cells={**actual(ar), **{pp: Ref("revenue") * In("dso") / 365 for pp in F}},
        )
    )
    ca = ["cash", "ar"]
    if dio is not None:
        m.add(
            Line(
                "inv",
                "Inventory",
                "bs",
                cells={**actual(inv), **{pp: Ref("cogs") * In("dio") / 365 for pp in F}},
            )
        )
        ca.append("inv")
    m.add(Line("tca", "Total current assets", "bs", cells={pp: Sum(tuple(ca)) for pp in A + F}))
    m.add(
        Line(
            "ppe",
            "PP&E, net",
            "bs",
            cells={**actual(ppe), **{pp: Ref("ppe", -1) - Ref("cf_capex") - Ref("dna") for pp in F}},
        )
    )
    m.add(Line("gw", "Goodwill", "bs", cells={**actual(gw), **{pp: Ref("gw", -1) for pp in F}}))
    m.add(Line("ta", "Total assets", "bs", cells={pp: Ref("tca") + Ref("ppe") + Ref("gw") for pp in A + F}))
    m.add(
        Line(
            "ap",
            "Accounts payable",
            "bs",
            cells={**actual(ap), **{pp: Ref("cogs") * In("dpo") / 365 for pp in F}},
        )
    )
    m.add(
        Line(
            "accrued",
            "Accrued expenses",
            "bs",
            cells={**actual(accrued), **{pp: Ref("accrued", -1) for pp in F}},
        )
    )
    m.add(Line("tcl", "Total current liabilities", "bs", cells={pp: Sum(("ap", "accrued")) for pp in A + F}))
    m.add(
        Line(
            "debt",
            "Long-term debt",
            "bs",
            cells={**actual(debt), **{pp: Ref("debt", -1) + Ref("cf_repay") for pp in F}},
        )
    )
    m.add(Line("tl", "Total liabilities", "bs", cells={pp: Ref("tcl") + Ref("debt") for pp in A + F}))
    apic_fc = Ref("apic", -1) + Ref("sbc") if "sbc" in p.modules else Ref("apic", -1)
    m.add(Line("apic", "Common stock and APIC", "bs", cells={**actual(apic), **{pp: apic_fc for pp in F}}))
    re_fc = Ref("re", -1) + Ref("ni") + Ref("cf_div") if payout else Ref("re", -1) + Ref("ni")
    m.add(Line("re", "Retained earnings", "bs", cells={**actual(re_), **{pp: re_fc for pp in F}}))
    m.add(Line("te", "Total equity", "bs", cells={pp: Ref("apic") + Ref("re") for pp in A + F}))
    m.add(
        Line("tle", "Total liabilities and equity", "bs", cells={pp: Ref("tl") + Ref("te") for pp in A + F})
    )
    m.add(
        Line(
            "check",
            "Check: assets - liabilities - equity (should be 0)",
            "bs",
            cells={pp: Ref("ta") - Ref("tle") for pp in A + F},
        )
    )

    # --- cash flow statement (forecast years) ----------------------------------------------
    cfo = ["cf_ni", "cf_dna"]
    m.add(Line("cf_ni", "Net income", "cf", cells={pp: Ref("ni") for pp in F}))
    m.add(Line("cf_dna", "Depreciation and amortization", "cf", cells={pp: Ref("dna") for pp in F}))
    if "sbc" in p.modules:
        m.add(Line("cf_sbc", "Stock-based compensation", "cf", cells={pp: Ref("sbc") for pp in F}))
        cfo.append("cf_sbc")
    wc = ["cf_ar"]
    m.add(
        Line(
            "cf_ar",
            "(Increase) / decrease in receivables",
            "cf",
            cells={pp: Ref("ar", -1) - Ref("ar") for pp in F},
        )
    )
    if dio is not None:
        m.add(
            Line(
                "cf_inv",
                "(Increase) / decrease in inventory",
                "cf",
                cells={pp: Ref("inv", -1) - Ref("inv") for pp in F},
            )
        )
        wc.append("cf_inv")
    m.add(
        Line(
            "cf_ap",
            "Increase / (decrease) in payables",
            "cf",
            cells={pp: Ref("ap") - Ref("ap", -1) for pp in F},
        )
    )
    m.add(
        Line(
            "cf_accr",
            "Increase / (decrease) in accrued expenses",
            "cf",
            cells={pp: Ref("accrued") - Ref("accrued", -1) for pp in F},
        )
    )
    wc += ["cf_ap", "cf_accr"]
    cfo += wc
    m.add(Line("cfo", "Cash from operating activities", "cf", cells={pp: Sum(tuple(cfo)) for pp in F}))
    m.add(
        Line(
            "cf_capex",
            "Capital expenditures",
            "cf",
            cells={pp: -(Ref("revenue") * Ref("capex_pct")) for pp in F},
        )
    )
    m.add(Line("cfi", "Cash from investing activities", "cf", cells={pp: Ref("cf_capex") for pp in F}))
    m.add(
        Line(
            "cf_repay",
            "Debt repayment",
            "cf",
            cells={pp: -Fn("MIN", Ref("repay"), Ref("debt", -1)) for pp in F},
        )
    )
    cff = ["cf_repay"]
    if payout:
        m.add(Line("cf_div", "Dividends paid", "cf", cells={pp: -(Ref("ni") * In("payout")) for pp in F}))
        cff.append("cf_div")
    m.add(Line("cff", "Cash from financing activities", "cf", cells={pp: Sum(tuple(cff)) for pp in F}))
    m.add(
        Line(
            "cf_net", "Net change in cash", "cf", cells={pp: Ref("cfo") + Ref("cfi") + Ref("cff") for pp in F}
        )
    )
    m.add(Line("cf_beg", "Beginning cash", "cf", cells={pp: Ref("cash", -1) for pp in F}))
    m.add(Line("cf_end", "Ending cash", "cf", cells={pp: Ref("cf_beg") + Ref("cf_net") for pp in F}))

    # --- DCF -------------------------------------------------------------------------------
    m.add(Line("d_ebit", "EBIT", "dcf", cells={pp: Ref("ebit") for pp in F}))
    if p.tax_sign == "negative":
        m.add(
            Line(
                "d_tax",
                "Tax on EBIT (shown as a negative number)",
                "dcf",
                cells={pp: -(Ref("d_ebit") * In("tax_rate")) for pp in F},
            )
        )
        m.add(
            Line(
                "d_nopat",
                "NOPAT (EBIT plus the negative tax line)",
                "dcf",
                cells={pp: Ref("d_ebit") + Ref("d_tax") for pp in F},
            )
        )
    else:
        m.add(Line("d_tax", "Tax on EBIT", "dcf", cells={pp: Ref("d_ebit") * In("tax_rate") for pp in F}))
        m.add(
            Line(
                "d_nopat",
                "NOPAT (EBIT less tax on EBIT)",
                "dcf",
                cells={pp: Ref("d_ebit") - Ref("d_tax") for pp in F},
            )
        )
    m.add(Line("d_dna", "Depreciation and amortization", "dcf", cells={pp: Ref("dna") for pp in F}))
    m.add(Line("d_capex", "Capital expenditures", "dcf", cells={pp: Ref("cf_capex") for pp in F}))
    m.add(Line("d_nwc", "Change in net working capital", "dcf", cells={pp: Sum(tuple(wc)) for pp in F}))
    m.add(
        Line(
            "d_ufcf",
            "Unlevered free cash flow",
            "dcf",
            cells={pp: Ref("d_nopat") + Ref("d_dna") + Ref("d_capex") + Ref("d_nwc") for pp in F},
        )
    )
    first = 0.5 if p.discounting == "mid" else 1
    m.add(
        Line(
            "d_period",
            "Discount period (years from valuation date)",
            "dcf",
            fmt="years",
            cells={F[0]: first, **{pp: Ref("d_period", -1) + 1 for pp in F[1:]}},
        )
    )
    m.add(
        Line(
            "d_df",
            "Discount factor",
            "dcf",
            fmt="x",
            cells={pp: 1 / (1 + In("wacc")) ** Ref("d_period") for pp in F},
        )
    )
    m.add(
        Line(
            "d_pv",
            "PV of unlevered free cash flow",
            "dcf",
            cells={pp: Ref("d_ufcf") * Ref("d_df") for pp in F},
        )
    )
    last_f, last_a = F[-1], A[-1]
    m.add(
        Line(
            "v_sumpv",
            "Sum of PV of unlevered free cash flow",
            "val",
            kind="scalar",
            cells={"": Across("d_pv")},
        )
    )
    m.add(
        Line(
            "v_tv",
            f"Terminal value at end of {last_f} (Gordon growth)",
            "val",
            kind="scalar",
            cells={"": Ref("d_ufcf", at=last_f) * (1 + In("tg")) / (In("wacc") - In("tg"))},
        )
    )
    if p.discounting == "mid":
        pvtv = Ref("v_tv", at="") / (1 + In("wacc")) ** (Ref("d_period", at=last_f) + 0.5)
    else:
        pvtv = Ref("v_tv", at="") * Ref("d_df", at=last_f)
    m.add(Line("v_pvtv", "PV of terminal value", "val", kind="scalar", cells={"": pvtv}))
    m.add(
        Line(
            "v_ev",
            "Enterprise value",
            "val",
            kind="scalar",
            cells={"": Ref("v_sumpv", at="") + Ref("v_pvtv", at="")},
        )
    )
    m.add(
        Line(
            "v_netdebt",
            "Net debt at valuation date",
            "val",
            kind="scalar",
            cells={"": Ref("debt", at=last_a) - Ref("cash", at=last_a)},
        )
    )
    m.add(
        Line(
            "v_eq",
            "Equity value",
            "val",
            kind="scalar",
            cells={"": Ref("v_ev", at="") - Ref("v_netdebt", at="")},
        )
    )
    m.add(
        Line(
            "v_shares",
            f"Diluted shares ({share_unit})",
            "val",
            kind="scalar",
            fmt="shares",
            cells={"": In("shares")},
        )
    )
    m.add(
        Line(
            "v_ps",
            "Equity value per share ($)",
            "val",
            kind="scalar",
            fmt="pershare",
            cells={"": Ref("v_eq", at="") / Ref("v_shares", at="")},
        )
    )
    m.add(
        Line(
            "v_tvpct",
            "Terminal value, % of enterprise value",
            "val",
            kind="scalar",
            fmt="pct",
            cells={"": Ref("v_pvtv", at="") / Ref("v_ev", at="")},
        )
    )
    if p.discounting == "mid":
        policy = (
            f"Valuation policy: valuation date is the end of {last_a}; forecast cash flows are discounted "
            f"mid-year (first period 0.5 years); the terminal value is set at the end of {last_f} on that "
            f"year's unlevered free cash flow and discounted from the end of {last_f}; net debt is taken at "
            f"the valuation date."
        )
    else:
        policy = (
            f"Valuation policy: valuation date is the end of {last_a}; forecast cash flows are discounted "
            f"at year end (first period 1 year); the terminal value is set at the end of {last_f} on that "
            f"year's unlevered free cash flow and discounted with {last_f}'s discount factor; net debt is "
            f"taken at the valuation date."
        )
    m.add(Line("v_policy", "", "val", kind="scalar", text=policy))
    # Shares outstanding: whatever puts the share price in a realistic range.
    from fin_model_edits.gen.model import Evaluator

    equity = Evaluator(m).value("v_eq", "")
    if equity > 0:
        m.lines["shares"].cells[""] = max(0.1, round(equity / rng.uniform(12, 120), 1))
    return m
