-- P5 schema (PLAN_v2 section 4.2/4.3), DuckDB dialect.
-- No live Postgres/ltree in this environment - DuckDB stands in as a single
-- embedded file. `nodes.path` is kept for parity with the plan's ltree design,
-- but subtree queries here should use `node_id LIKE 'prefix/%'` instead
-- (node_id is itself a hierarchical, globally unique path).

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    title TEXT,
    so_ky_hieu TEXT,
    ngay_ban_hanh DATE,
    loai_van_ban TEXT,
    ngay_co_hieu_luc DATE,
    ngay_het_hieu_luc DATE,
    nguon_thu_thap TEXT,
    nganh TEXT,
    linh_vuc TEXT,
    co_quan_ban_hanh TEXT,
    chuc_danh TEXT,
    nguoi_ky TEXT,
    pham_vi TEXT,
    thong_tin_ap_dung TEXT,
    tinh_trang_hieu_luc TEXT
);

-- Raw doc-level pairs from data/relationships.parquet. NOT the same as `edges`:
-- these are un-resolved (no target node_id yet) - P7's job is to resolve them.
CREATE TABLE document_relationships (
    doc_id TEXT,
    other_doc_id TEXT,
    relationship TEXT
);

-- One row per document, from reports/quality.parquet (P3 validator output).
CREATE TABLE parse_quality (
    doc_id TEXT PRIMARY KEY,
    n_nodes INTEGER,
    char_coverage DOUBLE,
    sequence_ok BOOLEAN,
    hierarchy_ok BOOLEAN,
    part_count_ok BOOLEAN,
    table_preserved BOOLEAN,
    conflict_rate DOUBLE,
    verdict TEXT,
    issues TEXT,
    loai_van_ban TEXT,
    decade TEXT,
    template_family TEXT
);

CREATE TABLE nodes (
    node_id TEXT PRIMARY KEY,
    doc_id TEXT,
    part_id TEXT,
    parent_id TEXT,
    path TEXT,
    depth INTEGER,
    order_index INTEGER,
    node_type TEXT,
    number_raw TEXT,
    number_norm TEXT,
    heading TEXT,
    text TEXT,
    text_full TEXT,
    breadcrumb TEXT,
    html_raw TEXT,
    confidence DOUBLE,
    classified_by TEXT
);
CREATE INDEX idx_nodes_doc_id ON nodes(doc_id);
CREATE INDEX idx_nodes_parent_id ON nodes(parent_id);

-- Empty until P7 (doc-level relationship -> node-level resolution) and P8
-- (semantic linking) are built; schema matches PLAN_v2 section 4.3 so those
-- phases can write into it without a migration.
CREATE TABLE edges (
    src_node_id TEXT,
    dst_node_id TEXT,
    dst_doc_id TEXT,
    edge_type TEXT,
    source TEXT,
    confidence DOUBLE,
    evidence_text TEXT
);
