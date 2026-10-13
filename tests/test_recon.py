"""The document-reconciliation tasks (fin_model_edits/recon) and what they need: comparisons and IF in
the expression language, the EDGAR HTML conversion with blackline markers, the source manifest, and the
Hillman tasks' build checks. Tests that need the downloaded filings are skipped without them
(scripts/fetch_sources.py hillman); scripts/validate_recon.py grades the tasks in LibreOffice."""

import pytest

from fin_model_edits.gen.expr import Cmp, Fn, In, Ref
from fin_model_edits.gen.layout import Compiler, Layout
from fin_model_edits.gen.model import Evaluator, Line, Model
from fin_model_edits.sources.convert import html_to_text
from fin_model_edits.sources.fetch import check, manifest


def _tiny() -> tuple[Model, Layout]:
    m = Model(company="T", sector="x", units="$ in millions", periods=["Y1", "Y2"], n_actual=0)
    m.add(Line("hi", "hi", "inputs", kind="scalar_input", cells={"": 3.0}))
    m.add(Line("lev", "lev", "debt", cells={"Y1": 3.5, "Y2": 2.0}))
    tier = Fn("IF", Cmp(">", Ref("lev"), In("hi")), 0.5, Fn("IF", Cmp(">", Ref("lev"), 2.5), 0.25, 0))
    m.add(Line("pct", "pct", "debt", cells={"Y1": tier, "Y2": tier}))
    lay = Layout(
        family="R",
        sheets=["S"],
        names={"S": "S"},
        cols={"Y1": "C", "Y2": "D"},
        rows={"lev": ("S", 2), "pct": ("S", 3)},
        scalars={"hi": ("S", "B1")},
    )
    return m, lay


def test_if_with_comparisons_evaluates_and_compiles():
    m, lay = _tiny()
    ev = Evaluator(m)
    assert ev.value("pct", "Y1") == 0.5 and ev.value("pct", "Y2") == 0
    assert Compiler(m, lay).formula("pct", "Y2") == "=IF(D2>$B$1,0.5,IF(D2>2.5,0.25,0))"


def test_if_evaluates_only_the_branch_taken():
    m, _ = _tiny()
    m.add(Line("zero", "zero", "debt", cells={"Y1": 0.0, "Y2": 0.0}))
    m.lines["pct"].cells["Y1"] = Fn("IF", Cmp(">", Ref("lev"), 1), 1, Ref("lev") / Ref("zero"))
    assert Evaluator(m).value("pct", "Y1") == 1


def test_comparisons_only_inside_if():
    from fin_model_edits.gen.model import EvalError

    m, lay = _tiny()
    m.lines["pct"].cells["Y1"] = Cmp(">", Ref("lev"), 1)
    with pytest.raises(EvalError):
        Evaluator(m).value("pct", "Y1")
    with pytest.raises(TypeError):
        Compiler(m, lay).formula("pct", "Y1")
    m.lines["pct"].cells["Y1"] = Fn("IF", Cmp(">", Ref("lev"), 1), 1)
    with pytest.raises(EvalError):
        Evaluator(m).value("pct", "Y1")


def test_blackline_markers_only_where_asked():
    html = (
        "<p>Pay <span style='color:#0000ff;text-decoration:underline'>0.25% of the total</span>"
        "<span style='color:#ff0000;text-decoration:line-through'>1.00%</span> quarterly, a "
        "<span style='color:#000000;text-decoration:underline'>Defined Term</span>.</p>"
        "<table><tr><td>Net sales</td><td>1,695</td></tr></table>"
    )
    marked = html_to_text(html, blackline=True)
    assert "[inserted: 0.25% of the total]" in marked and "[deleted: 1.00%]" in marked
    assert "[inserted: Defined Term]" not in marked and "Defined Term" in marked
    assert "Net sales | 1,695" in marked
    plain = html_to_text(html)
    assert "[inserted" not in plain and "0.25% of the total" in plain


def test_manifest_records_each_filing():
    docs = manifest("hillman")
    assert len({d.id for d in docs}) == len(docs)
    for d in docs:
        assert d.url.startswith("https://www.sec.gov/Archives/edgar/data/1822492/")
        assert d.accession.replace("-", "") in d.url and len(d.sha256) == 64
    assert [d.id for d in docs if d.blackline] == ["amendment_no_1"]


needs_sources = pytest.mark.skipif(
    not all(check(d) for d in manifest("hillman")), reason="Hillman filings not downloaded"
)


@needs_sources
def test_tasks_build_with_their_evidence_in_the_documents():
    from fin_model_edits.recon import checks
    from fin_model_edits.recon.issues import DECOYS, ISSUES, TASKS
    from fin_model_edits.recon.make import make, notes_text
    from fin_model_edits.recon.packet import build

    parts = build()
    for task_id, ids in TASKS.items():
        g = make(task_id)
        assert [i.kind for i in g.issues] == ids
        chains = {i: ISSUES[i].chain for i in ids} | {k: d.evidence for k, d in DECOYS.items()}
        assert checks.evidence_problems(parts, notes_text(g), chains) == []
    control = checks.search_baseline(parts, ISSUES["term_loan_margin"])
    assert control["found_by_search"]
    assert not checks.search_baseline(parts, ISSUES["leverage_gross_of_cash"])["found_by_search"]
