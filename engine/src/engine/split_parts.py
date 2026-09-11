"""T3 - split a block stream into document_parts, BEFORE building any tree
(PLAN_v2 section 5 T3, section 6 trap 11: one file often holds >1 document -
a "QUY ĐỊNH (Ban hành kèm theo ...)" annex with its own Điều 1.. numbering).

Boundary signals (either is enough, plan section 5):
- an uppercase, centered heading line matching QUY ĐỊNH/QUY CHẾ/ĐIỀU LỆ/DANH
  MỤC/PHỤ LỤC, especially paired with "(Ban hành kèm theo ...)"
- Điều numbering that was increasing suddenly restarts at 1
"""

import re

from engine.models import Block, DocumentPart

RE_DIEU = re.compile(r"^\s*Điều\s+(\d+)[a-zđ]?[.\s]", re.IGNORECASE)
RE_HEADING = re.compile(
    r"^\s*(QUY ĐỊNH|QUY CHẾ|ĐIỀU LỆ|DANH MỤC|PHỤ LỤC)\b", re.IGNORECASE
)
RE_BAN_HANH_KEM = re.compile(r"\(Ban hành kèm theo", re.IGNORECASE)
_LOOKBACK = 10  # same wrapped-title reasoning as _HEADING_LOOKAHEAD below


_HEADING_LOOKAHEAD = 6  # an annex title often wraps 2-3 lines before "(Ban hành kèm theo" (verified: doc 134516)


def _is_heading_signal(blocks: list[Block], i: int) -> bool:
    # A bare "QUY ĐỊNH CHUNG" / "QUY ĐỊNH CỤ THỂ" is just a chapter title
    # *inside* an annex (verified: doc 137801) - only a real annex boundary
    # is paired with "(Ban hành kèm theo ...)", in this block or shortly after.
    text = blocks[i].text.strip()
    if not RE_HEADING.match(text):
        return False
    if RE_BAN_HANH_KEM.search(text):
        return True
    return any(
        RE_BAN_HANH_KEM.search(blocks[j].text) for j in range(i + 1, min(i + _HEADING_LOOKAHEAD, len(blocks)))
    )


def split_parts(blocks: list[Block]) -> list[DocumentPart]:
    if not blocks:
        return []

    boundaries = [0]
    last_dieu_num: int | None = None

    for i, block in enumerate(blocks):
        if _is_heading_signal(blocks, i) and i > boundaries[-1]:
            boundaries.append(i)
            last_dieu_num = None
            continue

        m = RE_DIEU.match(block.text)
        if not m:
            continue
        num = int(m.group(1))
        if last_dieu_num is not None and num == 1 and last_dieu_num > 1:
            boundary_idx = i
            for j in range(i - 1, max(i - _LOOKBACK, boundaries[-1] - 1), -1):
                if RE_BAN_HANH_KEM.search(blocks[j].text) or RE_HEADING.match(blocks[j].text.strip()):
                    boundary_idx = j
                    break
            if boundary_idx > boundaries[-1]:
                boundaries.append(boundary_idx)
        last_dieu_num = num

    parts = []
    for idx, start in enumerate(boundaries):
        end = boundaries[idx + 1] - 1 if idx + 1 < len(boundaries) else len(blocks) - 1
        heading = blocks[start].text if idx > 0 else None
        parts.append(
            DocumentPart(part_id=f"p{idx + 1}", start_block=start, end_block=end, heading=heading, is_main=(idx == 0))
        )
    return parts


def demo() -> None:
    def b(text, is_center=False):
        return Block(text=text, tag="p", html_raw=f"<p>{text}</p>", dom_order=0, is_center=is_center)

    blocks = [
        b("Điều 1. Phạm vi"),
        b("Điều 2. Đối tượng"),
        b("QUY CHẾ (Ban hành kèm theo Quyết định số 1/QĐ-UBND)", is_center=True),
        b("Điều 1. Phạm vi quy chế"),
        b("Điều 2. Nội dung"),
    ]
    parts = split_parts(blocks)
    assert len(parts) == 2
    assert parts[0].start_block == 0 and parts[0].end_block == 1 and parts[0].is_main
    assert parts[1].start_block == 2 and parts[1].end_block == 4 and not parts[1].is_main

    # no boundary signal at all -> single part covering everything
    single = split_parts(blocks[:2])
    assert len(single) == 1 and single[0].end_block == 1

    assert split_parts([]) == []
    print("split_parts.py demo OK")


if __name__ == "__main__":
    demo()
