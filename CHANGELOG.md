# Các bản đã phát hành

Mỗi mục dưới đây là một bản có thể cài. Nút **Cập nhật** trong phần mềm đọc
đúng file này để hiện danh sách cho bạn chọn.

> **Nên chọn bản mới nhất.** Lùi về bản cũ là mất những gì đã sửa sau đó. Dữ
> liệu của bạn — tài khoản, page, content, UID nhóm — **không bị đụng tới** dù
> cập nhật hay lùi, vì chúng nằm ngoài phần mã nguồn. Trước mỗi lần cập nhật,
> phần mềm tự sao lưu dữ liệu vào `%LOCALAPPDATA%\MNT FB AutoPost\backup`.

---

## v2.0.0 — 25/08/2026

> ⚠ **Bản này cần bạn duyệt máy trước khi dùng được.** Mỗi máy cài lên sẽ hiện
> màn hình đăng ký; chủ phần mềm duyệt xong thì máy đó mới chạy. Máy đang chạy
> mà cập nhật lên bản này cũng phải đăng ký một lần.

**Đăng ký và phê duyệt**

- Mở phần mềm lần đầu → điền họ tên, số điện thoại, Gmail → chờ duyệt. Được
  duyệt thì màn hình tự tắt, không cần khởi động lại.
- Chủ phần mềm có **bảng quản lý**: xem ai đang dùng, máy nào, bản nào, duyệt
  hoặc cắt quyền. Cắt được theo từng máy hoặc theo cả người.
- Mất mạng vẫn dùng được tới 7 ngày bằng kết quả đã lưu.

**Trạng thái tài khoản — gọn lại còn 4**

- Bỏ trạng thái **Hỏng**. Trước đây hỏng nhiều phiên là nick bị tự tắt hẳn; bị
  Facebook chặn là chuyện bình thường và tự hết sau vài tiếng, tắt hẳn là mất
  luôn một nick còn sống. Nick cũ đang ở "Hỏng" chuyển thành **Dừng**.
- **Tạm dừng** đổi tên thành **Dừng**, và giờ nó dừng thật — trước đây đặt dừng
  mà nick vẫn chạy hết lịch đã gen từ trước.

**Nick dính spam giờ không nằm không**

- Trong một tiếng nghỉ, slot đăng bài và comment **chuyển thành phiên nuôi
  nick** thay vì bỏ trống. Trước đây mỗi lần dính spam là mất trắng số slot còn
  lại của ngày.
- Hết một tiếng, slot kế tiếp **đăng thử một bài**. Được thì chạy lại bình
  thường; không được thì nuôi nick thêm một tiếng rồi thử lại — lặp cho tới khi
  đăng được.
- **Dò spam sau mọi phiên**, không chỉ phiên đăng nhóm. Trước đây đăng tường
  Page, đăng chế độ VIA và đi comment đều không dò — nick bị gỡ bài trong ba
  trường hợp đó thì không ai biết.
- Gen lịch không còn khoá cứng cả ngày của nick spam thành comment. Nick dính
  spam lúc 8h, được thả lúc 9h, trước đây vẫn mất sạch slot đăng của 15 tiếng.

**Sửa nhỏ**

- Tab Page: cột **Loại đăng** thêm lựa chọn trống. Để trống thì Gen lịch bỏ qua
  Page đó — dùng khi tạm không muốn đăng mà chưa muốn xoá.
- Tham gia nhóm: nghỉ **15 giây** sau khi vừa vào một nhóm mới.

## v1.3.0 — 23/08/2026

Bản đầu tiên cài được bằng `setup.exe` — không cần cài Python hay git.

- Python và git đi kèm ngay trong bản cài. Máy mới chỉ cần bấm đúp file cài,
  không phải chuẩn bị gì trước.
- **Màn hình chuẩn bị lần chạy đầu**: phần mềm tự tải Chromium (khoảng 680 MB,
  chỉ một lần) và hiện thanh tiến độ, thay vì để bạn ngồi nhìn cửa sổ đen.
- Dữ liệu của bản cài để riêng ở `%LOCALAPPDATA%\MNT FB AutoPost`, nên gỡ phần
  mềm ra cài lại **không mất** tài khoản, cookie, lịch, content.
- Sửa lỗi khiến dữ liệu luôn bị tạo cạnh mã nguồn dù đã đặt nơi để khác.

## v1.2.1 — 23/08/2026

Thêm đường thoát khi không cập nhật được.

- `KHOI_PHUC.bat` kéo thẳng bản mới nhất từ GitHub, **không đi qua**
  `UPDATE.bat`. Dùng khi bấm `UPDATE.bat` mà nó báo lỗi hoặc không làm gì.
- File tự chứa: tự tìm git, không gọi file nào khác trong thư mục, nên chạy
  được cả trên máy đang kẹt ở bản rất cũ.
- Vẫn sao lưu dữ liệu trước, và dừng lại nếu sao lưu thất bại.

## v1.2.0 — 23/08/2026

Cập nhật ngay trong phần mềm, không cần mở file nào nữa.

- Bấm vào số phiên bản dưới logo để xem **mọi bản đã phát hành**, mỗi bản kèm
  ghi chú nói rõ nó sửa gì.
- Có bản mới thì hiện một **chấm nhỏ** cạnh số phiên bản, khỏi phải tự đi tìm.
- Chọn bản nào thì phần mềm tự tắt, cập nhật, rồi mở lại — trang tự nạp lại.
- Lùi về bản cũ được, nhưng sẽ hỏi lại vì lùi là mất những gì đã sửa sau đó.

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
