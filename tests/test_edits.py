"""The answer format: parsing, fill-right translation and rejection of malformed replies."""

import pytest

from fin_model_edits.edits import EditError, apply_edits, parse_edit_lines, parse_reply
from fin_model_edits.workbook import SHEETS, build_base_workbook

SHEET_NAMES = list(SHEETS)


def cells(text):
    return [
        (e.sheet, coord, value) for e in parse_edit_lines(text, SHEET_NAMES) for coord, value in e.cells()
    ]


def test_contents_are_typed():
    assert cells(
        "Inputs!C23 = 0.23\nInputs!C24 = 6%\nInputs!C25 = 1,250.5\nInputs!A9 = Downside\nCF!F6 ="
    ) == [
        ("Inputs", "C23", 0.23),
        ("Inputs", "C24", 0.06),
        ("Inputs", "C25", 1250.5),
        ("Inputs", "A9", "Downside"),
        ("CF", "F6", None),
    ]
    assert cells("Inputs!C4 = 3") == [("Inputs", "C4", 3)]
    assert cells("Inputs!D4 = 1 = Base, 2 = Upside") == [("Inputs", "D4", "1 = Base, 2 = Upside")]
    assert cells("Inputs!A9 = '42'") == [("Inputs", "A9", "42")], "quotes force text"


def test_range_fill_shifts_relative_references_only():
    got = cells("IS!F21:H21 = =F20*Inputs!$C$23+Inputs!F$10")
    assert got == [
        ("IS", "F21", "=F20*Inputs!$C$23+Inputs!F$10"),
        ("IS", "G21", "=G20*Inputs!$C$23+Inputs!G$10"),
        ("IS", "H21", "=H20*Inputs!$C$23+Inputs!H$10"),
    ]
    down = cells("IS!C14:C15 = =SUM(C11:C13)")
    assert down == [("IS", "C14", "=SUM(C11:C13)"), ("IS", "C15", "=SUM(C12:C14)")]
    assert cells("Inputs!F21:G21 = 0.05") == [("Inputs", "F21", 0.05), ("Inputs", "G21", 0.05)]


def test_sheet_names_and_dollar_signs_are_normalized():
    assert cells("is!$f$14 = =sum(f11:f13)") == [("IS", "F14", "=SUM(f11:f13)")]


def test_comments_and_blank_lines_are_ignored():
    assert cells("# a comment\n\nIS!F5 = 1\n") == [("IS", "F5", 1)]


@pytest.mark.parametrize(
    "text",
    [
        "IS F5 = 1",  # no sheet separator
        "Notes!A1 = x",  # unknown sheet
        "IS!AA5 = 1",  # outside A:Z
        "IS!F201 = 1",  # outside the row limit
        "IS!J5:F5 = 1",  # reversed range
        "IS!F5 = " + "x" * 1001,  # too long
        "IS!A1:Z200 = 1\nBS!A1:Z200 = 1",  # too many cells
    ],
)
def test_malformed_lines_reject_the_whole_reply(text):
    with pytest.raises(EditError):
        parse_edit_lines(text, SHEET_NAMES)


def test_reply_blocks():
    reply = "Thinking...\n```edits\nIS!F5 = 1\n```\nand also\n```edits\nIS!F5 = 2\nIS!G5 = 3\n```\n"
    edits = parse_reply(reply, SHEET_NAMES)
    wb = build_base_workbook()
    apply_edits(wb, edits)
    assert (wb["IS"]["F5"].value, wb["IS"]["G5"].value) == (2, 3), "later edits win"
    assert parse_reply("IS!F5 = 1", SHEET_NAMES) is None, "edits outside a block are not an answer"
    assert parse_reply("```\nIS!F5 = 1\n```", SHEET_NAMES) is None, "the block must be tagged edits"
    assert parse_reply("```edits\n```", SHEET_NAMES) == [], "an empty block is a (no-op) answer"
