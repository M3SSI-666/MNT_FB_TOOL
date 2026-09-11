# Các bản đã phát hành

Mỗi mục dưới đây là một bản có thể cài. Nút **Cập nhật** trong phần mềm đọc
đúng file này để hiện danh sách cho bạn chọn.

> **Nên chọn bản mới nhất.** Lùi về bản cũ là mất những gì đã sửa sau đó. Dữ
> liệu của bạn — tài khoản, page, content, UID nhóm — **không bị đụng tới** dù
> cập nhật hay lùi, vì chúng nằm ngoài phần mã nguồn. Trước mỗi lần cập nhật,
> phần mềm tự sao lưu dữ liệu vào `%LOCALAPPDATA%\MNT FB AutoPost\backup`.

---

## v2.10.0 — 11/09/2026

**Comment: bài của chính mình được 2 câu, bài Page khác vẫn 1 câu**

Trước đây mỗi bài chỉ nhận đúng một câu comment, không phân biệt bài của ai.
Giờ tách làm hai mức:

- **Bài do chính Page mình đăng: 2 câu** — tự trả lời dưới bài của mình là
  hành vi bình thường, và mỗi comment là một lần bài nổi lại lên đầu nhóm.
- **Bài của Page khác: 1 câu** — người lạ vào comment liền hai câu dưới một
  bài là thứ admin nhóm nhìn thấy ngay.

Cả hai chỉnh được trong **Cài đặt comment**. Để `0` ở ô "Page khác" thì những
bài đó bị bỏ hẳn khỏi phiên, không mở trang ra rồi mới bỏ đi.

Hai câu trên cùng một bài luôn **khác nhau** và cách nhau **20–45 giây** — dài
hơn hẳn nghỉ giữa hai bài (10–15 giây), vì hai comment nối đuôi trong vài giây
dưới cùng một bài đọc ra là máy ngay.

Trần thời gian một phiên comment nới từ 15 lên **25 phút**: phiên 9 bài chính
chủ nay tốn khoảng 14 phút, sát trần cũ đến mức mạng chậm một chút là bị cắt
giữa chừng.

Bảng lịch hiện thêm tổng số câu, ví dụ `💬 09:42 · 9/9 bài (15 câu)`.

## v2.9.2 — 28/08/2026

**Sửa: máy không ngủ mà không có lý do gì**

Tới giờ khuya mà máy vẫn chạy tiếp, không báo lỗi, không dấu hiệu — và hôm đó
sẽ không bao giờ ngủ nữa.

Nguyên nhân là thứ tự hai dòng lệnh. Phần mềm **đánh dấu "hôm nay đã nghỉ rồi"
TRƯỚC khi thật sự cho máy nghỉ**. Chỉ cần bước sau hỏng — hoặc phần mềm bị tắt
đúng khoảnh khắc giữa hai dòng — là mốc còn đó mà việc thì chưa làm. Vòng kiểm
tiếp theo nhìn vào mốc, thấy "xong rồi", và bỏ qua.

Giờ **làm xong mới đánh dấu**. Có trục trặc thì vòng sau thử lại, vì cửa sổ tắt
máy rộng 30 phút.

Áp dụng cho cả mốc buổi sáng.

## v2.9.1 — 28/08/2026

**Sửa: bấm "Tắt phần mềm" mà phần mềm không tắt**

Bấm nút đó thì runner chết hết thật, nhưng **server vẫn sống**. Đo trên máy
thật: **21 phút sau vẫn phục vụ bình thường**. Nhìn thì như đã tắt — runner
dừng, giao diện im — nhưng phần mềm vẫn còn đó, vẫn giữ cổng, vẫn chạy lịch.

Nguyên nhân là một dòng thiếu hạn chờ. Lệnh diệt tiến trình đợi tới khi ống dữ
liệu đóng, mà tiến trình con của Chrome giữ ống đó — nên nó **treo vĩnh viễn**,
và lệnh thoát nằm ngay phía sau không bao giờ chạy tới.

- Mọi lệnh diệt tiến trình giờ đều có **hạn chờ 15 giây**
- Việc dọn dẹp chạy tách riêng, chờ tối đa **25 giây** rồi **thoát dù xong hay
  chưa** — tắt là phải tắt
- **Nút X cũng vậy.** Nó gọi cùng đoạn mã đó, nên trước đây bấm X mấy lần cửa sổ
  cũng có thể không nhúc nhích

> Sau khi sửa: bấm Tắt phần mềm → **thoát sạch trong 5 giây**, không còn tiến
> trình nào sót lại.

## v2.9.0 — 28/08/2026

**Mở phần mềm giữa giờ làm việc thì runner tự dựng dậy**

Lịch hằng ngày chỉ nổ **một lần mỗi ngày**, và có ghi dấu *"hôm nay chạy rồi"*.
Nên tình huống rất thường gặp này lọt lưới:

```
07:00   máy chạy, runner bật, đánh dấu đã chạy hôm nay
12:00   bạn tắt máy đi ăn
14:00   bật máy lại  →  phần mềm thấy "hôm nay chạy rồi"  →  NẰM IM
```

Mất trắng cả buổi chiều, mà không có một dấu hiệu nào.

Giờ khi phần mềm vừa mở, nếu **đang trong giờ làm việc** thì nó dựng runner đã
tick dậy luôn, bất kể hôm nay đã chạy chưa. Giờ làm việc tính vắt qua nửa đêm:
đặt `07:00 → 02:00` thì 23h hay 1h sáng đều là đang trong giờ làm.

Chỉ dựng **một lần cho mỗi lần mở phần mềm**. Bấm Dừng một runner giữa ngày thì
nó nằm yên, không tự bật lại sau 20 giây.

> Nghĩa là: máy tắt hẳn, mở lại lúc nào cũng được — miễn trong giờ làm việc là
> phần mềm tự lên và tự chạy. Muốn cho nghỉ hẳn thì bấm **Tắt phần mềm**.

## v2.8.2 — 28/08/2026

**Sửa hai chỗ gây hiểu nhầm ở Lịch của máy**

**Nút "Chạy thử ngay" đặt tên sai.** Nó không thử gì cả — nó bật runner thật,
ngay lúc bấm. Tên đó khiến người dùng hoặc ngại bấm, hoặc bấm rồi tưởng chưa
chạy. Đổi thành **"Bật runner ngay"**, đúng việc nó làm.

**Ô giờ không nói gì khi đã lưu.** Gõ `01:00` thành `02:00` xong thì không biết
phải bấm đâu — vì thật ra không phải bấm đâu cả, nó tự lưu. Nhưng không nói ra
thì làm sao biết. Giờ:

- Lưu **ngay trong lúc gõ**, không phải rời khỏi ô. Gõ xong đóng luôn cửa sổ
  cũng không mất — trước đây thì mất, mà ô này quyết định mấy giờ máy ngủ.
- Hiện chữ **✓ Đã lưu** ngay cạnh, và nhãn ở đầu bảng đổi theo:
  `07:00 → 02:00`.

## v2.8.1 — 28/08/2026

**Đổi giờ sáng: giờ chỉ cần sửa một chỗ**

Giờ sáng vốn nằm ở **hai nơi**: phần mềm biết *"7h thì bật runner"*, còn việc
đánh thức máy là một **tác vụ của Windows**. Đổi trong phần mềm mà quên chạy lại
`CAI_LICH_MAY.bat` thì máy vẫn thức — **nhưng theo giờ cũ**.

Đó là kiểu hỏng khó chịu nhất: nhìn thì như chạy được, chỉ là muộn mấy tiếng, và
**không có lấy một dòng lỗi nào** để bạn biết.

Giờ phần mềm tự đi đọc giờ trong tác vụ Windows rồi đối chiếu, và nói thẳng ra:

- Khớp → `✅ Windows sẽ đánh thức máy lúc 07:00 — khớp với giờ bạn đặt.`
- Lệch → `⚠ Bạn đặt 02:00, nhưng Windows vẫn đánh thức máy lúc 07:00.`
  kèm nút **Sửa lại thành 02:00** — bấm một cái, xác nhận với Windows, xong.
- Chưa cài bao giờ → nút **Cài ngay**.

**Nên từ nay đổi giờ chỉ là sửa trong phần mềm rồi bấm nút hiện ra.** Không phải
nhớ chạy file nào nữa.

## v2.8.0 — 28/08/2026

**Lịch của máy: sáng tự chạy, khuya tự nghỉ**

Máy trạm chạy cả ngày thì tốn điện và hao máy; mà sáng nào cũng phải nhớ bấm Run
bốn cái thì trước sau gì cũng có hôm quên.

Đặt ở tab **Hành động** → *⏰ Lịch của máy*:

- **Sáng, lúc `07:00`** — tự bật những runner bạn **tick chọn**. Tick cái nào
  chạy cái đó, đổi lúc nào cũng được.
- **Khuya, lúc `01:00`** — dừng **hết** runner, rồi cho máy **ngủ đông** (hoặc
  ngủ thường / tắt hẳn / không làm gì — tuỳ bạn).

**Một sự thật cần biết trước.** Máy đã **tắt hẳn** thì không phần mềm nào bật nó
lên được — điện đã ngắt, Windows không còn chạy. Nên:

- Chọn **Ngủ đông** rồi bấm đúp `CAI_LICH_MAY.bat` **một lần** → Windows tự đánh
  thức máy đúng giờ sáng. Tốn điện gần như bằng tắt hẳn, mà máy thức dậy là phần
  mềm đã sẵn ở đó, không phải khởi động lại.
- Chọn **Tắt hẳn** thì bạn phải tự vào BIOS bật `RTC Alarm`. Phần mềm có hiện
  cảnh báo này ngay khi bạn chọn, để không ai sáng hôm sau ngồi chờ một cái máy
  nằm im.

Có nút **Chạy thử ngay** để bật đúng những runner đã tick mà không phải chờ tới
7h sáng mới biết mình tick sai.

> Việc cho máy nghỉ chỉ nổ trong **30 phút** quanh mốc giờ đã đặt. Đêm qua máy
> tắt, 9h sáng bạn mở phần mềm lên thì nó **không** ngủ đông ngay lúc đó — lỡ
> giờ thì bỏ hôm ấy, không làm bù.

## v2.7.1 — 28/08/2026

**Sửa: nhiều nick hỏng cùng lúc thì phần lớn bị bỏ quên 90 phút**

Mỗi lượt quét chỉ cứu tối đa 3 nick, để không mở cả loạt trình duyệt cùng lúc.
Nhưng phần lọc lại ghi dấu *"vừa thử"* cho **mọi** nick hỏng, không chỉ 3 nick
thật sự được thử. Có 10 nick hỏng thì 7 nick bị khoá 90 phút mà chưa hề được
đụng tới.

Giờ chỉ nick nào thật sự được thử mới bị ghi dấu; số còn lại vào lượt sau ngay.

> Máy càng nhiều nick thì lỗi này càng nặng — đúng hướng bạn đang mở rộng.

## v2.7.0 — 28/08/2026

**Tự lấy lại phiên cho nick báo hết cookie**

`xs` trong phần mềm và cookie trong profile Chrome là **hai kho riêng biệt**.
Cái trong phần mềm là ảnh chụp lúc bạn nhập tay; cái trong profile do Chrome giữ
và được Facebook làm mới mỗi lần nick hoạt động.

Đo trên máy thật: **12/12 nick đọc được đều có `xs` ở profile khác hẳn `xs` trong
phần mềm** — không một cái nào còn trùng. Nghĩa là mọi thứ dựng phiên từ dữ liệu
(đăng chế độ VIA, tham gia nhóm, xuất cookie) đều đang chạy bằng giá trị đã cũ.

**Giữ cho `xs` không cũ đi.** Sau mỗi phiên vừa đóng trình duyệt, phần mềm lấy
`xs` mới nhất từ profile ghi lại vào dữ liệu. Trước đây việc này chỉ chạy khi bạn
tự bật cột *Refresh = Yes*, nên giá trị cứ cũ dần cho tới ngày Facebook thu hồi
hẳn — lúc đó nick báo "hết cookie" trong khi profile vẫn còn đăng nhập tốt.

> Chạy ngay lần đầu trên máy tác giả: **11 nick lấy được `xs` mới**.

**Tự cứu nick đã báo hết cookie.** Cứ 10 phút, phần mềm mở profile của nick đó
lên và hỏi Facebook xem còn đăng nhập không. Còn thì lấy `xs` mới, trả nick về
**Active**, và nhắn `🟢 HOẠT ĐỘNG TRỞ LẠI` vào Telegram. Bạn không phải làm gì.

Cách này **không dùng một chữ mật khẩu nào**. Với Facebook thì đó chỉ là nick mở
trình duyệt xem trang chủ — đúng thứ nó vẫn làm hằng ngày. Khác hẳn đăng nhập
lại tự động, vốn là hành vi dễ bị hỏi xác minh nhất.

Có mấy chốt an toàn: bỏ qua nick đang chạy phiên, từ chối khi profile đã đăng
nhập sang nick khác, mỗi nick chỉ thử lại sau **90 phút**, và mỗi lượt chỉ cứu
tối đa 3 nick để không mở cả loạt trình duyệt cùng lúc.

> Nick nào profile cũng đã đăng xuất thì vẫn phải nạp cookie tay như trước.

## v2.6.2 — 28/08/2026

**Sửa: máy bật liên tục thì chỉ sao lưu đúng một lần rồi thôi**

Bản `v2.6.0` chỉ thử sao lưu **một lần cho mỗi lần chạy phần mềm**. Máy nào tắt
mở mỗi ngày thì không sao, nhưng **máy trạm bật suốt** — đúng cách chạy thường
gặp nhất — sẽ sao lưu đúng một lần lúc mở, rồi không bao giờ nữa: hôm sau, tuần
sau đều không chạy, mà không có một dấu hiệu nào.

Giờ phần mềm hỏi lại **mỗi 30 phút** xem hôm nay đã sao lưu chưa. Hỏi là rẻ:
xong rồi thì nó trả lời ngay, không đụng vào dữ liệu.

Kèm theo đó, hai chỗ khác cũng hết hỏng:

- **Mất mạng lúc mở phần mềm** thì nửa tiếng sau tự thử lại, thay vì bỏ cả ngày.
- **Sang ngày mới** trên máy không tắt: chậm nhất 30 phút là có bản của ngày mới.

## v2.6.1 — 28/08/2026

**Sao lưu gửi vào cùng khung chat với cảnh báo**

Bỏ ô *Gửi vào đâu* riêng trong bảng Sao lưu. Giờ nó dùng thẳng Chat ID đã điền
ở tab **Báo về Telegram** — chỉ phải điền một chỗ, và thêm một trạm mới cũng chỉ
là điền đúng một bộ thông số.

> Đánh đổi: ai ở trong khung chat đó cũng nhận được file sao lưu. File đã mã hoá
> nên không có mật khẩu thì không mở ra được, nhưng họ vẫn **giữ được file**.
> Nên hãy đặt mật khẩu mã hoá **khác** mọi mật khẩu mà người trong nhóm có thể
> đoán ra.

## v2.6.0 — 28/08/2026

**Sao lưu hằng ngày, tự gửi đi nơi khác, đã mã hoá**

Bản `v2.5.0` sửa cho bản sao lưu dùng được, nhưng nó vẫn nằm trên chính cái máy
có thể hỏng. Bản này đưa nó ra khỏi máy.

**Cách chạy** — mỗi ngày, lần đầu bạn mở phần mềm:

1. Tạo bản sao đầy đủ, giữ **14 bản gần nhất** trên máy
2. **Mã hoá** bản đó bằng mật khẩu của bạn
3. Gửi lên **kênh Telegram riêng** của bạn, tên file mang tên máy:
   `MNT_MayNha_20260906.db.enc`

Máy nào cũng tự làm, nên thêm trạm mới chỉ là điền cùng token và cùng mật khẩu.

**Vì sao bắt buộc mã hoá.** File sao lưu chứa mật khẩu Facebook, cookie `xs`,
mã 2FA và email khôi phục của **mọi tài khoản** — ai cầm được nó là đăng nhập
được vào tất cả. Nó không phải "file dữ liệu", nó là **xâu chìa khoá**. Nên nó
được mã hoá trước khi rời khỏi máy, và gửi vào **kênh riêng chỉ mình bạn**,
không phải nhóm quản trị: quản trị viên cần biết acc nào hỏng, không cần mật
khẩu của acc đó.

**Biết ngay khi sao lưu ngừng chạy.** Bản tổng kết hằng ngày thêm một dòng —
`🗄 Sao lưu: 08:14 · 17 tài khoản`, hoặc `⚠️ Sao lưu: 4 ngày trước`. Không có
dòng này thì một trạm hỏng thầm lặng nhiều tháng mà không ai biết.

**Đường về đã diễn tập thật.** Thêm `KHOI_PHUC_DU_LIEU.bat`: tắt phần mềm, chọn
bản sao lưu (hoặc dán file `.enc` tải từ Telegram), nhập mật khẩu. Nó giải mã,
**đếm lại số tài khoản**, rồi mới thay vào — và cất bản đang dùng sang một bên
trước, phòng khi bạn chọn nhầm file.

> Đã chạy thử trọn vòng trên một máy giả: xoá sạch dữ liệu, rồi khôi phục từ file
> `.enc` — về đủ 17 tài khoản, 1321 dòng lịch, 55 content, 128 UID nhóm, và đủ
> cả 17 mật khẩu lẫn 17 cookie.

> ⚠ **Ghi mật khẩu mã hoá ra giấy.** Còn một máy sống thì còn giải mã được. Mất
> hết máy **và** quên mật khẩu thì mọi bản sao lưu thành vô dụng vĩnh viễn —
> mã hoá đúng cách thì không có cửa sau.

## v2.5.0 — 28/08/2026

**Sửa: bản sao lưu trước khi cập nhật chưa bao giờ dùng được**

Đây là lỗi nặng nhất tìm được từ trước tới nay, và nó đã âm thầm suốt từ
`v1.0.2` — bản đầu tiên có tính năng sao lưu.

Mỗi lần cập nhật, phần mềm vẫn in `[OK] Da sao luu` rồi đi tiếp. Nhưng kiểm lại
bốn bản sao lưu đang có trên máy: **cả bốn đều không mở được**, SQLite báo
*file is not a database*. Dữ liệu thật 716 KB, bản sao ra 4 KB.

Hai nguyên nhân chồng lên nhau:

1. **Chép thiếu.** Cơ sở dữ liệu chạy chế độ WAL — những gì vừa ghi nằm ở file
   `app.db-wal`, chưa gộp vào `app.db`. Lệnh `copy` chỉ chép `app.db`, tức là
   chép đúng cái phần chưa có gì.
2. **Chép nhầm chỗ.** Bản cài đặt để dữ liệu ở `%LOCALAPPDATA%`, nhưng phần sao
   lưu lại đi tìm file dữ liệu **cạnh mã nguồn**. Trên máy vệ tinh nó không thấy
   gì, in *"chua co du lieu - bo qua sao luu"* rồi cập nhật luôn — nghĩa là
   **các máy cài đặt chưa từng được sao lưu lần nào**.

Giờ phần sao lưu hỏi thẳng phần mềm xem dữ liệu thật nằm đâu, dùng `VACUUM INTO`
của SQLite để gộp cả WAL, rồi **mở lại bản vừa tạo và đếm lại số tài khoản**.
Không khớp thì xoá bản đó đi và **dừng cập nhật**.

> Bản sao lưu đầu tiên dùng được thật đã tạo trên máy tác giả: 628 KB, mở lên đủ
> 17 tài khoản, 1321 dòng lịch, 55 content.

Nếu bạn từng cập nhật rồi mất dữ liệu và không khôi phục được — đây là lý do.

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
