# -*- coding: utf-8 -*-
import json
from sample_corpus import DOCS
from vbpl_extract import parse_document, make_chunks

results = {}
print("=" * 78)
for name, txt in DOCS.items():
    p = parse_document(txt, doc_id=name)
    ch = make_chunks(p)
    results[name] = (p, ch)
    h, s = p["header"], p["stats"]
    print(f"\n### {name}")
    print(f"  loại={h['loai_van_ban']!r} số={h['so_ky_hieu']!r} "
          f"ngày={h['ngay_ban_hanh']!r} cq={h['co_quan_ban_hanh']!r}")
    print(f"  trích yếu: {(h['trich_yeu'] or '')[:70]!r}")
    print(f"  căn cứ={len(h['can_cu'])}  người ký={p['signer']!r} ({p['chuc_danh']!r})")
    print(f"  cấu trúc: chương={s['n_chuong']} điều={s['n_dieu']} "
          f"khoản={s['n_khoan']} điểm={s['n_diem']} | phụ lục={s['n_appendix']} dòng")
    print(f"  facts: cites={len(p['facts']['citations'])} "
          f"amend={len(p['facts']['amendments'])} "
          f"defs={len(p['facts']['definitions'])} "
          f"eff={len(p['facts']['effective'])}")
    print(f"  chunks={len(ch)}  avg={sum(c['n_chars'] for c in ch)//max(len(ch),1)} chars")

print("\n" + "=" * 78)
print("MẪU CÂY — luat_gdđt")
for p in results["luat_gdđt"][0]["provisions"]:
    print("   " * (p["depth"] - 1) + f"[{p['path']}] {p['level']}{p['number']} "
          f"{(p['heading'] or p['text'])[:52]}")

print("\n" + "=" * 78)
print("ĐỊNH NGHĨA bóc được (nguồn vàng cho business glossary):")
for name in ("luat_gdđt", "nd_bvdlcn"):
    for d in results[name][0]["facts"]["definitions"]:
        print(f"  [{name} {d['at']}] {d['term']} := {d['definition'][:60]}")

print("\n" + "=" * 78)
print("LỆNH SỬA ĐỔI bóc được (tt_sua_doi):")
for a in results["tt_sua_doi"][0]["facts"]["amendments"]:
    print("  ", a)

print("\n" + "=" * 78)
print("HIỆU LỰC:")
for name in results:
    for e in results[name][0]["facts"]["effective"]:
        print(f"  [{name}] {e['kind']} {e['date']} @ {e['at']}")

print("\n" + "=" * 78)
print("1 CHUNK MẪU (cái sẽ đem đi embed):")
c = results["luat_gdđt"][1][1]
print(json.dumps({k: v for k, v in c.items() if k != "embed_text"},
                 ensure_ascii=False, indent=2))
print("--- embed_text ---")
print(c["embed_text"])
