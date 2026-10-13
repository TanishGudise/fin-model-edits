"""The schedules of the large workbooks (levels 4-6): a debt schedule with a revolver, leases,
deferred revenue, tax losses carried forward and non-controlling interests. Applied after
build.py's base model, only for the XL and XXL sizes, so the smaller levels are unchanged.

Mechanics (also stated in the prompt, so a broken schedule is checkable against them):
  debt         the term loan amortizes on its schedule; the senior notes are a bullet due after the
               forecast; the revolver draws to keep cash at the minimum balance and repays when
               cash allows (never below zero); interest is on beginning-of-year balances
  leases       each year's amortization is the opening right-of-use balance divided by the lease
               life; each year's principal repayment is the opening lease liability divided by the
               lease life (a financing cash flow); lease interest is on the opening liability.
               The valuation treats leases as debt: lease amortization is added back, new leases
               count as capital spending, and the lease liability is in net debt.
  deferred     deferred revenue is a % of revenue; its increase is a working capital inflow
  tax losses   losses carried forward offset taxable income up to the usage limit
  minority     non-controlling interests take their share of net income; retained earnings and
               dividends use the company's share; equity value deducts their book value
Actual years are re-balanced afterwards: retained earnings roll with the new net income and cash
makes each year tie, as in build.py.
"""

from __future__ import annotations

import random

from fin_model_edits.gen.expr import Fn, In, Ref, Sum
from fin_model_edits.gen.model import Evaluator, Line, Model

QUARTER_YEARS = 5


def extend(m: Model, p, rng: random.Random) -> None:
    A, F = m.actual, m.forecast
    nd = 0 if p.scale > 1 else 1
    L = m.lines

    def r(x: float) -> float:
        return round(x, nd)

    if "quarterly" in m.modules and len(F) > QUARTER_YEARS:
        _trim_quarters(m)
    rev = {pp: Evaluator(m).value("revenue", pp) for pp in A + F}

    if "debt_schedule" in m.modules:
        debt_a = {pp: float(L["debt"].cells[pp]) for pp in A}
        notes = r(debt_a[A[0]] * rng.uniform(0.35, 0.6))
        base_rate = float(L["int_rate"].cells[""])
        del L["int_rate"]
        for key, label, value in (
            ("tla_rate", "Term loan interest rate (on beginning-of-year balance)", base_rate - 0.005),
            ("notes_rate", "Senior notes coupon", base_rate + 0.01),
            ("rev_rate", "Revolver interest rate (on beginning-of-year balance)", base_rate + 0.005),
        ):
            m.add(Line(key, label, "inputs", kind="scalar_input", cells={"": round(value, 4)}, fmt="pct"))
        m.add(
            Line(
                "min_cash",
                "Minimum cash balance",
                "inputs",
                kind="scalar_input",
                cells={"": r(rev[A[-1]] * rng.uniform(0.03, 0.06))},
            )
        )
        L["repay"].label = "Term loan scheduled amortization"
        m.add(
            Line(
                "tla",
                "Term loan",
                "bs",
                cells={
                    **{pp: r(debt_a[pp] - notes) for pp in A},
                    **{pp: Ref("tla", -1) + Ref("cf_repay") for pp in F},
                },
            )
        )
        m.add(
            Line(
                "notes",
                "Senior notes",
                "bs",
                cells={**{pp: notes for pp in A}, **{pp: Ref("notes", -1) for pp in F}},
            )
        )
        m.add(
            Line(
                "revolver",
                "Revolver",
                "bs",
                cells={**{pp: 0.0 for pp in A}, **{pp: Ref("revolver", -1) + Ref("cf_revolver") for pp in F}},
            )
        )
        L["debt"].label = "Total debt"
        L["debt"].cells = {pp: Sum(("tla", "notes", "revolver")) for pp in A + F}
        for pp in F:
            L["interest"].cells[pp] = (
                In("tla_rate") * Ref("tla", -1)
                + In("notes_rate") * Ref("notes", -1)
                + In("rev_rate") * Ref("revolver", -1)
            )
            L["cf_repay"].cells[pp] = -Fn("MIN", Ref("repay"), Ref("tla", -1))
        L["cf_repay"].label = "Term loan amortization"
        m.add(
            Line(
                "cf_revolver",
                "Revolver draw / (repayment)",
                "cf",
                cells={pp: Fn("MAX", -Ref("revolver", -1), In("min_cash") - Ref("cf_pre")) for pp in F},
            )
        )

    if "leases" in m.modules:
        life = rng.randint(6, 12)
        rate = round(rng.uniform(0.05, 0.08), 3)
        rou0, g = rev[A[0]] * rng.uniform(0.05, 0.15), rng.uniform(0.01, 0.04)
        rou = [r(rou0 * (1 + g) ** i) for i in range(len(A))]
        ratio = rng.uniform(1.02, 1.12)
        liab = [r(x * ratio) for x in rou]
        prev_rou = [r(rou0 / (1 + g))] + rou[:-1]
        prev_liab = [r(prev_rou[0] * ratio)] + liab[:-1]
        pct = rng.uniform(0.01, 0.02)
        m.add(
            Line(
                "lease_new",
                "New leases signed",
                "inputs",
                kind="series",
                cells={pp: r(rev[pp] * pct) for pp in F},
            )
        )
        m.add(
            Line(
                "lease_life",
                "Lease life (years)",
                "inputs",
                kind="scalar_input",
                cells={"": float(life)},
                fmt="int",
            )
        )
        m.add(
            Line(
                "lease_rate",
                "Lease interest rate (on opening liability)",
                "inputs",
                kind="scalar_input",
                cells={"": rate},
                fmt="pct",
            )
        )
        m.add(
            Line(
                "rou",
                "Right-of-use assets",
                "bs",
                cells={
                    **dict(zip(A, rou, strict=True)),
                    **{pp: Ref("rou", -1) + Ref("lease_new") - Ref("lease_amort") for pp in F},
                },
            )
        )
        m.add(
            Line(
                "lease_liab",
                "Lease liabilities",
                "bs",
                cells={
                    **dict(zip(A, liab, strict=True)),
                    **{pp: Ref("lease_liab", -1) + Ref("lease_new") + Ref("cf_lease") for pp in F},
                },
            )
        )
        m.add(
            Line(
                "lease_amort",
                "Amortization of right-of-use assets",
                "is",
                cells={
                    **{pp: r(x / life) for pp, x in zip(A, prev_rou, strict=True)},
                    **{pp: Ref("rou", -1) / In("lease_life") for pp in F},
                },
            )
        )
        m.add(
            Line(
                "lease_int",
                "Interest on lease liabilities",
                "is",
                cells={
                    **{pp: r(x * rate) for pp, x in zip(A, prev_liab, strict=True)},
                    **{pp: In("lease_rate") * Ref("lease_liab", -1) for pp in F},
                },
            )
        )
        m.add(
            Line(
                "cf_lease_amort",
                "Amortization of right-of-use assets",
                "cf",
                cells={pp: Ref("lease_amort") for pp in F},
            )
        )
        m.add(
            Line(
                "cf_lease",
                "Lease principal repayments",
                "cf",
                cells={pp: -(Ref("lease_liab", -1) / In("lease_life")) for pp in F},
            )
        )
        m.add(
            Line(
                "d_lease_amort",
                "Amortization of right-of-use assets",
                "dcf",
                cells={pp: Ref("lease_amort") for pp in F},
            )
        )
        m.add(
            Line(
                "d_lease_new",
                "New leases (treated as capital spending)",
                "dcf",
                cells={pp: -Ref("lease_new") for pp in F},
            )
        )
        for pp in A + F:
            L["ebit"].cells[pp] = Ref("ebitda") - Ref("dna") - Ref("lease_amort")
            L["ebt"].cells[pp] = Ref("ebit") - Ref("interest") - Ref("lease_int")
            L["ta"].cells[pp] = Ref("tca") + Ref("ppe") + Ref("gw") + Ref("rou")
            L["tl"].cells[pp] = Ref("tcl") + Ref("debt") + Ref("lease_liab")

    if "deferred_revenue" in m.modules:
        lo, hi = (0.06, 0.15) if m.sector == "software" else (0.01, 0.04)
        pct = round(rng.uniform(lo, hi), 3)
        m.add(
            Line(
                "dr_pct",
                "Deferred revenue, % of revenue",
                "inputs",
                kind="scalar_input",
                cells={"": pct},
                fmt="pct",
            )
        )
        m.add(
            Line(
                "def_rev",
                "Deferred revenue",
                "bs",
                cells={
                    **{pp: r(rev[pp] * pct * rng.uniform(0.97, 1.03)) for pp in A},
                    **{pp: Ref("revenue") * In("dr_pct") for pp in F},
                },
            )
        )
        m.add(
            Line(
                "cf_defrev",
                "Increase / (decrease) in deferred revenue",
                "cf",
                cells={pp: Ref("def_rev") - Ref("def_rev", -1) for pp in F},
            )
        )
        for pp in A + F:
            L["tcl"].cells[pp] = Sum(("ap", "accrued", "def_rev"))

    if "nol" in m.modules:
        m.add(
            Line(
                "nol_cap",
                "Tax loss usage limit, % of taxable income",
                "inputs",
                kind="scalar_input",
                cells={"": 0.8},
                fmt="pct",
            )
        )
        m.add(
            Line(
                "nol_beg",
                "Tax losses carried forward: opening",
                "is",
                cells={pp: Ref("nol_end", -1) for pp in F},
            )
        )
        m.add(
            Line(
                "nol_use",
                "Tax losses used",
                "is",
                cells={pp: Fn("MIN", Ref("nol_beg"), In("nol_cap") * Fn("MAX", 0, Ref("ebt"))) for pp in F},
            )
        )
        m.add(
            Line(
                "nol_end",
                "Tax losses carried forward: closing",
                "is",
                cells={
                    A[-1]: r(rev[A[-1]] * rng.uniform(0.04, 0.12)),
                    **{pp: Ref("nol_beg") - Ref("nol_use") for pp in F},
                },
            )
        )
        for pp in F:
            L["tax"].cells[pp] = (Fn("MAX", 0, Ref("ebt")) - Ref("nol_use")) * In("tax_rate")

    if "minority" in m.modules:
        pct = round(rng.uniform(0.1, 0.3), 2)
        m.add(
            Line(
                "nci_pct",
                "Non-controlling interests' share of net income",
                "inputs",
                kind="scalar_input",
                cells={"": pct},
                fmt="pct",
            )
        )
        m.add(
            Line(
                "ni_nci",
                "Net income attributable to non-controlling interests",
                "is",
                cells={pp: Ref("ni") * In("nci_pct") for pp in A + F},
            )
        )
        m.add(
            Line(
                "ni_parent",
                "Net income attributable to the company",
                "is",
                cells={pp: Ref("ni") - Ref("ni_nci") for pp in A + F},
            )
        )
        m.add(Line("nci", "Non-controlling interests", "bs", cells={pp: 0.0 for pp in A}))
        m.lines["nci"].cells.update({pp: Ref("nci", -1) + Ref("ni_nci") for pp in F})
        for pp in A + F:
            L["te"].cells[pp] = Ref("apic") + Ref("re") + Ref("nci")
        for pp in F:
            L["re"].cells[pp] = Ref("re", -1) + Ref("ni_parent")
            if "cf_div" in L:
                L["re"].cells[pp] = L["re"].cells[pp] + Ref("cf_div")
                L["cf_div"].cells[pp] = -(Ref("ni_parent") * In("payout"))
        m.add(
            Line(
                "v_nci",
                "Non-controlling interests at valuation date (book value)",
                "val",
                kind="scalar",
                cells={"": Ref("nci", at=A[-1])},
            )
        )
        L["v_eq"].cells[""] = Ref("v_ev", at="") - Ref("v_netdebt", at="") - Ref("v_nci", at="")

    # cash flow totals, in the order the layouts show the lines
    wc = [k for k in ("cf_ar", "cf_inv", "cf_ap", "cf_accr", "cf_defrev") if k in L]
    cfo = [k for k in ("cf_ni", "cf_dna", "cf_lease_amort", "cf_sbc") if k in L] + wc
    fin = [k for k in ("cf_repay", "cf_lease", "cf_div", "cf_revolver") if k in L]
    for pp in F:
        L["cfo"].cells[pp] = Sum(tuple(cfo))
        L["d_nwc"].cells[pp] = Sum(tuple(wc))
        L["cff"].cells[pp] = Sum(tuple(fin))
    if "debt_schedule" in m.modules:
        pre = Ref("cf_beg") + Ref("cfo") + Ref("cfi")
        for k in fin:
            if k != "cf_revolver":
                pre = pre + Ref(k)
        m.add(Line("cf_pre", "Cash before revolver (memo)", "cf", cells={pp: pre for pp in F}))
    if "leases" in m.modules:
        for pp in F:
            L["d_ufcf"].cells[pp] = (
                Ref("d_nopat")
                + Ref("d_dna")
                + Ref("d_lease_amort")
                + Ref("d_capex")
                + Ref("d_lease_new")
                + Ref("d_nwc")
            )
        L["v_netdebt"].cells[""] = Ref("debt", at=A[-1]) + Ref("lease_liab", at=A[-1]) - Ref("cash", at=A[-1])
        L["v_netdebt"].label = "Net debt at valuation date (including lease liabilities)"
    extra = []
    if "leases" in m.modules:
        extra.append(
            "leases are treated as debt (lease amortization is added back, new leases count as capital "
            "spending, and lease liabilities are in net debt)"
        )
    if "minority" in m.modules:
        extra.append(
            "non-controlling interests are deducted from enterprise value at book value at the valuation date"
        )
    if "nol" in m.modules:
        extra.append("the DCF taxes EBIT at the full rate, ignoring tax losses carried forward")
    if extra:
        L["v_policy"].text = L["v_policy"].text.rstrip(".") + "; " + "; ".join(extra) + "."
    if "leases" in m.modules:
        # Historical tax follows the historical profit after the lease costs.
        rate = float(L["tax_rate"].cells[""])
        ev = Evaluator(m)
        for pp in A:
            L["tax"].cells[pp] = r(max(0.0, ev.value("ebt", pp)) * rate * rng.uniform(0.97, 1.03))
    _rebalance(m, p, nd)


def _trim_quarters(m: Model) -> None:
    """Quarterly build for the last actual year and the first QUARTER_YEARS forecast years only;
    later forecast years are annual, driven by the annual assumptions."""
    keep_years = [m.actual[-1], *m.forecast[:QUARTER_YEARS]]
    m.quarters = [q for q in m.quarters if m.quarter_year[q] in keep_years]
    m.quarter_year = {q: y for q, y in m.quarter_year.items() if y in keep_years}
    for line in m.lines.values():
        if line.freq == "Q":
            line.cells = {q: c for q, c in line.cells.items() if q in m.quarter_year}
    later = m.forecast[QUARTER_YEARS:]
    opex = [k for k in m.lines if k.startswith("opex") and k[4:].isdigit()]
    for pp in later:
        m.lines["revenue"].cells[pp] = Ref("revenue", -1) * (1 + Ref("growth"))
        m.lines["cogs"].cells[pp] = Ref("revenue") * (1 - Ref("gm"))
        for k in opex:
            m.lines[k].cells[pp] = Ref("revenue") * Ref(f"{k}_pct")


def _rebalance(m: Model, p, nd: int) -> None:
    """Actual years: roll retained earnings (and non-controlling interests) with the new net
    income, then set cash so that each year balances, as build.py does for the base model."""
    A = m.actual
    L = m.lines
    payout = float(L["payout"].cells[""]) if "payout" in L else 0.0
    ev = Evaluator(m)
    share = "ni_parent" if "ni_parent" in L else "ni"
    if "nci" in L:
        nci0 = round(ev.value("revenue", A[0]) * 0.05, nd)
        L["nci"].cells[A[0]] = nci0
        for i in range(1, len(A)):
            L["nci"].cells[A[i]] = round(float(L["nci"].cells[A[i - 1]]) + ev.value("ni_nci", A[i]), nd)
    for i in range(1, len(A)):
        income = ev.value(share, A[i])
        L["re"].cells[A[i]] = round(float(L["re"].cells[A[i - 1]]) + income - income * payout, nd)
    assets = [k for k in ("ar", "inv", "ppe", "gw", "rou") if k in L]
    for _ in range(5):
        ev = Evaluator(m)
        bump = 0.0
        for pp in A:
            cash = round(ev.value("tle", pp) - sum(ev.value(k, pp) for k in assets), nd)
            if cash < ev.value("revenue", pp) * 0.04:
                bump = max(bump, round(ev.value("revenue", pp) * 0.08 - cash, nd))
            L["cash"].cells[pp] = cash
        if not bump:
            return
        for pp in A:  # more paid-in capital in every actual year keeps cash positive; then recompute
            L["apic"].cells[pp] = round(float(L["apic"].cells[pp]) + bump, nd)
    raise ValueError("actual years don't balance")
