"""T1 - clean & normalize (PLAN_v2 section 5, T1).

Strips script/style/head, unwraps bare font/span wrappers, normalizes nbsp and
Unicode NFC, normalizes quotes/dashes/ellipsis, collapses whitespace.
`<table>` is left untouched - flatten.py treats it as an atomic block.
"""

import re
import unicodedata

from lxml import html as lxml_html
from lxml.html import HtmlElement

_STRIP_TAGS = ("script", "style", "head")
_UNWRAP_TAGS = ("font", "span")

_QUOTE_MAP = str.maketrans({
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "–": "-", "—": "-", "…": "...",
})
_NBSP_RE = re.compile("[  ]")
_WS_RE = re.compile(r"[ \t]+")


def _normalize_text(text: str | None) -> str | None:
    if text is None:
        return None
    text = _NBSP_RE.sub(" ", text)
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_QUOTE_MAP)
    return _WS_RE.sub(" ", text)


def clean_html(html_str: str) -> HtmlElement | None:
    """Parse raw content_html into a cleaned lxml tree, or None if empty/unparsable."""
    if not html_str or not html_str.strip():
        return None
    tree = lxml_html.fromstring(html_str)

    for tag in _STRIP_TAGS:
        for el in tree.findall(f".//{tag}"):
            el.getparent().remove(el)

    # Unwrap span/font that carry no class and no style - pure noise from Word export.
    for tag in _UNWRAP_TAGS:
        for el in tree.findall(f".//{tag}"):
            if not (el.get("class") or "").strip() and not (el.get("style") or "").strip():
                el.drop_tag()

    for el in tree.iter():
        el.text = _normalize_text(el.text)
        el.tail = _normalize_text(el.tail)

    return tree


def demo() -> None:
    raw = (
        "<html><head><style>.x{}</style></head><body>"
        "<p class=\"prov-article\">Điều 1.&nbsp;Phạm  vi  điều chỉnh – áp dụng…</p>"
        "<span>bare noise</span><span class=\"prov-clause\">1. Nội dung</span>"
        "</body></html>"
    )
    tree = clean_html(raw)
    assert tree is not None
    assert tree.find(".//style") is None
    p_text = tree.find(".//p").text_content()
    assert " " not in p_text
    assert "-" in p_text and "..." in p_text
    assert tree.find(".//span[@class='prov-clause']") is not None
    # bare <span>noise</span> must be unwrapped (no span left without class/style)
    assert not any(
        el.tag == "span" and not (el.get("class") or el.get("style"))
        for el in tree.iter("span")
    )
    assert clean_html("") is None
    print("clean.py demo OK")


if __name__ == "__main__":
    demo()
