-- =====================================================================
-- VBPL store — Postgres 16 + pgvector + ltree
-- Một DB duy nhất giữ cả metadata, cây quy phạm, graph và vector.
-- Chỉ tách sang Qdrant/Milvus khi vượt ~20M chunk hoặc cần multi-tenant QPS cao.
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ---------- BRONZE ----------
CREATE TABLE raw_docs (
  doc_id        text PRIMARY KEY,
  source        text NOT NULL,
  source_url    text,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  content_hash  text NOT NULL,          -- sha256(body); đổi hash = VB được sửa trên cổng
  raw_body      text,
  raw_html      text
);
CREATE INDEX ON raw_docs (content_hash);

-- ---------- SILVER ----------
CREATE TABLE documents (
  doc_id          text PRIMARY KEY,
  so_ky_hieu      text,
  loai_van_ban    text,
  co_quan         text,
  scope           text CHECK (scope IN ('trung_uong','dia_phuong')),
  trich_yeu       text,
  ngay_ban_hanh   date,
  ngay_hieu_luc   date,
  ngay_het_hieu_luc date,
  tinh_trang      text,
  linh_vuc        text,
  nguoi_ky        text,
  chuc_danh       text,
  content_hash    text,
  parser_version  text,
  ingested_at     timestamptz DEFAULT now()
);
CREATE INDEX ON documents (so_ky_hieu) WHERE so_ky_hieu IS NOT NULL;
CREATE INDEX ON documents (loai_van_ban, ngay_hieu_luc DESC);
CREATE INDEX ON documents (tinh_trang) WHERE tinh_trang = 'Còn hiệu lực';

CREATE TABLE document_versions (
  doc_id          text NOT NULL REFERENCES documents ON DELETE CASCADE,
  version_no      int NOT NULL,
  source          text,
  source_url      text,
  metadata_hash   text NOT NULL,
  content_hash    text NOT NULL,
  seen_from       timestamptz NOT NULL DEFAULT now(),
  seen_to         timestamptz,
  is_current      boolean NOT NULL DEFAULT true,
  change_status   text CHECK (change_status IN
                  ('NEW','META_CHANGED','CONTENT_CHANGED')),
  so_ky_hieu      text,
  loai_van_ban    text,
  co_quan         text,
  scope           text,
  trich_yeu       text,
  ngay_ban_hanh   date,
  ngay_hieu_luc   date,
  ngay_het_hieu_luc date,
  tinh_trang      text,
  linh_vuc        text,
  nguoi_ky        text,
  chuc_danh       text,
  raw_text        text,
  PRIMARY KEY (doc_id, version_no)
);
CREATE INDEX ON document_versions (doc_id, is_current);
CREATE INDEX ON document_versions (content_hash);

CREATE TABLE ingest_ledger (
  doc_id          text PRIMARY KEY,
  source          text,
  source_url      text,
  metadata_hash   text NOT NULL,
  content_hash    text NOT NULL,
  current_version_no int NOT NULL,
  last_snapshot   timestamptz NOT NULL DEFAULT now(),
  status          text NOT NULL CHECK (status IN
                  ('NEW','META_CHANGED','CONTENT_CHANGED','UNCHANGED','MISSING'))
);
CREATE INDEX ON ingest_ledger (status, last_snapshot DESC);

-- Physical namespaces inside one legal file. This prevents collisions such as
-- Decision Article 1 vs attached Regulation Article 1.
CREATE TABLE document_parts (
  part_id        text PRIMARY KEY,          -- '<doc_id>:main' / '<doc_id>:attached:quy_che'
  doc_id         text NOT NULL REFERENCES documents ON DELETE CASCADE,
  parent_part_id text REFERENCES document_parts ON DELETE CASCADE,
  part_type      text NOT NULL CHECK (part_type IN
                 ('main','attached_document','appendix','form','table','other')),
  title          text,
  attachment_label text,                    -- "ban hành kèm theo Quyết định..."
  path_prefix    ltree,                     -- main / att.quy_che / app.i
  starts_at_ord  int,
  ends_at_ord    int,
  raw_heading    text
);
CREATE INDEX ON document_parts (doc_id, part_type);
CREATE INDEX ON document_parts USING gist (path_prefix);

CREATE TABLE document_lines (
  doc_id          text NOT NULL REFERENCES documents ON DELETE CASCADE,
  version_no      int NOT NULL,
  line_no         int NOT NULL,
  section         text CHECK (section IN ('header','body','footer','appendix','unknown')),
  raw_text        text,
  normalized_text text,
  is_blank        boolean NOT NULL DEFAULT false,
  PRIMARY KEY (doc_id, version_no, line_no),
  FOREIGN KEY (doc_id, version_no) REFERENCES document_versions (doc_id, version_no)
    ON DELETE CASCADE
);
CREATE INDEX ON document_lines (doc_id, version_no, section, line_no);

CREATE TABLE document_blocks (
  block_id        text NOT NULL,
  doc_id          text NOT NULL REFERENCES documents ON DELETE CASCADE,
  version_no      int NOT NULL,
  part_id         text REFERENCES document_parts ON DELETE CASCADE,
  block_type      text NOT NULL CHECK (block_type IN ('header','body','footer','appendix')),
  ord             int NOT NULL,
  raw_text        text,
  normalized_text text,
  PRIMARY KEY (block_id, version_no),
  FOREIGN KEY (doc_id, version_no) REFERENCES document_versions (doc_id, version_no)
    ON DELETE CASCADE
);
CREATE INDEX ON document_blocks (doc_id, version_no, block_type, ord);

CREATE TABLE preamble_items (
  id             bigserial PRIMARY KEY,
  doc_id         text NOT NULL REFERENCES documents ON DELETE CASCADE,
  item_type      text NOT NULL CHECK (item_type IN
                 ('legal_basis','proposal','promulgation_formula','other')),
  ord            int NOT NULL,
  raw_text       text NOT NULL,
  target_so_ky_hieu text,
  resolved_doc_id text REFERENCES documents,
  evidence_span  int4range
);
CREATE INDEX ON preamble_items (doc_id, item_type, ord);
CREATE INDEX ON preamble_items (resolved_doc_id);

CREATE TABLE provisions (
  provision_id  text PRIMARY KEY,          -- '<doc_id>:ci.d3.k2.dma'
  doc_id        text NOT NULL REFERENCES documents ON DELETE CASCADE,
  part_id       text REFERENCES document_parts ON DELETE CASCADE,
  parent_id     text REFERENCES provisions ON DELETE CASCADE,
  path          ltree NOT NULL,            -- ci.d3.k2.dma  -> truy vấn cây bằng <@ / @>
  legal_path    ltree,
  source_context text NOT NULL DEFAULT 'own',
  quote_id      int,
  level         text NOT NULL,
  legal_role    text,                      -- scope|definition|effective|transition|implementation|...
  number        text,
  heading       text,
  breadcrumb    text,
  depth         smallint,
  ord           int,                       -- thứ tự đọc trong văn bản
  line_start    int,
  line_end      int,
  text          text,
  text_full     text,
  valid_from    date,
  valid_to      date,                      -- NULL = còn hiệu lực (point-in-time query)
  fts           tsvector
);
CREATE INDEX ON provisions USING gist (path);           -- lấy cả cây con: path <@ 'ci.d3'
CREATE INDEX ON provisions USING gin  (fts);            -- BM25-ish cho hybrid search
CREATE INDEX ON provisions (doc_id, ord);
CREATE INDEX ON provisions (level) WHERE level = 'dieu';
CREATE INDEX ON provisions (part_id, ord);

CREATE TABLE document_outline_items (
  outline_id    text PRIMARY KEY,
  doc_id        text NOT NULL REFERENCES documents ON DELETE CASCADE,
  version_no    int NOT NULL,
  section_ord   int NOT NULL,
  item_ord      int NOT NULL,
  section       text NOT NULL CHECK (section IN ('header','preamble','body','footer','appendix')),
  item_type     text NOT NULL,
  part_id       text REFERENCES document_parts ON DELETE CASCADE,
  provision_id  text REFERENCES provisions ON DELETE CASCADE,
  parent_id     text,
  level         text,
  path          ltree,
  legal_path    ltree,
  source_context text,
  quote_id      int,
  number        text,
  heading       text,
  breadcrumb    text,
  line_start    int,
  line_end      int,
  text          text,
  text_full     text,
  FOREIGN KEY (doc_id, version_no) REFERENCES document_versions (doc_id, version_no)
    ON DELETE CASCADE
);
CREATE INDEX ON document_outline_items (doc_id, version_no, section_ord, item_ord);
CREATE INDEX ON document_outline_items (doc_id, section, level);

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
  repeat('  ', GREATEST(COALESCE(
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
  NULLIF(regexp_replace(COALESCE(text, ''), E'\n\\s*\n+', E'\n', 'g'), '') AS content,
  NULLIF(regexp_replace(COALESCE(text_full, text, ''), E'\n\\s*\n+', E'\n', 'g'), '') AS content_full
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
  NULLIF(regexp_replace(COALESCE(p.text, ''), E'\n\\s*\n+', E'\n', 'g'), '') AS content_direct,
  NULLIF(regexp_replace(COALESCE(p.text_full, p.text, ''), E'\n\\s*\n+', E'\n', 'g'), '') AS content_full,
  concat_ws(E'\n',
    'doc_id: ' || p.doc_id,
    'doc_number: ' || COALESCE(d.so_ky_hieu, ''),
    'doc_type: ' || COALESCE(d.loai_van_ban, ''),
    'title: ' || COALESCE(d.trich_yeu, ''),
    'source_context: ' || p.source_context,
    CASE WHEN p.quote_id IS NOT NULL THEN 'quote_id: ' || p.quote_id::text END,
    'level: ' || p.level,
    'path: ' || p.path::text,
    'legal_path: ' || COALESCE(p.legal_path::text, ''),
    'breadcrumb: ' || COALESCE(p.breadcrumb, ''),
    'body_line_range: ' || COALESCE(p.line_start::text, '') || '-' || COALESCE(p.line_end::text, ''),
    'source_line_range: ' || COALESCE(bls.line_no::text, '') || '-' || COALESCE(ble.line_no::text, ''),
    'content:',
    NULLIF(regexp_replace(COALESCE(p.text_full, p.text, ''), E'\n\\s*\n+', E'\n', 'g'), '')
  ) AS retrieval_text,
  jsonb_build_object(
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
    'path', p.path::text,
    'legal_path', p.legal_path::text,
    'parent_id', p.parent_id,
    'breadcrumb', p.breadcrumb,
    'line_start', p.line_start,
    'line_end', p.line_end,
    'source_line_start', bls.line_no,
    'source_line_end', ble.line_no,
    'ancestors', COALESCE((
      SELECT jsonb_agg(jsonb_build_object(
        'provision_id', a.provision_id,
        'level', a.level,
        'number', a.number,
        'path', a.path::text,
        'legal_path', a.legal_path::text,
        'heading', a.heading
      ) ORDER BY nlevel(a.path))
      FROM provisions a
      WHERE a.doc_id = p.doc_id
        AND a.source_context = p.source_context
        AND COALESCE(a.quote_id, -1) = COALESCE(p.quote_id, -1)
        AND a.path @> p.path
        AND a.path <> p.path
    ), '[]'::jsonb),
    'children', COALESCE((
      SELECT jsonb_agg(jsonb_build_object(
        'provision_id', c.provision_id,
        'level', c.level,
        'number', c.number,
        'path', c.path::text,
        'legal_path', c.legal_path::text,
        'heading', c.heading
      ) ORDER BY c.ord)
      FROM provisions c
      WHERE c.parent_id = p.provision_id
    ), '[]'::jsonb)
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
  NULLIF(regexp_replace(COALESCE(o.text, ''), E'\n\\s*\n+', E'\n', 'g'), '') AS content_direct,
  NULLIF(regexp_replace(COALESCE(o.text_full, o.text, ''), E'\n\\s*\n+', E'\n', 'g'), '') AS content_full,
  concat_ws(E'\n',
    'doc_id: ' || o.doc_id,
    'doc_number: ' || COALESCE(d.so_ky_hieu, ''),
    'doc_type: ' || COALESCE(d.loai_van_ban, ''),
    'title: ' || COALESCE(d.trich_yeu, ''),
    'section: ' || o.section,
    'item_type: ' || o.item_type,
    CASE WHEN o.level IS NOT NULL THEN 'level: ' || o.level END,
    CASE WHEN o.path IS NOT NULL THEN 'path: ' || o.path::text END,
    CASE WHEN o.legal_path IS NOT NULL THEN 'legal_path: ' || o.legal_path::text END,
    CASE WHEN o.source_context IS NOT NULL THEN 'source_context: ' || o.source_context END,
    CASE WHEN o.quote_id IS NOT NULL THEN 'quote_id: ' || o.quote_id::text END,
    'source_line_range: ' || COALESCE(COALESCE(sls.line_no, ss.source_line_start)::text, '') || '-' || COALESCE(COALESCE(sle.line_no, ss.source_line_end)::text, ''),
    CASE WHEN o.breadcrumb IS NOT NULL THEN 'breadcrumb: ' || o.breadcrumb END,
    'content:',
    NULLIF(regexp_replace(COALESCE(o.text_full, o.text, ''), E'\n\\s*\n+', E'\n', 'g'), '')
  ) AS retrieval_text,
  jsonb_build_object(
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
    'path', o.path::text,
    'legal_path', o.legal_path::text,
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
  jsonb_build_object(
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
    string_agg(r.raw_text, E'\n' ORDER BY r.row_index) AS rows_text
  FROM appendix_tables t
  LEFT JOIN appendix_table_rows r
    ON r.table_id = t.table_id
  GROUP BY t.table_id
)
SELECT
  p.provision_id || ':embedded_table' AS table_context_id,
  p.doc_id,
  COALESCE(dv.version_no, 1) AS version_no,
  'body'::text AS section,
  p.part_id,
  p.provision_id,
  NULL::text AS table_id,
  'provision_embedded_table'::text AS source_kind,
  bls.line_no AS source_line_start,
  ble.line_no AS source_line_end,
  p.breadcrumb AS title,
  NULL::text AS header_json,
  p.text AS rows_text,
  concat_ws(E'\n',
    'doc_id: ' || p.doc_id,
    'doc_number: ' || COALESCE(d.so_ky_hieu, ''),
    'doc_type: ' || COALESCE(d.loai_van_ban, ''),
    'title: ' || COALESCE(d.trich_yeu, ''),
    'source_kind: provision_embedded_table',
    'provision_id: ' || p.provision_id,
    'path: ' || p.path::text,
    'breadcrumb: ' || COALESCE(p.breadcrumb, ''),
    'source_line_range: ' || COALESCE(bls.line_no::text, '') || '-' || COALESCE(ble.line_no::text, ''),
    'table_text:',
    p.text
  ) AS retrieval_text,
  jsonb_build_object(
    'doc_id', p.doc_id,
    'version_no', COALESCE(dv.version_no, 1),
    'doc_number', d.so_ky_hieu,
    'doc_type', d.loai_van_ban,
    'title', d.trich_yeu,
    'section', 'body',
    'source_kind', 'provision_embedded_table',
    'part_id', p.part_id,
    'provision_id', p.provision_id,
    'path', p.path::text,
    'legal_path', p.legal_path::text,
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
WHERE COALESCE(p.text, '') ~ '\|[^\n]*\|'
UNION ALL
SELECT
  t.table_id AS table_context_id,
  t.doc_id,
  COALESCE(dv.version_no, 1) AS version_no,
  'appendix'::text AS section,
  t.part_id,
  NULL::text AS provision_id,
  t.table_id,
  'appendix_table'::text AS source_kind,
  als.appendix_line_start AS source_line_start,
  als.appendix_line_end AS source_line_end,
  'Phụ lục bảng ' || t.table_no::text AS title,
  t.header_json::text AS header_json,
  att.rows_text,
  concat_ws(E'\n',
    'doc_id: ' || t.doc_id,
    'doc_number: ' || COALESCE(d.so_ky_hieu, ''),
    'doc_type: ' || COALESCE(d.loai_van_ban, ''),
    'title: ' || COALESCE(d.trich_yeu, ''),
    'source_kind: appendix_table',
    'table_id: ' || t.table_id,
    'part_id: ' || COALESCE(t.part_id, ''),
    'table_no: ' || t.table_no::text,
    'source_line_range: ' || COALESCE(als.appendix_line_start::text, '') || '-' || COALESCE(als.appendix_line_end::text, ''),
    'header_json: ' || COALESCE(t.header_json::text, ''),
    'table_text:',
    att.rows_text
  ) AS retrieval_text,
  jsonb_build_object(
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

-- Lịch sử: mỗi lần một Điều/Khoản bị sửa -> 1 version mới, version cũ đóng valid_to.
-- Đây là thứ cho phép trả lời "ngày 01/2022 điều này quy định gì".
CREATE TABLE provision_versions (
  version_id    bigserial PRIMARY KEY,
  provision_key text NOT NULL,             -- '<base_doc_so_ky_hieu>:d9.k2' (bền qua các lần sửa)
  provision_id  text REFERENCES provisions,
  doc_id        text REFERENCES documents ON DELETE CASCADE,
  version_no    int,
  legal_path    ltree,
  source_context text NOT NULL DEFAULT 'own',
  quote_id      int,
  text_full     text,
  is_current    boolean NOT NULL DEFAULT true,
  effective_status text,
  seen_from     timestamptz NOT NULL DEFAULT now(),
  seen_to       timestamptz,
  valid_from    date,
  valid_to      date,
  amended_by    text,                      -- so_ky_hieu của VB sửa đổi
  UNIQUE (provision_key, valid_from)
);
CREATE INDEX ON provision_versions (provision_key, valid_from DESC);
CREATE INDEX ON provision_versions (doc_id, version_no);
CREATE INDEX ON provision_versions (provision_id, is_current);

CREATE TABLE amendments (
  id bigserial PRIMARY KEY,
  src_doc_id text REFERENCES documents ON DELETE CASCADE,
  src_provision_id text,
  op text CHECK (op IN ('AMEND','ADD','REPEAL','REPLACE','EXPIRE','SUSPEND')),
  target_so_ky_hieu text, target_dieu text, target_khoan text, target_diem text,
  resolved_target_provision_id text,
  effective_date date,
  replacement_text text,
  evidence_text text,
  evidence_span int4range
);
CREATE INDEX ON amendments (target_so_ky_hieu, target_dieu);

-- Unified relation graph. Specialized tables above are extraction-friendly;
-- this table is query-friendly for tracing all legal links.
CREATE TABLE document_edges (
  edge_id        bigserial PRIMARY KEY,
  relation_type text NOT NULL CHECK (relation_type IN (
                 'LEGAL_BASIS','INLINE_CITATION','INTERNAL_REFERENCE',
                 'AMENDS','ADDS','REPEALS','REPLACES','EXPIRES','SUSPENDS',
                 'GUIDES','DETAILS','IMPLEMENTS',
                 'PROMULGATES','ATTACHED_TO',
                 'CONSOLIDATES','INCORPORATES',
                 'RELATED_BY_SECTOR','RELATED_BY_AUTHORITY',
                 'RELATED_BY_TERM','RELATED_BY_TOPIC')),
  src_doc_id     text NOT NULL REFERENCES documents ON DELETE CASCADE,
  src_part_id    text REFERENCES document_parts ON DELETE CASCADE,
  src_provision_id text REFERENCES provisions ON DELETE CASCADE,
  target_doc_id  text REFERENCES documents,
  target_part_id text REFERENCES document_parts,
  target_provision_id text REFERENCES provisions,
  target_so_ky_hieu text,
  target_dieu    text,
  target_khoan   text,
  target_diem    text,
  evidence_text  text,
  evidence_span  int4range,
  source_method  text NOT NULL,             -- legal_basis|inline_citation|amendment_clause|...
  confidence     numeric(4,3) NOT NULL DEFAULT 1.0,
  resolved       boolean NOT NULL DEFAULT false,
  effective_date date,
  created_at     timestamptz DEFAULT now()
);
CREATE INDEX ON document_edges (src_doc_id, relation_type);
CREATE INDEX ON document_edges (target_doc_id, relation_type);
CREATE INDEX ON document_edges (target_so_ky_hieu);
CREATE INDEX ON document_edges (src_provision_id);
CREATE INDEX ON document_edges (target_provision_id);
CREATE INDEX ON document_edges (source_method, confidence DESC);

CREATE TABLE definitions (
  id bigserial PRIMARY KEY,
  doc_id text REFERENCES documents ON DELETE CASCADE,
  provision_id text,
  term text, term_norm text, definition text
);
CREATE INDEX ON definitions USING gin (term_norm gin_trgm_ops);

CREATE TABLE semantic_signals (
  signal_id      bigserial PRIMARY KEY,
  doc_id         text NOT NULL REFERENCES documents ON DELETE CASCADE,
  provision_id   text REFERENCES provisions ON DELETE CASCADE,
  signal_type    text NOT NULL CHECK (signal_type IN
                 ('term','topic','subject','right','obligation','prohibition',
                  'authority','procedure','condition','exception','sanction',
                  'transition','effective_rule')),
  value          text NOT NULL,
  value_norm     text,
  evidence_text  text,
  evidence_span  int4range,
  confidence     numeric(4,3) NOT NULL DEFAULT 1.0,
  source_method  text NOT NULL
);
CREATE INDEX ON semantic_signals (doc_id, signal_type);
CREATE INDEX ON semantic_signals (provision_id);
CREATE INDEX ON semantic_signals USING gin (value_norm gin_trgm_ops);

CREATE TABLE appendix_blocks (
  block_id       text PRIMARY KEY,
  part_id        text NOT NULL REFERENCES document_parts ON DELETE CASCADE,
  doc_id         text NOT NULL REFERENCES documents ON DELETE CASCADE,
  block_type     text NOT NULL CHECK (block_type IN
                 ('paragraph','table','layout','form','list','formula','diagram','image','unknown')),
  ord            int NOT NULL,
  title          text,
  raw_text       text,
  structured_json jsonb
);
CREATE INDEX ON appendix_blocks (doc_id, ord);
CREATE INDEX ON appendix_blocks (part_id, block_type);

CREATE TABLE appendix_tables (
  table_id       text PRIMARY KEY,
  doc_id         text NOT NULL REFERENCES documents ON DELETE CASCADE,
  part_id        text NOT NULL REFERENCES document_parts ON DELETE CASCADE,
  table_no       int NOT NULL,
  start_ord      int NOT NULL,
  end_ord        int NOT NULL,
  header_json    jsonb,
  n_rows         int,
  n_cols         int
);
CREATE INDEX ON appendix_tables (doc_id, table_no);
CREATE INDEX ON appendix_tables (part_id, table_no);

CREATE TABLE appendix_table_rows (
  table_id       text NOT NULL REFERENCES appendix_tables ON DELETE CASCADE,
  doc_id         text NOT NULL REFERENCES documents ON DELETE CASCADE,
  part_id        text NOT NULL REFERENCES document_parts ON DELETE CASCADE,
  table_no       int NOT NULL,
  row_index      int NOT NULL,
  source_ord     int NOT NULL,
  raw_text       text,
  cells_json     jsonb,
  PRIMARY KEY (table_id, row_index)
);
CREATE INDEX ON appendix_table_rows (doc_id, table_no, row_index);

CREATE TABLE footnotes (
  doc_id          text NOT NULL REFERENCES documents ON DELETE CASCADE,
  version_no      int NOT NULL,
  ord             int NOT NULL,
  raw_text        text NOT NULL,
  PRIMARY KEY (doc_id, version_no, ord),
  FOREIGN KEY (doc_id, version_no) REFERENCES document_versions (doc_id, version_no)
    ON DELETE CASCADE
);
CREATE INDEX ON footnotes (doc_id, version_no);

CREATE TABLE parse_coverage (
  doc_id          text NOT NULL REFERENCES documents ON DELETE CASCADE,
  version_no      int NOT NULL,
  line_no         int NOT NULL,
  section         text,
  status          text NOT NULL CHECK (status IN
                  ('parsed','footnote','orphan','header','footer','appendix','blank','unknown')),
  provision_id    text REFERENCES provisions ON DELETE SET NULL,
  reason          text,
  raw_text        text,
  PRIMARY KEY (doc_id, version_no, line_no),
  FOREIGN KEY (doc_id, version_no) REFERENCES document_versions (doc_id, version_no)
    ON DELETE CASCADE
);
CREATE INDEX ON parse_coverage (doc_id, version_no, status);
CREATE INDEX ON parse_coverage (provision_id);

CREATE TABLE parse_quality_reports (
  doc_id          text NOT NULL REFERENCES documents ON DELETE CASCADE,
  version_no      int NOT NULL,
  n_lines         int NOT NULL,
  n_body_lines    int NOT NULL,
  n_parsed_body_lines int NOT NULL,
  n_orphan_body_lines int NOT NULL,
  n_footnote_lines int NOT NULL,
  coverage_ratio  double precision NOT NULL,
  parse_status    text NOT NULL CHECK (parse_status IN ('ok','warning','failed')),
  PRIMARY KEY (doc_id, version_no),
  FOREIGN KEY (doc_id, version_no) REFERENCES document_versions (doc_id, version_no)
    ON DELETE CASCADE
);
CREATE INDEX ON parse_quality_reports (parse_status, coverage_ratio);

-- ---------- GOLD ----------
CREATE TABLE chunks (
  chunk_id      text PRIMARY KEY,
  doc_id        text REFERENCES documents ON DELETE CASCADE,
  part_id       text REFERENCES document_parts ON DELETE CASCADE,
  provision_id  text REFERENCES provisions ON DELETE CASCADE,
  version_no    int,
  level         text,
  citation      text,                       -- hiển thị nguồn cho người dùng
  embed_text    text,                       -- context header + nội dung
  raw_text      text,
  n_chars       int,
  -- cột lọc denormalize, tránh JOIN trong đường ANN nóng
  loai_van_ban  text,
  co_quan       text,
  linh_vuc      text,
  ngay_hieu_luc date,
  con_hieu_luc  boolean,
  embedding     vector(1024)                -- đổi theo model (768 / 1024 / 2048)
);
-- HNSW cho ANN; partial index để index nhỏ và query nóng chỉ đụng VB còn hiệu lực
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64)
  WHERE con_hieu_luc;
CREATE INDEX ON chunks (loai_van_ban, ngay_hieu_luc DESC);
CREATE INDEX ON chunks USING gin (to_tsvector('simple', unaccent(raw_text)));

-- ---------- Ví dụ truy vấn ----------
-- 1) Lấy nguyên Điều 3 kèm mọi khoản/điểm:
--    SELECT * FROM provisions WHERE doc_id=$1 AND path <@ 'ci.d3' ORDER BY ord;
-- 2) Hybrid search có lọc hiệu lực:
--    SELECT chunk_id, citation, 1-(embedding <=> $1) AS sim
--    FROM chunks WHERE con_hieu_luc AND linh_vuc = $2
--    ORDER BY embedding <=> $1 LIMIT 20;
-- 3) Point-in-time: điều luật này nói gì ngày 2022-05-01?
--    SELECT text_full FROM provision_versions
--    WHERE provision_key=$1 AND valid_from <= DATE '2022-05-01'
--      AND (valid_to IS NULL OR valid_to > DATE '2022-05-01');
-- 4) Impact analysis: edit Dieu 9 TT 200 then who is affected?
--    SELECT DISTINCT e.src_provision_id FROM document_edges e
--    WHERE e.relation_type IN ('INLINE_CITATION','INTERNAL_REFERENCE')
--      AND e.target_so_ky_hieu='200/2014/TT-BTC' AND e.target_dieu='9';
-- 5) Trace all direct links from one document:
--    SELECT relation_type, target_so_ky_hieu, target_dieu, evidence_text
--    FROM document_edges WHERE src_doc_id=$1 ORDER BY confidence DESC;
-- 6) Find documents that cite, amend, guide, or use the same inferred topic:
--    SELECT * FROM document_edges
--    WHERE target_doc_id=$1 OR src_doc_id=$1
--    ORDER BY relation_type, confidence DESC;
