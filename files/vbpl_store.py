# -*- coding: utf-8 -*-
"""
vbpl_store.py — Tầng lưu trữ

Mô hình 3 lớp:
  BRONZE  raw_html / raw_text  (bất biến, có content_hash → phát hiện VB sửa)
  SILVER  documents / provisions / amendments / definitions
  GOLD    chunks (+ embedding) → nạp vào vector DB

Local/analytics = DuckDB (file .duckdb, chạy Parquet trực tiếp).
Production/serving = Postgres + pgvector (DDL ở schema_postgres.sql).
"""
import json
from datetime import datetime, timezone
import hashlib
import duckdb

DDL = """
CREATE TABLE IF NOT EXISTS raw_docs (
    doc_id          VARCHAR PRIMARY KEY,
    source          VARCHAR,          -- vbpl.vn / thuvienphapluat / upload
    source_url      VARCHAR,
    fetched_at      TIMESTAMP,
    content_hash    VARCHAR,          -- sha256 body -> diff giữa 2 lần crawl
    raw_body        VARCHAR
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id          VARCHAR PRIMARY KEY,
    so_ky_hieu      VARCHAR,
    loai_van_ban    VARCHAR,
    co_quan         VARCHAR,
    dia_danh        VARCHAR,
    trich_yeu       VARCHAR,
    ngay_ban_hanh   DATE,
    ngay_hieu_luc   DATE,
    ngay_het_hieu_luc DATE,
    tinh_trang      VARCHAR,
    linh_vuc        VARCHAR,
    scope           VARCHAR,          -- trung_uong / dia_phuong
    nguoi_ky        VARCHAR,
    chuc_danh       VARCHAR,
    parser_version  VARCHAR,
    content_hash    VARCHAR
);

CREATE TABLE IF NOT EXISTS document_versions (
    doc_id          VARCHAR,
    version_no      INTEGER,
    source          VARCHAR,
    source_url      VARCHAR,
    metadata_hash   VARCHAR,
    content_hash    VARCHAR,
    seen_from       TIMESTAMP,
    seen_to         TIMESTAMP,
    is_current      BOOLEAN,
    change_status   VARCHAR,       -- NEW|META_CHANGED|CONTENT_CHANGED
    so_ky_hieu      VARCHAR,
    loai_van_ban    VARCHAR,
    co_quan         VARCHAR,
    dia_danh        VARCHAR,
    trich_yeu       VARCHAR,
    ngay_ban_hanh   DATE,
    ngay_hieu_luc   DATE,
    ngay_het_hieu_luc DATE,
    tinh_trang      VARCHAR,
    linh_vuc        VARCHAR,
    scope           VARCHAR,
    nguoi_ky        VARCHAR,
    chuc_danh       VARCHAR,
    raw_text        VARCHAR,
    PRIMARY KEY (doc_id, version_no)
);

CREATE TABLE IF NOT EXISTS ingest_ledger (
    doc_id          VARCHAR PRIMARY KEY,
    source          VARCHAR,
    source_url      VARCHAR,
    metadata_hash   VARCHAR,
    content_hash    VARCHAR,
    current_version_no INTEGER,
    last_snapshot   TIMESTAMP,
    status          VARCHAR        -- NEW|META_CHANGED|CONTENT_CHANGED|UNCHANGED|MISSING
);

CREATE TABLE IF NOT EXISTS document_parts (
    part_id          VARCHAR PRIMARY KEY,
    doc_id           VARCHAR,
    parent_part_id   VARCHAR,
    part_type        VARCHAR,       -- main|attached_document|appendix|form|table|other
    title            VARCHAR,
    attachment_label VARCHAR,
    path_prefix      VARCHAR,
    starts_at_ord    INTEGER,
    ends_at_ord      INTEGER,
    raw_heading      VARCHAR
);

CREATE TABLE IF NOT EXISTS document_lines (
    doc_id          VARCHAR,
    version_no      INTEGER,
    line_no         INTEGER,
    section         VARCHAR,       -- header|body|footer|appendix|unknown
    raw_text        VARCHAR,
    normalized_text VARCHAR,
    is_blank        BOOLEAN,
    PRIMARY KEY (doc_id, version_no, line_no)
);

CREATE TABLE IF NOT EXISTS document_blocks (
    block_id        VARCHAR,
    doc_id          VARCHAR,
    version_no      INTEGER,
    part_id         VARCHAR,
    block_type      VARCHAR,       -- header|body|footer|appendix
    ord             INTEGER,
    raw_text        VARCHAR,
    normalized_text VARCHAR,
    PRIMARY KEY (block_id, version_no)
);

CREATE TABLE IF NOT EXISTS document_outline_items (
    outline_id      VARCHAR PRIMARY KEY,
    doc_id          VARCHAR,
    version_no      INTEGER,
    section_ord     INTEGER,
    item_ord        INTEGER,
    section         VARCHAR,       -- header|preamble|body|footer|appendix
    item_type       VARCHAR,       -- block|legal_basis|proposal|formula|provision|appendix_block
    part_id         VARCHAR,
    provision_id    VARCHAR,
    parent_id       VARCHAR,
    level           VARCHAR,
    path            VARCHAR,
    legal_path      VARCHAR,
    source_context  VARCHAR,
    quote_id        INTEGER,
    number          VARCHAR,
    heading         VARCHAR,
    breadcrumb      VARCHAR,
    line_start      INTEGER,
    line_end        INTEGER,
    text            VARCHAR,
    text_full       VARCHAR
);

CREATE TABLE IF NOT EXISTS preamble_items (
    id               BIGINT,
    doc_id           VARCHAR,
    item_type        VARCHAR,       -- legal_basis|proposal|promulgation_formula|other
    ord              INTEGER,
    raw_text         VARCHAR,
    target_so_ky_hieu VARCHAR,
    resolved_doc_id  VARCHAR,
    evidence_start   INTEGER,
    evidence_end     INTEGER
);

-- 1 dòng = 1 đơn vị quy phạm. path là materialized path -> truy vấn cây bằng LIKE.
CREATE TABLE IF NOT EXISTS provisions (
    provision_id    VARCHAR PRIMARY KEY,   -- "<doc_id>:ci.d3.k2.dma"
    doc_id          VARCHAR,
    part_id         VARCHAR,
    parent_id       VARCHAR,
    path            VARCHAR,
    legal_path      VARCHAR,
    source_context  VARCHAR,
    quote_id        INTEGER,
    level           VARCHAR,               -- phan|chuong|muc|tieu_muc|dieu|khoan|diem|tiet
    legal_role      VARCHAR,
    number          VARCHAR,
    heading         VARCHAR,
    breadcrumb      VARCHAR,               -- "Chương I > Điều 3. Giải thích từ ngữ > Khoản 2"
    depth           INTEGER,
    ord             INTEGER,               -- thứ tự xuất hiện, để đọc tuần tự
    line_start      INTEGER,
    line_end        INTEGER,
    text            VARCHAR,               -- text riêng của node
    text_full       VARCHAR,               -- text + toàn bộ con (cái đem đi embed)
    valid_from      DATE,                  -- point-in-time: điều luật này có hiệu lực từ...
    valid_to        DATE                   -- ...đến khi bị sửa/bãi bỏ (NULL = còn hiệu lực)
);

CREATE TABLE IF NOT EXISTS provision_versions (
    provision_version_id VARCHAR PRIMARY KEY,
    provision_id    VARCHAR,
    doc_id          VARCHAR,
    version_no      INTEGER,
    legal_path      VARCHAR,
    source_context  VARCHAR,
    quote_id        INTEGER,
    text            VARCHAR,
    text_full       VARCHAR,
    is_current      BOOLEAN,
    effective_status VARCHAR,
    valid_from      DATE,
    valid_to        DATE,
    seen_from       TIMESTAMP,
    seen_to         TIMESTAMP
);

CREATE TABLE IF NOT EXISTS amendments (
    src_doc_id       VARCHAR,
    src_provision_id VARCHAR,
    op               VARCHAR,      -- AMEND | ADD | REPEAL | REPLACE | EXPIRE | SUSPEND
    target_so_ky_hieu VARCHAR,
    target_dieu      VARCHAR,
    target_khoan     VARCHAR,
    target_diem      VARCHAR,
    resolved_target_provision_id VARCHAR,
    effective_date   DATE,
    replacement_text VARCHAR,
    evidence_text    VARCHAR,
    evidence_start   INTEGER,
    evidence_end     INTEGER
);

CREATE TABLE IF NOT EXISTS document_edges (
    edge_id          BIGINT,
    relation_type    VARCHAR,      -- LEGAL_BASIS|INLINE_CITATION|AMENDS|GUIDES|RELATED_BY_TOPIC|...
    src_doc_id       VARCHAR,
    src_part_id      VARCHAR,
    src_provision_id VARCHAR,
    target_doc_id    VARCHAR,
    target_part_id   VARCHAR,
    target_provision_id VARCHAR,
    target_so_ky_hieu VARCHAR,
    target_dieu      VARCHAR,
    target_khoan     VARCHAR,
    target_diem      VARCHAR,
    evidence_text    VARCHAR,
    evidence_start   INTEGER,
    evidence_end     INTEGER,
    source_method    VARCHAR,
    confidence       DOUBLE,
    resolved         BOOLEAN,
    effective_date   DATE
);

CREATE TABLE IF NOT EXISTS definitions (
    doc_id           VARCHAR,
    provision_id     VARCHAR,
    term             VARCHAR,
    definition       VARCHAR
);

CREATE TABLE IF NOT EXISTS semantic_signals (
    signal_id        BIGINT,
    doc_id           VARCHAR,
    provision_id     VARCHAR,
    signal_type      VARCHAR,      -- term|topic|subject|obligation|sanction|transition|...
    value            VARCHAR,
    value_norm       VARCHAR,
    evidence_text    VARCHAR,
    evidence_start   INTEGER,
    evidence_end     INTEGER,
    confidence       DOUBLE,
    source_method    VARCHAR
);

CREATE TABLE IF NOT EXISTS appendix_blocks (
    block_id         VARCHAR PRIMARY KEY,
    part_id          VARCHAR,
    doc_id           VARCHAR,
    block_type       VARCHAR,      -- paragraph|table|form|list|formula|diagram|image|unknown
    ord              INTEGER,
    title            VARCHAR,
    raw_text         VARCHAR,
    structured_json  VARCHAR
);

CREATE TABLE IF NOT EXISTS appendix_tables (
    table_id         VARCHAR PRIMARY KEY,
    doc_id           VARCHAR,
    part_id          VARCHAR,
    table_no         INTEGER,
    start_ord        INTEGER,
    end_ord          INTEGER,
    header_json      VARCHAR,
    n_rows           INTEGER,
    n_cols           INTEGER
);

CREATE TABLE IF NOT EXISTS appendix_table_rows (
    table_id         VARCHAR,
    doc_id           VARCHAR,
    part_id          VARCHAR,
    table_no         INTEGER,
    row_index        INTEGER,
    source_ord       INTEGER,
    raw_text         VARCHAR,
    cells_json       VARCHAR,
    PRIMARY KEY (table_id, row_index)
);

CREATE TABLE IF NOT EXISTS footnotes (
    doc_id          VARCHAR,
    version_no      INTEGER,
    ord             INTEGER,
    raw_text        VARCHAR,
    PRIMARY KEY (doc_id, version_no, ord)
);

CREATE TABLE IF NOT EXISTS parse_coverage (
    doc_id          VARCHAR,
    version_no      INTEGER,
    line_no         INTEGER,
    section         VARCHAR,
    status          VARCHAR,       -- parsed|footnote|orphan|header|footer|appendix|blank|unknown
    provision_id    VARCHAR,
    reason          VARCHAR,
    raw_text        VARCHAR,
    PRIMARY KEY (doc_id, version_no, line_no)
);

CREATE TABLE IF NOT EXISTS parse_quality_reports (
    doc_id          VARCHAR,
    version_no      INTEGER,
    n_lines         INTEGER,
    n_body_lines    INTEGER,
    n_parsed_body_lines INTEGER,
    n_orphan_body_lines INTEGER,
    n_footnote_lines INTEGER,
    coverage_ratio  DOUBLE,
    parse_status    VARCHAR,
    PRIMARY KEY (doc_id, version_no)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id         VARCHAR PRIMARY KEY,
    doc_id           VARCHAR,
    part_id          VARCHAR,
    provision_id     VARCHAR,
    version_no       INTEGER,
    path             VARCHAR,
    level            VARCHAR,
    citation         VARCHAR,
    embed_text       VARCHAR,
    raw_text         VARCHAR,
    n_chars          INTEGER
);

CREATE OR REPLACE VIEW document_tree_readable AS
SELECT
    doc_id,
    version_no,
    section,
    section_ord,
    item_ord,
    item_type,
    level,
    path,
    legal_path,
    parent_id,
    source_context,
    quote_id,
    line_start,
    line_end,
    repeat('  ', greatest(coalesce(
        CASE level
          WHEN 'phan' THEN 0
          WHEN 'chuong' THEN 1
          WHEN 'muc' THEN 2
          WHEN 'tieu_muc' THEN 3
          WHEN 'dieu' THEN 4
          WHEN 'roman_section' THEN 5
          WHEN 'khoan' THEN 6
          WHEN 'sub_khoan' THEN 7
          WHEN 'sub_sub_khoan' THEN 8
          WHEN 'diem' THEN 9
          WHEN 'tiet' THEN 10
          ELSE 0
        END, 0), 0)) ||
    trim(concat_ws(' ',
        CASE level
          WHEN 'phan' THEN 'Phần'
          WHEN 'chuong' THEN 'Chương'
          WHEN 'muc' THEN 'Mục'
          WHEN 'tieu_muc' THEN 'Tiểu mục'
          WHEN 'dieu' THEN 'Điều'
          WHEN 'roman_section' THEN 'Mục'
          WHEN 'khoan' THEN 'Khoản'
          WHEN 'sub_khoan' THEN 'Tiểu khoản'
          WHEN 'sub_sub_khoan' THEN 'Tiểu khoản'
          WHEN 'diem' THEN 'Điểm'
          WHEN 'tiet' THEN 'Tiết'
          ELSE item_type
        END,
        number,
        heading
    )) AS tree_label,
    NULLIF(regexp_replace(COALESCE(text, ''), '\n\\s*\n+', '\n', 'g'), '') AS content,
    NULLIF(regexp_replace(COALESCE(text_full, text, ''), '\n\\s*\n+', '\n', 'g'), '') AS content_full
FROM document_outline_items
WHERE NULLIF(trim(COALESCE(text_full, text, '')), '') IS NOT NULL;

CREATE OR REPLACE VIEW document_ai_context_units AS
WITH body_line_map AS (
    SELECT
        doc_id,
        version_no,
        line_no,
        row_number() OVER (PARTITION BY doc_id, version_no ORDER BY line_no) - 1 AS body_ord
    FROM document_lines
    WHERE section = 'body'
      AND NOT is_blank
)
SELECT
    p.provision_id AS context_id,
    p.doc_id,
    COALESCE(dv.version_no, 1) AS version_no,
    p.part_id,
    p.parent_id,
    p.path,
    p.legal_path,
    p.source_context,
    p.quote_id,
    p.level,
    p.legal_role,
    p.number,
    p.heading,
    p.breadcrumb,
    p.depth,
    p.ord,
    p.line_start,
    p.line_end,
    bls.line_no AS source_line_start,
    ble.line_no AS source_line_end,
    NULLIF(regexp_replace(COALESCE(p.text, ''), '\n\\s*\n+', '\n', 'g'), '') AS content_direct,
    NULLIF(regexp_replace(COALESCE(p.text_full, p.text, ''), '\n\\s*\n+', '\n', 'g'), '') AS content_full,
    concat_ws('\n',
        'doc_id: ' || p.doc_id,
        'doc_number: ' || COALESCE(d.so_ky_hieu, ''),
        'doc_type: ' || COALESCE(d.loai_van_ban, ''),
        'title: ' || COALESCE(d.trich_yeu, ''),
        'source_context: ' || COALESCE(p.source_context, ''),
        CASE WHEN p.quote_id IS NOT NULL THEN 'quote_id: ' || CAST(p.quote_id AS VARCHAR) END,
        'level: ' || COALESCE(p.level, ''),
        'path: ' || COALESCE(p.path, ''),
        'legal_path: ' || COALESCE(p.legal_path, ''),
        'breadcrumb: ' || COALESCE(p.breadcrumb, ''),
        'body_line_range: ' || COALESCE(CAST(p.line_start AS VARCHAR), '') || '-' || COALESCE(CAST(p.line_end AS VARCHAR), ''),
        'source_line_range: ' || COALESCE(CAST(bls.line_no AS VARCHAR), '') || '-' || COALESCE(CAST(ble.line_no AS VARCHAR), ''),
        'content:',
        NULLIF(regexp_replace(COALESCE(p.text_full, p.text, ''), '\n\\s*\n+', '\n', 'g'), '')
    ) AS retrieval_text,
    json_object(
        'doc_id', p.doc_id,
        'version_no', COALESCE(dv.version_no, 1),
        'doc_number', d.so_ky_hieu,
        'doc_type', d.loai_van_ban,
        'issuing_authority', d.co_quan,
        'title', d.trich_yeu,
        'source_context', p.source_context,
        'quote_id', p.quote_id,
        'level', p.level,
        'legal_role', p.legal_role,
        'number', p.number,
        'path', p.path,
        'legal_path', p.legal_path,
        'parent_id', p.parent_id,
        'breadcrumb', p.breadcrumb,
        'line_start', p.line_start,
        'line_end', p.line_end,
        'source_line_start', bls.line_no,
        'source_line_end', ble.line_no
    ) AS metadata_json
FROM provisions p
JOIN documents d ON d.doc_id = p.doc_id
LEFT JOIN document_versions dv
  ON dv.doc_id = p.doc_id
 AND dv.is_current = true
LEFT JOIN body_line_map bls
  ON bls.doc_id = p.doc_id
 AND bls.version_no = COALESCE(dv.version_no, 1)
 AND bls.body_ord = p.line_start
LEFT JOIN body_line_map ble
  ON ble.doc_id = p.doc_id
 AND ble.version_no = COALESCE(dv.version_no, 1)
 AND ble.body_ord = p.line_end
WHERE NULLIF(trim(COALESCE(p.text_full, p.text, p.heading, '')), '') IS NOT NULL;

CREATE OR REPLACE VIEW document_ai_context_outline_units AS
WITH section_line_map AS (
    SELECT
        doc_id,
        version_no,
        section,
        line_no,
        row_number() OVER (PARTITION BY doc_id, version_no, section ORDER BY line_no) - 1 AS section_ord0
    FROM document_lines
    WHERE NOT is_blank
),
section_span AS (
    SELECT doc_id, version_no, section, min(line_no) AS source_line_start, max(line_no) AS source_line_end
    FROM document_lines
    WHERE NOT is_blank
    GROUP BY doc_id, version_no, section
)
SELECT
    o.outline_id AS context_id,
    o.doc_id,
    o.version_no,
    o.section,
    o.section_ord,
    o.item_ord,
    o.item_type,
    o.part_id,
    o.provision_id,
    o.parent_id,
    o.level,
    o.path,
    o.legal_path,
    o.source_context,
    o.quote_id,
    o.number,
    o.heading,
    o.breadcrumb,
    o.line_start,
    o.line_end,
    COALESCE(sls.line_no, ss.source_line_start) AS source_line_start,
    COALESCE(sle.line_no, ss.source_line_end) AS source_line_end,
    NULLIF(regexp_replace(COALESCE(o.text, ''), '\n\\s*\n+', '\n', 'g'), '') AS content_direct,
    NULLIF(regexp_replace(COALESCE(o.text_full, o.text, ''), '\n\\s*\n+', '\n', 'g'), '') AS content_full,
    concat_ws('\n',
        'doc_id: ' || o.doc_id,
        'doc_number: ' || COALESCE(d.so_ky_hieu, ''),
        'doc_type: ' || COALESCE(d.loai_van_ban, ''),
        'title: ' || COALESCE(d.trich_yeu, ''),
        'section: ' || o.section,
        'item_type: ' || o.item_type,
        CASE WHEN o.level IS NOT NULL THEN 'level: ' || o.level END,
        CASE WHEN o.path IS NOT NULL THEN 'path: ' || o.path END,
        CASE WHEN o.legal_path IS NOT NULL THEN 'legal_path: ' || o.legal_path END,
        CASE WHEN o.source_context IS NOT NULL THEN 'source_context: ' || o.source_context END,
        CASE WHEN o.quote_id IS NOT NULL THEN 'quote_id: ' || CAST(o.quote_id AS VARCHAR) END,
        'source_line_range: ' || COALESCE(CAST(COALESCE(sls.line_no, ss.source_line_start) AS VARCHAR), '') || '-' || COALESCE(CAST(COALESCE(sle.line_no, ss.source_line_end) AS VARCHAR), ''),
        CASE WHEN o.breadcrumb IS NOT NULL THEN 'breadcrumb: ' || o.breadcrumb END,
        'content:',
        NULLIF(regexp_replace(COALESCE(o.text_full, o.text, ''), '\n\\s*\n+', '\n', 'g'), '')
    ) AS retrieval_text,
    json_object(
        'doc_id', o.doc_id,
        'version_no', o.version_no,
        'doc_number', d.so_ky_hieu,
        'doc_type', d.loai_van_ban,
        'issuing_authority', d.co_quan,
        'title', d.trich_yeu,
        'section', o.section,
        'section_ord', o.section_ord,
        'item_ord', o.item_ord,
        'item_type', o.item_type,
        'part_id', o.part_id,
        'provision_id', o.provision_id,
        'parent_id', o.parent_id,
        'level', o.level,
        'number', o.number,
        'path', o.path,
        'legal_path', o.legal_path,
        'source_context', o.source_context,
        'quote_id', o.quote_id,
        'breadcrumb', o.breadcrumb,
        'line_start', o.line_start,
        'line_end', o.line_end,
        'source_line_start', COALESCE(sls.line_no, ss.source_line_start),
        'source_line_end', COALESCE(sle.line_no, ss.source_line_end)
    ) AS metadata_json
FROM document_outline_items o
JOIN documents d ON d.doc_id = o.doc_id
LEFT JOIN section_span ss
  ON ss.doc_id = o.doc_id
 AND ss.version_no = o.version_no
 AND ss.section = CASE WHEN o.section = 'preamble' THEN 'header' ELSE o.section END
LEFT JOIN section_line_map sls
  ON sls.doc_id = o.doc_id
 AND sls.version_no = o.version_no
 AND sls.section = CASE WHEN o.section = 'preamble' THEN 'header' ELSE o.section END
 AND sls.section_ord0 = o.line_start
LEFT JOIN section_line_map sle
  ON sle.doc_id = o.doc_id
 AND sle.version_no = o.version_no
 AND sle.section = CASE WHEN o.section = 'preamble' THEN 'header' ELSE o.section END
 AND sle.section_ord0 = o.line_end
WHERE NULLIF(trim(COALESCE(o.text_full, o.text, '')), '') IS NOT NULL;

CREATE OR REPLACE VIEW document_ai_source_lines AS
WITH line_context_matches AS (
    SELECT
        l.doc_id,
        l.version_no,
        l.line_no,
        l.section,
        l.raw_text,
        l.normalized_text,
        l.is_blank,
        pc.status AS parse_status,
        pc.reason AS parse_reason,
        pc.provision_id AS parse_provision_id,
        u.context_id,
        u.section AS context_section,
        u.section_ord AS context_section_ord,
        u.item_ord AS context_item_ord,
        u.source_line_start AS context_source_line_start,
        u.source_line_end AS context_source_line_end
    FROM document_lines l
    LEFT JOIN parse_coverage pc
      ON pc.doc_id = l.doc_id
     AND pc.version_no = l.version_no
     AND pc.line_no = l.line_no
    LEFT JOIN document_ai_context_outline_units u
      ON u.doc_id = l.doc_id
     AND u.version_no = l.version_no
     AND u.source_line_start <= l.line_no
     AND u.source_line_end >= l.line_no
),
line_context_counts AS (
    SELECT
        doc_id,
        version_no,
        line_no,
        count(context_id) AS context_count,
        string_agg(context_id, ',' ORDER BY context_section_ord, context_item_ord, context_id) AS context_ids
    FROM line_context_matches
    GROUP BY doc_id, version_no, line_no
),
ranked_line_contexts AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY doc_id, version_no, line_no
            ORDER BY
              CASE WHEN context_id IS NULL THEN 1 ELSE 0 END,
              CASE WHEN context_section = section THEN 0 ELSE 1 END,
              (context_source_line_end - context_source_line_start),
              context_section_ord,
              context_item_ord,
              context_id
        ) AS context_rank
    FROM line_context_matches
)
SELECT
    r.doc_id,
    r.version_no,
    r.line_no,
    r.section,
    r.raw_text,
    r.normalized_text,
    r.is_blank,
    r.parse_status,
    r.parse_reason,
    r.parse_provision_id,
    r.context_id AS primary_context_id,
    c.context_count,
    c.context_ids,
    json_object(
        'doc_id', r.doc_id,
        'version_no', r.version_no,
        'line_no', r.line_no,
        'section', r.section,
        'is_blank', r.is_blank,
        'parse_status', r.parse_status,
        'parse_reason', r.parse_reason,
        'parse_provision_id', r.parse_provision_id,
        'primary_context_id', r.context_id,
        'context_count', c.context_count
    ) AS metadata_json
FROM ranked_line_contexts r
JOIN line_context_counts c
  ON c.doc_id = r.doc_id
 AND c.version_no = r.version_no
 AND c.line_no = r.line_no
WHERE r.context_rank = 1;

CREATE OR REPLACE VIEW document_ai_table_context_units AS
WITH body_line_map AS (
    SELECT
        doc_id,
        version_no,
        line_no,
        row_number() OVER (PARTITION BY doc_id, version_no ORDER BY line_no) - 1 AS body_ord
    FROM document_lines
    WHERE section = 'body'
      AND NOT is_blank
),
appendix_line_span AS (
    SELECT doc_id, version_no, min(line_no) AS appendix_line_start, max(line_no) AS appendix_line_end
    FROM document_lines
    WHERE section = 'appendix'
      AND NOT is_blank
    GROUP BY doc_id, version_no
),
appendix_table_text AS (
    SELECT
        t.table_id,
        string_agg(r.raw_text, '\n' ORDER BY r.row_index) AS rows_text
    FROM appendix_tables t
    LEFT JOIN appendix_table_rows r
      ON r.table_id = t.table_id
    GROUP BY t.table_id
)
SELECT
    p.provision_id || ':embedded_table' AS table_context_id,
    p.doc_id,
    COALESCE(dv.version_no, 1) AS version_no,
    'body' AS section,
    p.part_id,
    p.provision_id,
    CAST(NULL AS VARCHAR) AS table_id,
    'provision_embedded_table' AS source_kind,
    bls.line_no AS source_line_start,
    ble.line_no AS source_line_end,
    p.breadcrumb AS title,
    CAST(NULL AS VARCHAR) AS header_json,
    p.text AS rows_text,
    concat_ws('\n',
        'doc_id: ' || p.doc_id,
        'doc_number: ' || COALESCE(d.so_ky_hieu, ''),
        'doc_type: ' || COALESCE(d.loai_van_ban, ''),
        'title: ' || COALESCE(d.trich_yeu, ''),
        'source_kind: provision_embedded_table',
        'provision_id: ' || p.provision_id,
        'path: ' || COALESCE(p.path, ''),
        'breadcrumb: ' || COALESCE(p.breadcrumb, ''),
        'source_line_range: ' || COALESCE(CAST(bls.line_no AS VARCHAR), '') || '-' || COALESCE(CAST(ble.line_no AS VARCHAR), ''),
        'table_text:',
        p.text
    ) AS retrieval_text,
    json_object(
        'doc_id', p.doc_id,
        'version_no', COALESCE(dv.version_no, 1),
        'doc_number', d.so_ky_hieu,
        'doc_type', d.loai_van_ban,
        'title', d.trich_yeu,
        'section', 'body',
        'source_kind', 'provision_embedded_table',
        'part_id', p.part_id,
        'provision_id', p.provision_id,
        'path', p.path,
        'legal_path', p.legal_path,
        'breadcrumb', p.breadcrumb,
        'source_line_start', bls.line_no,
        'source_line_end', ble.line_no
    ) AS metadata_json
FROM provisions p
JOIN documents d ON d.doc_id = p.doc_id
LEFT JOIN document_versions dv
  ON dv.doc_id = p.doc_id
 AND dv.is_current = true
LEFT JOIN body_line_map bls
  ON bls.doc_id = p.doc_id
 AND bls.version_no = COALESCE(dv.version_no, 1)
 AND bls.body_ord = p.line_start
LEFT JOIN body_line_map ble
  ON ble.doc_id = p.doc_id
 AND ble.version_no = COALESCE(dv.version_no, 1)
 AND ble.body_ord = p.line_end
WHERE regexp_matches(COALESCE(p.text, ''), '\\|[^\\n]*\\|')
UNION ALL
SELECT
    t.table_id AS table_context_id,
    t.doc_id,
    COALESCE(dv.version_no, 1) AS version_no,
    'appendix' AS section,
    t.part_id,
    CAST(NULL AS VARCHAR) AS provision_id,
    t.table_id,
    'appendix_table' AS source_kind,
    als.appendix_line_start AS source_line_start,
    als.appendix_line_end AS source_line_end,
    'Phụ lục bảng ' || CAST(t.table_no AS VARCHAR) AS title,
    t.header_json,
    att.rows_text,
    concat_ws('\n',
        'doc_id: ' || t.doc_id,
        'doc_number: ' || COALESCE(d.so_ky_hieu, ''),
        'doc_type: ' || COALESCE(d.loai_van_ban, ''),
        'title: ' || COALESCE(d.trich_yeu, ''),
        'source_kind: appendix_table',
        'table_id: ' || t.table_id,
        'part_id: ' || COALESCE(t.part_id, ''),
        'table_no: ' || CAST(t.table_no AS VARCHAR),
        'source_line_range: ' || COALESCE(CAST(als.appendix_line_start AS VARCHAR), '') || '-' || COALESCE(CAST(als.appendix_line_end AS VARCHAR), ''),
        'header_json: ' || COALESCE(t.header_json, ''),
        'table_text:',
        att.rows_text
    ) AS retrieval_text,
    json_object(
        'doc_id', t.doc_id,
        'version_no', COALESCE(dv.version_no, 1),
        'doc_number', d.so_ky_hieu,
        'doc_type', d.loai_van_ban,
        'title', d.trich_yeu,
        'section', 'appendix',
        'source_kind', 'appendix_table',
        'part_id', t.part_id,
        'table_id', t.table_id,
        'table_no', t.table_no,
        'start_ord', t.start_ord,
        'end_ord', t.end_ord,
        'n_rows', t.n_rows,
        'n_cols', t.n_cols,
        'source_line_start', als.appendix_line_start,
        'source_line_end', als.appendix_line_end
    ) AS metadata_json
FROM appendix_tables t
JOIN documents d ON d.doc_id = t.doc_id
LEFT JOIN document_versions dv
  ON dv.doc_id = t.doc_id
 AND dv.is_current = true
LEFT JOIN appendix_line_span als
  ON als.doc_id = t.doc_id
 AND als.version_no = COALESCE(dv.version_no, 1)
LEFT JOIN appendix_table_text att
  ON att.table_id = t.table_id;
"""


def open_db(path: str = "vbpl.duckdb"):
    con = duckdb.connect(path)
    con.execute(DDL)
    return con


def _stable_hash(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=str
    ).encode("utf-8")).hexdigest()


_REF_TABLES = {
    "amendments": {
        "evidence": "evidence_text",
        "doc_col": None,
        "provision_col": "resolved_target_provision_id",
        "has_resolved_flag": False,
    },
    "document_edges": {
        "evidence": "evidence_text",
        "doc_col": "target_doc_id",
        "provision_col": "target_provision_id",
        "has_resolved_flag": True,
    },
}


def _norm_so_expr(col: str) -> str:
    return (
        "NULLIF(regexp_replace(upper(trim(replace(replace("
        f"{col}, chr(160), ' '), chr(8203), ''))), '\\s+', ' ', 'g'), '')"
    )


def _norm_path_num_expr(col: str) -> str:
    return f"lower(replace(trim({col}), '.', '_'))"


def _make_provision_suffix_expr(alias: str) -> str:
    dieu = _norm_path_num_expr(f"{alias}.target_dieu")
    khoan = _norm_path_num_expr(f"{alias}.target_khoan")
    diem = _norm_path_num_expr(f"{alias}.target_diem")
    return f"""
        'd' || {dieu}
        || CASE WHEN {alias}.target_khoan IS NOT NULL
                THEN '.k' || {khoan} ELSE '' END
        || CASE WHEN {alias}.target_diem IS NOT NULL
                THEN '.dm' || {diem} ELSE '' END
    """


def _fetch_scalar(con, sql: str):
    return con.execute(sql).fetchone()[0]


def resolve_references(con, ambiguous_examples_limit: int = 5):
    doc_norm = _norm_so_expr("so_ky_hieu")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _resolve_doc_candidates AS
        SELECT doc_id, so_ky_hieu, co_quan, dia_danh, loai_van_ban,
               {doc_norm} AS so_norm
        FROM documents
        WHERE {doc_norm} IS NOT NULL
    """)

    stats = {}
    for table, cfg in _REF_TABLES.items():
        if cfg["doc_col"]:
            con.execute(f"UPDATE {table} SET {cfg['doc_col']} = NULL")
        if cfg["provision_col"]:
            con.execute(f"UPDATE {table} SET {cfg['provision_col']} = NULL")
        if cfg["has_resolved_flag"]:
            con.execute(f"UPDATE {table} SET resolved = false")

        target_norm = _norm_so_expr("target_so_ky_hieu")
        evidence_col = cfg["evidence"]
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _resolve_refs_{table} AS
            SELECT rowid AS rid, target_so_ky_hieu, target_dieu, target_khoan,
                   target_diem, {evidence_col} AS evidence_text,
                   {target_norm} AS target_norm
            FROM {table}
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _resolve_candidates_{table} AS
            SELECT r.rid, d.doc_id, d.so_ky_hieu, d.co_quan, d.dia_danh,
                   d.loai_van_ban, r.evidence_text,
                   count(*) OVER (PARTITION BY r.rid) AS candidate_count
            FROM _resolve_refs_{table} r
            JOIN _resolve_doc_candidates d
              ON d.so_norm = r.target_norm
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _resolve_narrowed_{table} AS
            SELECT rid, doc_id
            FROM _resolve_candidates_{table}
            WHERE candidate_count = 1
               OR (
                    evidence_text IS NOT NULL
                    AND (
                        (co_quan IS NOT NULL AND length(trim(co_quan)) >= 3
                         AND contains(lower(evidence_text), lower(co_quan)))
                        OR (dia_danh IS NOT NULL AND length(trim(dia_danh)) >= 3
                         AND contains(lower(evidence_text), lower(dia_danh)))
                        OR (loai_van_ban IS NOT NULL AND length(trim(loai_van_ban)) >= 3
                         AND contains(lower(evidence_text), lower(loai_van_ban)))
                    )
               )
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _resolve_docs_{table} AS
            SELECT rid, min(doc_id) AS doc_id
            FROM _resolve_narrowed_{table}
            GROUP BY rid
            HAVING count(*) = 1
        """)

        if cfg["doc_col"]:
            con.execute(f"""
                UPDATE {table} AS t
                SET {cfg['doc_col']} = rd.doc_id
                FROM _resolve_docs_{table} rd
                WHERE t.rowid = rd.rid
            """)
        if cfg["has_resolved_flag"]:
            con.execute(f"""
                UPDATE {table} AS t
                SET resolved = true
                FROM _resolve_docs_{table} rd
                WHERE t.rowid = rd.rid
            """)

        suffix_expr = _make_provision_suffix_expr("r")
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _resolve_provision_candidates_{table} AS
            SELECT r.rid, p.provision_id
            FROM _resolve_refs_{table} r
            JOIN _resolve_docs_{table} rd ON rd.rid = r.rid
            JOIN provisions p
              ON p.doc_id = rd.doc_id
             AND coalesce(p.source_context, 'own') = 'own'
             AND p.legal_path IS NOT NULL
             AND (
                    p.legal_path = ({suffix_expr})
                 OR ends_with(p.legal_path, '.' || ({suffix_expr}))
             )
            WHERE r.target_dieu IS NOT NULL
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _resolve_provisions_{table} AS
            SELECT rid, min(provision_id) AS provision_id
            FROM _resolve_provision_candidates_{table}
            GROUP BY rid
            HAVING count(*) = 1
        """)
        if cfg["provision_col"]:
            con.execute(f"""
                UPDATE {table} AS t
                SET {cfg['provision_col']} = rp.provision_id
                FROM _resolve_provisions_{table} rp
                WHERE t.rowid = rp.rid
            """)

        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE _resolve_status_{table} AS
            WITH candidate_counts AS (
                SELECT rid, max(candidate_count) AS candidate_count
                FROM _resolve_candidates_{table}
                GROUP BY rid
            )
            SELECT r.rid,
                   CASE
                     WHEN r.target_norm IS NULL THEN 'no_target'
                     WHEN coalesce(c.candidate_count, 0) = 0 THEN 'not_found'
                     WHEN rd.doc_id IS NOT NULL THEN 'resolved_doc'
                     ELSE 'ambiguous'
                   END AS status
            FROM _resolve_refs_{table} r
            LEFT JOIN candidate_counts c ON c.rid = r.rid
            LEFT JOIN _resolve_docs_{table} rd ON rd.rid = r.rid
        """)

        total = _fetch_scalar(con, f"SELECT count(*) FROM {table}")
        resolved_docs = _fetch_scalar(
            con, f"SELECT count(*) FROM _resolve_status_{table} WHERE status = 'resolved_doc'"
        )
        ambiguous = _fetch_scalar(
            con, f"SELECT count(*) FROM _resolve_status_{table} WHERE status = 'ambiguous'"
        )
        not_found = _fetch_scalar(
            con, f"SELECT count(*) FROM _resolve_status_{table} WHERE status = 'not_found'"
        )
        no_target = _fetch_scalar(
            con, f"SELECT count(*) FROM _resolve_status_{table} WHERE status = 'no_target'"
        )
        provision_miss = _fetch_scalar(con, f"""
            SELECT count(*)
            FROM _resolve_refs_{table} r
            JOIN _resolve_docs_{table} rd ON rd.rid = r.rid
            LEFT JOIN _resolve_provisions_{table} rp ON rp.rid = r.rid
            WHERE r.target_dieu IS NOT NULL
              AND rp.provision_id IS NULL
        """)
        resolved_provisions = _fetch_scalar(con, f"SELECT count(*) FROM _resolve_provisions_{table}")

        stats[table] = {
            "total": total,
            "resolved_docs": resolved_docs,
            "resolved_provisions": resolved_provisions,
            "ambiguous": ambiguous,
            "not_found": not_found,
            "no_target": no_target,
            "provision_miss": provision_miss,
        }

    stats["ambiguous_examples"] = con.execute("""
        SELECT r.target_so_ky_hieu AS so_ky_hieu,
               string_agg(DISTINCT coalesce(c.co_quan, ''), ' | ' ORDER BY coalesce(c.co_quan, '')) AS co_quan,
               count(DISTINCT c.doc_id) AS n_candidates
        FROM _resolve_refs_document_edges r
        JOIN _resolve_candidates_document_edges c ON c.rid = r.rid
        LEFT JOIN _resolve_docs_document_edges rd ON rd.rid = r.rid
        WHERE rd.doc_id IS NULL
          AND r.target_norm IS NOT NULL
        GROUP BY r.target_so_ky_hieu
        HAVING count(DISTINCT c.doc_id) > 1
        ORDER BY n_candidates DESC, so_ky_hieu
        LIMIT ?
    """, [ambiguous_examples_limit]).fetchall()
    return stats


def upsert(con, parsed, chunks, source="sample", url=None):
    h = parsed["header"]
    d = parsed["doc_id"]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    eff = next((e["date"] for e in parsed["facts"]["effective"]
                if e["kind"] == "EFFECTIVE" and e["date"]), None)
    metadata_hash = parsed.get("metadata_hash") or _stable_hash({
        "header": h,
        "signer": parsed.get("signer"),
        "chuc_danh": parsed.get("chuc_danh"),
    })
    content_hash = parsed.get("content_hash") or hashlib.sha256(
        "\n".join(p.get("text_full") or "" for p in parsed["provisions"]).encode("utf-8")
    ).hexdigest()

    previous = con.execute("""SELECT metadata_hash, content_hash, current_version_no
        FROM ingest_ledger WHERE doc_id=?""", [d]).fetchone()
    if previous and previous[0] == metadata_hash and previous[1] == content_hash:
        con.execute("""UPDATE ingest_ledger
            SET last_snapshot=?, status='UNCHANGED', source=?, source_url=?
            WHERE doc_id=?""", [now, source, url, d])
        return {"doc_id": d, "status": "UNCHANGED", "version_no": previous[2]}

    if not previous:
        status = "NEW"
        version_no = 1
    elif previous[1] != content_hash:
        status = "CONTENT_CHANGED"
        version_no = int(previous[2] or 0) + 1
    else:
        status = "META_CHANGED"
        version_no = int(previous[2] or 0) + 1

    con.execute("""UPDATE document_versions
        SET seen_to=?, is_current=false
        WHERE doc_id=? AND is_current=true""", [now, d])
    con.execute("""UPDATE provision_versions
        SET seen_to=?, is_current=false
        WHERE doc_id=? AND is_current=true""", [now, d])

    con.execute("DELETE FROM documents WHERE doc_id=?", [d])
    con.execute("DELETE FROM raw_docs WHERE doc_id=?", [d])
    con.execute("""INSERT INTO raw_docs
        (doc_id,source,source_url,fetched_at,content_hash,raw_body)
        VALUES (?,?,?,?,?,?)""",
                [d, source, url, now, content_hash, parsed.get("raw_text")])
    con.execute("""INSERT INTO documents
        (doc_id,so_ky_hieu,loai_van_ban,co_quan,dia_danh,trich_yeu,
         ngay_ban_hanh,ngay_hieu_luc,linh_vuc,nguoi_ky,chuc_danh,parser_version,content_hash)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [d, h["so_ky_hieu"], h["loai_van_ban"], h["co_quan_ban_hanh"],
                 h["dia_danh"], h["trich_yeu"], h["ngay_ban_hanh"], eff,
                 h.get("linh_vuc"), parsed["signer"], parsed["chuc_danh"], "0.3", content_hash])

    con.execute("""INSERT INTO document_versions
        (doc_id,version_no,source,source_url,metadata_hash,content_hash,
         seen_from,seen_to,is_current,change_status,so_ky_hieu,loai_van_ban,
         co_quan,dia_danh,trich_yeu,ngay_ban_hanh,ngay_hieu_luc,
         ngay_het_hieu_luc,tinh_trang,linh_vuc,scope,nguoi_ky,chuc_danh,raw_text)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [d, version_no, source, url, metadata_hash, content_hash,
                 now, None, True, status, h["so_ky_hieu"], h["loai_van_ban"],
                 h["co_quan_ban_hanh"], h["dia_danh"], h["trich_yeu"],
                 h["ngay_ban_hanh"], eff, None, None,
                 h.get("linh_vuc"), None, parsed["signer"], parsed["chuc_danh"],
                 parsed.get("raw_text")])

    con.execute("DELETE FROM ingest_ledger WHERE doc_id=?", [d])
    con.execute("""INSERT INTO ingest_ledger
        (doc_id,source,source_url,metadata_hash,content_hash,current_version_no,
         last_snapshot,status)
        VALUES (?,?,?,?,?,?,?,?)""",
                [d, source, url, metadata_hash, content_hash, version_no, now, status])

    for t, col in [("document_parts", "doc_id"), ("document_outline_items", "doc_id"),
                   ("preamble_items", "doc_id"),
                   ("provisions", "doc_id"), ("chunks", "doc_id"),
                   ("definitions", "doc_id"), ("amendments", "src_doc_id"),
                   ("document_edges", "src_doc_id"), ("semantic_signals", "doc_id"),
                   ("appendix_blocks", "doc_id"), ("appendix_tables", "doc_id"),
                   ("appendix_table_rows", "doc_id")]:
        con.execute(f"DELETE FROM {t} WHERE {col}=?", [d])

    parts = parsed.get("document_parts") or [{
        "part_id": f"{d}:main",
        "doc_id": d,
        "parent_part_id": None,
        "part_type": "main",
        "title": h["trich_yeu"],
        "attachment_label": None,
        "path_prefix": "main",
        "starts_at_ord": 0,
        "ends_at_ord": None,
        "raw_heading": None,
    }]
    main_part_id = parts[0]["part_id"]
    for part in parts:
        con.execute("""INSERT INTO document_parts
            (part_id,doc_id,parent_part_id,part_type,title,attachment_label,
             path_prefix,starts_at_ord,ends_at_ord,raw_heading)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [part["part_id"], part["doc_id"], part.get("parent_part_id"),
                     part["part_type"], part.get("title"), part.get("attachment_label"),
                     part.get("path_prefix"), part.get("starts_at_ord"),
                     part.get("ends_at_ord"), part.get("raw_heading")])

    for line in parsed.get("source_lines", []):
        con.execute("""INSERT INTO document_lines
            (doc_id,version_no,line_no,section,raw_text,normalized_text,is_blank)
            VALUES (?,?,?,?,?,?,?)""",
                    [d, version_no, line["line_no"], line.get("section"),
                     line.get("raw_text"), line.get("normalized_text"),
                     line.get("is_blank")])

    for block in parsed.get("document_blocks", []):
        con.execute("""INSERT INTO document_blocks
            (block_id,doc_id,version_no,part_id,block_type,ord,raw_text,normalized_text)
            VALUES (?,?,?,?,?,?,?,?)""",
                    [block["block_id"], d, version_no, block.get("part_id"),
                     block["block_type"], block["ord"], block.get("raw_text"),
                     block.get("normalized_text")])

    for i, item in enumerate(parsed.get("preamble_items", [])):
        span = item.get("span") or (None, None)
        con.execute("""INSERT INTO preamble_items
            (id,doc_id,item_type,ord,raw_text,target_so_ky_hieu,
             resolved_doc_id,evidence_start,evidence_end)
            VALUES (?,?,?,?,?,?,?,?,?)""",
                    [i + 1, d, item["item_type"], item["ord"], item["raw_text"],
                     item.get("target_so_ky_hieu"), item.get("resolved_doc_id"),
                     span[0], span[1]])

    for i, p in enumerate(parsed["provisions"]):
        con.execute("""INSERT INTO provisions
            (provision_id,doc_id,part_id,parent_id,path,legal_path,source_context,quote_id,level,legal_role,number,heading,breadcrumb,
             depth,ord,line_start,line_end,text,text_full,valid_from)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [p["provision_id"], d, p.get("part_id") or main_part_id,
                     f"{d}:{p['parent_path']}" if p["parent_path"] else None,
                     p["path"], p.get("legal_path") or p["path"],
                     p.get("source_context", "own"), p.get("quote_id"),
                     p["level"], p.get("legal_role"), p["number"], p["heading"],
                     p["breadcrumb"], p["depth"], i, p.get("line_start"), p.get("line_end"),
                     p["text"], p["text_full"], eff])
        con.execute("""INSERT INTO provision_versions
            (provision_version_id,provision_id,doc_id,version_no,legal_path,source_context,quote_id,text,text_full,
             is_current,effective_status,valid_from,valid_to,seen_from,seen_to)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [f"{p['provision_id']}:v{version_no}", p["provision_id"], d,
                     version_no, p.get("legal_path") or p["path"],
                     p.get("source_context", "own"), p.get("quote_id"),
                     p["text"], p["text_full"], True, None, eff, None,
                     now, None])

    for a in parsed["facts"]["amendments"]:
        span = a.get("span") or (None, None)
        con.execute("""INSERT INTO amendments
            (src_doc_id,op,target_so_ky_hieu,target_dieu,target_khoan,
             target_diem,effective_date,replacement_text,evidence_text,
             evidence_start,evidence_end) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    [d, a["op"], a["target_doc"], a["target_dieu"],
                     a["target_khoan"], a["target_diem"], eff,
                     a.get("replacement_text"), a.get("evidence_text"),
                     span[0], span[1]])

    for df in parsed["facts"]["definitions"]:
        con.execute("INSERT INTO definitions VALUES (?,?,?,?)",
                    [d, f"{d}:{df['at']}", df["term"], df["definition"]])

    for i, edge in enumerate(parsed.get("document_edges", [])):
        span = edge.get("evidence_span") or (None, None)
        con.execute("""INSERT INTO document_edges
            (edge_id,relation_type,src_doc_id,src_part_id,src_provision_id,
             target_doc_id,target_part_id,target_provision_id,target_so_ky_hieu,
             target_dieu,target_khoan,target_diem,evidence_text,evidence_start,
             evidence_end,source_method,confidence,resolved,effective_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [i + 1, edge["relation_type"], edge["src_doc_id"],
                     edge.get("src_part_id"), edge.get("src_provision_id"),
                     edge.get("target_doc_id"), edge.get("target_part_id"),
                     edge.get("target_provision_id"), edge.get("target_so_ky_hieu"),
                     edge.get("target_dieu"), edge.get("target_khoan"),
                     edge.get("target_diem"), edge.get("evidence_text"),
                     span[0], span[1], edge["source_method"],
                     edge.get("confidence", 1.0), edge.get("resolved", False),
                     edge.get("effective_date")])

    for i, signal in enumerate(parsed.get("semantic_signals", [])):
        span = signal.get("evidence_span") or (None, None)
        con.execute("""INSERT INTO semantic_signals
            (signal_id,doc_id,provision_id,signal_type,value,value_norm,
             evidence_text,evidence_start,evidence_end,confidence,source_method)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    [i + 1, signal["doc_id"], signal.get("provision_id"),
                     signal["signal_type"], signal["value"], signal.get("value_norm"),
                     signal.get("evidence_text"), span[0], span[1],
                     signal.get("confidence", 1.0), signal["source_method"]])

    for block in parsed.get("appendix_blocks", []):
        structured = block.get("structured_json")
        con.execute("""INSERT INTO appendix_blocks
            (block_id,part_id,doc_id,block_type,ord,title,raw_text,structured_json)
            VALUES (?,?,?,?,?,?,?,?)""",
                    [block["block_id"], block["part_id"], block["doc_id"],
                     block["block_type"], block["ord"], block.get("title"),
                     block.get("raw_text"), json.dumps(structured, ensure_ascii=False)
                     if structured is not None else None])

    for table in parsed.get("appendix_tables", []):
        con.execute("""INSERT INTO appendix_tables
            (table_id,doc_id,part_id,table_no,start_ord,end_ord,header_json,n_rows,n_cols)
            VALUES (?,?,?,?,?,?,?,?,?)""",
                    [table["table_id"], table["doc_id"], table["part_id"],
                     table["table_no"], table["start_ord"], table["end_ord"],
                     json.dumps(table["header"], ensure_ascii=False),
                     table["n_rows"], table["n_cols"]])
        for row in table.get("rows", []):
            con.execute("""INSERT INTO appendix_table_rows
                (table_id,doc_id,part_id,table_no,row_index,source_ord,raw_text,cells_json)
                VALUES (?,?,?,?,?,?,?,?)""",
                        [table["table_id"], table["doc_id"], table["part_id"],
                         table["table_no"], row["row_index"], row["source_ord"],
                         row["raw_text"], json.dumps(row["cells"], ensure_ascii=False)])

    for note in parsed.get("footnotes", []):
        con.execute("""INSERT INTO footnotes
            (doc_id,version_no,ord,raw_text) VALUES (?,?,?,?)""",
                    [d, version_no, note["ord"], note["raw_text"]])

    for row in parsed.get("parse_coverage", []):
        con.execute("""INSERT INTO parse_coverage
            (doc_id,version_no,line_no,section,status,provision_id,reason,raw_text)
            VALUES (?,?,?,?,?,?,?,?)""",
                    [d, version_no, row["line_no"], row.get("section"),
                     row["status"], row.get("provision_id"), row.get("reason"),
                     row.get("raw_text")])

    q = parsed.get("parse_quality")
    if q:
        con.execute("""INSERT INTO parse_quality_reports
            (doc_id,version_no,n_lines,n_body_lines,n_parsed_body_lines,
             n_orphan_body_lines,n_footnote_lines,coverage_ratio,parse_status)
            VALUES (?,?,?,?,?,?,?,?,?)""",
                    [d, version_no, q["n_lines"], q["n_body_lines"],
                     q["n_parsed_body_lines"], q["n_orphan_body_lines"],
                     q["n_footnote_lines"], q["coverage_ratio"], q["parse_status"]])

    for c in chunks:
        con.execute("""INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    [c["chunk_id"], c["doc_id"], c.get("part_id") or main_part_id,
                     c["provision_id"], version_no, c["path"],
                     c["level"], c["citation"], c["embed_text"], c["raw_text"],
                     c["n_chars"]])

    outline_rows = []
    section_ord = {"header": 0, "preamble": 1, "body": 2, "footer": 3, "appendix": 4}
    for block in parsed.get("document_blocks", []):
        section = block["block_type"]
        if section in ("body", "appendix"):
            continue
        text = block.get("normalized_text") or block.get("raw_text") or ""
        text = "\n".join(line for line in text.splitlines() if line.strip())
        if not text:
            continue
        outline_rows.append({
            "outline_id": f"{d}:outline:{section}:block",
            "doc_id": d,
            "version_no": version_no,
            "section_ord": section_ord.get(section, 9),
            "item_ord": 0,
            "section": section,
            "item_type": "block",
            "part_id": block.get("part_id"),
            "provision_id": None,
            "parent_id": None,
            "level": None,
            "path": None,
            "legal_path": None,
            "source_context": None,
            "quote_id": None,
            "number": None,
            "heading": None,
            "breadcrumb": None,
            "line_start": None,
            "line_end": None,
            "text": text,
            "text_full": text,
        })
    for item in parsed.get("preamble_items", []):
        raw = item.get("raw_text") or ""
        if not raw.strip():
            continue
        outline_rows.append({
            "outline_id": f"{d}:outline:preamble:{item['ord']}:{item['item_type']}",
            "doc_id": d,
            "version_no": version_no,
            "section_ord": section_ord["preamble"],
            "item_ord": item["ord"],
            "section": "preamble",
            "item_type": item["item_type"],
            "part_id": main_part_id,
            "provision_id": None,
            "parent_id": None,
            "level": None,
            "path": None,
            "legal_path": None,
            "source_context": None,
            "quote_id": None,
            "number": None,
            "heading": None,
            "breadcrumb": None,
            "line_start": item["ord"],
            "line_end": item["ord"],
            "text": raw,
            "text_full": raw,
        })
    for p in parsed["provisions"]:
        outline_rows.append({
            "outline_id": f"{d}:outline:body:{p['path']}",
            "doc_id": d,
            "version_no": version_no,
            "section_ord": section_ord["body"],
            "item_ord": p.get("line_start") if p.get("line_start") is not None else 0,
            "section": "body",
            "item_type": "provision",
            "part_id": p.get("part_id") or main_part_id,
            "provision_id": p["provision_id"],
            "parent_id": f"{d}:{p['parent_path']}" if p["parent_path"] else None,
            "level": p["level"],
            "path": p["path"],
            "legal_path": p.get("legal_path") or p["path"],
            "source_context": p.get("source_context", "own"),
            "quote_id": p.get("quote_id"),
            "number": p["number"],
            "heading": p["heading"],
            "breadcrumb": p["breadcrumb"],
            "line_start": p.get("line_start"),
            "line_end": p.get("line_end"),
            "text": p["text"] or p.get("heading"),
            "text_full": p["text_full"] or p["text"] or p.get("heading"),
        })
    for block in parsed.get("appendix_blocks", []):
        raw = block.get("raw_text") or ""
        if not raw.strip():
            continue
        outline_rows.append({
            "outline_id": f"{d}:outline:appendix:{block['ord']}",
            "doc_id": d,
            "version_no": version_no,
            "section_ord": section_ord["appendix"],
            "item_ord": block["ord"],
            "section": "appendix",
            "item_type": block["block_type"],
            "part_id": block["part_id"],
            "provision_id": None,
            "parent_id": None,
            "level": block["block_type"],
            "path": None,
            "legal_path": None,
            "source_context": None,
            "quote_id": None,
            "number": None,
            "heading": block.get("title"),
            "breadcrumb": block.get("title"),
            "line_start": block["ord"],
            "line_end": block["ord"],
            "text": raw,
            "text_full": raw,
        })
    for row in sorted(outline_rows, key=lambda x: (x["section_ord"], x["item_ord"], x["outline_id"])):
        con.execute("""INSERT INTO document_outline_items
            (outline_id,doc_id,version_no,section_ord,item_ord,section,item_type,
             part_id,provision_id,parent_id,level,path,legal_path,number,heading,
             source_context,quote_id,breadcrumb,line_start,line_end,text,text_full)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [row["outline_id"], row["doc_id"], row["version_no"],
                     row["section_ord"], row["item_ord"], row["section"],
                     row["item_type"], row["part_id"], row["provision_id"],
                     row["parent_id"], row["level"], row["path"], row["legal_path"],
                     row["number"], row["heading"], row.get("source_context"),
                     row.get("quote_id"), row["breadcrumb"],
                     row["line_start"], row["line_end"], row["text"],
                     row["text_full"]])

    return {"doc_id": d, "status": status, "version_no": version_no}
