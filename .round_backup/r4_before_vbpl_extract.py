# -*- coding: utf-8 -*-
"""
vbpl_extract.py — Agent bóc tách văn bản QPPL Việt Nam

Trả về 6 nhóm thành phần:
  1. header      — quốc hiệu, cơ quan, số ký hiệu, địa danh/ngày, loại VB, trích yếu
  2. can_cu      — danh sách căn cứ pháp lý (mỗi cái là 1 tham chiếu VB)
  3. provisions  — cây Phần/Chương/Mục/Tiểu mục/Điều/Khoản/Điểm/Tiết
  4. footer      — nơi nhận, chức danh, người ký
  5. appendix    — phụ lục / biểu mẫu / bảng (KHÔNG đưa vào cây)
  6. facts       — citations, amendment_ops, definitions, effective_dates
"""
from __future__ import annotations

import re
import json
import hashlib
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

# =============================================================================
# 0. Chuẩn hoá
# =============================================================================
# oà->òa chỉ đúng khi âm tiết không có phụ âm cuối: "hoà"->"hòa" nhưng "Hoàng" giữ nguyên
_VN = "a-zA-ZÀ-ỹ"
_TONE_MAP = {"oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
             "uỳ": "ùy", "uý": "úy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy"}
_TONE_MAP.update({k.capitalize(): v.capitalize() for k, v in list(_TONE_MAP.items())})
_TONE_RX = re.compile(r"(?<![%s])([A-Za-zÀ-ỹ]*?)(%s)(?![%s])"
                      % (_VN, "|".join(_TONE_MAP), _VN))


def _fix_tone(s: str) -> str:
    def rep(m):
        return m.group(1) + _TONE_MAP[m.group(2)]
    return _TONE_RX.sub(rep, s)


def normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\xa0", " ").replace("\u200b", "").replace("\u00ad", "")
    s = _fix_tone(s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def to_lines(text: str) -> List[str]:
    return [normalize(l) for l in text.split("\n") if normalize(l)]


def to_source_lines(text: str) -> List[Dict[str, Any]]:
    records = []
    for i, raw in enumerate(text.splitlines()):
        norm = normalize(raw)
        records.append({
            "line_no": i,
            "raw_text": raw,
            "normalized_text": norm,
            "is_blank": not bool(norm),
            "section": None,
        })
    if text.endswith(("\n", "\r")):
        records.append({
            "line_no": len(records),
            "raw_text": "",
            "normalized_text": "",
            "is_blank": True,
            "section": None,
        })
    return records


def assign_line_sections(records: List[Dict[str, Any]], seg: Dict[str, Any]) -> None:
    section_items = []
    for section in ("header", "body", "footer", "appendix"):
        section_items.extend((section, line) for line in seg.get(section, []))

    cursor = 0
    current_section = None
    for rec in records:
        if rec["is_blank"]:
            rec["section"] = current_section
            continue
        if cursor < len(section_items) and rec["normalized_text"] == section_items[cursor][1]:
            current_section = section_items[cursor][0]
            rec["section"] = current_section
            cursor += 1
        else:
            rec["section"] = current_section or "unknown"


# =============================================================================
# 1. Regex nhận diện
# =============================================================================
ROMAN = r"[IVXLCDM]+"
DIEM_LETTERS = "abcdđefghiklmnopqrstuvxy"   # bảng chữ cái dùng cho điểm; một số VB/điều ước dùng cả f)
ORDINAL_WORDS = {
    "nhất": "1", "một": "1", "hai": "2", "ba": "3", "bốn": "4", "tư": "4",
    "năm": "5", "sáu": "6", "bảy": "7", "tám": "8", "chín": "9", "mười": "10",
}

RX = {
    "phan":     re.compile(rf"^PHẦN\s+(?:THỨ\s+)?({ROMAN}|\d+|[A-ZĐÀ-Ỹ]+)\b\s*[.:–-]?\s*(.*)$", re.I),
    "chuong":   re.compile(rf"^CHƯƠNG\s+({ROMAN}|\d+)\b\s*[.:–-]?\s*(.*)$", re.I),
    "muc":      re.compile(rf"^MỤC\s+(\d+|{ROMAN})\b\s*[.:–-]?\s*(.*)$", re.I),
    "tieu_muc": re.compile(r"^TIỂU\s+MỤC\s+(\d+)\b\s*[.:–-]?\s*(.*)$", re.I),
    "dieu":     re.compile(r"^ĐIỀU\s+(\d+[a-zà-ỹ]?)\s*[.:]?\s*(.*)$", re.I),
    "decimal_item": re.compile(r"^(\d{1,3}(?:\.\d{1,3}){1,5})[.)]?\s+(.+)$"),
    "khoan":    re.compile(r"^(\d{1,3}[a-zà-ỹ]?)\s*[.)](?!\d)\s*(.*)$"),
    "roman_section": re.compile(rf"^({ROMAN})([a-z]?)(\s*[.]\s+|\s+)(.+)$", re.I),
    "diem":     re.compile(rf"^([{DIEM_LETTERS}]\d?)\s*[.)]\s*(?:\[\d+\])?\s+(.+)$"),
    "tiet":     re.compile(r"^[-–—+•]\s+(.+)$"),
}

RX_SO_KY_HIEU = re.compile(
    r"(?:Số|SỐ)\s*:?\s*([0-9A-ZĐ][0-9A-ZĐa-zà-ỹ./\-]{1,40})")
RX_SO_LUAT = re.compile(
    r"(?:Luật|Bộ luật|Pháp lệnh|Nghị quyết)\s+số\s*:?\s*([\dA-Z/\-]+)", re.I)
RX_DIA_DANH_NGAY = re.compile(
    r"^([A-ZĐÀ-Ỹ][\wÀ-ỹ\s.]{1,30}),\s*ngày\s+(\d{1,2})\s*tháng\s+(\d{1,2})\s*năm\s+(\d{4})", re.I)
RX_NGAY = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.I)
RX_NGAY_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
RX_CAN_CU = re.compile(r"^(Căn cứ|Chiểu theo|Chiểu|Thực hiện|Theo đề nghị|Xét đề nghị|Theo quyết nghị)\b", re.I)
RX_PROMULGATION_FORMULA = re.compile(
    r"^(QUYẾT ĐỊNH|QUYẾT NGHỊ|NGHỊ QUYẾT)\s*:\s*$|"
    r"^(?!Căn cứ\b|Theo đề nghị\b|Xét đề nghị\b|Thực hiện\b).*\b(ban hành|thông qua|xây dựng)\b.*\bnhư sau\s*:?\s*$",
    re.I,
)
RX_ENACT = re.compile(r"^(QUYẾT ĐỊNH|QUYẾT NGHỊ|NGHỊ QUYẾT|THÔNG TƯ|CHỈ THỊ)\s*:?\s*$", re.I)
RX_NOI_NHAN = re.compile(r"^Nơi nhận\s*:?", re.I)
RX_APPENDIX = re.compile(
    r"^(PHỤ\s*LỤC|BIỂU\s*MẪU|MẪU\s+SỐ|MẪU\s+\d|DANH\s+MỤC\b.*KÈM|BIỂU\s+SỐ)", re.I)
RX_ATTACHMENT_HEADING = re.compile(
    r"^(PHẦN\s+(?:[IVXLCDM]+|\d+)\b|DANH\s+MỤC\b|THỦ\s+TỤC\s+HÀNH\s+CHÍNH\b|"
    r"QUY\s+CHẾ\b|QUY\s+ĐỊNH\b).*(?:Ban hành kèm theo|Kèm theo)", re.I)
RX_QUOC_HIEU = re.compile(r"CỘNG\s+HÒA\s+XÃ\s+HỘI\s+CHỦ\s+NGHĨA|Độc lập\s*[-–]\s*Tự do", re.I)

DOC_TYPES = ["Bộ luật", "Hiến pháp", "Luật", "Pháp lệnh", "Lệnh", "Nghị quyết liên tịch",
             "Nghị quyết", "Nghị định", "Quyết định", "Thông tư liên tịch", "Thông tư",
             "Chỉ thị", "Sắc lệnh", "Văn bản hợp nhất", "Công văn", "Thông báo", "Kế hoạch"]
RX_DOC_TYPE_LINE = re.compile(
    r"^(" + "|".join(t.upper() for t in DOC_TYPES) + r")\s*$", re.I)

# ký hiệu văn bản: 13/2023/NĐ-CP, 200/2014/TT-BTC, 88/2015/QH13, 24/LĐ-NĐ
RX_DOC_REF = re.compile(
    r"\b(\d{1,4}[a-z]?/(?:\d{4}/)?[A-ZĐ][A-ZĐ0-9\-]{1,20})\b")
# trích dẫn nội bộ: điểm a khoản 2 Điều 103
RX_PROV_REF = re.compile(
    r"(?:(?:điểm|Điểm)\s+([a-zđ]\d?)\s*[,]?\s*)?"
    r"(?:(?:khoản|Khoản)\s+(\d{1,3}[a-z]?)\s*[,]?\s*)?"
    r"(?:Điều|điều)\s+(\d{1,3}[a-z]?)")

RX_AMEND = re.compile(
    r"\b(sửa đổi,\s*bổ sung|sửa đổi|bổ sung|bãi bỏ|thay thế|hủy bỏ|hết hiệu lực|ngưng hiệu lực)\b", re.I)
RX_HIEU_LUC = re.compile(
    r"(có hiệu lực(?:\s+thi hành)?|hết hiệu lực)\s*(?:kể\s+từ|từ|sau)?\s*(.{0,80})", re.I)
RX_DEF = re.compile(
    r"^(.{2,80}?)\s+(?:là|được hiểu là|bao gồm|gồm)\s+(.+)$")


_LVL_HEAD = {"phan": r"PHẦN\s+(?:THỨ\s+)?", "chuong": r"CHƯƠNG\s+",
             "muc": r"MỤC\s+", "tieu_muc": r"TIỂU\s+MỤC\s+", "dieu": r"ĐIỀU\s+"}


def _hit_structural(line: str):
    up = line.upper()
    for lvl in ("phan", "chuong", "tieu_muc", "muc", "dieu"):
        m = RX[lvl].match(line)
        if not m:
            continue
        # phải là "<TỪ KHOÁ> <số/số La Mã>" thật, tránh "Mục tiêu", "Chương trình"
        if lvl == "phan":
            allowed = rf"({ROMAN}|\d+[A-ZÀ-Ỹ]?|{'|'.join(w.upper() for w in ORDINAL_WORDS)})\b"
            if not re.match(_LVL_HEAD[lvl] + allowed, up):
                continue
        elif not re.match(_LVL_HEAD[lvl] + rf"({ROMAN}|\d+[A-ZÀ-Ỹ]?)\b", up):
            continue
        num = m.group(1)
        num_norm = normalize(num).lower()
        if num_norm in ORDINAL_WORDS:
            num = ORDINAL_WORDS[num_norm]
        else:
            num = num.upper() if re.fullmatch(ROMAN, num, re.I) else num.lower()
        return lvl, num, normalize(m.group(2))
    m = RX["roman_section"].match(line)
    if m:
        roman_part = m.group(1)
        suffix = m.group(2) or ""
        sep = m.group(3)
        raw_token = roman_part + suffix
        if roman_part != roman_part.upper():
            return None
        if "." not in sep:
            if suffix or raw_token != raw_token.upper():
                return None
        elif suffix and suffix != suffix.lower():
            return None
        num = roman_part.upper() + suffix.lower()
        return "roman_section", num, normalize(m.group(4))
    return None


# =============================================================================
# 2. Cấu trúc dữ liệu
# =============================================================================
RANK = {"root": 0, "phan": 1, "chuong": 2, "muc": 3, "tieu_muc": 4,
        "dieu": 5, "roman_section": 6, "khoan": 7, "sub_khoan": 8,
        "sub_sub_khoan": 9, "diem": 10, "tiet": 11}
VI = {"phan": "Phần", "chuong": "Chương", "muc": "Mục", "tieu_muc": "Tiểu mục",
      "dieu": "Điều", "roman_section": "Mục", "khoan": "Khoản",
      "sub_khoan": "Tiểu khoản", "sub_sub_khoan": "Tiểu khoản",
      "diem": "Điểm", "tiet": "Tiết"}
CODE = {"phan": "p", "chuong": "c", "muc": "m", "tieu_muc": "tm",
        "dieu": "d", "roman_section": "rs", "khoan": "k",
        "sub_khoan": "sk", "sub_sub_khoan": "ssk", "diem": "dm", "tiet": "t"}


def _path_num(number: str) -> str:
    return (number or "").lower().replace(".", "_")


def _node_segment(n: "Node") -> str:
    return f"{CODE[n.level]}{_path_num(n.number)}"


@dataclass
class Node:
    level: str
    number: str = ""
    heading: str = ""
    text: str = ""
    line_start: int = -1
    line_end: int = -1
    source_context: str = "own"
    quote_id: Optional[int] = None
    children: List["Node"] = field(default_factory=list)
    parent: Optional["Node"] = None

    @property
    def label(self) -> str:
        return f"{VI.get(self.level, self.level)} {self.number}".strip()

    @property
    def path(self) -> str:
        """Khoá ổn định: c2.m1.d8.k2.dma — dùng làm provision_id + citation key."""
        parts, n = [], self
        while n and n.level != "root":
            parts.append(_node_segment(n))
            n = n.parent
        return ".".join(reversed(parts))

    @property
    def breadcrumb(self) -> str:
        parts, n = [], self
        while n and n.level != "root":
            lbl = n.label
            if n.level == "dieu" and n.heading:
                lbl += f". {n.heading}"
            parts.append(lbl)
            n = n.parent
        return " > ".join(reversed(parts))

    def full_text(self) -> str:
        out = []
        if self.heading:
            out.append(self.heading)
        if self.text:
            out.append(self.text)
        for c in self.children:
            pre = {"khoan": f"{c.number}.", "sub_khoan": f"{c.number}.",
                   "sub_sub_khoan": f"{c.number}.", "diem": f"{c.number})",
                   "tiet": "-"}.get(c.level, "")
            out.append(f"{pre} {c.full_text()}".strip())
        return "\n".join(x for x in out if x)

    def walk(self):
        for c in self.children:
            yield c
            yield from c.walk()


# =============================================================================
# 3. Tách vùng: header | body | appendix | footer
# =============================================================================
def segment(lines: List[str]) -> Dict[str, Any]:
    body_start = None
    for i, l in enumerate(lines):
        if _hit_structural(l) or RX_ENACT.match(l):
            body_start = i + (1 if RX_ENACT.match(l) else 0)
            if RX_ENACT.match(l):
                continue
            break
    if body_start is None:
        body_start = len(lines)

    app_start = None
    for i in range(body_start, len(lines)):
        if RX_APPENDIX.match(lines[i]) or RX_ATTACHMENT_HEADING.match(lines[i]):
            app_start = i
            break

    foot_start = None
    end = app_start if app_start is not None else len(lines)
    for i in range(body_start, end):
        if RX_NOI_NHAN.match(lines[i]) or re.match(
                r"^(TM\.|KT\.|CHỦ TỊCH|THỦ TƯỚNG|BỘ TRƯỞNG|THỨ TRƯỞNG|PHÓ)", lines[i]):
            foot_start = i
            break

    if foot_start is not None and app_start is None:
        for i in range(foot_start + 1, len(lines)):
            if RX_APPENDIX.match(lines[i]) or RX_ATTACHMENT_HEADING.match(lines[i]):
                app_start = i
                break

    body_end = min(x for x in [foot_start, app_start, len(lines)] if x is not None)
    return {
        "header": lines[:body_start],
        "body": lines[body_start:body_end],
        "footer": lines[foot_start:app_start if app_start else len(lines)] if foot_start else [],
        "appendix": lines[app_start:] if app_start is not None else [],
    }


# =============================================================================
# 4. Parse header
# =============================================================================
_TYPE_CANON = {t.upper(): t for t in DOC_TYPES}


def _canon_type(l: str) -> str:
    return _TYPE_CANON.get(l.strip().upper(), l.strip().capitalize())


def parse_header(hlines: List[str]) -> Dict[str, Any]:
    h: Dict[str, Any] = {"co_quan_ban_hanh": None, "so_ky_hieu": None,
                         "dia_danh": None, "ngay_ban_hanh": None,
                         "loai_van_ban": None, "trich_yeu": None,
                         "can_cu": [], "quoc_hieu": False}
    trich = []
    seen_type = False
    for i, l in enumerate(hlines):
        if RX_QUOC_HIEU.search(l):
            h["quoc_hieu"] = True
            continue
        if h["co_quan_ban_hanh"] is None and i < 4 and l.isupper() \
                and not RX_QUOC_HIEU.search(l) and len(l) > 4 \
                and not RX_DOC_TYPE_LINE.match(l):
            h["co_quan_ban_hanh"] = l.strip("-– ")
            continue
        m = RX_DIA_DANH_NGAY.match(l)
        if m:
            h["dia_danh"] = m.group(1).strip()
            h["ngay_ban_hanh"] = f"{int(m.group(4)):04d}-{int(m.group(3)):02d}-{int(m.group(2)):02d}"
            continue
        if h["so_ky_hieu"] is None:
            m = RX_SO_LUAT.search(l) or RX_SO_KY_HIEU.search(l)
            if m and "/" in m.group(1):
                h["so_ky_hieu"] = m.group(1).rstrip(".,;")
                continue
        if RX_DOC_TYPE_LINE.match(l):
            h["loai_van_ban"] = _canon_type(l)
            seen_type = True
            continue
        if RX_CAN_CU.match(l):
            h["can_cu"].append(l.rstrip(";,."))
            continue
        if seen_type and not RX_CAN_CU.match(l) and len(l) > 3 \
                and not re.match(r"^(Quốc hội|Chính phủ|Bộ trưởng|Thủ tướng)\b.*ban hành", l, re.I):
            trich.append(l)
    if trich:
        h["trich_yeu"] = normalize(" ".join(trich[:3]))
    if h["ngay_ban_hanh"] is None:
        for l in hlines:
            m = RX_NGAY.search(l)
            if m:
                h["ngay_ban_hanh"] = f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
                break
    return h


def _parse_metadata_date(value) -> Optional[str]:
    if value is None:
        return None
    s = normalize(str(value))
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    m = RX_NGAY_SLASH.search(s)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _clean_metadata_text(value) -> Optional[str]:
    if value is None:
        return None
    s = normalize(str(value))
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    return s


def _clean_signer(value) -> Optional[str]:
    s = _clean_metadata_text(value)
    if not s:
        return None
    return s.split(":", 1)[0].strip()


def apply_metadata(header: Dict[str, Any], metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not metadata:
        return header
    out = dict(header)
    mapping = {
        "document_number": "so_ky_hieu",
        "legal_type": "loai_van_ban",
        "issuing_authority": "co_quan_ban_hanh",
        "title": "trich_yeu",
        "legal_sectors": "linh_vuc",
    }
    for src, dst in mapping.items():
        value = _clean_metadata_text(metadata.get(src))
        if value:
            out[dst] = value
    date_value = _parse_metadata_date(metadata.get("issuance_date"))
    if date_value:
        out["ngay_ban_hanh"] = date_value
    return out


# =============================================================================
# 5. Parse body -> cây
# =============================================================================
FOOTNOTE = re.compile(r"^_{3,}$|^\d+\s+(Khoản|Điều|Điểm|Chương|Mục)\s+này được")
QUOTE_CHARS_OPEN = "“\""
QUOTE_CHARS_CLOSE = "”\""
RX_AMEND_INTRO_LINE = re.compile(r"\b(sửa đổi|bổ sung|bãi bỏ|thay thế|hủy bỏ).{0,120}như sau\s*:?\s*$", re.I)
RX_AMEND_HEADING_LINE = re.compile(r"\b(sửa đổi|bổ sung|bãi bỏ|thay thế|hủy bỏ)\b", re.I)


def _strip_leading_quotes(line: str) -> str:
    return line.lstrip("“”\"' ")


INLINE_DIEM = re.compile(rf"\s([{DIEM_LETTERS}]\d?)\)\s*(?:\[\d+\])?\s+")


def _split_inline_diem(text: str) -> tuple[str, List[tuple[str, str]]]:
    matches = []
    for m in INLINE_DIEM.finditer(text):
        prefix = text[:m.start()].rstrip()
        if not prefix:
            continue
        if re.search(r"\bđiểm$", prefix, re.I):
            continue
        matches.append(m)
    if not matches:
        return text, []

    head = text[:matches[0].start()].strip()
    items = []
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        items.append((m.group(1), text[m.end():end].strip()))
    return head, [(num, body) for num, body in items if body]


def parse_body(blines: List[str]) -> tuple[Node, List[Dict[str, Any]], Dict[int, Node]]:
    root = Node("root")
    stack = [root]
    footnotes = []
    line_owner: Dict[int, Node] = {}
    quote_open = False
    quote_id = 0
    quote_intro_active = False

    def push(n: Node):
        if n.source_context == "quoted_target":
            while (stack[-1].level != "root"
                   and stack[-1].source_context == "quoted_target"
                   and stack[-1].quote_id == n.quote_id
                   and RANK[stack[-1].level] >= RANK[n.level]):
                stack.pop()
        else:
            while stack[-1].source_context == "quoted_target":
                stack.pop()
            while RANK[stack[-1].level] >= RANK[n.level]:
                stack.pop()
        n.parent = stack[-1]
        stack[-1].children.append(n)
        stack.append(n)
        line_owner[n.line_start] = n

    def advance_quote_state(current_line: str):
        nonlocal quote_open, quote_intro_active
        open_curly = current_line.count("“")
        close_curly = current_line.count("”")
        straight = current_line.count('"')
        if open_curly and not close_curly:
            quote_open = True
        elif close_curly and not open_curly:
            if quote_open:
                quote_open = False
                quote_intro_active = False
                while stack[-1].source_context == "quoted_target":
                    stack.pop()
            elif quote_intro_active:
                quote_intro_active = False
        elif straight % 2 == 1:
            quote_open = not quote_open
            if not quote_open:
                quote_intro_active = False
                while stack[-1].source_context == "quoted_target":
                    stack.pop()

    def activate_quote_intro():
        nonlocal quote_intro_active, quote_id
        quote_intro_active = True
        quote_id += 1

    i = 0
    while i < len(blines):
        line = blines[i]
        starts_quote = line[:1] in QUOTE_CHARS_OPEN
        line_clean = _strip_leading_quotes(line)
        preliminary_hit = _hit_structural(line_clean)
        list_hit_for_intro = (
            RX["decimal_item"].match(line_clean)
            or RX["khoan"].match(line_clean)
            or RX["diem"].match(line_clean)
            or RX["tiet"].match(line_clean)
        )
        is_amend_intro = bool(RX_AMEND_INTRO_LINE.search(line_clean))
        is_own_amend_heading = bool(
            (preliminary_hit or list_hit_for_intro)
            and not starts_quote
            and not quote_open
            and not quote_intro_active
            and RX_AMEND_HEADING_LINE.search(line_clean)
        )
        is_own_doc_article = bool(
            preliminary_hit
            and preliminary_hit[0] == "dieu"
            and not starts_quote
            and not quote_open
            and not quote_intro_active
        )
        if is_own_amend_heading or is_own_doc_article:
            quote_open = False
            quote_intro_active = False
            while stack[-1].source_context == "quoted_target":
                stack.pop()
        line_quote_id = quote_id
        line_is_quoted = starts_quote or (
            (quote_open or quote_intro_active) and not is_own_amend_heading and not is_own_doc_article
        )
        if starts_quote and not quote_open:
            if not quote_intro_active:
                quote_id += 1
            line_quote_id = quote_id
        elif quote_intro_active and not quote_open and line_is_quoted:
            if not line_quote_id:
                quote_id += 1
                line_quote_id = quote_id
        if FOOTNOTE.match(line):          # ghi chú VBHN
            footnotes.append({"ord": i, "raw_text": line})
            advance_quote_state(line)
            i += 1
            continue

        structural_line = line_clean if line_is_quoted else line
        hit = preliminary_hit if structural_line == line_clean else _hit_structural(structural_line)
        if hit:
            lvl, num, rest = hit
            n = Node(
                lvl,
                num,
                heading=rest if lvl == "dieu" else "",
                line_start=i,
                source_context="quoted_target" if line_is_quoted else "own",
                quote_id=line_quote_id if line_is_quoted else None,
            )
            if lvl != "dieu" and not rest and i + 1 < len(blines):
                nxt = blines[i + 1]
                if not _hit_structural(nxt) and not RX["decimal_item"].match(nxt) and not RX["khoan"].match(nxt):
                    n.heading = nxt
                    n.line_end = i + 1
                    i += 1
            push(n)
            line_owner[n.line_end] = n
            if not line_is_quoted and is_amend_intro:
                activate_quote_intro()
            advance_quote_state(line)
            i += 1
            continue

        cur = RANK[stack[-1].level]
        if cur >= RANK["dieu"]:
            mt = RX["tiet"].match(structural_line)
            md = RX["diem"].match(structural_line)
            mx = RX["decimal_item"].match(structural_line)
            mk = RX["khoan"].match(structural_line)
            if mx:
                num = mx.group(1)
                lvl = "sub_khoan" if num.count(".") == 1 else "sub_sub_khoan"
                head, inline_diems = _split_inline_diem(normalize(mx.group(2)))
                push(Node(lvl, num, text=head, line_start=i,
                          source_context="quoted_target" if line_is_quoted else "own",
                          quote_id=line_quote_id if line_is_quoted else None))
                for diem_num, diem_text in inline_diems:
                    push(Node("diem", diem_num, text=normalize(diem_text), line_start=i,
                              source_context="quoted_target" if line_is_quoted else "own",
                              quote_id=line_quote_id if line_is_quoted else None))
                    line_owner[i] = stack[-1]
                if not line_is_quoted and is_amend_intro:
                    activate_quote_intro()
                advance_quote_state(line)
                i += 1
                continue
            if mt and cur >= RANK["dieu"]:
                par = stack[-1]
                while (RANK[par.level] >= RANK["tiet"]
                       and par.source_context == ("quoted_target" if line_is_quoted else "own")):
                    par = par.parent
                seq = sum(1 for c in par.children if c.level == "tiet") + 1
                push(Node("tiet", str(seq), text=normalize(mt.group(1)), line_start=i,
                          source_context="quoted_target" if line_is_quoted else "own",
                          quote_id=line_quote_id if line_is_quoted else None))
                if not line_is_quoted and is_amend_intro:
                    activate_quote_intro()
                advance_quote_state(line)
                i += 1
                continue
            if md and cur >= RANK["dieu"]:
                head, inline_diems = _split_inline_diem(normalize(md.group(2)))
                push(Node("diem", md.group(1), text=head, line_start=i,
                          source_context="quoted_target" if line_is_quoted else "own",
                          quote_id=line_quote_id if line_is_quoted else None))
                for diem_num, diem_text in inline_diems:
                    push(Node("diem", diem_num, text=normalize(diem_text), line_start=i,
                              source_context="quoted_target" if line_is_quoted else "own",
                              quote_id=line_quote_id if line_is_quoted else None))
                    line_owner[i] = stack[-1]
                if not line_is_quoted and is_amend_intro:
                    activate_quote_intro()
                advance_quote_state(line)
                i += 1
                continue
            if mk:
                # VBHN: "2.1 Chứng từ..." -> số khoản 2, chú thích 1
                num = re.sub(r"(\d+)\.\d+$", r"\1", mk.group(1))
                head, inline_diems = _split_inline_diem(normalize(mk.group(2)))
                push(Node("khoan", num, text=head, line_start=i,
                          source_context="quoted_target" if line_is_quoted else "own",
                          quote_id=line_quote_id if line_is_quoted else None))
                for diem_num, diem_text in inline_diems:
                    push(Node("diem", diem_num, text=normalize(diem_text), line_start=i,
                              source_context="quoted_target" if line_is_quoted else "own",
                              quote_id=line_quote_id if line_is_quoted else None))
                    line_owner[i] = stack[-1]
                if not line_is_quoted and is_amend_intro:
                    activate_quote_intro()
                advance_quote_state(line)
                i += 1
                continue

        node = stack[-1]
        if node.level in {"dieu", "khoan", "sub_khoan", "sub_sub_khoan"}:
            head, inline_diems = _split_inline_diem(normalize(structural_line))
            if head and len(inline_diems) >= 2:
                node.text = (node.text + " " + head).strip() if node.text else head
                if node.level != "root":
                    node.line_end = i
                    line_owner[i] = node
                for diem_num, diem_text in inline_diems:
                    push(Node("diem", diem_num, text=normalize(diem_text), line_start=i,
                              source_context="quoted_target" if line_is_quoted else "own",
                              quote_id=line_quote_id if line_is_quoted else None))
                    line_owner[i] = stack[-1]
                if line_is_quoted and starts_quote and not preliminary_hit and "”" in line:
                    quote_intro_active = False
                if not line_is_quoted and is_amend_intro:
                    activate_quote_intro()
                advance_quote_state(line)
                i += 1
                continue

        node.text = (node.text + " " + line).strip() if node.text else line
        if node.level != "root":
            node.line_end = i
            line_owner[i] = node
        if line_is_quoted and starts_quote and not preliminary_hit and "”" in line:
            quote_intro_active = False
        if not line_is_quoted and is_amend_intro:
            activate_quote_intro()
        advance_quote_state(line)
        i += 1
    for n in root.walk():
        if n.line_end < n.line_start:
            n.line_end = n.line_start
    return root, footnotes, line_owner


# =============================================================================
# 6. Trích xuất facts
# =============================================================================
def extract_citations(text: str) -> List[Dict[str, Any]]:
    out = []
    for m in RX_DOC_REF.finditer(text):
        out.append({"kind": "doc", "so_ky_hieu": m.group(1),
                    "raw": m.group(0), "span": m.span()})
    for m in RX_PROV_REF.finditer(text):
        if not any(m.groups()):
            continue
        out.append({"kind": "provision", "diem": m.group(1),
                    "khoan": m.group(2), "dieu": m.group(3),
                    "raw": m.group(0), "span": m.span()})
    return out


AMEND_MAP = {"sửa đổi": "AMEND", "sửa đổi, bổ sung": "AMEND", "bổ sung": "ADD",
             "bãi bỏ": "REPEAL", "thay thế": "REPLACE", "hủy bỏ": "REPEAL",
             "hết hiệu lực": "EXPIRE", "ngưng hiệu lực": "SUSPEND"}


def extract_amendments(text: str) -> List[Dict[str, Any]]:
    ops, last_end = [], -1
    self_ref_effect = re.compile(
        "(?:Lu\u1eadt|Ngh\u1ecb \u0111\u1ecbnh|Ngh\u1ecb quy\u1ebft|"
        "Quy\u1ebft \u0111\u1ecbnh|Th\u00f4ng t\u01b0|Ph\u00e1p l\u1ec7nh)"
        "\\s+n\u00e0y\\s+(?:c\u00f3 hi\u1ec7u l\u1ef1c|\u0111\u01b0\u1ee3c th\u00f4ng qua)",
        re.I,
    )
    for m in RX_AMEND.finditer(text):
        if m.start() < last_end:
            continue
        last_end = m.end()
        verb = m.group(1).lower()
        win = text[m.end(): m.end() + 220]
        op = AMEND_MAP.get(verb, "OTHER")
        same_clause = re.split(r"[.;\n]", win, maxsplit=1)[0]
        doc = RX_DOC_REF.search(win)
        prov_win = win if doc else same_clause
        prov = RX_PROV_REF.search(prov_win)
        evidence_start = m.start()
        self_ref_match = op in {"EXPIRE", "SUSPEND"} and self_ref_effect.search(win[:100])
        if self_ref_match:
            tail_start = len(same_clause)
            while tail_start < len(win) and win[tail_start] in ".;\n \t":
                tail_start += 1
            target_is_list_doc = doc and doc.start() >= tail_start and re.match(r"\d+\.", win[tail_start:]) and not RX_AMEND.search(win[tail_start:doc.start()])
            if target_is_list_doc:
                evidence_start = m.end() + tail_start
                trimmed_clause = re.split(r"[.;\n]", win[tail_start:], maxsplit=1)[0]
                if self_ref_effect.search(win[tail_start:]) and not RX_DOC_REF.search(trimmed_clause):
                    evidence_start = m.end() + doc.start()
            elif not same_clause.rstrip().endswith(":"):
                continue
        if not doc and not prov:
            continue
        quoted = re.search(r'"([^"]{5,2000})"', win, re.S)
        ops.append({
            "op": op,
            "verb": verb,
            "target_doc": doc.group(1) if doc else None,
            "target_dieu": prov.group(3) if prov else None,
            "target_khoan": prov.group(2) if prov else None,
            "target_diem": prov.group(1) if prov else None,
            "replacement_text": normalize(quoted.group(1)) if quoted else None,
            "evidence_text": normalize(text[evidence_start: m.end() + len(win)]),
            "span": (evidence_start, m.end() + len(win)),
        })
    return ops


def parse_preamble(hlines: List[str]) -> List[Dict[str, Any]]:
    items = []
    for i, l in enumerate(hlines):
        if not RX_CAN_CU.match(l):
            continue
        if re.match(r"^Thực hiện\b", l, re.I) and l.upper() == l and not RX_DOC_REF.search(l) and not RX_NGAY.search(l):
            continue
        item_type = "legal_basis"
        if re.match(r"^(Theo đề nghị|Xét đề nghị)\b", l, re.I):
            item_type = "proposal"
        ref = RX_DOC_REF.search(l)
        items.append({
            "item_type": item_type,
            "ord": i,
            "raw_text": l.rstrip(";,"),
            "target_so_ky_hieu": ref.group(1) if ref else None,
            "span": None,
        })

    for i, l in enumerate(hlines):
        if RX_PROMULGATION_FORMULA.match(l):
            items.append({
                "item_type": "promulgation_formula",
                "ord": i,
                "raw_text": l.rstrip(";,"),
                "target_so_ky_hieu": None,
                "span": None,
            })
    return sorted(items, key=lambda x: (x["ord"], x["item_type"]))


def make_document_parts(doc_id: str, header: Dict[str, Any], seg: Dict[str, Any]) -> List[Dict[str, Any]]:
    parts = [{
        "part_id": f"{doc_id}:main",
        "doc_id": doc_id,
        "parent_part_id": None,
        "part_type": "main",
        "title": header.get("trich_yeu"),
        "attachment_label": None,
        "path_prefix": "main",
        "starts_at_ord": 0,
        "ends_at_ord": len(seg["body"]) - 1 if seg["body"] else None,
        "raw_heading": None,
    }]
    if seg["appendix"]:
        parts.append({
            "part_id": f"{doc_id}:appendix:1",
            "doc_id": doc_id,
            "parent_part_id": f"{doc_id}:main",
            "part_type": "appendix",
            "title": seg["appendix"][0],
            "attachment_label": None,
            "path_prefix": "app.i",
            "starts_at_ord": 0,
            "ends_at_ord": len(seg["appendix"]) - 1,
            "raw_heading": seg["appendix"][0],
        })
    return parts


def _split_markdown_row(line: str) -> List[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [normalize(cell) for cell in raw.split("|")]


def _is_table_separator(cells: List[str]) -> bool:
    if not cells:
        return False
    return all(not cell or re.fullmatch(r":?-{2,}:?", cell.strip()) for cell in cells)


def _is_empty_table_row(cells: List[str]) -> bool:
    return not any(cell.strip() for cell in cells)


def parse_markdown_tables(lines: List[str]) -> Dict[int, Dict[str, Any]]:
    tables: Dict[int, Dict[str, Any]] = {}
    i = 0
    table_no = 0
    while i < len(lines):
        if "|" not in lines[i]:
            i += 1
            continue
        start = i
        table_lines = []
        while i < len(lines) and "|" in lines[i]:
            cells = _split_markdown_row(lines[i])
            if not _is_table_separator(cells) and not _is_empty_table_row(cells):
                table_lines.append({"ord": i, "raw": lines[i], "cells": cells})
            i += 1
        if len(table_lines) < 2:
            continue
        header = table_lines[0]["cells"]
        if len(header) < 2:
            continue
        table_no += 1
        rows = []
        for row_idx, row in enumerate(table_lines[1:], 1):
            cells = list(row["cells"])
            if len(cells) < len(header):
                cells.extend([""] * (len(header) - len(cells)))
            row_map = {
                header[col_idx] if header[col_idx] else f"col_{col_idx + 1}": cells[col_idx]
                for col_idx in range(min(len(header), len(cells)))
            }
            if len(cells) > len(header):
                for extra_idx, cell in enumerate(cells[len(header):], 1):
                    row_map[f"extra_{extra_idx}"] = cell
            rows.append({
                "row_index": row_idx,
                "source_ord": row["ord"],
                "raw_text": row["raw"],
                "cells": row_map,
            })
        table = {
            "table_no": table_no,
            "start_ord": start,
            "end_ord": i - 1,
            "header": header,
            "rows": rows,
            "n_rows": len(rows),
            "n_cols": len(header),
        }
        for ord_ in range(start, i):
            tables[ord_] = table
    return tables


def parse_appendix_blocks(doc_id: str, parts: List[Dict[str, Any]], appendix: List[str]) -> List[Dict[str, Any]]:
    if not appendix:
        return []
    part_id = next((p["part_id"] for p in parts if p["part_type"] == "appendix"), f"{doc_id}:appendix:1")
    tables_by_ord = parse_markdown_tables(appendix)
    blocks = []
    for i, line in enumerate(appendix):
        table = tables_by_ord.get(i)
        block_type = "table" if table else ("layout" if "|" in line else "paragraph")
        if RX_APPENDIX.match(line):
            title = line
        else:
            title = None
        blocks.append({
            "block_id": hashlib.sha1(f"{part_id}|{i}|{line[:80]}".encode()).hexdigest()[:20],
            "part_id": part_id,
            "doc_id": doc_id,
            "block_type": block_type,
            "ord": i,
            "title": title,
            "raw_text": line,
            "structured_json": {
                "table_no": table["table_no"],
                "start_ord": table["start_ord"],
                "end_ord": table["end_ord"],
                "header": table["header"],
                "row_count": table["n_rows"],
                "col_count": table["n_cols"],
            } if table else None,
        })
    return blocks


def extract_appendix_tables(doc_id: str, parts: List[Dict[str, Any]], appendix: List[str]) -> List[Dict[str, Any]]:
    if not appendix:
        return []
    part_id = next((p["part_id"] for p in parts if p["part_type"] == "appendix"), f"{doc_id}:appendix:1")
    by_ord = parse_markdown_tables(appendix)
    seen = set()
    tables = []
    for table in by_ord.values():
        if table["table_no"] in seen:
            continue
        seen.add(table["table_no"])
        table_id = f"{part_id}:table:{table['table_no']}"
        tables.append({
            "table_id": table_id,
            "doc_id": doc_id,
            "part_id": part_id,
            "table_no": table["table_no"],
            "start_ord": table["start_ord"],
            "end_ord": table["end_ord"],
            "header": table["header"],
            "rows": table["rows"],
            "n_rows": table["n_rows"],
            "n_cols": table["n_cols"],
        })
    return tables


def _edge(relation_type: str, src_doc_id: str, source_method: str, **kw) -> Dict[str, Any]:
    out = {
        "relation_type": relation_type,
        "src_doc_id": src_doc_id,
        "src_part_id": kw.get("src_part_id"),
        "src_provision_id": kw.get("src_provision_id"),
        "target_doc_id": kw.get("target_doc_id"),
        "target_part_id": kw.get("target_part_id"),
        "target_provision_id": kw.get("target_provision_id"),
        "target_so_ky_hieu": kw.get("target_so_ky_hieu"),
        "target_dieu": kw.get("target_dieu"),
        "target_khoan": kw.get("target_khoan"),
        "target_diem": kw.get("target_diem"),
        "evidence_text": kw.get("evidence_text"),
        "evidence_span": kw.get("evidence_span"),
        "source_method": source_method,
        "confidence": kw.get("confidence", 1.0),
        "resolved": kw.get("resolved", False),
        "effective_date": kw.get("effective_date"),
    }
    return out


def build_document_edges(doc_id: str, preamble_items: List[Dict[str, Any]],
                         provisions: List[Dict[str, Any]], parts: List[Dict[str, Any]],
                         facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    main_part_id = f"{doc_id}:main"
    edges = []
    for item in preamble_items:
        if item["item_type"] == "legal_basis":
            edges.append(_edge(
                "LEGAL_BASIS", doc_id, "legal_basis",
                src_part_id=main_part_id,
                target_so_ky_hieu=item.get("target_so_ky_hieu"),
                evidence_text=item["raw_text"],
                confidence=1.0 if item.get("target_so_ky_hieu") else 0.8,
            ))

    for p in provisions:
        pid = p["provision_id"]
        text = p["text_full"] or p["text"] or ""
        if not text:
            continue
        for c in extract_citations(text):
            rel = "INLINE_CITATION" if c["kind"] == "doc" else "INTERNAL_REFERENCE"
            edges.append(_edge(
                rel, doc_id, "inline_citation",
                src_part_id=p.get("part_id"), src_provision_id=pid,
                target_so_ky_hieu=c.get("so_ky_hieu"),
                target_dieu=c.get("dieu"), target_khoan=c.get("khoan"),
                target_diem=c.get("diem"), evidence_text=c.get("raw"),
                evidence_span=c.get("span"),
            ))
        for a in extract_amendments(text):
            rel = {"AMEND": "AMENDS", "ADD": "ADDS", "REPEAL": "REPEALS",
                   "REPLACE": "REPLACES", "EXPIRE": "EXPIRES",
                   "SUSPEND": "SUSPENDS"}.get(a["op"], "AMENDS")
            edges.append(_edge(
                rel, doc_id, "amendment_clause",
                src_part_id=p.get("part_id"), src_provision_id=pid,
                target_so_ky_hieu=a.get("target_doc"),
                target_dieu=a.get("target_dieu"), target_khoan=a.get("target_khoan"),
                target_diem=a.get("target_diem"), evidence_text=a.get("evidence_text"),
                evidence_span=a.get("span"),
                effective_date=next((e["date"] for e in facts["effective"]
                                     if e["kind"] == "EFFECTIVE" and e["date"]), None),
            ))

    for p in parts:
        if p["part_type"] == "appendix":
            edges.append(_edge(
                "ATTACHED_TO", doc_id, "attached_document",
                src_part_id=p["part_id"], target_part_id=p["parent_part_id"],
                evidence_text=p.get("raw_heading"), confidence=1.0,
            ))
    seen = set()
    deduped = []
    for e in edges:
        key = (e["relation_type"], e.get("src_provision_id"), e.get("src_part_id"),
               e.get("target_so_ky_hieu"), e.get("target_dieu"),
               e.get("target_khoan"), e.get("target_diem"),
               e.get("target_part_id"), e.get("evidence_text"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


def build_semantic_signals(doc_id: str, facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for d in facts["definitions"]:
        out.append({
            "doc_id": doc_id,
            "provision_id": f"{doc_id}:{d['at']}",
            "signal_type": "term",
            "value": d["term"],
            "value_norm": normalize(d["term"]).lower(),
            "evidence_text": d["definition"],
            "evidence_span": None,
            "confidence": 1.0,
            "source_method": "definition_clause",
        })
    for e in facts["effective"]:
        out.append({
            "doc_id": doc_id,
            "provision_id": f"{doc_id}:{e['at']}",
            "signal_type": "effective_rule",
            "value": e["date"] or e["raw"],
            "value_norm": e["date"] or normalize(e["raw"]).lower(),
            "evidence_text": e["raw"],
            "evidence_span": None,
            "confidence": 0.9 if e["date"] else 0.6,
            "source_method": "effective_clause",
        })
    return out


def build_parse_coverage(doc_id: str, source_lines: List[Dict[str, Any]],
                         body_lines: List[str], line_owner: Dict[int, Node],
                         footnotes: List[Dict[str, Any]],
                         provisions: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    provision_by_path = {p["path"]: p for p in provisions}
    footnote_ords = {f["ord"] for f in footnotes}
    body_cursor = 0
    coverage = []

    for rec in source_lines:
        section = rec.get("section")
        status = section or "unknown"
        provision_id = None
        reason = None

        if rec["is_blank"]:
            status = "blank"
            reason = "blank_line"
        elif section == "body":
            body_ord = body_cursor
            body_cursor += 1
            if body_ord in footnote_ords:
                status = "footnote"
                reason = "excluded_from_legal_tree_but_preserved"
            elif body_ord in line_owner:
                node = line_owner[body_ord]
                status = "parsed"
                reason = node.level
                provision = provision_by_path.get(node.path)
                provision_id = provision["provision_id"] if provision else f"{doc_id}:{node.path}"
            else:
                status = "orphan"
                reason = "body_line_not_attached_to_provision"
        elif section in ("header", "footer", "appendix"):
            reason = f"{section}_section"
        else:
            status = "unknown"
            reason = "unclassified_line"

        coverage.append({
            "doc_id": doc_id,
            "line_no": rec["line_no"],
            "section": section,
            "status": status,
            "provision_id": provision_id,
            "reason": reason,
            "raw_text": rec["raw_text"],
        })

    n_lines = sum(1 for r in coverage if r["status"] != "blank")
    n_body = sum(1 for r in coverage if r["section"] == "body" and r["status"] != "blank")
    n_parsed = sum(1 for r in coverage if r["status"] == "parsed")
    n_orphan = sum(1 for r in coverage if r["status"] == "orphan")
    n_footnote = sum(1 for r in coverage if r["status"] == "footnote")
    covered_body = n_parsed + n_footnote
    ratio = covered_body / n_body if n_body else 1.0
    quality = {
        "doc_id": doc_id,
        "n_lines": n_lines,
        "n_body_lines": n_body,
        "n_parsed_body_lines": n_parsed,
        "n_orphan_body_lines": n_orphan,
        "n_footnote_lines": n_footnote,
        "coverage_ratio": ratio,
        "parse_status": "ok" if ratio >= 0.98 and n_orphan == 0 else "warning",
    }
    return coverage, quality


def classify_legal_role(level: str, heading: Optional[str], text: str) -> Optional[str]:
    if level != "dieu":
        return None
    hay = normalize(" ".join(filter(None, [heading or "", text]))).lower()
    if "giải thích từ ngữ" in hay:
        return "definition"
    if "hiệu lực" in hay:
        return "effective"
    if "chuyển tiếp" in hay:
        return "transition"
    if "trách nhiệm" in hay and "thi hành" in hay:
        return "implementation"
    if "phạm vi điều chỉnh" in hay:
        return "scope"
    if "đối tượng áp dụng" in hay:
        return "subject"
    if RX_AMEND.search(hay):
        return "amendment"
    return None


def extract_definitions(root: Node) -> List[Dict[str, str]]:
    defs = []
    for n in root.walk():
        d = n
        while d and d.level != "dieu":
            d = d.parent
        if not d or "giải thích từ ngữ" not in (d.heading or "").lower():
            continue
        if n.level not in ("khoan", "diem"):
            continue
        m = RX_DEF.match(n.text)
        if m and len(m.group(1)) < 90:
            defs.append({"term": m.group(1).strip(),
                         "definition": m.group(2).strip().rstrip(".;:"),
                         "at": n.path})
    return defs


def extract_effective(root: Node) -> List[Dict[str, Any]]:
    out = []
    for n in root.walk():
        if n.level not in ("dieu", "khoan"):
            continue
        t = n.full_text()
        m = RX_HIEU_LUC.search(t)
        if not m:
            continue
        tail = m.group(2)
        d = RX_NGAY.search(tail) or RX_NGAY_SLASH.search(tail)
        iso = None
        if d:
            g = d.groups()
            iso = f"{int(g[2]):04d}-{int(g[1]):02d}-{int(g[0]):02d}"
        out.append({"kind": "EFFECTIVE" if "có hiệu lực" in m.group(1).lower()
                    else "EXPIRE", "date": iso, "at": n.path,
                    "raw": normalize(tail)[:120]})
    return out


# =============================================================================
# 7. API chính
# =============================================================================
def parse_document(text: str, doc_id: str = "", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source_lines = to_source_lines(text)
    lines = to_lines(text)
    normalized_text = "\n".join(lines)
    seg = segment(lines)
    assign_line_sections(source_lines, seg)
    header = apply_metadata(parse_header(seg["header"]), metadata)
    preamble_items = parse_preamble(seg["header"])
    document_parts = make_document_parts(doc_id, header, seg)
    main_part_id = f"{doc_id}:main"
    root, footnotes, line_owner = parse_body(seg["body"])
    body_text = "\n".join(seg["body"])

    signer = None
    chuc_danh = None
    if seg["footer"]:
        cand = [l for l in seg["footer"] if not RX_NOI_NHAN.match(l)
                and not l.startswith("-")]
        for j, l in enumerate(cand):
            if l.isupper() and len(l) > 3:
                chuc_danh = l
            elif chuc_danh and not l.isupper():
                signer = l
                break
    metadata_signer = _clean_signer(metadata.get("signers")) if metadata else None
    if metadata_signer:
        signer = metadata_signer

    provisions = []
    path_counts: Dict[str, int] = {}
    unique_path_by_node: Dict[int, str] = {}
    for n in root.walk():
        legal_role = classify_legal_role(n.level, n.heading, n.text)
        legal_path = n.path
        source_context = n.source_context or "own"
        quote_id = n.quote_id
        parent_path = None
        parent_same_context = False
        if n.parent and n.parent.level != "root":
            parent_path = unique_path_by_node.get(id(n.parent), n.parent.path)
            parent_same_context = (
                (n.parent.source_context or "own") == source_context
                and n.parent.quote_id == quote_id
            )
        if parent_same_context and parent_path:
            storage_base_path = f"{parent_path}.{_node_segment(n)}"
        else:
            storage_base_path = f"q{quote_id}.{legal_path}" if source_context == "quoted_target" and quote_id else legal_path
        path_counts[storage_base_path] = path_counts.get(storage_base_path, 0) + 1
        path = storage_base_path if path_counts[storage_base_path] == 1 else f"{storage_base_path}.occ{path_counts[storage_base_path]}"
        unique_path_by_node[id(n)] = path
        if source_context == "quoted_target":
            legal_role = "quoted_target"
        provisions.append({
            "doc_id": doc_id,
            "provision_id": f"{doc_id}:{path}",
            "part_id": main_part_id,
            "path": path,
            "legal_path": legal_path,
            "source_context": source_context,
            "quote_id": quote_id,
            "level": n.level,
            "legal_role": legal_role,
            "number": n.number,
            "heading": n.heading or None,
            "breadcrumb": n.breadcrumb,
            "parent_path": parent_path,
            "depth": RANK[n.level],
            "line_start": n.line_start,
            "line_end": n.line_end,
            "text": n.text,
            "text_full": n.full_text(),
            "n_children": len(n.children),
        })

    facts = {
        "citations": extract_citations(body_text),
        "amendments": extract_amendments(body_text),
        "definitions": extract_definitions(root),
        "effective": extract_effective(root),
    }
    appendix_blocks = parse_appendix_blocks(doc_id, document_parts, seg["appendix"])
    appendix_tables = extract_appendix_tables(doc_id, document_parts, seg["appendix"])
    document_edges = build_document_edges(doc_id, preamble_items, provisions,
                                          document_parts, facts)
    semantic_signals = build_semantic_signals(doc_id, facts)
    parse_coverage, parse_quality = build_parse_coverage(
        doc_id, source_lines, seg["body"], line_owner, footnotes, provisions
    )
    metadata_hash = hashlib.sha256(json.dumps({
        "header": header,
        "metadata": metadata or {},
        "signer": signer,
        "chuc_danh": chuc_danh,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    return {
        "doc_id": doc_id,
        "metadata_hash": metadata_hash,
        "content_hash": content_hash,
        "raw_text": text,
        "normalized_text": normalized_text,
        "source_lines": source_lines,
        "document_blocks": [
            {
                "block_id": f"{doc_id}:{section}",
                "doc_id": doc_id,
                "part_id": main_part_id if section != "appendix" else next(
                    (p["part_id"] for p in document_parts if p["part_type"] == "appendix"),
                    None,
                ),
                "block_type": section,
                "ord": ord_,
                "raw_text": "\n".join(
                    r["raw_text"] for r in source_lines if r["section"] == section
                ),
                "normalized_text": "\n".join(seg.get(section, [])),
            }
            for ord_, section in enumerate(("header", "body", "footer", "appendix"))
            if seg.get(section)
        ],
        "header": header,
        "document_parts": document_parts,
        "preamble_items": preamble_items,
        "signer": signer,
        "chuc_danh": chuc_danh,
        "tree": root,
        "provisions": provisions,
        "appendix": seg["appendix"],
        "appendix_blocks": appendix_blocks,
        "appendix_tables": appendix_tables,
        "footnotes": footnotes,
        "parse_coverage": parse_coverage,
        "parse_quality": parse_quality,
        "facts": facts,
        "document_edges": document_edges,
        "semantic_signals": semantic_signals,
        "stats": {
            "n_lines": len(lines),
            "n_header": len(seg["header"]),
            "n_body": len(seg["body"]),
            "n_appendix": len(seg["appendix"]),
            "n_dieu": sum(1 for p in provisions if p["level"] == "dieu"),
            "n_roman_section": sum(1 for p in provisions if p["level"] == "roman_section"),
            "n_khoan": sum(1 for p in provisions if p["level"] == "khoan"),
            "n_diem": sum(1 for p in provisions if p["level"] == "diem"),
            "n_chuong": sum(1 for p in provisions if p["level"] == "chuong"),
            "orphan_lines": sum(1 for p in provisions
                                if p["level"] == "root"),
        },
    }


# =============================================================================
# 8. Chunking cho vector DB
# =============================================================================
def _split_chunk_text(text: str, max_chars: int) -> List[str]:
    text = normalize(text)
    if not text or len(text) <= max_chars:
        return [text] if text else []

    parts: List[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf.strip():
            parts.append(buf.strip())
        buf = ""

    blocks = [b.strip() for b in re.split(r"\n+", text) if b.strip()] or [text]
    for block in blocks:
        if len(block) > max_chars:
            sentences = re.split(r"(?<=[.;:!?])\s+", block)
        else:
            sentences = [block]
        for sent in sentences:
            while len(sent) > max_chars:
                if buf:
                    flush()
                parts.append(sent[:max_chars].strip())
                sent = sent[max_chars:].strip()
            candidate = f"{buf}\n{sent}".strip() if buf else sent
            if len(candidate) > max_chars:
                flush()
                buf = sent
            else:
                buf = candidate
    flush()
    return parts


def make_chunks(parsed: Dict[str, Any], max_chars: int = 2200) -> List[Dict[str, Any]]:
    """Chunk theo đơn vị pháp lý nhỏ nhất có thể đọc độc lập.
    Node lá dùng text_full; node cha có câu dẫn riêng ("bao gồm:", "như sau:")
    vẫn có chunk direct để không mất phần mở đầu của Điều/Khoản."""
    h = parsed["header"]
    doc_ctx = " | ".join(filter(None, [
        h.get("loai_van_ban"), h.get("so_ky_hieu"), h.get("trich_yeu")]))
    child_count: Dict[str, int] = {}
    for p in parsed["provisions"]:
        parent_id = p.get("parent_id")
        if parent_id:
            child_count[parent_id] = child_count.get(parent_id, 0) + 1
    chunks = []

    for p in parsed["provisions"]:
        if p["level"] in {"phan", "chuong", "muc", "tieu_muc", "roman_section"}:
            continue
        has_children = child_count.get(p["provision_id"], 0) > 0
        direct_text = normalize(p.get("text") or "")
        full_text = normalize(p.get("text_full") or direct_text)
        if has_children:
            if not direct_text:
                continue
            txt = direct_text
        else:
            txt = full_text
        if not txt:
            continue
        text_parts = _split_chunk_text(txt, max_chars)
        for idx, part_text in enumerate(text_parts, 1):
            suffix = f" [phần {idx}/{len(text_parts)}]" if len(text_parts) > 1 else ""
            citation = f"{p['breadcrumb']}{suffix}"
            ctx = f"{doc_ctx}\n{citation}"
            chunks.append({
                "chunk_id": hashlib.sha1(
                    f"{p['provision_id']}|{idx}|{part_text[:200]}".encode()).hexdigest()[:20],
                "doc_id": parsed["doc_id"],
                "part_id": p.get("part_id"),
                "provision_id": p["provision_id"],
                "path": p["path"],
                "level": p["level"],
                "citation": citation,
                "embed_text": f"{ctx}\n\n{part_text}",   # cái đem đi embed
                "raw_text": part_text,                    # cái đem đi hiển thị
                "n_chars": len(part_text),
            })
    return chunks
