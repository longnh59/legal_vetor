"""Ties T1-T4b together for a single document (PLAN_v2 section 5).
No LLM tier (D) and no validator scoring (T5/P3) yet - those are separate phases.
"""

from engine.build_tree import build_tree, doc_slug_for
from engine.classify import Classifier
from engine.clean import clean_html
from engine.flatten import flatten
from engine.models import Node
from engine.quote_mask import mask_quoted_blocks
from engine.split_parts import split_parts


def parse_document(doc_id: str, html_str: str, classifier: Classifier, so_ky_hieu: str | None = None) -> list[Node]:
    tree = clean_html(html_str)
    if tree is None:
        return []
    blocks = flatten(tree)
    parts = split_parts(blocks)
    doc_slug = doc_slug_for(doc_id, so_ky_hieu)

    nodes: list[Node] = []
    for part in parts:
        part_blocks = blocks[part.start_block : part.end_block + 1]
        classifications = [classifier.classify(b) for b in part_blocks]
        classifications = mask_quoted_blocks(part_blocks, classifications)
        nodes.extend(build_tree(doc_id, doc_slug, part, part_blocks, classifications))
    return nodes


def demo() -> None:
    html_str = (
        "<html><body>"
        '<p class="prov-article">Điều 1. Phạm vi điều chỉnh</p>'
        '<p class="prov-clause">1. Nội dung khoản 1</p>'
        '<p class="prov-item">a) Điểm a</p>'
        '<p class="prov-article">Điều 2. Đối tượng áp dụng</p>'
        '<p class="prov-clause">1. Áp dụng cho mọi cơ quan</p>'
        "</body></html>"
    )
    classifier = Classifier(class_map={"prov-article": ("dieu", 1.0), "prov-clause": ("khoan", 1.0), "prov-item": ("diem", 1.0)})
    nodes = parse_document("doc-x", html_str, classifier, so_ky_hieu="12/2024/QD-UBND")
    assert [n.node_type for n in nodes] == ["dieu", "khoan", "diem", "dieu", "khoan"]
    assert nodes[0].node_id.startswith("12-2024-qd-ubnd-doc-x/p1/dieu-1")
    assert nodes[3].node_id == "12-2024-qd-ubnd-doc-x/p1/dieu-2"
    print("parse_document.py demo OK")


if __name__ == "__main__":
    demo()
