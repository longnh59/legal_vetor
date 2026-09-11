# Engine bóc tách văn bản pháp luật Việt Nam — Plan & Handoff

> Tài liệu bàn giao để tiếp tục với Claude Code. Gồm: hiện trạng dữ liệu (đã kiểm chứng),
> quyết định kiến trúc, mô hình dữ liệu, pipeline, danh sách bẫy, lộ trình, và prompt sẵn dùng.
>
> Cập nhật: 2026-09-11

---

## 1. Mục tiêu

Xây engine tự động bóc tách văn bản quy phạm pháp luật Việt Nam thành cây có cấu trúc, phục vụ:

1. **Tra cứu ngữ nghĩa (vector DB / RAG)** — truy vấn bằng ngôn ngữ tự nhiên, trả về đúng khoản/điều.
2. **Quan hệ pháp lý** — sửa đổi, bổ sung, thay thế, bãi bỏ, dẫn chiếu, căn cứ; kèm thời hạn và đối tượng áp dụng (những thứ **đã có sẵn trong văn bản**, không suy diễn).
3. **Liên kết theo ý nghĩa** — nối các điều luật có nội dung liên quan, kể cả khi không dẫn chiếu nhau.

Yêu cầu chất lượng: **tách đúng là ưu tiên số một**. Một hệ thống tra cứu pháp luật trả sai khoản còn tệ hơn không trả.

---

## 2. Hiện trạng dữ liệu — đã kiểm chứng trực tiếp

Nguồn: `huggingface.co/datasets/th1nhng0/vietnamese-legal-documents` (crawl từ **vbpl.vn** — Cổng thông tin VBQPPL, Bộ Tư pháp). CC BY 4.0, refresh 2026-07-23.

### 2.1 Repo HF có HAI bộ dữ liệu khác nhau — dễ nhầm

| Thư mục | Config | Cột nội dung | Dung lượng | Số bản ghi |
|---|---|---|---|---|
| `legacy/` | `legacy_content`, `legacy_metadata` | `content` = **plain text đã bóc tag** | ~3,5 GB (11 shard) | 518.235 / 518.601 |
| `data/` | `content`, `metadata`, `relationships` | `content_html` = **HTML thô** | ~430 MB | 170.824 / 171.556 / 1.033.255 |

**Kết luận:** phải dùng `data/`. Bộ đang có trong `D:\vnpt_opemetadata\datasets\vietnamese-legal-documents\{content,metadata}\` là **legacy** — đã bóc tag sẵn, mất hết tín hiệu class/style, không dùng làm nguồn chính được.

### 2.2 Schema

**`data/metadata.parquet`** (171.556 dòng) — gần như bê thẳng vào bảng `documents`:

```
id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban, ngay_co_hieu_luc,
ngay_het_hieu_luc, nguon_thu_thap, nganh, linh_vuc, co_quan_ban_hanh (551 giá trị),
chuc_danh, nguoi_ky, pham_vi, thong_tin_ap_dung, tinh_trang_hieu_luc
```
Tất cả đều là `string`; ngày ở dạng `DD/MM/YYYY` — phải parse, không tin kiểu dữ liệu.

**`data/content.parquet`** (170.824 dòng): `id` (string), `content_html` (string). **732 bản ghi metadata không có content** — phải xử lý như trường hợp hợp lệ, không phải lỗi.

**`data/relationships.parquet`** (1.033.255 dòng): `doc_id`, `other_doc_id`, `relationship`.
→ Quan hệ ở **mức văn bản**, có sẵn từ ngày đầu. **Không** cho biết điều nào sửa điều nào — đó là việc của engine (xem P7).

### 2.3 Đo trên bộ legacy (vẫn còn giá trị tham chiếu)

Đã đọc thử 3.000 văn bản của shard 10:

- **Phân bố độ dài rất lệch**: p50 ≈ 6,8 KB · p90 ≈ 36 KB · max ≈ 659 KB.
  Đa số là quyết định hành chính ngắn vài Điều; phần "đáng tra cứu" nằm ở đuôi dài.
  → Chiến lược sampling, ngân sách LLM và cách chia batch đều phải bám phân bố này, không chia đều theo số văn bản.
- **Một file thường chứa NHIỀU HƠN một văn bản.** Ví dụ Quyết định 3933/QĐ-UBND (Nghệ An): phần Quyết định có Điều 1–3, rồi đến khối *"QUY ĐỊNH (Ban hành kèm theo Quyết định số…)"* **đánh số Điều lại từ 1**, có Chương riêng. Nhóm "ban hành kèm theo" chiếm tỷ trọng rất lớn trong Quyết định và Thông tư.
  → **Đây là lỗi chí mạng nếu bỏ sót**: parser coi cả file là một cây sẽ thấy Điều 1,2,3,1,2,3… và hỏng toàn bộ. Phải tách `document_part` **trước khi** dựng cây.
- Ký tự Unicode tiếng Việt có cả dạng tổ hợp — **bắt buộc normalize NFC** trước mọi regex.

---

## 3. Quyết định kiến trúc

| Quyết định | Lý do |
|---|---|
| Nguồn = `data/` (HTML), không dùng `legacy/` | HTML giữ class/style/`<a href>` — tín hiệu cấu trúc mà bản plain text đã mất |
| Parser **deterministic trước, LLM sau** | Phải tái lập được 100%, debug được, không tốn tiền cho 170k văn bản |
| **Cascade nhiều tầng + chấm điểm tin cậy** | Không bộ rule nào đúng 100% cho 170k văn bản trải 30 năm và 551 cơ quan ban hành |
| **Thà báo lỗi còn hơn tách sai âm thầm** | Văn bản `failed` vào hàng đợi review; không index |
| PostgreSQL + `ltree` + `pgvector` + `tsvector` | Một DB lo cả cây, vector, full-text và graph (bảng `edges`). Chưa cần Neo4j |
| `node_id` dạng human-readable, bất biến | `nd-13-2023-nd-cp/p1/dieu-8/khoan-1/diem-a` — vector DB, graph, citation đều trỏ vào đây |
| Versioning thay vì ghi đè khi có sửa đổi | Tra cứu được "điều này quy định thế nào tại thời điểm T" |

---

## 4. Mô hình dữ liệu

### 4.1 Cây cấu trúc

```
document → document_part → Phần → Chương → Mục → Tiểu mục → Điều → Khoản → Điểm → (gạch đầu dòng)
```

`document_part` là tầng bắt buộc (mục 2.3): một file có thể chứa phần chính + nhiều phụ lục/quy định ban hành kèm theo, mỗi phần có hệ đánh số Điều độc lập.

### 4.2 Bảng `nodes`

| Cột | Ghi chú |
|---|---|
| `node_id` | PK, human-readable, bất biến. `<so-ky-hieu-slug>/<part>/dieu-8/khoan-1/diem-a` |
| `doc_id` | FK → documents |
| `part_id` | phần nào trong file |
| `parent_id`, `path` (`ltree`), `depth`, `order_index` | quan hệ cha–con, query cả nhánh bằng `path <@ 'x.y'` |
| `node_type` | `phan`/`chuong`/`muc`/`tieu_muc`/`dieu`/`khoan`/`diem`/`gach_dau_dong`/`preamble`/`phu_luc` |
| `number_raw`, `number_norm` | `"8a"` / `"8a"`; `"đ"` giữ nguyên |
| `heading` | tiêu đề Điều (nếu có) |
| `text` | nội dung riêng của node |
| `text_full` | node + toàn bộ con — dùng cho small-to-big retrieval |
| `breadcrumb` | `"Luật Dữ liệu 60/2024/QH15 › Chương II › Điều 8. Quản lý nhà nước… › Khoản 1"` |
| `html_raw` | HTML gốc của node — cần để dựng lại bảng biểu |
| `confidence`, `classified_by` | `regex`/`css_class`/`style`/`llm`; điểm tin cậy |
| `valid_from`, `valid_to` | bitemporal (P7) |

### 4.3 Bảng `edges`

```
edge_id, src_node_id, dst_node_id (hoặc dst_doc_id), edge_type,
source ('rule' | 'llm' | 'human' | 'dataset'), confidence, evidence_text, effective_from
```

**Cạnh trích từ chính văn bản** (`source` ≠ `llm`):
`REFERENCES` · `AMENDS` · `SUPPLEMENTS` · `REPLACES` · `REPEALS` · `GUIDES` · `BASED_ON`

**Cạnh suy luận** (P8) — lưu riêng, **không trộn** với cạnh trên:
`SIMILAR_TO` · `SAME_TOPIC` · `POTENTIAL_CONFLICT`

Nguyên tắc: cạnh "luật ghi" và cạnh "máy đoán" phải phân biệt được bằng truy vấn, mãi mãi.

### 4.4 Thuộc tính rút từ văn bản

- `pham_vi_dieu_chinh` — thường Điều 1
- `doi_tuong_ap_dung` — thường Điều 2
- `thoi_han` — regex: `trong thời hạn (\d+) (ngày|tháng|năm)`, `kể từ ngày`, `chậm nhất là`, `không quá`
- `che_tai`, `co_quan_chu_tri`

---

## 5. Pipeline bóc tách — 5 tầng

```
content_html
 → [T1] Clean & normalize
 → [T2] Flatten thành block stream
 → [T3] Split document_part
 → [T4] Classify từng block (cascade) + Build tree
 → [T5] Validate + scoring
```

### T1 — Clean
Bỏ `<script>/<style>/<head>`; unwrap `<font>/<span>` rỗng; `&nbsp;`/`\u00a0` → space;
**Unicode NFC**; chuẩn hoá dấu ngoặc, gạch ngang, dấu chấm; gộp whitespace.
**Giữ `<table>` nguyên khối**, không flatten.

### T2 — Flatten
```python
{ text, tag, classes, style_indent, is_bold, is_italic, is_center,
  is_table, html_raw, dom_order, anchors: [href...] }
```
Giữ `html_raw` để dựng lại bảng và link.

### T3 — Split document_part
Nhận diện ranh giới: dòng in hoa căn giữa kiểu `QUY ĐỊNH` / `QUY CHẾ` / `ĐIỀU LỆ` / `DANH MỤC` / `PHỤ LỤC ...`
theo sau bởi `(Ban hành kèm theo ...)`, **hoặc** số Điều đang tăng bỗng quay về 1.
Mỗi part có hệ đánh số riêng.

### T4 — Classify (cascade, dừng ở tầng đầu tiên chắc chắn)

| Tầng | Tín hiệu | Độ tin |
|---|---|---|
| A | Regex text: `^Điều\s+(\d+[a-zđ]?)[.\s]`, `^Chương\s+([IVXLC]+)`, `^Mục\s+\d+`, `^\d+\.\s`, `^([a-zđ])\)\s` | cao |
| B | Class CSS đã map từ profiling | cao |
| C | Style: indent level + bold + độ dài dòng | trung bình |
| D | LLM — **chỉ cho block mơ hồ còn lại**, batch, schema cố định | thấp–trung bình |

**A và B phải khớp nhau.** Lệch nhau ⇒ đánh dấu `conflict`, hạ `confidence` của văn bản.
Đây là cơ chế phát hiện lỗi rẻ nhất có được — dùng triệt để.

Phân biệt **khoản** với **danh sách đánh số trong nội dung**: không phân loại từng block độc lập, mà dùng ràng buộc chuỗi — (a) số phải liên tục từ 1, (b) tổ tiên gần nhất phải là `dieu`, (c) indent nhất quán.

### T4b — Build tree
State machine + stack. Ràng buộc:
- Số thứ tự cùng cấp tăng liên tục
- Nhảy cóc (3 → 7) ⇒ nghi phân loại sai ⇒ thử chiến lược khác hoặc đánh cờ
- Block không nhận dạng được ⇒ **nối vào node trước** (đoạn tiếp nối), **không vứt đi**

---

## 6. Danh sách bẫy — xử lý sẵn, đừng đợi gặp

1. **Điểm `đ`.** Bảng chữ cái điểm: `a b c d đ e g h i k l m n o p q r s t u v x y` — không có `f j w z`. Sequence validator phải dùng đúng bảng này.
2. **`Điều 8a`, `Điều 12b`** — điều bổ sung bởi văn bản sửa đổi. Regex phải cho hậu tố chữ.
3. **Bảng biểu** — nội dung trong `<table>` đầy `1.`, `a)` sẽ phá parser. Cô lập thành block atomic ngay ở T2.
4. **Khối "Căn cứ…"** đầu văn bản — không thuộc Điều nào. Gán node `preamble`; đây chính là nguồn cạnh `BASED_ON`.
5. **Phụ lục / Biểu mẫu** (Mẫu số 01, Phụ lục I) — cấu trúc khác hẳn. Tách riêng, **không** ép vào cây Điều.
6. **Văn bản hợp nhất (VBHN)** — có footnote đánh dấu nội dung đã sửa. Nhận diện và tách riêng, nếu không chú thích lẫn vào điều luật.
7. **Chữ ký / Nơi nhận** cuối văn bản — căn giữa, in đậm. Cắt bằng heuristic vị trí + pattern (`Nơi nhận:`, `TM. CHÍNH PHỦ`, `KT. BỘ TRƯỞNG`).
8. **Văn bản cũ (trước ~2005)** — không có cấu trúc Điều rõ, hoặc là ảnh scan. Đánh nhãn `unstructured`, **loại khỏi index chính**.
9. **Khoản không đánh số** — Điều chỉ có một đoạn. Tạo node ẩn `khoan-0` để ID luôn đồng nhất.
10. **Thẻ `<a href>` sẵn có** — vbpl.vn đã link nhiều trích dẫn. Lấy `href` ⇒ có ngay cạnh `REFERENCES` chính xác, **khỏi cần NLP**. Ưu tiên khai thác trước khi viết citation parser.
11. **Nhiều văn bản trong một file** (mục 2.3) — nghiêm trọng nhất. Xử lý ở T3.
12. **732 bản ghi metadata không có content** — trường hợp hợp lệ, không phải lỗi.

---

## 7. Validator — thứ quyết định "chính xác"

Mỗi văn bản chấm điểm, lưu vào `parse_quality`:

| Chỉ số | Ngưỡng |
|---|---|
| `char_coverage` = ký tự trong cây / ký tự text gốc | **> 0,97** — dưới ngưỡng là mất nội dung |
| `sequence_ok` | không đứt số ở mọi cấp |
| `hierarchy_ok` | không có khoản mồ côi, không đảo cấp |
| `part_count` | khớp số khối "ban hành kèm theo" nhận diện được |
| `conflict_rate` | tỷ lệ block mà tầng A và B bất đồng |
| `table_preserved` | số bảng vào = số bảng ra |

Phân loại: `clean` (index bình thường) · `warn` (index, gắn cờ) · `failed` (không index, vào hàng đợi review).

**Mục tiêu thực tế: ~85–92% `clean` ở lần chạy đầu.** Đặt mục tiêu 100% là tự lừa mình.

**Golden set — 30 văn bản tách tay**, chọn trải đều họ template (từ profiling) và đủ loại: luật, nghị định, thông tư, quyết định (có "ban hành kèm theo"), VBHN, văn bản sửa đổi, văn bản trước 2005, văn bản có nhiều bảng biểu. Snapshot test chạy mỗi lần đổi rule — đây là thứ cho phép sửa rule mà không sợ vỡ chỗ khác.

---

## 8. Lộ trình

| Phase | Nội dung | Xong là có gì |
|---|---|---|
| **P0** | Tải `data/`, viết loader, **profiling corpus** | Báo cáo class/template — input để thiết kế rule |
| **P1** | T1–T2 (clean + flatten) + golden set 30 văn bản | Block stream chuẩn, có chuẩn đối chiếu |
| **P2** | T3 (split part) + T4 (classify A+B+C, build tree), **chưa dùng LLM** | Cây điều/khoản/điểm |
| **P3** | T5 validator + scoring + báo cáo chất lượng toàn corpus | Biết chính xác bao nhiêu % đạt, hỏng ở đâu |
| **P4** | Tầng D (LLM cho phần mơ hồ) + vòng lặp cải thiện rule theo lỗi thật | Nâng tỷ lệ `clean` |
| **P5** | PostgreSQL + `ltree`, nạp `metadata` + `relationships` | Tra cứu theo cấu trúc |
| **P6** | Chunking + embedding + hybrid search (BM25 + dense + rerank) | RAG hoạt động |
| **P7** | Hạ phân giải quan hệ sửa đổi xuống mức Điều/Khoản + bitemporal | Tra cứu theo mốc thời gian |
| **P8** | Liên kết ngữ nghĩa, phát hiện xung đột | Nối điều luật theo ý nghĩa |

### Ghi chú thiết kế cho P6 (chunking)

- **Đơn vị chunk = Khoản** (Điều nếu quá ngắn). Điểm quá nhỏ → gộp vào Khoản cha.
- Mỗi chunk embed **kèm breadcrumb + tên văn bản + heading Điều** — giải quyết việc "khoản 2" đứng một mình không có ngữ cảnh.
- **Parent-child retrieval**: match ở mức Khoản, trả về `text_full` của Điều cha.
- **Hybrid**: BM25 trên tiếng Việt có dấu (rất quan trọng với thuật ngữ pháp lý) + dense vector + rerank.
- `EmbeddingProvider` là interface — đổi model không phải rebuild pipeline.

### Ghi chú thiết kế cho P7

`relationships.parquet` cho sẵn cặp `doc_id → other_doc_id` có nhãn sửa đổi. Việc của engine là **hạ độ phân giải**: với mỗi cặp đó, parse text văn bản sửa đổi để tìm `target_node_id` cụ thể — `{action, target_node_id, new_text?, effective_from}`, đủ để **áp dụng được** chứ không chỉ để đọc. Có sẵn cặp doc→doc khiến bài toán này dễ hơn nhiều (không phải resolve mù).
Amendment engine sinh **phiên bản mới của node**, không ghi đè. Vector DB chỉ index bản đang hiệu lực; bản cũ vẫn giữ để tra lịch sử.

---

## 9. Tiến độ đến hiện tại

**Đã xong:**
- ✅ Xác định đúng nguồn dữ liệu và phát hiện nhầm lẫn `legacy/` vs `data/` — tránh xây parser trên bộ đã mất tag
- ✅ Đọc được schema thật của cả hai bộ (đã tự viết parquet reader thuần Python vì môi trường không cài được `pyarrow`)
- ✅ Đo phân bố độ dài văn bản, phát hiện bẫy "nhiều văn bản trong một file"
- ✅ Chốt mô hình dữ liệu, pipeline 5 tầng, bộ validator, lộ trình P0–P8

**Đang chờ:** tải `data/content.parquet` (412 MB), `data/metadata.parquet`, `data/relationships.parquet` từ HF về `D:\vnpt_opemetadata\datasets\vietnamese-legal-documents\data\`.

```powershell
cd D:\vnpt_opemetadata\datasets\vietnamese-legal-documents
uv run --with huggingface_hub --with pyarrow python -c @"
from huggingface_hub import hf_hub_download
import pyarrow.parquet as pq, os, shutil
os.makedirs('data', exist_ok=True)
for f in ['content.parquet','metadata.parquet','relationships.parquet']:
    p = hf_hub_download('th1nhng0/vietnamese-legal-documents', f'data/{f}', repo_type='dataset')
    shutil.copy(p, f'data/{f}'); print('OK', f, os.path.getsize(f'data/{f}')//10**6, 'MB')
print(pq.read_schema('data/content.parquet'))
"@
```

**Việc kế tiếp:** chạy P0 — profiling.

---

## 10. Prompt cho Claude Code (P0 → P3)

> Copy nguyên khối dưới đây vào Claude Code, chạy trong thư mục repo.
> Tài liệu này (`PLAN_v2_engine_boc_tach_vbpl.md`) nên để cùng thư mục để Claude Code đọc kèm.

````markdown
# Nhiệm vụ

Xây phần lõi của engine bóc tách văn bản quy phạm pháp luật Việt Nam: từ HTML thô → cây
điều/khoản/điểm có kiểm chứng chất lượng. Phạm vi lần này là **P0 → P3**; chưa làm vector DB,
chưa làm LLM, chưa làm bitemporal.

Đọc kỹ `PLAN_v2_engine_boc_tach_vbpl.md` trong repo trước khi viết dòng code đầu tiên —
đặc biệt mục 2 (hiện trạng dữ liệu), mục 6 (danh sách bẫy) và mục 7 (validator).

**Bỏ qua toàn bộ code bóc tách đã có trong repo** (`files/vbpl_extract.py`, `files/vbpl_store.py`,
`crawler/`, `PLAN.md` cũ). Chúng chưa chính xác. Có thể tham khảo để biết đã thử gì, nhưng
không kế thừa. Viết mới trong package `engine/`.

## Dữ liệu

`data/content.parquet` — cột `id` (string), `content_html` (string), 170.824 dòng
`data/metadata.parquet` — 171.556 dòng, 16 cột, **tất cả đều là string, ngày dạng DD/MM/YYYY**
`data/relationships.parquet` — 1.033.255 dòng: `doc_id`, `other_doc_id`, `relationship`

Nguồn: vbpl.vn. HTML là **Word → HTML export**, không phải HTML ngữ nghĩa: class có mang thông tin
nhưng **không nhất quán** giữa các thời kỳ và 551 cơ quan ban hành; style inline
(`text-indent`, `margin-left`, `font-weight`) mang thông tin cấp bậc nhiều hơn tưởng.

## Stack

Python 3.11+, `pydantic` cho schema, `typer` cho CLI, `lxml` cho HTML, `pyarrow` cho parquet,
`pytest` cho test. Chưa cần database ở phase này — ghi ra JSONL/parquet trung gian.

---

## P0 — Profiling corpus (làm trước tiên, ĐỪNG viết parser vội)

Mục tiêu: **không đoán class name**. Thiết kế rule dựa trên số liệu thật.

Chạy trên **toàn bộ 170.824 văn bản** (chỉ làm việc rẻ, không dựng cây):

1. Tần suất mọi `class` trên `<p>`, `<div>`, `<span>`, kèm **3 text mẫu mỗi class**
2. Phân bố `style` (`text-indent`, `margin-left`, `font-weight`) theo từng class
3. Tỷ lệ văn bản có `<table>`, có `<img>` (khả năng là scan), có `<a href>` (dẫn chiếu đã link sẵn)
4. Phân cụm văn bản theo **"chữ ký DOM"** (tập class đã sắp xếp) → ra 5–15 **họ template**
5. Regex `Điều` / `Chương` / `Mục` / `Khoản` / `Điểm` khớp bao nhiêu % văn bản
6. **Mức độ khớp/lệch giữa regex và class** — đây là chỉ số quan trọng nhất, nó chỉ thẳng ra
   parser sẽ gãy ở đâu
7. Bao nhiêu % văn bản có dấu hiệu **nhiều document_part** (số Điều quay về 1, hoặc có khối
   `(Ban hành kèm theo ...)`)
8. Phân bố độ dài, số Điều/văn bản, theo `loai_van_ban` và theo thập niên ban hành

Output: `profiling/corpus_profile.json` + `profiling/REPORT.md` đọc được bằng mắt.

Sau đó lấy **mẫu phân tầng ~5.000 văn bản** (phân tầng theo `loai_van_ban` × thập niên × họ
template) làm tập phát triển, và chọn ra **30 văn bản làm golden set** — trải đều họ template và
đủ các loại: luật, nghị định, thông tư, quyết định có "ban hành kèm theo", VBHN, văn bản sửa đổi,
văn bản trước 2005, văn bản nhiều bảng biểu.

**Dừng lại và báo cáo số liệu profiling trước khi sang P1.**

## P1 — Clean + Flatten

`engine/clean.py`: bỏ `<script>/<style>/<head>`, unwrap `<font>/<span>` rỗng, `&nbsp;` → space,
**Unicode NFC** (bắt buộc — tiếng Việt có dạng tổ hợp, không normalize là regex trượt),
chuẩn hoá dấu ngoặc/gạch ngang, gộp whitespace. **Giữ `<table>` nguyên khối.**

`engine/flatten.py`: DOM → list block, mỗi block giữ
`{text, tag, classes, style_indent, is_bold, is_italic, is_center, is_table, html_raw, dom_order, anchors}`.

Dựng golden set: 30 file JSON cây chuẩn, tách tay, trong `tests/golden/`.

## P2 — Split part + Classify + Build tree

`engine/split_parts.py` — **làm trước khi dựng cây**. Một file thường chứa nhiều văn bản:
phần chính (Điều 1..n) rồi `QUY ĐỊNH / QUY CHẾ / ĐIỀU LỆ / PHỤ LỤC (Ban hành kèm theo ...)`
với hệ đánh số Điều **bắt đầu lại từ 1**. Nhận diện bằng: dòng in hoa căn giữa + `(Ban hành kèm theo`,
hoặc số Điều đang tăng bỗng quay về 1.

`engine/classify.py` — cascade, dừng ở tầng đầu tiên chắc chắn:
- **A. Regex**: `^Điều\s+(\d+[a-zđ]?)[.\s]`, `^Chương\s+([IVXLC]+)`, `^Mục\s+\d+`,
  `^(\d+)\.\s`, `^([a-zđ])\)\s`
- **B. Class CSS** đã map từ profiling
- **C. Style**: indent + bold + độ dài dòng
- (Tầng D dùng LLM để sau, đừng làm bây giờ)

**A và B lệch nhau ⇒ ghi `conflict`, hạ `confidence`.** Không im lặng chọn một bên.

Phân biệt khoản với danh sách đánh số trong nội dung bằng **ràng buộc chuỗi**, không phân loại
block độc lập: số phải liên tục từ 1, tổ tiên gần nhất phải là `dieu`, indent nhất quán.

`engine/build_tree.py` — state machine + stack, ràng buộc số thứ tự liên tục.
Bảng chữ cái điểm tiếng Việt: `a b c d đ e g h i k l m n o p q r s t u v x y` (**không có f j w z**).
Cho phép `Điều 8a`. Block không nhận dạng được thì **nối vào node trước**, không vứt.
Điều chỉ có một đoạn → tạo node ẩn `khoan-0`.

`node_id` bất biến: `<slug so_ky_hieu>/<part>/dieu-8/khoan-1/diem-a`.
Mỗi node có `text`, `text_full` (node + con), `breadcrumb`, `html_raw`.

Khai thác `<a href>` có sẵn trong HTML để sinh cạnh `REFERENCES` — chính xác, khỏi cần NLP.

## P3 — Validator

`engine/validate.py` tính cho mỗi văn bản:
`char_coverage` (> 0,97), `sequence_ok`, `hierarchy_ok`, `part_count`, `conflict_rate`,
`table_preserved` → xếp loại `clean` / `warn` / `failed`.

Chạy toàn corpus, xuất `reports/quality.parquet` + `reports/QUALITY.md`:
tỷ lệ từng loại, **top 20 mẫu lỗi phổ biến nhất kèm ví dụ cụ thể**, phân rã theo
`loai_van_ban` / thập niên / họ template.

Snapshot test golden set chạy trong `pytest`.

## CLI

```
python -m engine profile              # P0
python -m engine parse <doc_id>       # 1 văn bản, in cây ra stdout
python -m engine parse-all            # toàn corpus → parquet
python -m engine validate             # báo cáo chất lượng
python -m engine show <node_id>
```

## Nguyên tắc bắt buộc

1. **Thà báo lỗi còn hơn tách sai âm thầm.** Văn bản `failed` không được index.
2. **Không dùng LLM ở P0–P3.** Rule phải deterministic và tái lập 100%.
3. **Mọi ngưỡng để trong `engine/config.py`**, không rải magic number khắp code.
4. **Mỗi bước ghi file trung gian kiểm tra được** — đừng làm pipeline một cục.
5. Mục tiêu thực tế **85–92% `clean`** ở lần chạy đầu. Đừng tinh chỉnh rule để ép lên 100%
   trên golden set — sẽ overfit.
6. Sau P0 và sau P3, **dừng lại báo cáo số liệu** trước khi đi tiếp.
````
