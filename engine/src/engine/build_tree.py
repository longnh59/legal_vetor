"""T4b - state machine + stack that turns classified blocks into a Node tree
(PLAN_v2 section 5, T4b; section 6 traps 1, 2, 9).

Unrecognized blocks are appended to the current leaf node's text, never
dropped (trap: "thà báo lỗi còn hơn tách sai âm thầm" applies to content loss
too). A Điều with unnumbered content directly under it gets a synthetic
khoan-0 child so every Điều's content lives under a khoan (trap 9).
Unrecognized blocks that appear before any structural node has opened (e.g.
"Căn cứ ...") become a `preamble` node instead of being dropped (trap 4).
"""

import re
import unicodedata
from collections import defaultdict

from engine.classify import Classification
from engine.models import Block, DocumentPart, Node

LEVELS = ["phan", "chuong", "muc", "tieu_muc", "dieu", "khoan", "diem", "gach_dau_dong"]
LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "doc"


def doc_slug_for(doc_id: str, so_ky_hieu: str | None) -> str:
    """so_ky_hieu (e.g. "14/2018/QĐ-UBND") is only unique within one issuing
    agency, not corpus-wide - many provinces reuse the same numbering, so
    using it alone collides node_id across different documents (verified:
    two real docs both produced "14-2018-q-ubnd/p1/dieu-1/khoan-2"). Always
    fold in the corpus's own unique doc_id to guarantee uniqueness, keeping
    so_ky_hieu only for human readability."""
    if so_ky_hieu:
        return f"{slugify(so_ky_hieu)}-{slugify(doc_id)}"
    return slugify(doc_id)


def _norm_number(node_type: str, raw: str | None) -> str | None:
    if raw is None:
        return None
    return raw.lower() if node_type == "diem" else raw


def _append_to(node: Node, block: Block) -> None:
    node.text += "\n" + block.text
    node.text_full += "\n" + block.text
    node.html_raw += block.html_raw


def build_tree(
    doc_id: str,
    doc_slug: str,
    part: DocumentPart,
    blocks: list[Block],
    classifications: list[Classification],
) -> list[Node]:
    """blocks/classifications must be aligned 1:1 (same slice of one document_part)."""
    nodes: list[Node] = []
    stack: list[Node] = []
    dieu_has_child: dict[str, bool] = {}
    # Fallback ordinal when no number could be extracted from the text (e.g. an
    # old-format doc classified only via css_class, which carries no number) -
    # keyed by (parent_id, node_type) so siblings never collide on node_id
    # (verified bug: doc 57284 previously gave every unnumbered khoan sibling
    # the same id because the old fallback was len(stack)+1, a constant).
    sibling_seq: dict[tuple[str | None, str], int] = defaultdict(int)
    # node_id is a citation key - it must never collide, even when the source
    # text itself repeats a number (verified: doc 129591, an amending decree
    # that embeds another document's "Điều 1...Khoản 2" with no quote marks at
    # all - deeper than quote_mask.py can catch, since there's no delimiter to
    # track). A repeat gets a disambiguating suffix rather than silently
    # colliding two different provisions under one id.
    seen_ids: set[str] = set()

    def close_to(rank: int) -> None:
        while stack and LEVEL_RANK[stack[-1].node_type] >= rank:
            stack.pop()

    def push(node_type, number_raw, confidence, classified_by, text, html_raw) -> Node:
        close_to(LEVEL_RANK[node_type])
        parent = stack[-1] if stack else None
        number_norm = _norm_number(node_type, number_raw)
        if number_norm:
            tail = f"{node_type}-{number_norm}"
        else:
            key = (parent.node_id if parent else None, node_type)
            sibling_seq[key] += 1
            tail = f"{node_type}-u{sibling_seq[key]}"  # 'u' = unnumbered, avoid colliding with a real number
        node_id = f"{parent.node_id}/{tail}" if parent else f"{doc_slug}/{part.part_id}/{tail}"
        if node_id in seen_ids:
            dedup = 2
            while f"{node_id}~{dedup}" in seen_ids:
                dedup += 1
            node_id = f"{node_id}~{dedup}"
        seen_ids.add(node_id)
        path = f"{parent.path}.{tail.replace('-', '_')}" if parent else tail.replace("-", "_")
        breadcrumb = f"{parent.breadcrumb} › {text[:60]}" if parent else text[:60]

        node = Node(
            node_id=node_id,
            doc_id=doc_id,
            part_id=part.part_id,
            parent_id=parent.node_id if parent else None,
            path=path,
            depth=len(stack),
            order_index=len(nodes),
            node_type=node_type,
            number_raw=number_raw,
            number_norm=number_norm,
            heading=text if node_type in ("dieu", "chuong", "muc", "tieu_muc", "phan") else None,
            text=text,
            text_full=text,
            breadcrumb=breadcrumb,
            html_raw=html_raw,
            confidence=confidence,
            classified_by=classified_by,
        )
        nodes.append(node)
        stack.append(node)
        if parent and parent.node_type == "dieu":
            dieu_has_child[parent.node_id] = True
        return node

    preamble: Node | None = None

    for block, cls in zip(blocks, classifications):
        if cls.node_type is None:
            top = stack[-1] if stack else None
            if top is not None and top.node_type == "dieu" and not dieu_has_child.get(top.node_id):
                push("khoan", None, 0.5, "style", block.text, block.html_raw)
                dieu_has_child[top.node_id] = True
                # number_norm defaults to None above; force it to the sentinel "0"
                nodes[-1].number_norm = "0"
                nodes[-1].node_id = f"{top.node_id}/khoan-0"
                nodes[-1].path = f"{top.path}.khoan_0"
                continue
            if top is not None:
                _append_to(nodes[-1], block)
                continue
            # nothing opened yet in this part (trap 4: "Can cu..." block before
            # Dieu 1 belongs to no Dieu) -> keep it, don't drop it
            if preamble is None:
                preamble = Node(
                    node_id=f"{doc_slug}/{part.part_id}/preamble",
                    doc_id=doc_id,
                    part_id=part.part_id,
                    parent_id=None,
                    path="preamble",
                    depth=0,
                    order_index=len(nodes),
                    node_type="preamble",
                    text=block.text,
                    text_full=block.text,
                    breadcrumb=block.text[:60],
                    html_raw=block.html_raw,
                    confidence=0.6,
                    classified_by="regex",
                )
                nodes.append(preamble)
            else:
                _append_to(preamble, block)
            continue

        push(cls.node_type, cls.number_raw, cls.confidence, cls.classified_by, block.text, block.html_raw)

    by_id = {n.node_id: n for n in nodes}
    for n in nodes:
        pid = n.parent_id
        while pid and pid in by_id:
            ancestor = by_id[pid]
            ancestor.text_full += "\n" + n.text
            pid = ancestor.parent_id

    return nodes


def demo() -> None:
    def b(text):
        return Block(text=text, tag="p", html_raw=f"<p>{text}</p>", dom_order=0)

    def c(node_type, number_raw, confidence=0.9, by="regex"):
        return Classification(node_type, number_raw, confidence, by)

    part = DocumentPart(part_id="p1", start_block=0, end_block=4, is_main=True)
    blocks = [b("Điều 1. Phạm vi"), b("1. Nội dung khoản một"), b("a) điểm a"), b("b) điểm b"), b("Điều 2. Không có khoản")]
    classes = [c("dieu", "1"), c("khoan", "1"), c("diem", "a"), c("diem", "b"), c("dieu", "2")]

    nodes = build_tree("doc1", "quyet-dinh-1", part, blocks, classes)
    assert [n.node_type for n in nodes] == ["dieu", "khoan", "diem", "diem", "dieu"]
    assert nodes[0].node_id == "quyet-dinh-1/p1/dieu-1"
    assert nodes[1].node_id == "quyet-dinh-1/p1/dieu-1/khoan-1"
    assert nodes[2].node_id == "quyet-dinh-1/p1/dieu-1/khoan-1/diem-a"
    assert nodes[0].text_full.count("điểm a") == 1  # ancestor text_full includes descendants

    # Dieu 2 has no khoan child -> unrecognized trailing content becomes khoan-0
    blocks2 = [b("Điều 3. Một đoạn"), b("Nội dung không đánh số nằm ngay dưới Điều.")]
    classes2 = [c("dieu", "3"), c(None, None, 0.0, None)]
    nodes2 = build_tree("doc1", "quyet-dinh-1", part, blocks2, classes2)
    assert nodes2[1].node_type == "khoan" and nodes2[1].number_norm == "0"
    assert nodes2[1].node_id == "quyet-dinh-1/p1/dieu-3/khoan-0"

    # a genuinely unrecognized block after content exists just appends, no data lost
    blocks3 = [b("Điều 4."), b("1. Khoản một"), b("Ghi chú thêm cuối khoản.")]
    classes3 = [c("dieu", "4"), c("khoan", "1"), c(None, None, 0.0, None)]
    nodes3 = build_tree("doc1", "quyet-dinh-1", part, blocks3, classes3)
    assert "Ghi chú thêm" in nodes3[-1].text

    # preamble: unclassified content before the first structural node is kept, not dropped
    blocks4 = [b("Căn cứ Luật Tổ chức chính quyền địa phương..."), b("Căn cứ Nghị định..."), b("Điều 1. Phạm vi")]
    classes4 = [c(None, None, 0.0, None), c(None, None, 0.0, None), c("dieu", "1")]
    nodes4 = build_tree("doc1", "quyet-dinh-1", part, blocks4, classes4)
    assert nodes4[0].node_type == "preamble"
    assert "Căn cứ Nghị định" in nodes4[0].text
    assert nodes4[1].node_type == "dieu"

    print("build_tree.py demo OK")


if __name__ == "__main__":
    demo()
