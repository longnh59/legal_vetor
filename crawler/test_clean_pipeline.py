# -*- coding: utf-8 -*-
"""
Unit and integration tests for the dataset cleaning pipeline.
"""

import unicodedata
import pandas as pd
from clean_dataset import (
    normalize_unicode_nfc,
    parse_vietnamese_date,
    clean_html_to_text,
    extract_articles_from_text,
    categorize_relationship,
)


def test_normalize_unicode_nfc():
    # NFD decomposed string: 'Trâ\u0300n' vs NFC 'Trần'
    nfd_str = 'Trâ\u0300n'
    nfc_str = 'Trần'
    assert nfd_str != nfc_str
    
    cleaned = normalize_unicode_nfc(nfd_str)
    assert cleaned == nfc_str
    assert unicodedata.is_normalized('NFC', cleaned)
    
    # Check placeholder removal
    assert normalize_unicode_nfc('...') is None
    assert normalize_unicode_nfc('   ') is None
    assert normalize_unicode_nfc(None) is None


def test_parse_vietnamese_date():
    assert parse_vietnamese_date("23/07/2026") == "2026-07-23"
    assert parse_vietnamese_date("5/1/2020") == "2020-01-05"
    assert parse_vietnamese_date("...") is None
    assert parse_vietnamese_date("") is None
    assert parse_vietnamese_date("invalid_date") is None
    assert parse_vietnamese_date("99/99/9999") is None
    assert parse_vietnamese_date("31/02/2024") is None
    assert parse_vietnamese_date("29/02/2024") == "2024-02-29"


def test_clean_html_to_text():
    html = """
    <html>
      <head><style>body { color: red; }</style></head>
      <body>
        <h1>Luật Thủ đô</h1>
        <p>Điều 1. Phạm vi điều chỉnh</p>
        <p>Luật này quy định vị trí, vai trò của Thủ đô&nbsp;Hà Nội.</p>
        <script>console.log("ignore");</script>
      </body>
    </html>
    """
    text = clean_html_to_text(html)
    assert "Luật Thủ đô" in text
    assert "Điều 1. Phạm vi điều chỉnh" in text
    assert "Thủ đô Hà Nội" in text
    assert "color: red" not in text
    assert "console.log" not in text


def test_extract_articles_from_text():
    text = """
    CHƯƠNG I: QUY ĐỊNH CHUNG
    
    Điều 1. Phạm vi điều chỉnh
    Luật này quy định về các biện pháp thi hành.
    
    Điều 2. Đối tượng áp dụng
    1. Cơ quan nhà nước.
    2. Tổ chức, cá nhân.
    """
    articles = extract_articles_from_text("doc_100", text)
    assert len(articles) == 2
    assert articles[0]["article_number"] == 1
    assert "Phạm vi điều chỉnh" in articles[0]["article_header"]
    assert articles[1]["article_number"] == 2
    assert "Đối tượng áp dụng" in articles[1]["article_header"]


def test_categorize_relationship():
    assert categorize_relationship("Căn cứ pháp lý") == "CAN_CU"
    assert categorize_relationship("Văn bản căn cứ") == "LA_CAN_CU_CHO"
    assert categorize_relationship("Sửa đổi, bổ sung một số điều") == "SUA_DOI_BO_SUNG"
    assert categorize_relationship("Văn bản sửa đổi") == "DUOC_SUA_DOI"
    assert categorize_relationship("Văn bản bổ sung") == "DUOC_BO_SUNG"
    assert categorize_relationship("Bãi bỏ toàn bộ") == "BAI_BO"
    assert categorize_relationship("Văn bản hết hiệu lực") == "BAI_BO"
    assert categorize_relationship("Văn bản quy định hết hiệu lực") == "QUY_DINH_HET_HIEU_LUC"
    assert categorize_relationship("Quy định chi tiết") == "HUONG_DAN_CHI_TIET"
    assert categorize_relationship("Văn bản HD, QĐ chi tiết") == "DUOC_HUONG_DAN_CHI_TIET"
    assert categorize_relationship("Dẫn chiếu khoản 2") == "DAN_CHIEU"
    assert categorize_relationship("Văn bản dẫn chiếu") == "DUOC_DAN_CHIEU"
    assert categorize_relationship("Loại ngẫu nhiên") == "KHAC"
