"""EDGAR HTML to plain text for the document tasks.

Tables become rows of cells joined by " | ". Blacklined amendments (a conformed copy with the changes
marked) keep their markup as explicit markers, because colour and strike-through are lost in plain
text: inserted text (blue) becomes "[inserted: ...]" and deleted text (red, struck through) becomes
"[deleted: ...]". Black underlining is how agreements mark defined terms, so it is dropped. The hidden
inline-XBRL header of 10-K and 10-Q filings is skipped."""

from __future__ import annotations

import re
from html.parser import HTMLParser

BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "hr", "ul", "ol"}
CELL = {"td", "th"}
SKIP = {"script", "style", "head", "title", "ix:header"}
INSERTED_COLOURS = {"#0000ff", "#1100f0", "blue"}
STRUCK_TAGS = {"s", "strike", "del"}
"""Some blacklines strike text with a tag rather than a style."""
VOID = {"br", "hr", "img", "meta", "link", "input", "col", "area", "base", "wbr"}


def _mark(style: str) -> str | None:
    style = style.lower().replace(" ", "")
    colour = re.search(r"(?:^|;)color:([^;]+)", style)
    colour = colour.group(1) if colour else ""
    if "line-through" in style:
        return "deleted"
    if colour in INSERTED_COLOURS:
        return "inserted"
    return None


class _Text(HTMLParser):
    def __init__(self, blackline: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.blackline = blackline
        self.out: list[str] = []
        self.stack: list[tuple[str, str | None, bool]] = []  # (tag, mark, hidden)
        self.mark: str | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    # the current mark and visibility come from the innermost element that sets them
    def _state(self) -> tuple[str | None, bool]:
        mark, hidden = None, False
        for _, m, h in self.stack:
            mark = m or mark
            hidden = hidden or h
        return mark, hidden

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        style = a.get("style") or ""
        hidden = tag in SKIP or "display:none" in style.replace(" ", "").lower()
        if tag in VOID:
            if tag in BLOCK:
                self._emit("\n")
            return
        if tag == "tr":
            self.row = []
        elif tag in CELL and self.row is not None:
            self.cell = []
        elif tag in BLOCK:
            self._emit("\n")
        mark = _mark(style) if self.blackline else None
        if self.blackline and tag in STRUCK_TAGS:
            mark = "deleted"
        elif self.blackline and mark is None:
            # older blacklines colour with a FONT attribute and double-underline with a border
            flat = style.replace(" ", "").lower()
            coloured = (a.get("color") or "").lower() in INSERTED_COLOURS
            if coloured or ("border-bottom" in flat and "double" in flat):
                mark = "inserted"
        self.stack.append((tag, mark, hidden))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        # pop to the matching tag (EDGAR HTML is mostly well formed; tolerate strays)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in CELL and self.row is not None and self.cell is not None:
            text = _squash("".join(self.cell))
            self.row.append(text)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            cells = [c for c in self.row if c]
            self.row = None
            if cells:
                self._raw("\n" + " | ".join(cells) + "\n")
        elif tag in BLOCK:
            self._emit("\n")

    def handle_data(self, data):
        mark, hidden = self._state()
        if hidden:
            return
        if mark and data.strip():
            data = f"[{mark}: {data}]"
        self._emit(data)

    def _emit(self, text: str) -> None:
        if self.cell is not None:
            self.cell.append(text.replace("\n", " "))
        else:
            self.out.append(text)

    def _raw(self, text: str) -> None:
        self.out.append(text)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _merge_marks(text: str) -> str:
    # adjacent spans of the same mark on one line read as one change: "[inserted: a][inserted: b]" ->
    # "[inserted: ab]"; never across a line break, so every paragraph keeps its own markers
    for mark in ("inserted", "deleted"):
        pattern = re.compile(rf"\[{mark}: ([^\[\]\n]*)\]([ \t]*)\[{mark}: ")
        while True:
            new = pattern.sub(lambda m, mark=mark: f"[{mark}: {m.group(1)}{m.group(2)}", text)
            if new == text:
                break
            text = new
    return text


def html_to_text(raw: str, blackline: bool = False) -> str:
    """Plain text of an EDGAR HTML document. `blackline` turns on the change markers; only marked-up
    copies need it (elsewhere blue is just a hyperlink)."""
    parser = _Text(blackline)
    parser.feed(raw)
    parser.close()
    lines = []
    for line in "".join(parser.out).replace("\xa0", " ").split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return _merge_marks(text)
