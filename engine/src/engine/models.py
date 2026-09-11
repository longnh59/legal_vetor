"""Pydantic schemas shared across pipeline stages (PLAN_v2 section 4)."""

from typing import Literal

from pydantic import BaseModel


class Block(BaseModel):
    """T2 output: one flattened DOM element, before part-split / classification."""

    text: str
    tag: str
    classes: list[str] = []
    style_indent: float | None = None
    is_bold: bool = False
    is_italic: bool = False
    is_center: bool = False
    is_table: bool = False
    html_raw: str
    dom_order: int
    anchors: list[str] = []


NodeType = Literal[
    "phan",
    "chuong",
    "muc",
    "tieu_muc",
    "dieu",
    "khoan",
    "diem",
    "gach_dau_dong",
    "preamble",
    "phu_luc",
]

ClassifiedBy = Literal["regex", "css_class", "style", "llm"]


class Node(BaseModel):
    """A node in the document tree (`nodes` table, PLAN_v2 section 4.2)."""

    node_id: str
    doc_id: str
    part_id: str
    parent_id: str | None
    path: str  # ltree-style dotted path, e.g. "p1.dieu_8.khoan_1"
    depth: int
    order_index: int
    node_type: NodeType
    number_raw: str | None = None
    number_norm: str | None = None
    heading: str | None = None
    text: str
    text_full: str
    breadcrumb: str
    html_raw: str
    confidence: float
    classified_by: ClassifiedBy


EdgeType = Literal[
    "REFERENCES",
    "AMENDS",
    "SUPPLEMENTS",
    "REPLACES",
    "REPEALS",
    "GUIDES",
    "BASED_ON",
]

EdgeSource = Literal["rule", "llm", "human", "dataset"]


class Edge(BaseModel):
    src_node_id: str
    dst_node_id: str | None = None
    dst_doc_id: str | None = None
    edge_type: EdgeType
    source: EdgeSource
    confidence: float
    evidence_text: str | None = None


class DocumentPart(BaseModel):
    """A `document_part` boundary found by T3 (PLAN_v2 section 5, T3)."""

    part_id: str
    start_block: int
    end_block: int
    heading: str | None = None
    is_main: bool
