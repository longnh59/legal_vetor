"""T5 - per-document quality scoring (PLAN_v2 section 7).

Runs the full T1-T4b pipeline per document and scores it clean/warn/failed on:
char_coverage, sequence_ok, hierarchy_ok, part_count_ok, table_preserved,
conflict_rate. Writes reports/quality.parquet + reports/QUALITY.md.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.parquet as pq

from engine.build_tree import build_tree, doc_slug_for
from engine.classify import Classifier
from engine.classify_llm import LlmClassifier, enrich_with_llm
from engine.clean import clean_html
from engine.config import CHAR_COVERAGE_CLEAN_MIN, CHAR_COVERAGE_WARN_MIN, REPORTS_DIR
from engine.flatten import flatten
from engine.io import iter_content_rows, metadata_by_id
from engine.models import Node
from engine.profiling import _decade, _dom_signature
from engine.quote_mask import mask_quoted_blocks
from engine.split_parts import RE_BAN_HANH_KEM, split_parts

CONFLICT_CONFIDENCE = 0.45  # classify.py sets exactly 0.4 on a regex/class conflict
CONFLICT_RATE_MAX = 0.05

DIEM_ORDER = {c: i for i, c in enumerate("abcdđeghiklmnopqrstuvxy")}
_NUM_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")


@dataclass
class QualityReport:
    doc_id: str
    n_nodes: int
    char_coverage: float
    sequence_ok: bool
    hierarchy_ok: bool
    part_count_ok: bool
    table_preserved: bool
    conflict_rate: float
    verdict: str
    issues: list[str] = field(default_factory=list)
    loai_van_ban: str = "unknown"
    decade: str = "unknown"
    template_family: str = ""


def _sequence_ok(nodes: list[Node]) -> bool:
    children: dict[str | None, list[Node]] = defaultdict(list)
    for n in nodes:
        children[n.parent_id].append(n)

    for siblings in children.values():
        by_type: dict[str, list[Node]] = defaultdict(list)
        for n in siblings:
            by_type[n.node_type].append(n)
        for node_type, group in by_type.items():
            if node_type == "diem":
                # Real corpus docs don't consistently follow the "no f/j/w/z"
                # convention (verified: doc 106917 uses a full a..g run
                # including f) - so only require strictly increasing order,
                # not the traditional alphabet's exact consecutive positions.
                nums = [DIEM_ORDER.get((n.number_norm or "").lower()) for n in group]
                nums = [x for x in nums if x is not None]
                if len(nums) < 2:
                    continue
                if nums != sorted(nums) or len(set(nums)) != len(nums):
                    return False
            elif node_type in ("dieu", "khoan"):
                nums = []
                for n in group:
                    m = _NUM_RE.match(n.number_norm or "")
                    nums.append(int(m.group()) if m else None)
                nums = [x for x in nums if x is not None]
                if len(nums) < 2:
                    continue
                if nums != list(range(nums[0], nums[0] + len(nums))):
                    return False
    return True


def _hierarchy_ok(nodes: list[Node]) -> bool:
    # A "diem" always needs a "khoan" parent. A "khoan" needs a "dieu" parent
    # ONLY if this document actually has Dieu structure elsewhere - many real
    # doc types (Chi thi, Cong van; verified on docs 5417, 89362, 110065) are
    # flat numbered lists with median Dieu count 0 (see profiling REPORT.md),
    # so a parentless khoan there is normal, not an orphan.
    by_id = {n.node_id: n for n in nodes}
    has_dieu = any(n.node_type == "dieu" for n in nodes)
    for n in nodes:
        if n.node_type == "diem":
            parent = by_id.get(n.parent_id) if n.parent_id else None
            if parent is None or parent.node_type != "khoan":
                return False
        elif n.node_type == "khoan":
            parent = by_id.get(n.parent_id) if n.parent_id else None
            if parent is not None and parent.node_type != "dieu":
                return False
            if parent is None and has_dieu:
                return False
    return True


def validate_document(
    doc_id: str,
    html_str: str,
    classifier: Classifier,
    so_ky_hieu: str | None = None,
    llm: LlmClassifier | None = None,
) -> QualityReport:
    tree = clean_html(html_str)
    blocks = flatten(tree) if tree is not None else []
    # 732+ docs genuinely have empty content_html (e.g. "<body></body>", or ""),
    # per PLAN_v2 trap #12: "hop le, khong phai loi". Nothing to check == clean,
    # not a part_count/failed false positive (verified: doc 135139).
    if not blocks:
        return QualityReport(doc_id, 0, 1.0, True, True, True, True, 0.0, "clean")

    parts = split_parts(blocks)
    doc_slug = doc_slug_for(doc_id, so_ky_hieu)

    nodes: list[Node] = []
    n_classified = n_conflict = 0
    for part in parts:
        part_blocks = blocks[part.start_block : part.end_block + 1]
        classifications = [classifier.classify(b) for b in part_blocks]
        classifications = mask_quoted_blocks(part_blocks, classifications)
        if llm is not None:
            classifications = enrich_with_llm(part_blocks, classifications, llm)
        for cls in classifications:
            if cls.node_type is not None:
                n_classified += 1
                if cls.confidence < CONFLICT_CONFIDENCE:
                    n_conflict += 1
        nodes.extend(build_tree(doc_id, doc_slug, part, part_blocks, classifications))

    # Compare non-whitespace chars only: tree.text_content() preserves the
    # original inter-tag whitespace/newlines that per-block .strip() discards,
    # which otherwise reads as "content loss" when it's actually just formatting.
    tree_chars = len(_WS_RE.sub("", tree.text_content() or ""))
    block_chars = len(_WS_RE.sub("", "".join(b.text for b in blocks)))
    char_coverage = (block_chars / tree_chars) if tree_chars else 1.0

    ban_hanh_kem_signals = sum(1 for b in blocks if RE_BAN_HANH_KEM.search(b.text))
    part_count_ok = len(parts) == ban_hanh_kem_signals + 1

    n_tables_in = len(tree.findall(".//table"))
    n_tables_out = sum(1 for b in blocks if b.is_table)
    table_preserved = n_tables_in == n_tables_out

    seq_ok = _sequence_ok(nodes)
    hier_ok = _hierarchy_ok(nodes)
    conflict_rate = (n_conflict / n_classified) if n_classified else 0.0

    issues = []
    if char_coverage < CHAR_COVERAGE_CLEAN_MIN:
        issues.append("char_coverage")
    if not seq_ok:
        issues.append("sequence")
    if not hier_ok:
        issues.append("hierarchy")
    if not part_count_ok:
        issues.append("part_count")
    if not table_preserved:
        issues.append("table_preserved")
    if conflict_rate >= CONFLICT_RATE_MAX:
        issues.append("conflict_rate")

    if char_coverage < CHAR_COVERAGE_WARN_MIN:
        verdict = "failed"
    elif not issues:
        verdict = "clean"
    else:
        verdict = "warn"

    return QualityReport(
        doc_id=doc_id,
        n_nodes=len(nodes),
        char_coverage=char_coverage,
        sequence_ok=seq_ok,
        hierarchy_ok=hier_ok,
        part_count_ok=part_count_ok,
        table_preserved=table_preserved,
        conflict_rate=conflict_rate,
        verdict=verdict,
        issues=issues,
        template_family=_dom_signature(tree),
    )


def run_validation() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    meta = metadata_by_id()
    classifier = Classifier()

    reports: list[QualityReport] = []
    for row in iter_content_rows():
        doc_id = row["id"]
        m = meta.get(doc_id, {})
        r = validate_document(doc_id, row.get("content_html") or "", classifier, so_ky_hieu=m.get("so_ky_hieu"))
        r.loai_van_ban = m.get("loai_van_ban") or "unknown"
        r.decade = _decade(m.get("ngay_ban_hanh"))
        reports.append(r)

    table = pa.Table.from_pylist(
        [
            {
                "doc_id": r.doc_id,
                "n_nodes": r.n_nodes,
                "char_coverage": r.char_coverage,
                "sequence_ok": r.sequence_ok,
                "hierarchy_ok": r.hierarchy_ok,
                "part_count_ok": r.part_count_ok,
                "table_preserved": r.table_preserved,
                "conflict_rate": r.conflict_rate,
                "verdict": r.verdict,
                "issues": ",".join(r.issues),
                "loai_van_ban": r.loai_van_ban,
                "decade": r.decade,
                "template_family": r.template_family[:300],
            }
            for r in reports
        ]
    )
    pq.write_table(table, REPORTS_DIR / "quality.parquet")
    _write_quality_md(reports)


def _write_quality_md(reports: list[QualityReport]) -> None:
    total = len(reports)
    verdict_counts = Counter(r.verdict for r in reports)
    issue_combo_counts: Counter = Counter()
    issue_combo_example: dict[str, str] = {}
    by_type: dict[str, Counter] = defaultdict(Counter)
    by_decade: dict[str, Counter] = defaultdict(Counter)
    by_template: dict[str, Counter] = defaultdict(Counter)

    for r in reports:
        combo = ",".join(r.issues) or "none"
        issue_combo_counts[combo] += 1
        issue_combo_example.setdefault(combo, r.doc_id)
        by_type[r.loai_van_ban][r.verdict] += 1
        by_decade[r.decade][r.verdict] += 1
        by_template[r.template_family[:80]][r.verdict] += 1

    lines = ["# Parse quality report (P3)", ""]
    lines.append(f"- Total docs: {total}")
    for v in ("clean", "warn", "failed"):
        c = verdict_counts.get(v, 0)
        lines.append(f"- {v}: {c} ({c / total:.1%})" if total else f"- {v}: 0")
    lines.append("")
    lines.append("## Top 20 issue combinations")
    lines.append("| issues | count | example doc_id |")
    lines.append("|---|---|---|")
    for combo, count in issue_combo_counts.most_common(20):
        lines.append(f"| {combo} | {count} | {issue_combo_example[combo]} |")
    lines.append("")
    lines.append("## By loai_van_ban")
    lines.append("| loai_van_ban | clean | warn | failed | n |")
    lines.append("|---|---|---|---|---|")
    for k, c in sorted(by_type.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        lines.append(f"| {k} | {c.get('clean', 0)} | {c.get('warn', 0)} | {c.get('failed', 0)} | {n} |")
    lines.append("")
    lines.append("## By decade")
    lines.append("| decade | clean | warn | failed | n |")
    lines.append("|---|---|---|---|---|")
    for k, c in sorted(by_decade.items()):
        n = sum(c.values())
        lines.append(f"| {k} | {c.get('clean', 0)} | {c.get('warn', 0)} | {c.get('failed', 0)} | {n} |")
    lines.append("")
    lines.append("## Top 15 template families by volume")
    lines.append("| template (first 80 chars) | clean | warn | failed | n |")
    lines.append("|---|---|---|---|---|")
    for k, c in sorted(by_template.items(), key=lambda kv: -sum(kv[1].values()))[:15]:
        n = sum(c.values())
        lines.append(f"| `{k}` | {c.get('clean', 0)} | {c.get('warn', 0)} | {c.get('failed', 0)} | {n} |")

    (REPORTS_DIR / "QUALITY.md").write_text("\n".join(lines), encoding="utf-8")


def demo() -> None:
    classifier = Classifier(class_map={"prov-article": ("dieu", 1.0), "prov-clause": ("khoan", 1.0), "prov-item": ("diem", 1.0)})

    good_html = (
        "<html><body>"
        '<p class="prov-article">Điều 1. Phạm vi</p>'
        '<p class="prov-clause">1. Nội dung khoản 1</p>'
        '<p class="prov-clause">2. Nội dung khoản 2</p>'
        "</body></html>"
    )
    r = validate_document("d1", good_html, classifier)
    assert r.verdict == "clean", r.issues
    assert r.sequence_ok and r.hierarchy_ok and r.table_preserved

    gap_html = (
        "<html><body>"
        '<p class="prov-article">Điều 1. Phạm vi</p>'
        '<p class="prov-clause">1. Khoản 1</p>'
        '<p class="prov-clause">3. Khoản 3 - nhảy cóc</p>'
        "</body></html>"
    )
    r = validate_document("d2", gap_html, classifier)
    assert not r.sequence_ok and "sequence" in r.issues

    empty_r = validate_document("d3", "", classifier)
    assert empty_r.verdict == "clean" and empty_r.n_nodes == 0

    empty_shell_r = validate_document("d4", "<html><body></body></html>", classifier)
    assert empty_shell_r.verdict == "clean" and empty_shell_r.n_nodes == 0

    print("validate.py demo OK")


if __name__ == "__main__":
    demo()
