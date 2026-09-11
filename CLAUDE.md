# CLAUDE.md

## Quy ước code

Mọi task code trong repo này áp dụng skill `ponytail` ở mức `full`: nạp skill
ponytail ngay khi bắt đầu, và giữ nguyên cho tới hết phiên.

Tóm tắt để khỏi phải mở skill: đi theo thang — task có cần tồn tại không (YAGNI)
→ code sẵn trong repo → stdlib → tính năng native → dependency đã cài → một dòng
→ cuối cùng mới là code tối thiểu. Dừng ở nấc đầu tiên chạy được. Diff ngắn nhất
mà đúng thì thắng, nhưng chỉ sau khi đã đọc hiểu toàn bộ luồng mà thay đổi chạm
vào. Không lười ở khâu hiểu vấn đề.

Không bao giờ đơn giản hoá mất: validate input ở biên, xử lý lỗi tránh mất dữ
liệu, bảo mật, và bất cứ thứ gì được yêu cầu rõ ràng.
