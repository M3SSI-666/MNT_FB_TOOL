# Các bản đã phát hành

Mỗi mục dưới đây là một bản có thể cài. Nút **Cập nhật** trong phần mềm đọc
đúng file này để hiện danh sách cho bạn chọn.

> **Nên chọn bản mới nhất.** Lùi về bản cũ là mất những gì đã sửa sau đó. Dữ
> liệu của bạn — tài khoản, page, content, UID nhóm — **không bị đụng tới** dù
> cập nhật hay lùi, vì chúng nằm ngoài phần mã nguồn. Trước mỗi lần cập nhật,
> phần mềm tự sao lưu dữ liệu vào `%LOCALAPPDATA%\MNT FB AutoPost\backup`.

---

## v1.1.0 — 23/08/2026

Máy khách giờ chỉ còn phần để **dùng và cập nhật**.

- Gỡ các công cụ đẩy code, gắn tag và đóng gói khỏi bản cài trên máy khách.
  Trước đây mọi máy đều nhận được chúng khi cập nhật.
- Không ảnh hưởng gì tới việc chạy hằng ngày: đăng bài, comment, nuôi nick,
  tham gia nhóm đều y nguyên.

## v1.0.5 — 23/08/2026

Chặn cả một lớp lỗi từng làm hỏng bản cập nhật.

- Thêm bài kiểm tự động cho toàn bộ file `.bat`, bắt đúng loại lỗi đã khiến
  `UPDATE.bat` chết trên mọi máy suốt ba tuần.
- Từ bản này, một bản chỉ được phát hành khi **bài kiểm đã qua**.
- Sửa nút *gỡ tự động chạy khi mở máy* — nó chưa bao giờ chạy được, cùng loại
  lỗi cú pháp trên.

## v1.0.4 — 23/08/2026

Làm bản cập nhật không tự phá mình giữa chừng.

- `UPDATE.bat` chạy từ một bản sao tạm. Trước đây nó tự ghi đè chính mình khi
  đang chạy, và có thể chết giữa chừng — ngay sau khi đã tắt app.
- Tên file sao lưu đổi sang dạng `app_20260823_180045.db`, đọc được và xếp
  đúng theo thời gian trên mọi máy.

## v1.0.3 — 23/08/2026

> ⚠ **Bản sửa lỗi quan trọng nhất.** Mọi máy đang ở bản cũ hơn đều **không cập
> nhật được** và phải chạy tay hai lệnh git một lần để thoát ra.

- `UPDATE.bat` bị lỗi cú pháp từ 01/08/2026: bấm vào là in ra một dòng
  `KHONG was unexpected at this time` rồi chết, không làm gì cả.
- Lỗi nổ trên **mọi máy, mọi lần chạy**, kể cả máy không rơi vào nhánh chứa lỗi.
- Nghĩa là các máy vệ tinh chưa hề cập nhật được lần nào từ 01/08 đến 23/08.

## v1.0.2 — 23/08/2026

Hai thay đổi lớn về cách cập nhật.

- **Sao lưu dữ liệu trước mỗi lần cập nhật**, giữ 10 bản gần nhất. Sao lưu thất
  bại thì dừng hẳn, không cập nhật tiếp.
- **Cập nhật theo bản phát hành** thay vì lấy code mới nhất. Trước đây máy khách
  nhận cả code đang sửa dở. Giờ chỉ nhận những gì đã được tuyên bố phát hành, và
  có thể ghim về một bản cụ thể: `UPDATE.bat v1.0.5`.

## v1.0.1 — 23/08/2026

- Sửa lỗi trong script phát hành. Không có thay đổi nào với người dùng.

## v1.0.0 — 23/08/2026

Bản đánh dấu đầu tiên.

- Tách dữ liệu khỏi mã nguồn, chuẩn bị cho bản cài đặt `setup.exe`.
- Số phiên bản có một nguồn duy nhất, hiện dưới logo trong phần mềm.

> Ba bản `v1.0.0` – `v1.0.2` **không máy khách nào cài được**, vì lỗi ở
> `v1.0.3` đã có sẵn từ trước đó. Giữ lại đây cho đủ lịch sử.
