# Trợ lý pháp luật của Chính phủ - Tài liệu thiết kế

# Blueprint Rà soát

Kiến trúc MVP cho một trợ lý soạn thảo, dùng để kiểm tra các quy định pháp luật Việt Nam được đề xuất so với pháp luật hiện hành, ở cấp độ từng Điều và Khoản, dựa trên một legal knowledge graph được cập nhật liên tục.

Ngày: 2026-08-23  
Corpus: `vbpl.vn` qua Hugging Face - `th1nhng0/vietnamese-legal-documents`  
Trạng thái: Đã phê duyệt để build

## Các quyết định đã chốt

### Phạm vi MVP

Full pipeline, thin slice.

Retrieval + mở rộng graph + LLM judgment, chạy end-to-end, nhưng xây tối thiểu.

### Corpus

Tập dữ liệu curated - 171.556 văn bản.

Metadata giàu thông tin, gồm hiệu lực, loại văn bản, và graph quan hệ 1.033.255 cạnh.

### Truy cập LLM

Frontier models qua OpenRouter.

Pin phiên bản model; định tuyến nhà cung cấp ZDR / no-training để bảo vệ riêng tư bản thảo.

### Knowledge graph

Thiết kế để cập nhật được.

Ingestion dạng append-only, có version, dựa trên delta. Chi phí cập nhật tỷ lệ với kích thước delta.

## Tổng quan hệ thống

Năm giai đoạn, một báo cáo.

Luật sư đưa vào một quy định dự thảo hoặc cả một văn bản dự thảo. Hệ thống phân tách nó thành các truy vấn ở cấp Khoản/Điều; với mỗi khoản, hệ thống tạo một báo cáo tương thích có trích dẫn: các Điều/Khoản hiện hành nào liên quan, mỗi phần là mâu thuẫn, chồng lấp, hay tương thích, và mức độ nghiêm trọng của phát hiện theo thứ bậc pháp lý. RAG là xương sống của một trong năm giai đoạn.

### 01. Phân tách và lọc

Tách dự thảo thành các Điều/Khoản riêng; suy ra các bộ lọc có cấu trúc, gồm lĩnh vực, cấp bậc thứ bậc của văn bản được đề xuất, và hiệu lực = chỉ văn bản hiện hành.

### 02. Hybrid retrieval

BM25 + dense embeddings (`bge-m3`) trên các chunk cấp Điều, lọc bằng metadata, sau đó rerank bằng cross-encoder để lấy top khoảng 10 kết quả cho mỗi khoản.

### 03. Mở rộng graph

Với mỗi Điều ứng viên, đi theo các cạnh có kiểu: bị sửa đổi bởi / bị bãi bỏ bởi (text này có còn hiện hành không?), được hướng dẫn bởi (kéo Thông tư thi hành), trích dẫn (một hop ngữ cảnh).

### 04. Đánh giá từng cặp

Frontier LLM phân loại từng cặp `(khoản dự thảo, khoản truy xuất)`: mâu thuẫn / trùng lặp-chồng lấp / liên quan-tương thích, với lập luận dựa trên đoạn văn được trích dẫn.

### 05. Quy tắc và báo cáo

Logic thứ bậc xác định, gồm `lex superior`, `lex posterior`, `lex specialis` theo Luật Ban hành VBQPPL, xếp hạng mức độ nghiêm trọng; bộ composer xuất báo cáo có trích dẫn để luật sư kiểm chứng.

Pipeline truy vấn:

```text
Quy định dự thảo
  -> 1. Phân tách + bộ lọc
  -> 2. Hybrid retrieval: BM25 + dense + rerank
  -> 3. Mở rộng graph: amends / repeals / guides
  -> 4. LLM pairwise judgment
  -> 5. Rules + severity
  -> Báo cáo có trích dẫn
```

Legal knowledge graph và vector/BM25 index là một store transactional duy nhất: Postgres + pgvector, được giữ mới bằng update pipeline bên dưới.

Lập trường sản phẩm: mọi đầu ra là một phát hiện hỗ trợ, kèm trích dẫn chính xác theo `document -> chương -> điều -> khoản` để luật sư tự kiểm chứng, không bao giờ là kết luận có thẩm quyền. False negative là lỗi đắt giá; pipeline ưu tiên recall ở retrieval, rồi dùng judgment + rules để khôi phục precision.

## Mô hình dữ liệu

### Graph schema

Documents và articles là các node hạng một với định danh ổn định; mọi fact có thể thay đổi đều nằm trong một dòng có version, không bao giờ overwrite. Article ID mang tính xác định, ví dụ `{doc_id}:d5:k2` = Khoản 2, Điều 5, để edges, chunks và citations sống sót qua các lần re-ingestion.

| Bảng | Vai trò | Trường chính |
|---|---|---|
| `documents` | Một dòng cho mỗi văn bản; chỉ danh tính | `doc_id`, `so_ky_hieu`, `loai_van_ban`, `hierarchy_rank` |
| `document_versions` | Snapshot metadata + content dạng append-only | `doc_id`, `version_no`, `tinh_trang_hieu_luc`, `content_hash`, `seen_from` / `seen_to` |
| `articles` | Node Điều/Khoản với path phân cấp | `article_id`, `doc_id`, `path` (`phan/chuong/muc/dieu/khoan/diem`) |
| `article_versions` | Text đã parse theo từng version ingestion | `article_id`, `version_no`, `text`, `is_current`, `effective_status` |
| `doc_relations` | Cạnh do portal curate, 1,03M cạnh | `doc_id`, `other_doc_id`, `relationship`, `source='vbpl'`, `seen_from` / `seen_to` |
| `article_relations` | Cạnh cấp Điều/Khoản được extract | `from_article`, `to_article`, `relation`, `source='extracted'`, `model`, `confidence` |
| `chunks` | Đơn vị retrieval = article versions | `chunk_id = article_version_id`, `embedding`, `embedding_model`, `tsvector`, `is_current` |
| `ingest_ledger` | Trạng thái phát hiện delta | `doc_id`, `metadata_hash`, `content_hash`, `last_snapshot`, `status` |
| `report_citations` | Báo cáo nào trích dẫn article version nào | `report_id`, `article_version_id`, `stale` |

Hai trục thời gian được ghi nhận và giữ riêng:

- System time: `seen_from` / `seen_to`, tức thời điểm pipeline biết một fact.
- Legal time: ngày có hiệu lực / ngày hết hiệu lực, tức thời điểm văn bản có hiệu lực pháp lý.

MVP chỉ query "pháp luật hiện hành", nhưng layout bitemporal này giúp truy vấn point-in-time, ví dụ "năm 2023 quy định nào đang có hiệu lực?", trở thành tính năng sau này chứ không phải tái kiến trúc.

Article-level edge extraction nâng cấp graph document-to-document của portal lên đúng độ mịn mà sản phẩm hứa hẹn. Các văn bản sửa đổi nêu đích rõ mục tiêu, ví dụ "Sửa đổi, bổ sung Điều 5 của...", sẽ được parse bằng regex patterns, kèm một LLM rẻ tiền cho ca khó. Đây là grounded extraction, không phải suy diễn.

## Kiến trúc cập nhật

### Knowledge graph luôn mới

Văn bản mới được công bố liên tục; trạng thái hiệu lực thay đổi; sửa đổi được ban hành. Vì vậy graph được xây như một hệ append-only dựa trên delta: mỗi refresh là một snapshot run có chi phí tỷ lệ với phần thay đổi, không tỷ lệ với toàn corpus.

Luồng cập nhật:

```text
Snapshot pull
HF refresh / vbpl.vn crawl
  -> Diff với ingest_ledger: metadata + content hashes
  -> Classify: NEW / META_CHANGED / CONTENT_CHANGED / MISSING
  -> Parse -> version -> embed -> index
```

Nhánh con:

- `NEW`: tạo `doc_version` mới.
- `META_CHANGED`: ví dụ validity flip.
- `CONTENT_CHANGED`: re-parse các article thay đổi, chỉ re-embed các article đó.
- `MISSING`: tombstone.
- Propagate: tính lại `effective_status` cho subgraph bị ảnh hưởng.
- Invalidate stale report citations.
- Chạy report: counts + anomalies.

Refresh job được schedule bằng cron và idempotent: chạy lại cùng một snapshot thì không làm gì.

### Cơ chế

**Ingest ledger + hashing.** Mỗi văn bản đầu vào được phân loại theo `(metadata_hash, content_hash)` đã lưu: `NEW`, `META_CHANGED`, `CONTENT_CHANGED`, `UNCHANGED`, `MISSING`. Chỉ văn bản thay đổi mới đi qua parse -> chunk -> embed.

**Append-only versions, tombstones cho deletion.** Không update tại chỗ; các dòng bị thay thế được đóng dấu `seen_to` và `is_current=false`. Lịch sử có thể query; rollback đơn giản.

**Incremental propagation.** Khi văn bản X thay đổi, tập bị ảnh hưởng được tính bằng graph closure: các article của X cộng hàng xóm qua cạnh `amends/repeals/guides`. `effective_status` phái sinh chỉ được tính lại cho subgraph đó. Article-edge extraction chỉ chạy lại cho các văn bản sửa đổi có thay đổi.

**Đồng bộ index transactional.** Vector và full-text index nằm trong cùng Postgres với graph, nên một delta commit cập nhật graph và index một cách atomic. Không có drift giữa "graph biết gì" và "search trả về gì". Query lọc theo `is_current`.

**Versioning embedding model.** Mỗi chunk ghi lại `embedding_model`; nâng cấp embedder trở thành một batch migration có theo dõi, không phải rebuild đồng loạt trong một ngày cắt chuyển.

**Nguồn gốc cạnh.** Cạnh portal (`source='vbpl'`) và cạnh extract (`source='extracted'`, có `model + confidence`) không bao giờ bị merge âm thầm; dữ liệu portal mới có thể sửa cạnh extract, nhưng không ngược lại.

**Vô hiệu hóa báo cáo.** `report_citations` nối các phân tích cũ với article versions mà chúng đã trích dẫn; khi một version bị thay thế, các báo cáo bị ảnh hưởng được flag. Sau này có thể thông báo "một văn bản được trích dẫn trong báo cáo của bạn đã thay đổi".

### Vì sao không dùng cách xây dựng kiểu GraphRAG?

LLM entity-graph extraction phù hợp với corpus không có graph. Corpus này đã có một graph chính thức, do con người curate. Phần construction duy nhất là parse cạnh cấp Điều/Khoản từ các phát biểu sửa đổi rõ ràng. Cách này rẻ, kiểm chứng được, và có thể chạy lại theo từng delta.

## Model stack

### Sử dụng LLM hai tầng qua OpenRouter

| Stage | Model tier | Ghi chú |
|---|---|---|
| Embeddings | `bge-m3` local | Đa ngôn ngữ, mạnh trên benchmark pháp lý tiếng Việt; chỉ đổi nếu eval cho thấy đây là nút thắt. |
| Reranking | `bge-reranker-v2-m3` local | Cross-encoder trên top khoảng 100 ứng viên mỗi khoản. |
| Pairwise judgment | Frontier, lớp Claude/GPT | Volume thấp mỗi query, khoảng 10-50 cặp; chất lượng là sản phẩm. Pin version model. |
| Bulk offline: edge extraction, decomposition | Model rẻ và nhanh | Volume cao, có tính cơ học; regex trước, LLM cho phần còn lại. |

OpenRouter được cấu hình với provider allowlist / cờ ZDR, để bản thảo của luật sư chỉ được route tới provider không training, không retention; phiên bản model được pin để đảm bảo eval lặp lại được.

## Phân bổ nhóm

### Năm agent, một thin slice

**Data & Graph Engineer**  
Chạy đầu tiên - nắm ground truth.

- Ingestion Parquet.
- Chuyển HTML thành parser `Phan/Chuong/Muc/Dieu/Khoan`.
- Versioned schema, ingest ledger, delta pipeline.
- Job extract cạnh cấp Điều/Khoản.

**Retrieval Engineer**  
Chất lượng tìm kiếm.

- Chunking cấp Điều với metadata phân cấp.
- Hybrid index: pgvector + FTS + reranker.
- API retrieval có lọc metadata; incremental upsert.

**Conflict-Analysis Engineer**  
Lõi đánh giá.

- Phân tách clause; logic mở rộng graph.
- Prompt pairwise LLM judgment + structured outputs.
- Rule engine thứ bậc; report composer.

**App Engineer**  
Bề mặt dành cho luật sư.

- FastAPI backend; UI paste draft -> report.
- Render citation, cảnh báo hiệu lực + sửa đổi.
- Cấu hình OpenRouter, pin model, ZDR routing.

**Evaluation Engineer**  
Biết hệ thống có hoạt động hay không.

- Weak-label gold set từ các cạnh repeal/amend.
- Retrieval recall@k; judgment precision/recall.
- Ablation: hybrid vs dense, graph vs no graph.

### Trình tự

Data & Graph Engineer chạy trước và giao một sample slice, gồm một lĩnh vực pháp lý và vài nghìn văn bản, trong versioned schema. Bốn người còn lại build song song dựa trên slice đó; scale lên full 171K corpus là một lần chạy script, không phải code mới.

## Thin slice và rủi ro

### Definition of done

MVP hoàn thành khi: một luật sư paste một quy định dự thảo vào web UI và nhận được, trong khoảng một phút, một báo cáo theo từng khoản trên sample sector. Mỗi phát hiện được phân loại: conflict / overlap / related, được xếp hạng mức độ nghiêm trọng theo thứ bậc, và trích dẫn tới đúng Điều/Khoản với flag current-validity và amended-by. Eval harness báo cáo retrieval recall@k và judgment precision/recall trên weak-label set.

### Rủi ro

**Parsing.** HTML pháp lý Việt Nam không đồng nhất qua các thập kỷ; parser cần fallback path, ví dụ tách phẳng theo Điều, và metric chất lượng parse ngay từ ngày đầu.

**False positives.** Gắn cờ conflict với text đã bị bãi bỏ hoặc đã bị sửa đổi sẽ phá niềm tin ngay lập tức. Validity và amendment flags phải được enforce trong retrieval filter, không chỉ hiển thị.

**False negatives.** Đây là lỗi đắt giá. Retrieval được tune theo recall trước; eval gold set tồn tại chính để đo tỷ lệ bỏ sót trước khi luật sư phát hiện.

**Eval validity.** Weak labels từ cạnh repeal/amend chỉ xấp xỉ conflict; cần một tập nhỏ được kiểm tra thủ công, và sau này là các báo cáo rà soát của Bộ Tư pháp, để hiệu chuẩn chúng.

Rà Soát Blueprint - `gov_law_assistant`
