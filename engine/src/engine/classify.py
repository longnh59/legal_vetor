"""T4 tiers A-B - classify each block into a node_type (PLAN_v2 section 5, T4).
Cascade stops at the first confident tier; A (regex) and B (css class) are
cross-checked whenever both fire - disagreement is flagged `conflict` and
confidence is lowered rather than silently picking one (plan section 5).

Tier C (style-only fallback) is deliberately not implemented: a naive
"bold + short line" guess misclassifies title/signature lines as `dieu`
(verified against real corpus docs - see doc 142373). A real tier C needs
sequence-continuity context that only build_tree has; unclassified blocks
fall through to build_tree's preamble/append-to-leaf handling instead of a
guessed type. Tier D (LLM) is out of scope for P0-P3.
"""

import json
import re
from dataclasses import dataclass

from engine.config import PROFILING_DIR
from engine.models import Block, ClassifiedBy, NodeType

RE_DIEU = re.compile(r"^\s*Điều\s+(\d+[a-zđ]?)[.\s]", re.IGNORECASE)
RE_CHUONG = re.compile(r"^\s*Chương\s+([IVXLC]+)", re.IGNORECASE)
RE_MUC = re.compile(r"^\s*Mục\s+(\d+)", re.IGNORECASE)
RE_KHOAN = re.compile(r"^\s*(\d+)[.\-]\s")  # older docs (pre-2005, verified doc 57284) use "1-" not "1."
RE_DIEM = re.compile(r"^\s*([a-zđ])\)\s")

CLASS_PURITY_MIN = 0.7  # tier B trusted only when the class predicts one type this reliably


@dataclass
class Classification:
    node_type: NodeType | None
    number_raw: str | None
    confidence: float
    classified_by: ClassifiedBy | None
    conflict: bool = False


def _regex_tier(text: str) -> tuple[NodeType | None, str | None]:
    if m := RE_DIEU.match(text):
        return "dieu", m.group(1)
    if m := RE_CHUONG.match(text):
        return "chuong", m.group(1)
    if m := RE_MUC.match(text):
        return "muc", m.group(1)
    if m := RE_KHOAN.match(text):
        return "khoan", m.group(1)
    if m := RE_DIEM.match(text):
        return "diem", m.group(1)
    return None, None


def load_class_map() -> dict[str, tuple[NodeType, float]]:
    profile_path = PROFILING_DIR / "corpus_profile.json"
    if not profile_path.exists():
        return {}
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    return {
        cls: (info["node_type"], info["purity"])
        for cls, info in data.get("class_to_node_type_mapping", {}).items()
    }


class Classifier:
    """Holds the profiling-derived class map so it's loaded once, not per block."""

    def __init__(self, class_map: dict[str, tuple[NodeType, float]] | None = None):
        self.class_map = class_map if class_map is not None else load_class_map()

    def _class_tier(self, classes: list[str]) -> NodeType | None:
        for cls in classes:
            info = self.class_map.get(cls)
            if info and info[1] >= CLASS_PURITY_MIN:
                return info[0]
        return None

    def classify(self, block: Block) -> Classification:
        regex_type, number = _regex_tier(block.text)
        class_type = self._class_tier(block.classes)

        if regex_type is not None and class_type is not None:
            if regex_type == class_type:
                return Classification(regex_type, number, 0.95, "regex")
            return Classification(regex_type, number, 0.4, "regex", conflict=True)

        if regex_type is not None:
            return Classification(regex_type, number, 0.8, "regex")

        if class_type is not None:
            return Classification(class_type, None, 0.7, "css_class")

        return Classification(None, None, 0.0, None)


def demo() -> None:
    def b(text, classes=None):
        return Block(text=text, tag="p", classes=classes or [], html_raw=f"<p>{text}</p>", dom_order=0)

    clf = Classifier(class_map={"prov-article": ("dieu", 1.0), "prov-clause": ("khoan", 1.0)})

    c = clf.classify(b("Điều 5. Phạm vi", classes=["prov-article"]))
    assert c.node_type == "dieu" and c.number_raw == "5" and not c.conflict and c.confidence > 0.9

    c = clf.classify(b("Điều 5. Phạm vi", classes=["prov-clause"]))
    assert c.node_type == "dieu" and c.conflict and c.confidence < 0.5

    c = clf.classify(b("1. Nội dung khoản", classes=[]))
    assert c.node_type == "khoan" and c.number_raw == "1"

    c = clf.classify(b("a) điểm a", classes=[]))
    assert c.node_type == "diem" and c.number_raw == "a"

    c = clf.classify(b("Văn bản này có hiệu lực...", classes=["prov-content"]))
    assert c.node_type is None

    print("classify.py demo OK")


if __name__ == "__main__":
    demo()
