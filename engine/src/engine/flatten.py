"""T2 - flatten a cleaned DOM into a block stream (PLAN_v2 section 5, T2).

Each block is one text-bearing element in document order, except `<table>`
which is kept as a single atomic block (never flattened into its rows).
"""

import re

from lxml.html import HtmlElement, tostring

from engine.models import Block

BLOCK_TAGS = {"p", "div", "li", "td", "h1", "h2", "h3", "h4", "h5", "h6"}

_INDENT_RE = re.compile(r"(?:text-indent|margin-left):\s*(-?[\d.]+)")
_BOLD_RE = re.compile(r"font-weight:\s*(bold|[6-9]00)", re.IGNORECASE)
_CENTER_RE = re.compile(r"text-align:\s*center", re.IGNORECASE)


def _style_signals(style: str) -> tuple[float | None, bool, bool]:
    indent = None
    m = _INDENT_RE.search(style)
    if m:
        try:
            indent = float(m.group(1))
        except ValueError:
            indent = None
    is_bold = bool(_BOLD_RE.search(style))
    is_center = bool(_CENTER_RE.search(style)) or "center" in style.lower()
    return indent, is_bold, is_center


def _to_block(el: HtmlElement, dom_order: int, is_table: bool = False) -> Block | None:
    text = (el.text_content() or "").strip()
    if not text:
        return None
    style = el.get("style") or ""
    indent, style_bold, is_center = _style_signals(style)
    is_bold = style_bold or el.find(".//b") is not None or el.find(".//strong") is not None
    is_italic = el.find(".//i") is not None or el.find(".//em") is not None
    anchors = [a.get("href") for a in el.findall(".//a[@href]")] + (
        [el.get("href")] if el.tag == "a" and el.get("href") else []
    )
    return Block(
        text=text,
        tag=el.tag,
        classes=(el.get("class") or "").split(),
        style_indent=indent,
        is_bold=is_bold,
        is_italic=is_italic,
        is_center=is_center,
        is_table=is_table,
        html_raw=tostring(el, encoding="unicode"),
        dom_order=dom_order,
        anchors=[a for a in anchors if a],
    )


def flatten(tree: HtmlElement) -> list[Block]:
    """Walk `tree` in document order, one Block per leaf block-level element.
    A block-level element nested inside another (e.g. <p> inside a <div> that
    is itself in BLOCK_TAGS) is not double-emitted for the ancestor - only the
    innermost text-bearing element is kept, so text isn't duplicated.
    `<table>` is always emitted whole and never descended into.
    """
    blocks: list[Block] = []
    dom_order = 0
    body = tree.find(".//body")
    root = body if body is not None else tree

    def visit(el: HtmlElement) -> bool:
        """Returns True if `el` (or a descendant) produced a block, so the
        caller (an ancestor also in BLOCK_TAGS) knows not to re-emit itself."""
        nonlocal dom_order
        if el.tag == "table":
            block = _to_block(el, dom_order, is_table=True)
            if block:
                blocks.append(block)
                dom_order += 1
            return True

        produced = False
        for child in el:
            if visit(child):
                produced = True

        if not produced and el.tag in BLOCK_TAGS:
            block = _to_block(el, dom_order)
            if block:
                blocks.append(block)
                dom_order += 1
                produced = True

        return produced

    visit(root)
    return blocks


def demo() -> None:
    from engine.clean import clean_html

    raw = (
        "<html><body>"
        '<p class="prov-article">Điều 1. Phạm vi</p>'
        '<table><tr><td>a</td><td>b</td></tr></table>'
        '<div><p class="prov-clause">1. Nội dung <a href="/vb/123">tham chiếu</a></p></div>'
        "<p></p>"
        "</body></html>"
    )
    tree = clean_html(raw)
    blocks = flatten(tree)
    assert [b.tag for b in blocks] == ["p", "table", "p"]
    assert blocks[1].is_table is True
    assert blocks[2].anchors == ["/vb/123"]
    assert blocks[0].dom_order == 0 and blocks[2].dom_order == 2
    # empty <p></p> must not produce a block
    assert all(b.text.strip() for b in blocks)
    print("flatten.py demo OK")


if __name__ == "__main__":
    demo()
