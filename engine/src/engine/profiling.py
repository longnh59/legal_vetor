"""P0 - corpus-wide profiling. No parser is written until this has run (PLAN_v2 section 10:
"khong doan class name, thiet ke rule dua tren so lieu that").

Runs once over all 170,824 documents, doing only cheap work (no tree building):
1. class frequency on p/div/span, with 3 text samples each
2. style distribution (text-indent, margin-left, font-weight) per class
3. % docs with <table>, <img>, <a href>
4. DOM-signature clustering -> template families
5. % docs matched by Dieu/Chuong/Muc/Khoan/Diem regexes
6. regex-vs-class agreement rate
7. % docs with signs of multiple document_parts
8. length / dieu-count distribution by loai_van_ban and by decade
"""

import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from lxml import html as lxml_html

from engine.config import (
    DEV_SAMPLE_SIZE,
    GOLDEN_SET_SIZE,
    PROFILING_DIR,
)
from engine.io import iter_content_rows, metadata_by_id

TEXT_TAGS = {"p", "div", "span", "li", "td"}

RE_DIEU = re.compile(r"^\s*Điều\s+(\d+[a-zđ]?)[.\s]", re.IGNORECASE)
RE_CHUONG = re.compile(r"^\s*Chương\s+([IVXLC]+)", re.IGNORECASE)
RE_MUC = re.compile(r"^\s*Mục\s+(\d+)", re.IGNORECASE)
RE_KHOAN = re.compile(r"^\s*(\d+)\.\s")
RE_DIEM = re.compile(r"^\s*([a-zđ])\)\s")
RE_BAN_HANH_KEM = re.compile(r"\(Ban hành kèm theo", re.IGNORECASE)


@dataclass
class ClassStat:
    tag_counts: Counter = field(default_factory=Counter)
    samples: list[str] = field(default_factory=list)
    indents: Counter = field(default_factory=Counter)
    bold_count: int = 0
    total: int = 0


def _style_signals(style: str) -> tuple[str | None, bool]:
    indent = None
    m = re.search(r"text-indent:\s*([-\d.]+)", style or "")
    if not m:
        m = re.search(r"margin-left:\s*([-\d.]+)", style or "")
    if m:
        indent = m.group(1)
    is_bold = bool(re.search(r"font-weight:\s*(bold|[6-9]00)", style or "", re.IGNORECASE))
    return indent, is_bold


def _dom_signature(tree) -> str:
    classes = set()
    for el in tree.iter():
        cls = el.get("class")
        if cls:
            classes.update(cls.split())
    return "|".join(sorted(classes))


def _decade(ngay_ban_hanh: str | None) -> str:
    if not ngay_ban_hanh:
        return "unknown"
    m = re.search(r"(\d{4})$", ngay_ban_hanh.strip())
    if not m:
        return "unknown"
    year = int(m.group(1))
    return f"{(year // 10) * 10}s"


def run_profiling() -> dict:
    PROFILING_DIR.mkdir(parents=True, exist_ok=True)
    meta = metadata_by_id()

    class_stats: dict[str, ClassStat] = defaultdict(ClassStat)
    has_table = has_img = has_anchor = 0
    dieu_match = chuong_match = muc_match = khoan_match = diem_match = 0
    multi_part_signal = 0
    total_docs = 0
    parse_errors = 0

    dom_signatures: Counter = Counter()

    length_by_type: dict[str, list[int]] = defaultdict(list)
    length_by_decade: dict[str, list[int]] = defaultdict(list)
    dieu_count_by_type: dict[str, list[int]] = defaultdict(list)

    # class -> Counter(regex_type -> count), built from blocks where a regex signal fired.
    # Used to derive a class->node_type mapping (for T4 tier B) and a meaningful
    # agreement rate: "if we always predicted from each class's majority regex-type,
    # how often would that match the regex label" - not a naive string-substring check.
    class_regex_crosstab: dict[str, Counter] = defaultdict(Counter)

    all_ids: list[str] = []
    stratify_bucket: dict[tuple, list[str]] = defaultdict(list)

    for row in iter_content_rows():
        doc_id = row["id"]
        html_str = row.get("content_html") or ""
        total_docs += 1
        all_ids.append(doc_id)

        m = meta.get(doc_id, {})
        loai = m.get("loai_van_ban") or "unknown"
        decade = _decade(m.get("ngay_ban_hanh"))
        length_by_type[loai].append(len(html_str))
        length_by_decade[decade].append(len(html_str))

        if not html_str.strip():
            continue

        try:
            tree = lxml_html.fromstring(html_str)
        except Exception:
            parse_errors += 1
            continue

        if tree.find(".//table") is not None:
            has_table += 1
        if tree.find(".//img") is not None:
            has_img += 1
        anchors = tree.findall(".//a[@href]")
        if anchors:
            has_anchor += 1

        sig = _dom_signature(tree)
        dom_signatures[sig] += 1
        stratify_bucket[(loai, decade, sig)].append(doc_id)

        doc_dieu_numbers: list[int] = []
        doc_has_dieu = doc_has_chuong = doc_has_muc = doc_has_khoan = doc_has_diem = False
        seen_ban_hanh_kem = False

        for el in tree.iter():
            if el.tag not in TEXT_TAGS:
                continue
            text = (el.text_content() or "").strip()
            if not text:
                continue

            classes = (el.get("class") or "").split()
            style = el.get("style") or ""
            indent, is_bold = _style_signals(style)

            regex_hit = None
            dm = RE_DIEU.match(text)
            if dm:
                regex_hit = "dieu"
                doc_has_dieu = True
                try:
                    doc_dieu_numbers.append(int(re.match(r"\d+", dm.group(1)).group()))
                except Exception:
                    pass
            elif RE_CHUONG.match(text):
                regex_hit = "chuong"
                doc_has_chuong = True
            elif RE_MUC.match(text):
                regex_hit = "muc"
                doc_has_muc = True
            elif RE_KHOAN.match(text):
                regex_hit = "khoan"
                doc_has_khoan = True
            elif RE_DIEM.match(text):
                regex_hit = "diem"
                doc_has_diem = True

            if RE_BAN_HANH_KEM.search(text):
                seen_ban_hanh_kem = True

            for cls in classes:
                stat = class_stats[cls]
                stat.total += 1
                stat.tag_counts[el.tag] += 1
                if indent is not None:
                    stat.indents[indent] += 1
                if is_bold:
                    stat.bold_count += 1
                if len(stat.samples) < 3:
                    stat.samples.append(text[:200])

            if classes and regex_hit is not None:
                for cls in classes:
                    class_regex_crosstab[cls][regex_hit] += 1

        if doc_has_dieu:
            dieu_match += 1
        if doc_has_chuong:
            chuong_match += 1
        if doc_has_muc:
            muc_match += 1
        if doc_has_khoan:
            khoan_match += 1
        if doc_has_diem:
            diem_match += 1

        dieu_count_by_type[loai].append(len(doc_dieu_numbers))

        is_non_increasing_restart = any(
            b < a for a, b in zip(doc_dieu_numbers, doc_dieu_numbers[1:])
        )
        if seen_ban_hanh_kem or is_non_increasing_restart:
            multi_part_signal += 1

    def _pctiles(values: list[int]) -> dict:
        if not values:
            return {}
        s = sorted(values)
        n = len(s)

        def pct(p):
            idx = min(n - 1, int(n * p))
            return s[idx]

        return {"p50": pct(0.5), "p90": pct(0.9), "max": s[-1], "n": n}

    top_classes = sorted(class_stats.items(), key=lambda kv: -kv[1].total)[:200]
    template_families = sorted(dom_signatures.items(), key=lambda kv: -kv[1])[:15]

    class_to_node_type: dict[str, dict] = {}
    agree_numerator = agree_denominator = 0
    for cls, counter in class_regex_crosstab.items():
        total = sum(counter.values())
        best_type, best_count = counter.most_common(1)[0]
        class_to_node_type[cls] = {
            "node_type": best_type,
            "purity": best_count / total,
            "n": total,
            "breakdown": dict(counter),
        }
        agree_numerator += best_count
        agree_denominator += total
    class_to_node_type = dict(
        sorted(class_to_node_type.items(), key=lambda kv: -kv[1]["n"])
    )

    profile = {
        "total_docs": total_docs,
        "parse_errors": parse_errors,
        "pct_with_table": has_table / total_docs if total_docs else 0,
        "pct_with_img": has_img / total_docs if total_docs else 0,
        "pct_with_anchor_href": has_anchor / total_docs if total_docs else 0,
        "regex_match_rate": {
            "dieu": dieu_match / total_docs if total_docs else 0,
            "chuong": chuong_match / total_docs if total_docs else 0,
            "muc": muc_match / total_docs if total_docs else 0,
            "khoan": khoan_match / total_docs if total_docs else 0,
            "diem": diem_match / total_docs if total_docs else 0,
        },
        "regex_vs_class_agreement_rate": (
            agree_numerator / agree_denominator if agree_denominator else None
        ),
        "class_to_node_type_mapping": class_to_node_type,
        "pct_multi_part_signal": multi_part_signal / total_docs if total_docs else 0,
        "top_classes": [
            {
                "class": cls,
                "total": stat.total,
                "tags": dict(stat.tag_counts),
                "top_indents": stat.indents.most_common(5),
                "bold_ratio": stat.bold_count / stat.total if stat.total else 0,
                "samples": stat.samples,
            }
            for cls, stat in top_classes
        ],
        "template_families": [
            {"signature": sig[:300], "doc_count": count} for sig, count in template_families
        ],
        "length_by_type": {k: _pctiles(v) for k, v in length_by_type.items()},
        "length_by_decade": {k: _pctiles(v) for k, v in length_by_decade.items()},
        "dieu_count_by_type": {k: _pctiles(v) for k, v in dieu_count_by_type.items()},
    }

    (PROFILING_DIR / "corpus_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _write_report_md(profile)
    dev_sample, golden_ids = _select_samples(stratify_bucket, all_ids)
    (PROFILING_DIR / "dev_sample_ids.json").write_text(
        json.dumps(dev_sample, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (PROFILING_DIR / "golden_set_ids.json").write_text(
        json.dumps(golden_ids, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return profile


def _select_samples(
    stratify_bucket: dict[tuple, list[str]], all_ids: list[str]
) -> tuple[list[str], list[str]]:
    rng = random.Random(42)
    buckets = list(stratify_bucket.items())
    rng.shuffle(buckets)

    dev_sample: list[str] = []
    golden_ids: list[str] = []

    # round-robin across buckets so both samples span type x decade x template family
    idx = 0
    while len(dev_sample) < min(DEV_SAMPLE_SIZE, len(all_ids)) and buckets:
        key, ids = buckets[idx % len(buckets)]
        if ids:
            pick = ids.pop(rng.randrange(len(ids)))
            dev_sample.append(pick)
        idx += 1
        if all(not ids for _, ids in buckets):
            break

    idx = 0
    attempts = 0
    while len(golden_ids) < min(GOLDEN_SET_SIZE, len(dev_sample)) and attempts < 10 * len(buckets):
        key, ids = buckets[idx % len(buckets)]
        if ids:
            pick = ids.pop(rng.randrange(len(ids)))
            golden_ids.append(pick)
        idx += 1
        attempts += 1

    return dev_sample, golden_ids


def _write_report_md(profile: dict) -> None:
    lines = ["# Corpus profiling report (P0)", ""]
    lines.append(f"- Total docs scanned: {profile['total_docs']}")
    lines.append(f"- HTML parse errors: {profile['parse_errors']}")
    lines.append(f"- % with <table>: {profile['pct_with_table']:.1%}")
    lines.append(f"- % with <img>: {profile['pct_with_img']:.1%}")
    lines.append(f"- % with <a href>: {profile['pct_with_anchor_href']:.1%}")
    lines.append(f"- % with multi-document_part signal: {profile['pct_multi_part_signal']:.1%}")
    lines.append("")
    lines.append("## Regex match rate (% of docs where at least one block matches)")
    for k, v in profile["regex_match_rate"].items():
        lines.append(f"- {k}: {v:.1%}")
    lines.append("")
    agree = profile["regex_vs_class_agreement_rate"]
    lines.append(
        f"## Regex-vs-class agreement rate: {agree:.1%}"
        if agree is not None
        else "## Regex-vs-class agreement rate: n/a"
    )
    lines.append("")
    lines.append("## Derived class -> node_type mapping (majority vote, for T4 tier B)")
    lines.append("| class | node_type | purity | n | breakdown |")
    lines.append("|---|---|---|---|---|")
    for cls, info in list(profile["class_to_node_type_mapping"].items())[:40]:
        lines.append(
            f"| `{cls}` | {info['node_type']} | {info['purity']:.0%} | {info['n']} | {info['breakdown']} |"
        )
    lines.append("")
    lines.append("## Top 30 CSS classes by usage")
    lines.append("| class | total | bold ratio | tags | sample |")
    lines.append("|---|---|---|---|---|")
    for c in profile["top_classes"][:30]:
        sample = (c["samples"][0] if c["samples"] else "").replace("|", "/").replace("\n", " ")[:80]
        lines.append(
            f"| `{c['class']}` | {c['total']} | {c['bold_ratio']:.0%} | "
            f"{c['tags']} | {sample} |"
        )
    lines.append("")
    lines.append("## Template families (top 15 by DOM class-signature)")
    for t in profile["template_families"]:
        lines.append(f"- {t['doc_count']} docs — `{t['signature'][:150]}`")
    lines.append("")
    lines.append("## Length distribution by loai_van_ban")
    for k, v in sorted(profile["length_by_type"].items(), key=lambda kv: -kv[1].get("n", 0)):
        lines.append(f"- {k}: n={v.get('n')} p50={v.get('p50')} p90={v.get('p90')} max={v.get('max')}")
    lines.append("")
    lines.append("## Length distribution by decade")
    for k, v in sorted(profile["length_by_decade"].items()):
        lines.append(f"- {k}: n={v.get('n')} p50={v.get('p50')} p90={v.get('p90')} max={v.get('max')}")
    lines.append("")
    lines.append("## Dieu count by loai_van_ban")
    for k, v in sorted(profile["dieu_count_by_type"].items(), key=lambda kv: -kv[1].get("n", 0)):
        lines.append(f"- {k}: n={v.get('n')} p50={v.get('p50')} p90={v.get('p90')} max={v.get('max')}")

    (PROFILING_DIR / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run_profiling()
