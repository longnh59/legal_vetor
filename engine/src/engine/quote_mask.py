"""Mask classifications inside an unmatched-quote span.

Amending documents ("Điều 1. Sửa đổi, bổ sung...") quote the target
provision's original text inline, e.g.:

    1. Khoản 4, Điều 3 được sửa đổi, bổ sung như sau:
    "4. Định kỳ theo quy định báo cáo kết quả...
    5. Thực hiện...
    6. ..."

The first quoted line is usually safe (its leading `"` blocks the khoan/diem
regex), but continuation lines of a multi-line quotation carry no `"` of
their own and match the regex exactly like real numbering of *this*
document - scrambling the sequence with the target document's numbers
(verified: doc 130974, sequence became 1,2,5,9,3,4,5,6,1,2,...).

clean.py already normalizes curly quotes to straight `"`, so a simple
open/close parity counter per block is enough; this is a heuristic; an
unbalanced quote (rare, sloppy source doc) just means the rest of the part
gets absorbed as quoted content, no data is lost.
"""

from engine.classify import Classification
from engine.models import Block

MASKED = Classification(None, None, 0.0, None)


def mask_quoted_blocks(blocks: list[Block], classifications: list[Classification]) -> list[Classification]:
    out: list[Classification] = []
    quote_open = False
    for block, cls in zip(blocks, classifications):
        out.append(MASKED if quote_open else cls)
        if block.text.count('"') % 2 == 1:
            quote_open = not quote_open
    return out


def demo() -> None:
    def b(text):
        return Block(text=text, tag="p", html_raw=f"<p>{text}</p>", dom_order=0)

    def c(node_type, number_raw):
        return Classification(node_type, number_raw, 0.9, "regex")

    blocks = [
        b("1. Khoản 4, Điều 3 được sửa đổi, bổ sung như sau:"),
        b('"4. Định kỳ theo quy định báo cáo...'),
        b("5. Thực hiện..."),
        b('6. Nội dung."'),
        b("2. Khoản khác được sửa đổi như sau:"),
    ]
    classes = [c("khoan", "1"), c(None, None), c("khoan", "5"), c("khoan", "6"), c("khoan", "2")]
    masked = mask_quoted_blocks(blocks, classes)
    assert [m.node_type for m in masked] == ["khoan", None, None, None, "khoan"]
    assert [m.number_raw for m in masked] == ["1", None, None, None, "2"]

    # a doc with no quotes at all is untouched
    blocks2 = [b("1. A"), b("2. B")]
    classes2 = [c("khoan", "1"), c("khoan", "2")]
    assert mask_quoted_blocks(blocks2, classes2) == classes2

    print("quote_mask.py demo OK")


if __name__ == "__main__":
    demo()
