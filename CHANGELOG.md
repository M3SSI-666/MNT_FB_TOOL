# Các bản đã phát hành

Mỗi mục dưới đây là một bản có thể cài. Nút **Cập nhật** trong phần mềm đọc
đúng file này để hiện danh sách cho bạn chọn.

> **Nên chọn bản mới nhất.** Lùi về bản cũ là mất những gì đã sửa sau đó. Dữ
> liệu của bạn — tài khoản, page, content, UID nhóm — **không bị đụng tới** dù
> cập nhật hay lùi, vì chúng nằm ngoài phần mã nguồn. Trước mỗi lần cập nhật,
> phần mềm tự sao lưu dữ liệu vào `%LOCALAPPDATA%\MNT FB AutoPost\backup`.

---

## v2.4.2 — 28/08/2026

**Sửa: khởi động lại app là nhận thêm một bản tổng kết**

Mốc "hôm nay đã gửi tổng kết rồi" chỉ nằm trong bộ nhớ, nên tắt phần mềm mở lại
là quên sạch. Ngày nào mở lại vài lần sau giờ tổng kết là ngần ấy tin giống hệt
nhau. Giờ mốc được ghi xuống cơ sở dữ liệu.

## v2.4.1 — 28/08/2026

**Thu gọn bảng Telegram khi không dùng tới**

Bảng cấu hình Telegram là thứ cài một lần rồi thôi, nhưng nó chiếm nửa trang
*Hành động* — nơi việc hằng ngày là bấm mấy nút **Run**.

- Thêm nút **Ẩn / Hiện** ở thanh tiêu đề của bảng. Bấm vào đâu trên thanh đó
  cũng gập được, và phần mềm nhớ lựa chọn cho lần mở sau.
- Mặc định **thu lại**.
- Thu lại rồi vẫn thấy ngay đang bật hay tắt, nhờ nhãn ở thanh tiêu đề:
  *Đang bật* · *Đang tắt* · *Bật, chưa điền* (bật mà thiếu Token hoặc Chat ID —
  trước đây phải mở bảng ra mới biết mình quên).

## v2.4.0 — 28/08/2026

**Chỉ báo khi acc thật sự đổi từ chạy sang ngừng, hoặc ngược lại**

Bản trước báo theo **mỗi lần ghi** trạng thái, không phải theo lần đổi. Mà acc
dính spam thì cứ mỗi tiếng lại có một phiên thăm dò, và mỗi lần thăm dò hỏng lại
ghi `Spam` đè lên `Spam`. Nghĩa là **một acc kẹt một tuần sẽ nhắn 168 lần**, toàn
tin giống hệt nhau — rồi bạn tắt bot đi, và bỏ lỡ cảnh báo thật sự tiếp theo.

Giờ phần mềm so trạng thái cũ với mới, và chỉ nhắn khi vượt qua ranh giới:

| Chuyển | Kết quả |
|---|---|
| Active → Spam / Lỗi Composer / Cookie hết hạn | 🔴 **NGỪNG HOẠT ĐỘNG** |
| Spam / Lỗi Composer / Cookie hết hạn → Active | 🟢 **HOẠT ĐỘNG TRỞ LẠI** |
| Thăm dò lại vẫn hỏng (Spam → Spam) | im lặng |
| Bạn tự cho nick nghỉ, hoặc tự bật lại (Dừng) | im lặng |

Tin nhắn cũng nói rõ chiều đổi: `Ngân Nấm: Active → Spam`.

**Báo cả khi bạn tự tay sửa xong.** Nạp lại cookie rồi bật acc về Active thì
nhóm nhận được tin *HOẠT ĐỘNG TRỞ LẠI* — để hai người không cùng đi sửa một acc.

## v2.3.2 — 28/08/2026

**Dùng kênh (channel) thay nhóm cũng chạy**

Trong kênh, bài đăng đến dưới dạng khác hẳn trong nhóm. Bản trước chỉ nghe kiểu
của nhóm, nên nếu bạn trỏ vào một kênh thì **cảnh báo vẫn tới bình thường còn
`/tinhtrang` im lặng vĩnh viễn** — hỏng mà không có lấy một dòng lỗi nào để lần
ra. Mà nút *Lấy hộ* lại có hiện kênh ra, nên hoàn toàn có thể chọn nhầm vào đó.

Giờ nghe cả hai kiểu, và nút *Lấy hộ* ghi rõ từng khung là **Nhóm**, **Kênh**
hay **Chat riêng** để bạn biết mình đang chọn gì.

> Vẫn nên dùng **nhóm**: trong kênh chỉ quản trị viên của kênh gõ được lệnh, và
> mọi người không trao đổi với nhau được.

## v2.3.1 — 28/08/2026

**Báo vào nhóm chung cho nhiều người cùng quản lý**

Nhiều máy báo chung vào một nhóm Telegram vốn đã chạy được từ `v2.3.0`, nhưng
nhóm có mấy chỗ vấp mà chat riêng không có. Bản này gỡ hết:

- **Nút "Lấy hộ" Chat ID.** ID của nhóm là số âm dạng `-100...` và Telegram
  không hiện nó ở đâu cả — `@userinfobot` chỉ cho ID cá nhân. Giờ thêm bot vào
  nhóm, gõ `/start` trong đó, bấm nút là phần mềm tự hỏi bot và điền vào.
- **Không còn mất cảnh báo khi hỏng hàng loạt.** Telegram chỉ nhận khoảng 20
  tin/phút vào một nhóm; vượt thì nó *nuốt* tin chứ không báo gì. Mất mạng một
  cái là cả loạt acc cùng hết cookie trong vài giây — đúng lúc cần biết nhất
  thì lại là lúc dễ mất tin nhất. Giờ các tin được giãn ra và gửi lại nếu
  Telegram bảo chờ.
- **Hướng dẫn cài ngay trong phần mềm** viết lại theo đúng thứ tự làm: tạo bot →
  tạo nhóm → thêm quản trị viên → lấy Chat ID → sang máy khác điền y hệt.
- Báo lỗi rõ hơn: bot bị xoá khỏi nhóm, hoặc điền nhầm ID cá nhân vào ô nhóm.

> **Lưu ý khi thêm người:** ai ở trong nhóm cũng gõ được `/tinhtrang` và thấy
> tên mọi tài khoản. Chỉ thêm người bạn thực sự tin, và xoá người nghỉ việc ra
> khỏi nhóm.

## v2.3.0 — 28/08/2026

**Báo về Telegram khi tài khoản gặp vấn đề**

Chạy nhiều máy thì mỗi máy một cơ sở dữ liệu riêng, không máy nào nhìn thấy máy
nào — muốn biết acc nào hỏng phải mở từng giao diện lên xem. Giờ mỗi máy tự nhắn
vào **cùng một khung chat Telegram**, mỗi tin có tên máy ở đầu.

- **Báo ngay** khi acc chuyển sang Spam, Cookie hết hạn hay Lỗi Composer — và
  báo cả khi acc **được thả về Active**, để biết lúc nào KHÔNG cần đụng tay.
- **Tổng kết hằng ngày** vào giờ bạn chọn: `12/14 Active`, kèm danh sách acc
  đang có vấn đề. Không liệt kê acc đang chạy tốt — nhìn 40 dòng xanh không cho
  biết thêm gì.
- **Hỏi bất cứ lúc nào**: gõ `/tinhtrang` trong Telegram, **mọi máy đang bật đều
  trả lời**. Đây là cách xem tổng mà không phải mở từng máy.
- Acc dính spam bị dò lại mỗi tiếng, nên cùng một acc + một trạng thái chỉ báo
  **một lần trong 55 phút**, khỏi bị dội tin.

Bật ở tab **Hành động**. Cần Token bot lấy từ `@BotFather` và Chat ID — có hướng
dẫn ngay trong phần mềm. Nhiều máy thì điền **cùng** Token và Chat ID, chỉ khác
ô *Tên máy này*.

> **Không bật thì không có gì thay đổi.** Và bật rồi mà mất mạng, sai token hay
> Telegram sập thì phần mềm **vẫn đăng bài như thường** — chỉ là không có tin
> nhắn. Việc báo cáo không bao giờ chặn việc đăng.

## v2.2.0 — 28/08/2026

**Gỡ hẳn cổng đăng ký và phê duyệt**

Bản `v2.0.1` chỉ *tắt* cổng đăng ký; mã của nó vẫn nằm trong phần mềm, vẫn có
màn hình chờ duyệt, vẫn có đường gọi ra máy chủ. Bản này **gỡ bỏ hoàn toàn**:

- Không còn màn hình đăng ký, không còn màn hình chờ duyệt, không còn mã máy.
- Không còn bất kỳ đường nào gọi ra máy chủ ngoài. Mở phần mềm là dùng được ngay,
  kể cả khi máy mất mạng.
- Bớt một thư viện phải cài (`cryptography`) — nó chỉ dùng để kiểm chữ ký của
  máy chủ duyệt.

Toàn bộ tính năng chạy hằng ngày **không đổi**: đăng bài, comment, nuôi nick,
tham gia nhóm, Page, lịch, dò spam — y nguyên.

## v2.1.0 — 28/08/2026

**Nhận ra nick bị Facebook chặn đăng bài**

Có lúc Facebook chặn một nick bằng cách mở hộp thoại *Tạo bài viết* rồi để trống
— không ô nhập, không nút, không báo lỗi gì. Trước đây phần mềm dò mất **41 giây**
rồi ghi `Hybrid thất bại`, nhìn như lỗi kỹ thuật.

- Giờ nhận ra trong **10 giây**, và cột Trạng thái ghi rõ:
  `🚫 Lỗi Composer` · `Nghỉ tới HH:MM`
- Nick đó vào đúng luồng nghỉ như khi bị gỡ bài: nghỉ một tiếng, rồi tự đăng thử
  một bài. Được thì chạy lại ngay; chưa được thì nghỉ tiếp — lặp tới khi Facebook
  thả. Bạn không phải làm gì.

**Nick nghỉ không còn bị nuôi quá tay**

Nick đang nghỉ mà **không tick Nuôi** thì không chạy phiên nuôi nào. Có tick thì
giữ đúng chu kỳ đã cài (mặc định 150 phút), thay vì nuôi liên tục mỗi slot.

**Log tham gia nhóm đọc được**

- Mỗi dòng log giờ có **tên tài khoản** ở đầu. Trước đây 5 phiên cùng ghi vào một
  file, các dòng trộn vào nhau, thấy `❌ Cookie hết hạn` mà không biết của nick nào.
- Hết cookie khi tham gia nhóm giờ **đổi luôn Trạng thái của tài khoản**, không
  chỉ ghi vào dòng lịch rồi bị ghi đè.

**Bớt báo nhầm cookie hết hạn**

Lịch tham gia nhóm mở tới 5 trình duyệt cùng lúc; trang tải chậm thì nhìn giống
hệt trang chưa đăng nhập. Giờ phần mềm **hỏi lại lần nữa** trước khi kết luận.
Cookie chết thật thì hỏi lại vẫn chết — chỉ tốn vài giây, và chỉ tốn đúng lúc
sắp báo lỗi.

## v2.0.1 — 25/08/2026

**Tắt cổng đăng ký.** Bản `v2.0.0` bật nó lên, khiến mọi máy cập nhật đều phải
xin duyệt mới chạy được. Chưa cần tới việc đó, nên bản này tắt đi: phần mềm chạy
y như chưa từng có tính năng ấy — không màn hình đăng ký, không gọi máy chủ,
không chặn ai.

Mọi thay đổi cốt lõi của `v2.0.0` bên dưới vẫn còn nguyên.

> Nếu bạn đang ở `v2.0.0` và bị hỏi đăng ký: cập nhật lên bản này là hết.

## v2.0.0 — 25/08/2026

> ⚠ Bản này bật cổng đăng ký — **đã tắt lại ở `v2.0.1`**. Đừng dùng bản này.

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
