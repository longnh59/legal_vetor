# So sánh 3 nguồn VBPL & kế hoạch triển khai

## 1. Bảng so sánh

| Tiêu chí | **th1nhng0/vietnamese-legal-documents** | **tmquan/vbpl-vn** | **Monmoonluna/vbpl-vn-legal-corpus** |
|---|---|---|---|
| Số văn bản | **171.556** metadata / 170.824 có body | 158.822 (147.317 có body, 11.505 `markdown=null`) | ~42.000 (**chỉ Trung ương**) |
| Phạm vi | TW + địa phương | TW (34%) + địa phương (66%) | Chỉ TW |
| Dạng body | **HTML thô** (chưa làm sạch) | **Markdown đã làm sạch** (bóc CSS/Word junk, giảm 42% ≈ 1,77 GB) | `text_clean` |
| Cấu trúc Chương/Điều/Khoản | **Không có** | **Trên danh nghĩa có** (`structure_json`: section→paragraph→sentence) nhưng `num_sections` = 1 cho **mọi** dòng, median paragraph = 1 → thực chất **phẳng**, không phải Điều/Khoản | **Có thật**: `provision_tree_json` + `chunks.parquet` 447k chunk chia theo Điều/Khoản |
| Quan hệ giữa VB | **1.033.255 cạnh**, 14+ loại | `statute_refs` trong `extracted_json` (mức text, chưa resolve) | ~37k cạnh + **`provision_relations.jsonl` mức Điều/Khoản** |
| NER / trích xuất | Không | **Có** (DATE, ARTICLE, ORG-COURT, statute linker, kèm char offset) | Không |
| Chuẩn hoá tiếng Việt | Không (NFC tuỳ nguồn) | **Có** (ftfy NFC + Toà→Tòa, thuỷ→thủy) | Một phần |
| Metadata | 17 trường, tiếng Việt | ~28 trường + `scope`, `doc_type` slug, `legal_area` | ~50 cột, có flags (`is_consolidated`…) |
| Cập nhật gần nhất | **2026-07-23** | 2026-05-23 | không ghi rõ |
| Tần suất | Có changelog, refresh theo đợt (~vài tháng) | Rerun tháng 5/2026 | Một lần |
| Kích thước | 4,37 GB | 3,86 GB | 7,96 GB |
| Độ tin cậy cộng đồng | 1.488 tải/tháng, 43 like, **có DOI** | 2.876 tải/tháng, 7 like | 114 tải/tháng, 0 like, **dataset viewer đang lỗi** |
| Code crawler công khai | Có (Scrapy, trong repo) | Có (github tmquan/ViLA) | Có (github Monmoonluna/LEGALSEARCHVN_LOCALAI) |
| Giấy phép | CC-BY-4.0 | CC-BY-4.0 | CC-BY-SA-4.0 (**viral**, cẩn thận nếu nội bộ DN) |

### Kết luận nhanh
- **th1nhng0** = xương sống: coverage rộng nhất, graph quan hệ mạnh nhất, mới nhất, có DOI.
  Nhược: HTML bẩn, không cấu trúc.
- **tmquan** = lớp text sạch + NER. **Đừng tin cái "structure layer"** — nó không phải Chương/Điều.
  Giá trị thật: markdown đã bóc rác + entity offset + `scope`/`legal_area`.
- **Monmoonluna** = đối chứng cấu trúc. Nhược: coverage 1/4, license SA, độ chín thấp.
  Dùng để **benchmark parser của mình**, không dùng làm nguồn chính.

---

## 2. Kiến trúc kết hợp (khuyến nghị)

```
th1nhng0.metadata      ──┐
th1nhng0.relationships ──┤  → documents + doc_edges   (nguồn chân lý về VB & quan hệ)
th1nhng0.content_html  ──┘
                          ↘
tmquan.markdown          ──→  body ưu tiên (sạch hơn) ; fallback = HTML th1nhng0
tmquan.extracted_json    ──→  seed NER/statute_refs để đối chiếu
                          ↘
        PARSER CỦA MÌNH  ──→  provisions (cây thật) + chunks + amendments
                          ↗
Monmoonluna.chunks       ──→  chỉ dùng làm tập đối chiếu độ chính xác
```

Khoá join: `so_ky_hieu` đã chuẩn hoá (bỏ tiền tố "Nghị quyết số:", bỏ hậu tố
"(A11)", "ngày 18/5/2007"). ID nội bộ 3 nguồn **không khớp nhau** — đừng join
bằng `doc_id`.

---

## 3. Kế hoạch 6 giai đoạn

**GĐ 0 — Khảo sát (2 ngày)**
Tải `metadata` (nhẹ) của cả 3, đối chiếu `so_ky_hieu` để đo độ phủ chồng lấn.
Lấy 200 VB đại diện (phân tầng theo loại VB × thập niên × TW/ĐP) làm golden set.

**GĐ 1 — Bronze (3 ngày)**
Đổ raw vào object storage/Parquet, mỗi bản ghi có `content_hash`.
Không sửa gì ở tầng này. Hash là thứ cho phép crawl lại chỉ phần thay đổi.

**GĐ 2 — Chọn body & chuẩn hoá (3 ngày)**
Với mỗi `so_ky_hieu`: ưu tiên `tmquan.markdown` → nếu null lấy
`th1nhng0.content_html` qua `html_to_lines()`. Chuẩn hoá NFC + dấu thanh.

**GĐ 3 — Parse cấu trúc (2 tuần — phần nặng nhất)**
Chạy parser, chấm điểm trên golden set 200 VB. Ngưỡng chấp nhận:
- `Điều` recall ≥ 99% (dễ, mốc rất rõ)
- `Khoản` precision ≥ 95% (khó nhất: `1.` giả trong bảng/danh sách)
- `Điểm` ≥ 97%
- % dòng "mồ côi" (không gắn được vào node nào) < 2%
Cái nào không đạt → đẩy sang hàng đợi review thủ công, **không nhét đại vào cây**.

**GĐ 4 — Resolve quan hệ (1 tuần)**
Nối `citations`/`amendments` từ text với `documents.so_ky_hieu`.
Đối chiếu với `th1nhng0.relationships` — chênh lệch chính là chỗ parser sai.
Sinh `provision_versions` từ các lệnh sửa đổi.

**GĐ 5 — Chunk + embed + serve (1 tuần)**
Chunk theo Điều, tách Khoản khi > 2.200 ký tự, prepend context header.
Embed → pgvector. Hybrid BM25 + dense, rerank.

**GĐ 6 — Cập nhật định kỳ**
- Hàng tháng: crawl delta `vbpl.vn` bằng crawler của th1nhng0 (`-a resume=1`), so `content_hash`.
- Hàng quý: đối chiếu lại với bản refresh mới của th1nhng0/tmquan.
- Không bao giờ overwrite: VB đổi → version mới, đóng `valid_to` version cũ.

---

## 4. Danh mục thành phần bóc tách được

| Nhóm | Thành phần | Trạng thái parser |
|---|---|---|
| Thể thức | Quốc hiệu, tiêu ngữ | ✅ |
| | Cơ quan ban hành | ✅ |
| | Số, ký hiệu | ✅ |
| | Địa danh + ngày ban hành | ✅ |
| | Loại văn bản | ✅ |
| | Trích yếu | ✅ (đôi khi dính dòng thừa với VBHN) |
| | Căn cứ pháp lý (list) | ✅ |
| Nội dung | Phần / Chương / Mục / Tiểu mục | ✅ |
| | Điều (kể cả Điều 4a) | ✅ |
| | Khoản (kể cả 1a) | ✅ |
| | Điểm (a…y, không f/j/w/z) | ✅ |
| | Tiết (gạch đầu dòng) | ✅ |
| Kết thúc | Nơi nhận | ✅ |
| | Chức danh + người ký | ✅ |
| Phụ lục | Phụ lục / biểu mẫu / bảng | ✅ tách riêng, **không** đưa vào cây |
| Ngữ nghĩa | Trích dẫn VB khác | ✅ |
| | Trích dẫn nội bộ (điểm a khoản 2 Điều 103) | ✅ |
| | Lệnh sửa đổi/bổ sung/bãi bỏ + đích | ✅ |
| | Ngày hiệu lực / hết hiệu lực | ✅ |
| | Định nghĩa thuật ngữ → glossary | ✅ |
| | Ghi chú VBHN (footnote) | ⚠️ lọc được dòng ghi chú, nhưng chỉ số footnote dính vào text khoản (`2.1` → text bắt đầu bằng `1`) |
| | Nghĩa vụ / chế tài / chủ thể | ❌ chưa — cần lớp NER riêng |

---

## 5. Kết quả chạy thử (6 VB mẫu phủ ca khó)

```
docs=6  provisions=54  chunks=16  definitions=7  amendments=9
khoan=19  dieu=16  diem=10  chuong=4  tiet=4  muc=1
```

Cây bóc đúng tới 4 cấp lồng nhau:
```
ci.d3            Điều 3. Giải thích từ ngữ
ci.d3.k2         Khoản 2
ci.d3.k2.dmb     Điểm b
ci.d3.k2.dmb.t2  Tiết 2
```

Graph sửa đổi tự sinh:
```
tt_sua_doi AMEND  200/2014/TT-BTC Điều 9 Khoản 2
tt_sua_doi ADD    200/2014/TT-BTC Điều 15 Khoản 1
tt_sua_doi REPEAL 200/2014/TT-BTC Điều 27
qd_ubnd    ADD    20/2013/QĐ-UBND Điều 13 Khoản 4
```

Lỗi còn lại đã phát hiện: chỉ số footnote VBHN lẫn vào text
(`"1 Chứng từ kế toán"` thay vì `"Chứng từ kế toán"`).

---

## 6. Nguyên tắc lưu trữ cho vector DB

1. **`provision_id` = `<doc_id>:<path>`** (`luat_gdđt:ci.d3.k2.dma`).
   Đây vừa là khoá chính, vừa là citation key, vừa là chunk id. Ổn định qua
   mọi lần re-parse vì bắt nguồn từ chính số hiệu Điều/Khoản.
2. **Lưu cả cây lẫn breadcrumb phẳng.** Cây (`ltree`) để lấy ngữ cảnh cha/con;
   breadcrumb denormalize trên chunk để không phải JOIN lúc trả kết quả.
3. **Chunk = Điều, không phải N token.** Điều là đơn vị trích dẫn pháp lý tự
   nhiên. Chỉ tách xuống Khoản khi Điều quá dài.
4. **Prepend context header vào `embed_text`.** Số hiệu + trích yếu + breadcrumb.
   Đây là đòn bẩy lớn nhất cho chất lượng retrieval — lớn hơn cả việc chỉnh
   kích thước chunk. Lưu `raw_text` riêng để hiển thị.
5. **Denormalize cột lọc lên bảng chunk** (`loai_van_ban`, `linh_vuc`,
   `ngay_hieu_luc`, `con_hieu_luc`) và đánh **partial HNSW index** chỉ trên
   `con_hieu_luc = true`. Truy vấn nóng hầu như luôn chỉ hỏi VB còn hiệu lực.
6. **Hybrid bắt buộc.** Số hiệu văn bản ("13/2023/NĐ-CP") là token hiếm, dense
   embedding bắt rất tệ. `tsvector` + `unaccent` gánh phần đó.
7. **Point-in-time qua `provision_versions`.** Không update tại chỗ.
8. **Không embed phụ lục/biểu mẫu như text thường** — bảng biểu làm nhiễu.
   Lưu riêng, index bằng full-text hoặc chuyển thành bản ghi có cấu trúc.
