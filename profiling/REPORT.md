# Corpus profiling report (P0)

- Total docs scanned: 170824
- HTML parse errors: 0
- % with <table>: 43.7%
- % with <img>: 5.1%
- % with <a href>: 3.3%
- % with multi-document_part signal: 16.7%

## Regex match rate (% of docs where at least one block matches)
- dieu: 71.7%
- chuong: 15.7%
- muc: 2.8%
- khoan: 64.0%
- diem: 39.4%

## Regex-vs-class agreement rate: 87.1%

## Derived class -> node_type mapping (majority vote, for T4 tier B)
| class | node_type | purity | n | breakdown |
|---|---|---|---|---|
| `prov-clause` | khoan | 100% | 820187 | {'khoan': 818691, 'chuong': 18, 'diem': 1340, 'dieu': 135, 'muc': 3} |
| `prov-item` | diem | 100% | 652474 | {'diem': 649921, 'khoan': 2506, 'dieu': 46, 'chuong': 1} |
| `MsoNormal` | khoan | 52% | 486541 | {'chuong': 8297, 'dieu': 64510, 'khoan': 253162, 'diem': 158440, 'muc': 2132} |
| `prov-article` | dieu | 100% | 385618 | {'dieu': 384704, 'khoan': 905, 'diem': 8, 'chuong': 1} |
| `prov-content` | diem | 51% | 131342 | {'khoan': 61920, 'diem': 67478, 'dieu': 1613, 'muc': 123, 'chuong': 208} |
| `prov-section` | khoan | 77% | 38479 | {'khoan': 29761, 'muc': 8654, 'dieu': 39, 'diem': 19, 'chuong': 6} |
| `prov-chapter` | chuong | 99% | 26190 | {'chuong': 25798, 'diem': 85, 'khoan': 268, 'dieu': 38, 'muc': 1} |
| `p` | khoan | 48% | 7294 | {'khoan': 3517, 'diem': 2415, 'dieu': 1169, 'chuong': 160, 'muc': 33} |
| `MsoBodyText` | khoan | 46% | 3389 | {'diem': 1264, 'khoan': 1543, 'dieu': 503, 'muc': 20, 'chuong': 59} |
| `MsoBodyTextIndent` | khoan | 51% | 2730 | {'khoan': 1386, 'diem': 967, 'dieu': 316, 'muc': 21, 'chuong': 40} |
| `fontstyle2` | khoan | 56% | 2298 | {'khoan': 1286, 'diem': 952, 'dieu': 54, 'chuong': 6} |
| `MsoListParagraph` | khoan | 46% | 2131 | {'diem': 840, 'khoan': 990, 'dieu': 298, 'chuong': 3} |
| `fontstyle0` | dieu | 79% | 2034 | {'dieu': 1603, 'chuong': 193, 'khoan': 92, 'diem': 121, 'muc': 25} |
| `mab2` | khoan | 48% | 1526 | {'dieu': 293, 'khoan': 732, 'diem': 458, 'chuong': 34, 'muc': 9} |
| `fontstyle3` | khoan | 53% | 1343 | {'khoan': 708, 'diem': 609, 'dieu': 24, 'chuong': 2} |
| `MsoBodyTextIndent2` | khoan | 49% | 1269 | {'khoan': 624, 'diem': 498, 'dieu': 133, 'chuong': 13, 'muc': 1} |
| `MsoBodyText2` | khoan | 58% | 854 | {'dieu': 141, 'khoan': 493, 'diem': 192, 'chuong': 21, 'muc': 7} |
| `15` | dieu | 39% | 808 | {'dieu': 314, 'khoan': 262, 'chuong': 54, 'diem': 178} |
| `16` | khoan | 34% | 715 | {'khoan': 244, 'chuong': 25, 'dieu': 196, 'diem': 239, 'muc': 11} |
| `normal-p` | khoan | 56% | 678 | {'dieu': 114, 'khoan': 383, 'diem': 160, 'chuong': 10, 'muc': 11} |
| `normal-h` | khoan | 59% | 629 | {'khoan': 373, 'diem': 156, 'dieu': 82, 'chuong': 9, 'muc': 9} |
| `docitem-11` | khoan | 100% | 625 | {'khoan': 624, 'dieu': 1} |
| `FontStyle17` | khoan | 44% | 597 | {'dieu': 224, 'khoan': 263, 'diem': 110} |
| `normal_(Web)` | khoan | 47% | 585 | {'diem': 223, 'khoan': 274, 'dieu': 82, 'muc': 2, 'chuong': 4} |
| `05NidungVB` | khoan | 64% | 582 | {'dieu': 59, 'khoan': 371, 'diem': 152} |
| `05nidungvb` | khoan | 57% | 573 | {'dieu': 72, 'diem': 175, 'khoan': 326} |
| `FontStyle24` | dieu | 49% | 567 | {'dieu': 276, 'khoan': 231, 'diem': 60} |
| `MsoBodyTextIndent3` | khoan | 49% | 564 | {'khoan': 275, 'diem': 204, 'dieu': 79, 'chuong': 5, 'muc': 1} |
| `MsoBodyText3` | khoan | 55% | 558 | {'khoan': 309, 'dieu': 77, 'chuong': 13, 'diem': 154, 'muc': 5} |
| `ds-markdown-paragraph` | diem | 39% | 511 | {'dieu': 140, 'khoan': 153, 'diem': 201, 'chuong': 13, 'muc': 4} |
| `Bodytext20` | khoan | 53% | 497 | {'chuong': 10, 'dieu': 114, 'khoan': 262, 'diem': 111} |
| `docx-tab-cols` | khoan | 48% | 462 | {'diem': 168, 'khoan': 220, 'dieu': 73, 'chuong': 1} |
| `docitem-12` | diem | 98% | 416 | {'diem': 408, 'khoan': 8} |
| `prov-subsection` | khoan | 88% | 397 | {'muc': 2, 'khoan': 349, 'diem': 45, 'dieu': 1} |
| `18` | khoan | 66% | 365 | {'khoan': 241, 'diem': 78, 'chuong': 10, 'dieu': 36} |
| `BCX0` | khoan | 41% | 328 | {'khoan': 135, 'diem': 114, 'chuong': 18, 'dieu': 61} |
| `GramE` | dieu | 97% | 322 | {'dieu': 311, 'diem': 7, 'khoan': 4} |
| `style7` | diem | 59% | 299 | {'khoan': 122, 'diem': 177} |
| `docitem-5` | dieu | 100% | 293 | {'dieu': 293} |
| `demuc4` | dieu | 100% | 292 | {'dieu': 292} |

## Top 30 CSS classes by usage
| class | total | bold ratio | tags | sample |
|---|---|---|---|---|
| `MsoNormal` | 2110828 | 0% | {'p': 2110566, 'li': 167, 'div': 95} | Nơi nhận:- Như Điều 3;- Bộ Thông tin và Truyền thông;- Cục Thông tin đối ngoại;- |
| `prov-content` | 1390860 | 0% | {'p': 1287030, 'td': 102440, 'div': 804, 'li': 586} | Lý do: Không còn phù hợp với thực tiễn. |
| `prov-clause` | 846492 | 0% | {'p': 844674, 'td': 935, 'li': 402, 'div': 481} | 1. Khoản 4, Điều 3 được sửa đổi, bổ sung như sau: |
| `prov-item` | 678136 | 0% | {'p': 676926, 'td': 765, 'div': 290, 'li': 155} | a) Chủ trì, phối hợp với Sở Thông tin và Truyền thông và các cơ quan chức năng đ |
| `prov-article` | 398960 | 0% | {'p': 398883, 'div': 74, 'td': 1, 'li': 2} | Điều 1. Bãi bỏ Quyết định số 08/2015/QĐ-UBND ngày 24 tháng 7 năm 2015 của Ủy ban |
| `prov-section` | 54209 | 0% | {'p': 54195, 'div': 3, 'td': 8, 'li': 3} | 1.Quán triệt, phổ biến, nhận thức đầy đủ về ý nghĩa, vai trò, vị trí và tầm quan |
| `prov-chapter` | 48084 | 0% | {'p': 48074, 'td': 7, 'div': 3} | Chương I        QUY ĐỊNH CHUNG |
| `15` | 35868 | 0% | {'span': 34700, 'p': 1168} | TM. ỦY BAN NHÂN DÂN |
| `p` | 33417 | 0% | {'p': 33417} | TM. ỦY BAN NHÂN DÂN |
| `16` | 22603 | 0% | {'span': 4686, 'p': 17917} | --------------- |
| `fontstyle3` | 18945 | 0% | {'span': 18945} | ; |
| `TableParagraph` | 18515 | 0% | {'p': 18515} | TM. UỶ BAN NHÂN DÂN |
| `Other0` | 16377 | 0% | {'p': 16377} | Chỉ tiêu chất lượng |
| `MsoBodyText` | 11478 | 0% | {'p': 11478} | Căn cứ Luật Khoa học và công nghệ ngày 18 tháng 6 năm 2013; |
| `prov-part` | 11194 | 0% | {'p': 11189, 'div': 2, 'td': 3} | QUYẾT NGHỊ: |
| `MsoBodyTextIndent` | 9232 | 0% | {'p': 9232} | Sản xuất gốm sứ tại các cụm tiểu thủ công nghiệp tập trung có quy mô trung bình  |
| `fontstyle0` | 9157 | 0% | {'span': 9157} | Số: 04/2023/NQ-HĐND |
| `fontstyle2` | 7605 | 0% | {'span': 7605} | Căn cứ Luật Tổ chức chính quyền địa phương ngày 19 tháng 6 năm 2015;       Căn c |
| `BCX0` | 7452 | 0% | {'span': 6665, 'div': 378, 'p': 345, 'td': 54, 'li': 10} | Số lượng Tổ bảo vệ an ninh, trật tự; số lượng thành viên Tổ bảo vệ an ninh, trật |
| `NormalTextRun` | 6422 | 0% | {'span': 6422} | Số lượng Tổ bảo vệ an ninh, trật tự; số lượng thành viên Tổ bảo vệ an ninh, trật |
| `MsoBodyTextIndent2` | 5820 | 0% | {'p': 5820} | Căn cứ Luật Tổ chức chính quyền địa phương ngày 19/6/2015; |
| `MsoListParagraph` | 5698 | 0% | {'p': 5698} | c) Quy hoạch phát triển lâm nghiệp tỉnh Tây Ninh đến năm 2020 |
| `SpellingErrorV2Themed` | 5453 | 0% | {'span': 5453} | Đã |
| `xl66` | 5323 | 0% | {'td': 5323} | Cửa khẩu chính (cửa khẩu song phương) |
| `VLLFBold` | 4358 | 0% | {'p': 4358} | DECISION |
| `than` | 4352 | 0% | {'p': 4352} | 1.2. Vốn huy động: |
| `rpv-core__text-layer-text` | 3659 | 0% | {'span': 3659} | Hành vi vi ph |
| `05NidungVB` | 3140 | 0% | {'p': 3140} | Căn cứ Luật Tổ chức Hội đồng nhân dân và Ủy ban nhân dân ngày 26 tháng 11 năm 20 |
| `MsoBodyText2` | 2962 | 0% | {'p': 2962} | (Ban hành kèm theo Quyết định  số 90/2014/QĐ-UBND |
| `ng-star-inserted` | 2720 | 0% | {'div': 489, 'p': 416, 'span': 972, 'td': 824, 'li': 19} | Căn cứ Thông tư số 45/2018/TT-BTC ngày 07/5/2018 của Bộ Tài chính hướng dẫn chế  |

## Template families (top 15 by DOM class-signature)
- 81912 docs — ``
- 12490 docs — `prov-article|prov-clause|prov-content|prov-item`
- 11223 docs — `prov-article`
- 10308 docs — `prov-article|prov-clause|prov-content`
- 8526 docs — `prov-article|prov-content`
- 3797 docs — `MsoNormal`
- 3071 docs — `prov-article|prov-clause`
- 2639 docs — `prov-article|prov-chapter|prov-clause|prov-content|prov-item`
- 2103 docs — `MsoNormal|VLLFBold`
- 1489 docs — `MsoNormal|MsoNormalTable`
- 1385 docs — `MsoNormal|prov-article`
- 1258 docs — `MsoNormal|prov-article|prov-content`
- 1143 docs — `prov-article|prov-clause|prov-item`
- 1065 docs — `prov-article|prov-chapter|prov-clause|prov-content|prov-item|prov-section`
- 1061 docs — `MsoNormal|prov-article|prov-clause|prov-content|prov-item`

## Length distribution by loai_van_ban
- Quyết định: n=90980 p50=9366 p90=44310 max=13473568
- Nghị quyết: n=28283 p50=9995 p90=33908 max=8073124
- Thông tư: n=17214 p50=19097 p90=87365 max=12012441
- Bản dịch văn bản: n=10952 p50=1455 p90=36878 max=1911484
- Chỉ thị: n=8538 p50=8010 p90=16365 max=562189
- Nghị định: n=5319 p50=28165 p90=144833 max=12756339
- Thông tư liên tịch: n=3518 p50=17936 p90=51141 max=1647834
- Văn bản hợp nhất: n=2203 p50=83 p90=38375 max=7559072
- Sắc lệnh: n=981 p50=2612 p90=6059 max=147358
- Công văn: n=732 p50=83 p90=7193 max=207754
- Luật: n=608 p50=81744 p90=249327 max=908536
- Văn bản hệ thống hóa: n=390 p50=32534 p90=1290778 max=15436746
- Lệnh: n=379 p50=2825 p90=5815 max=305409
- Pháp lệnh: n=248 p50=23717 p90=75169 max=225703
- Văn bản hành chính liên quan: n=243 p50=6029 p90=13549 max=307346
- Văn bản liên quan: n=43 p50=7498 p90=12826 max=163158
- Chương trình: n=42 p50=10620 p90=21075 max=27772
- Nghị quyết liên tịch: n=34 p50=18022 p90=57473 max=202408
- Hiệp định: n=24 p50=59595 p90=105432 max=170122
- Bộ luật: n=17 p50=347775 p90=1191626 max=1194916
- Công ước: n=16 p50=15638 p90=33195 max=67594
- Văn bản khác: n=16 p50=15754 p90=47866 max=244922
- Thông báo: n=11 p50=1021 p90=9784 max=11117
- Chưa xác định: n=8 p50=83 p90=20073 max=20073
- Thông tư liên bộ: n=7 p50=15762 p90=58201 max=58201
- Hiến pháp: n=6 p50=108473 p90=161668 max=161668
- Nghị định thư: n=4 p50=6588 p90=14960 max=14960
- Sắc luật: n=4 p50=14921 p90=37888 max=37888
- Bản ghi nhớ: n=2 p50=16026 p90=16026 max=16026
- Quy định: n=1 p50=32502 p90=32502 max=32502
- Thỏa thuận: n=1 p50=15839 p90=15839 max=15839

## Length distribution by decade
- 1920s: n=1 p50=54249 p90=54249 max=54249
- 1940s: n=689 p50=2685 p90=6827 max=147358
- 1950s: n=639 p50=4370 p90=17862 max=148078
- 1960s: n=382 p50=9175 p90=31304 max=254172
- 1970s: n=855 p50=6457 p90=25174 max=1666661
- 1980s: n=3687 p50=7551 p90=25822 max=1458080
- 1990s: n=15569 p50=7827 p90=30711 max=10314070
- 2000s: n=51164 p50=8057 p90=38988 max=6256476
- 2010s: n=54444 p50=10814 p90=52900 max=15436746
- 2020s: n=43300 p50=12914 p90=68171 max=13473568
- 3020s: n=1 p50=309 p90=309 max=309
- unknown: n=93 p50=83 p90=83 max=556279

## Dieu count by loai_van_ban
- Quyết định: n=90980 p50=5 p90=22 max=552
- Nghị quyết: n=28283 p50=3 p90=10 max=213
- Thông tư: n=17214 p50=5 p90=31 max=578
- Bản dịch văn bản: n=10952 p50=0 p90=0 max=0
- Chỉ thị: n=8538 p50=0 p90=0 max=48
- Nghị định: n=5319 p50=15 p90=70 max=618
- Thông tư liên tịch: n=3518 p50=0 p90=16 max=88
- Văn bản hợp nhất: n=2203 p50=0 p90=12 max=416
- Sắc lệnh: n=981 p50=0 p90=0 max=24
- Công văn: n=732 p50=0 p90=0 max=12
- Luật: n=608 p50=51 p90=158 max=744
- Văn bản hệ thống hóa: n=390 p50=3 p90=11 max=151
- Lệnh: n=379 p50=0 p90=0 max=0
- Pháp lệnh: n=248 p50=2 p90=72 max=242
- Văn bản hành chính liên quan: n=243 p50=3 p90=6 max=15
- Văn bản liên quan: n=43 p50=3 p90=8 max=10
- Chương trình: n=42 p50=0 p90=0 max=16
- Nghị quyết liên tịch: n=34 p50=3 p90=40 max=116
- Hiệp định: n=24 p50=67 p90=162 max=228
- Bộ luật: n=17 p50=445 p90=1020 max=1034
- Công ước: n=16 p50=0 p90=6 max=10
- Văn bản khác: n=16 p50=0 p90=12 max=17
- Thông báo: n=11 p50=0 p90=0 max=0
- Chưa xác định: n=8 p50=0 p90=14 max=14
- Thông tư liên bộ: n=7 p50=0 p90=0 max=0
- Hiến pháp: n=6 p50=0 p90=0 max=0
- Nghị định thư: n=4 p50=1 p90=2 max=2
- Sắc luật: n=4 p50=0 p90=0 max=0
- Bản ghi nhớ: n=2 p50=0 p90=0 max=0
- Quy định: n=1 p50=30 p90=30 max=30
- Thỏa thuận: n=1 p50=0 p90=0 max=0