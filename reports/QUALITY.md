# Parse quality report (P3)

- Total docs: 170824
- clean: 127892 (74.9%)
- warn: 42717 (25.0%)
- failed: 215 (0.1%)

## Top 20 issue combinations
| issues | count | example doc_id |
|---|---|---|
| none | 127892 | 132934 |
| sequence | 21091 | 130884 |
| sequence,part_count | 4074 | 129591 |
| hierarchy | 3587 | 131987 |
| table_preserved | 3484 | 129262 |
| sequence,hierarchy | 3361 | 125906 |
| part_count | 2781 | 133057 |
| sequence,table_preserved | 869 | 128588 |
| char_coverage | 823 | vbpqta_2171 |
| sequence,hierarchy,part_count | 686 | 83554 |
| sequence,part_count,table_preserved | 386 | 86061 |
| sequence,conflict_rate | 291 | 105146 |
| part_count,table_preserved | 280 | 104641 |
| sequence,hierarchy,table_preserved | 253 | 120585 |
| conflict_rate | 243 | 26767 |
| hierarchy,part_count | 173 | 103747 |
| sequence,hierarchy,part_count,table_preserved | 156 | 106060 |
| hierarchy,table_preserved | 124 | 113184 |
| hierarchy,conflict_rate | 78 | 64948 |
| sequence,hierarchy,conflict_rate | 60 | 28001050-7b7c-11f1-9c9a-857c170a090b |

## By loai_van_ban
| loai_van_ban | clean | warn | failed | n |
|---|---|---|---|---|
| Quyết định | 69037 | 21928 | 15 | 90980 |
| Nghị quyết | 23157 | 5122 | 4 | 28283 |
| Thông tư | 11195 | 6001 | 18 | 17214 |
| Bản dịch văn bản | 6878 | 3902 | 172 | 10952 |
| Chỉ thị | 7235 | 1301 | 2 | 8538 |
| Nghị định | 3763 | 1556 | 0 | 5319 |
| Thông tư liên tịch | 1637 | 1878 | 3 | 3518 |
| Văn bản hợp nhất | 1975 | 228 | 0 | 2203 |
| Sắc lệnh | 872 | 109 | 0 | 981 |
| Công văn | 699 | 33 | 0 | 732 |
| Luật | 312 | 296 | 0 | 608 |
| Văn bản hệ thống hóa | 277 | 112 | 1 | 390 |
| Lệnh | 369 | 10 | 0 | 379 |
| Pháp lệnh | 119 | 129 | 0 | 248 |
| Văn bản hành chính liên quan | 226 | 17 | 0 | 243 |
| Văn bản liên quan | 40 | 3 | 0 | 43 |
| Chương trình | 35 | 7 | 0 | 42 |
| Nghị quyết liên tịch | 14 | 20 | 0 | 34 |
| Hiệp định | 11 | 13 | 0 | 24 |
| Bộ luật | 8 | 9 | 0 | 17 |
| Công ước | 2 | 14 | 0 | 16 |
| Văn bản khác | 6 | 10 | 0 | 16 |
| Thông báo | 11 | 0 | 0 | 11 |
| Chưa xác định | 7 | 1 | 0 | 8 |
| Thông tư liên bộ | 2 | 5 | 0 | 7 |
| Hiến pháp | 0 | 6 | 0 | 6 |
| Nghị định thư | 2 | 2 | 0 | 4 |
| Sắc luật | 1 | 3 | 0 | 4 |
| Bản ghi nhớ | 0 | 2 | 0 | 2 |
| Quy định | 1 | 0 | 0 | 1 |
| Thỏa thuận | 1 | 0 | 0 | 1 |

## By decade
| decade | clean | warn | failed | n |
|---|---|---|---|---|
| 1920s | 1 | 0 | 0 | 1 |
| 1940s | 603 | 86 | 0 | 689 |
| 1950s | 507 | 132 | 0 | 639 |
| 1960s | 225 | 157 | 0 | 382 |
| 1970s | 615 | 240 | 0 | 855 |
| 1980s | 2458 | 1229 | 0 | 3687 |
| 1990s | 10276 | 5268 | 25 | 15569 |
| 2000s | 36314 | 14686 | 164 | 51164 |
| 2010s | 42446 | 11983 | 15 | 54444 |
| 2020s | 34356 | 8933 | 11 | 43300 |
| 3020s | 1 | 0 | 0 | 1 |
| unknown | 90 | 3 | 0 | 93 |

## Top 15 template families by volume
| template (first 80 chars) | clean | warn | failed | n |
|---|---|---|---|---|
| `` | 60702 | 21353 | 29 | 82084 |
| `prov-article|prov-clause|prov-content|prov-item` | 10817 | 1668 | 5 | 12490 |
| `prov-article` | 8241 | 2976 | 6 | 11223 |
| `prov-article|prov-clause|prov-content` | 8831 | 1471 | 6 | 10308 |
| `prov-article|prov-content` | 7015 | 1508 | 3 | 8526 |
| `MsoNormal` | 2757 | 960 | 80 | 3797 |
| `prov-article|prov-clause` | 2590 | 480 | 1 | 3071 |
| `prov-article|prov-chapter|prov-clause|prov-content|prov-item` | 2046 | 593 | 0 | 2639 |
| `MsoNormal|VLLFBold` | 2099 | 2 | 2 | 2103 |
| `MsoNormal|MsoNormalTable` | 1128 | 361 | 0 | 1489 |
| `MsoNormal|prov-article` | 1068 | 317 | 0 | 1385 |
| `MsoNormal|prov-article|prov-content` | 1044 | 214 | 0 | 1258 |
| `prov-article|prov-clause|prov-item` | 964 | 179 | 0 | 1143 |
| `prov-article|prov-chapter|prov-clause|prov-content|prov-item|prov-section` | 187 | 878 | 0 | 1065 |
| `MsoNormal|prov-article|prov-clause|prov-content|prov-item` | 896 | 164 | 1 | 1061 |