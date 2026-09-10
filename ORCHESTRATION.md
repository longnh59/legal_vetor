# Codex Orchestration Log

This repository uses the root Codex model as the orchestrator. Codex Orchestration
may route planner/advisor/executor roles in future tasks, but it does not replace
the root model's responsibility for goal state, integration, or final verification.

## Current Validated State

Sample database:

- DuckDB: `legal_sample_200.duckdb`
- Postgres: `postgresql://vbpl:vbpl_dev@localhost:5433/vbpl`
- Docker compose: `docker-compose.postgres.yml`

Validated counts on the 200-document sample:

- `documents`: 200
- `document_lines`: 60147
- `provisions`: 9300
- `document_outline_items`: 25849
- `chunks`: 9541
- `document_ai_table_context_units`: 451

Final audit gate:

```powershell
python files\validate_parse_invariants.py --db legal_sample_200.duckdb --expected-docs 200
```

Expected result:

```text
PASS=27 WARN=0 FAIL=0
```

## Required Loop For Future Optimization Rounds

Each optimization round must follow this sequence:

1. Scan the current DB/code for a concrete defect or measurable weakness.
2. Patch only the parser, schema, store, importer, chunker, or audit code needed for that defect.
3. Compile changed Python files.
4. Rebuild the 200-document sample when extraction/chunking changes.
5. Run the invariant audit.
6. Import DuckDB to Postgres when persisted tables changed.
7. Refresh Postgres views from `files/schema_postgres.sql` when views changed.
8. Record the evidence: counts, failed-to-zero checks, and at least one sample query.

Do not count a round as successful unless it improves or preserves all existing
audit gates.

## Standard Commands

Compile:

```powershell
python -m py_compile files\vbpl_extract.py files\vbpl_store.py files\validate_parse_invariants.py
```

Rebuild sample:

```powershell
python -u files\ingest_parquet_sample.py --root . --db legal_sample_200.duckdb --limit 200 --overwrite
```

Audit:

```powershell
python files\validate_parse_invariants.py --db legal_sample_200.duckdb --expected-docs 200
```

Import to Postgres:

```powershell
python files\import_duckdb_to_postgres.py --duckdb legal_sample_200.duckdb --dsn "postgresql://vbpl:vbpl_dev@localhost:5433/vbpl" --truncate
```

Refresh Postgres AI/context views:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$lines = Get-Content -Encoding UTF8 files\schema_postgres.sql
$lines[208..708] | docker exec -i vbpl-postgres psql -U vbpl -d vbpl
```

## Core Quality Gates

These checks must remain zero:

```sql
SELECT count(*) FROM document_ai_source_lines
WHERE NOT is_blank AND context_count = 0;

SELECT count(*) FROM chunks
WHERE n_chars > 2200;

SELECT count(*) FROM parse_coverage
WHERE section='body'
  AND raw_text ~ '^[-–—+•]\s+'
  AND reason <> 'tiet';

SELECT count(*) FROM parse_coverage
WHERE section='body'
  AND raw_text ~ '^[a-zđf][0-9]?\)\s+'
  AND reason <> 'diem';

SELECT count(*) FROM provisions
WHERE level='roman_section'
  AND number IN ('C','D','L','M');

SELECT count(*) FROM provisions
WHERE level='diem'
  AND coalesce(text,'') ~ '\s[a-zđf][0-9]?\)\s+';
```

Current expected summary:

```text
unmapped_nonblank_source_lines = 0
oversized_chunks = 0
body_bullets_not_tiet = 0
body_diem_not_diem = 0
bad_single_letter_roman = 0
diem_with_inline_marker = 0
```

## Important Views

- `document_tree_readable`: readable legal tree with indented labels.
- `document_ai_context_units`: provision-level AI retrieval units.
- `document_ai_context_outline_units`: full outline retrieval units across header, preamble, body, footer, appendix.
- `document_ai_source_lines`: every source line mapped to context coverage.
- `document_ai_table_context_units`: appendix tables and body/provision-embedded tables as separate AI context.

## Notes For Codex Orchestration

The root model remains responsible for:

- deciding whether another round is worth doing;
- integrating all edits;
- preserving user and repository changes;
- running verification;
- marking goals complete or blocked.

Use child roles only for bounded, non-overlapping work. Good future slices:

- parser anomaly scan and proposal;
- schema/view review;
- SQL audit query design;
- code review of a patch before rebuild;
- documentation update after verification.

Each child handoff must include owned files, stop conditions, and required evidence.
Executor completion is not final acceptance; the root must verify in DuckDB and
Postgres.
