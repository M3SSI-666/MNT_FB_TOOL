# MNT FB AutoPost

Công cụ tự động đăng bài Facebook (nhóm + tường Page) bằng Playwright, có bảng
điều khiển web chạy trong cửa sổ app desktop.

## Yêu cầu
- Windows 10/11
- Python 3.11+ (nhớ tick **Add Python to PATH** khi cài)

## Cài đặt (máy mới)
Chạy **`INSTALL.bat`** — tự cài:
1. Python packages (`flask`, `playwright`, `openpyxl`…)
2. Chromium cho Playwright

Xong thì chạy `RUN_APP.bat`.

## Chạy
| File | Công dụng |
|------|-----------|
| `RUN_APP.bat` | Mở app dạng **cửa sổ** (pywebview). Nhấn **X** = tắt sạch (server + runner nền). |
| `START_BACKGROUND.bat` | Chạy **ẩn**, không cửa sổ — chỉ có server, điều khiển qua trình duyệt. |
| `RESTART.bat` | Tắt hết rồi mở lại cửa sổ (dùng sau khi sửa code Python). |
| `INSTALL_AUTOSTART.bat` | Đăng ký tự chạy nền khi mở máy. |
| `UNINSTALL_AUTOSTART.bat` | Gỡ tự chạy. |

Bảng điều khiển: `http://localhost:8080`

> **Chỉ chạy tại máy.** Server lắng nghe `127.0.0.1` nên không máy nào khác —
> kể cả trong cùng mạng LAN — chạm được cổng 8080. Vì vậy cũng không cần mật
> khẩu hay đăng nhập.

## Cấu trúc
| File | Vai trò |
|------|---------|
| `server.py` | Flask backend + login + mở cửa sổ app |
| `scheduler.py` | Vòng lặp đọc lịch, chạy đăng bài đúng giờ |
| `via_poster.py` / `page_via_poster.py` | Đăng bài bằng Playwright (Via / Hybrid / tường Page) |
| `fb_common.py` | Helper Playwright dùng chung cho 2 file poster ở trên |
| `nuoi_nick.py` | Tính năng nuôi nick (ramp-up + phiên hoạt động giống người) |
| `comment_bai.py` | Phiên đi comment vào danh sách bài viết (chạy tay được) |
| `xep_lich.py` | Phân bổ thời điểm phiên đăng + comment sao cho phủ đều khung giờ |
| `anh_bien_the.py` | Biến thể ảnh chống dedupe + công cụ đo pHash (chạy trực tiếp được) |
| `cookie_exporter.py` | Đọc/refresh cookie từ profile trình duyệt |
| `db.py` | Lớp dữ liệu SQLite (`data/app.db`) |
| `utils.py` | Logger, jitter (chống nhịp cố định), phân loại lỗi |
| `static/` `templates/` | Giao diện web |

> Sửa selector Facebook: nếu hàm nằm trong `fb_common.py` thì chỉ sửa một chỗ,
> cả hai poster cùng nhận. Đừng copy hàm ngược lại vào từng file.

## Nuôi nick
Bật bằng cách tick cột **Nuôi** ở bảng Tài khoản. Cột **Chu kỳ (p)** cạnh nó quyết
định bao lâu nuôi một lần — mặc định **150 phút (2h30)**, sửa được từng nick.

| Cột "Loại đăng" | Nick làm gì |
|---|---|
| Có (Homestay/Thuê/Bán) | Đăng bài bình thường; cứ mỗi *chu kỳ*, **một slot đăng biến thành phiên nuôi** (badge 🌱). Không thêm slot mới nên lịch không dày lên, và một slot chỉ đăng **hoặc** nuôi → không đụng nhau. |
| **Để trống** | **Chỉ nuôi, không đăng gì.** Vào tab **Lịch Nuôi nick** → *Gen lịch* để xếp phiên mỗi *chu kỳ* phút. Dùng cho nick yếu thời gian đầu; khi nick khỏe thì điền Loại đăng để chuyển sang vừa đăng vừa nuôi. |

Các phiên nuôi được **tách giãn tối đa**: mỗi nick lệch pha nhau (nick thứ k dời
phiên đầu đi k/n chu kỳ) và mọi phiên cách nhau tối thiểu 10 phút. Nhờ vậy các
slot 🌱 rải đều cả ngày thay vì dồn cục — ví dụ 3 nick chu kỳ 150 phút cho ra
`05:03 · 06:06 · 06:57 · 07:39 · 08:42 …` (cách nhau 42–63 phút). Tới giờ, phiên nuôi kéo dài 5–8 phút, làm
các hành động **bốc ngẫu nhiên tập con + xáo thứ tự**: lướt feed, xem story, like,
xác nhận lời mời kết bạn.

> Nick "chỉ nuôi" chạy bằng **runner Nuôi nick** riêng — nhớ bật nó ở tab
> **Hành động** (giống các runner khác).

### Cài đặt nuôi
Nút **⚙️ Cài đặt nuôi** ở tab *Lịch Nuôi nick*: bật/tắt từng hành động, số like,
độ dài phiên, và phần **nhắn tin nhóm**.

**Nhắn tin nhóm nội bộ** — tạo 1–2 nhóm chat chứa các nick cần nuôi, dán link nhóm
vào ô *Link nhóm chat*, rồi nhập **thư viện câu** (mỗi dòng 1 câu). Mỗi phiên bốc
2–3 câu ngẫu nhiên, gõ từng ký tự có độ trễ, không lặp hai câu giống nhau liền kề.

Có sẵn **500 câu mẫu** (công việc / công nghệ / nấu ăn / sức khỏe / đời sống) trong
[nuoi_msg_mau.txt](nuoi_msg_mau.txt) — bấm **📥 Nạp 500 câu mẫu** để dùng ngay, hoặc
**➕ Thêm vào** để nối vào thư viện đang có. Sửa file đó là đổi được bộ mẫu.

> **Acc bị hạn chế nhắn tin** (FB hiện *"Xác nhận danh tính để gửi tin nhắn"*) sẽ
> được **bỏ qua tự động** — phiên nuôi quay lại lướt newsfeed / story thay thế.
> Cố gửi tiếp lúc đang bị hạn chế chỉ khiến nick bị soi nặng hơn. Log ghi rõ nick
> nào đang bị chặn để bạn biết mà xử lý.

> **Gửi lời mời kết bạn mặc định TẮT** — đây là hành động dễ khóa nick nhất.
> Có nút bật trong cài đặt nhưng nên để nguyên.

> **Mặc định an toàn:** phần *gửi* lời mời kết bạn và *nhắn tin* **TẮT sẵn**
> (`nuoi_enable_addfriend`, `nuoi_enable_message` trong bảng `settings`). Gửi kết
> bạn hàng loạt là hành động dễ khóa nick nhất — chỉ bật khi đã chạy thử
> non-headless và chấp nhận rủi ro. Nhắn tin cần thư viện câu (`nuoi_msg_pool`) +
> nhóm chat nội bộ (`nuoi_msg_group_url`), xây sau.
>
> Chỉnh thông số nuôi (số like, số/tốc độ kết bạn, độ dài phiên, bật/tắt hành động)
> qua bảng `settings` — xem mặc định ở `DEFAULTS` trong [nuoi_nick.py](nuoi_nick.py).

## Đi comment (khi acc bị dỡ bài)
Nhiều acc bị Facebook dỡ bài ngay khi đăng nhưng **vẫn comment được**. Trong
nhóm, bài có comment mới sẽ nổi lên đầu — vậy thay vì cố đăng bài mới để rồi bị
dỡ, cho acc comment vào các bài cũ còn sống để đẩy chúng lên.

**Cách bật:**
1. Tab **💬 Bài đi Comment** → chọn loại → **+ Dán danh sách link** (mỗi dòng
   một link bài viết, link trùng tự bỏ).
2. **⚙️ Cài đặt comment** → nhập **thư viện câu** cho từng loại. Không có câu
   thì phiên tự bỏ qua.
3. Bảng **Tài khoản** → đặt cột **Loại đăng** thành `C_*` hoặc `X_*` (xem bảng dưới).
4. **Gen lịch** lại. Slot bị chuyển hiện badge 💬 Comment.

### Hai cách cho acc đi comment
| Cột **Loại đăng** | Acc làm gì |
|---|---|
| **C_Home** / **C_Thuê** / **C_Bán** | **Chỉ comment, không đăng bài.** Vào đúng lịch của mảng đó, mọi slot đều là phiên comment. Dùng cho acc bị dỡ bài. |
| **X_Home** / **X_Thuê** / **X_Bán** | **Vừa đăng vừa comment** theo tỉ lệ đặt ở *⚙️ Cài đặt comment* (mặc định 75% đăng / 25% comment). Ưu tiên comment vào bài của chính Page mình. |
| Homestay / Thuê / Bán | Chỉ đăng bài, không comment. |

Song song với cơ chế nuôi nick (Loại đăng trống + tick Nuôi = chỉ nuôi).

> Chỉ có **ba** cách dùng một acc: đăng, chỉ comment, đăng + comment — và cả ba
> đều nằm gọn trong cột *Loại đăng*. Bản đầu còn thêm cột tick **Comment** + cột
> **Chu kỳ CM**; hai cột đó **đã bị xoá** vì cùng một acc có hai nguồn sự thật
> mâu thuẫn nhau. Tài liệu hay ảnh chụp cũ nhắc tới chúng thì bỏ qua.

**Acc `C_*` tick thêm Nuôi thì vẫn được nuôi bình thường**: cứ mỗi *Chu kỳ (p)*
lại hy sinh một phiên comment để đi nuôi, y như acc đăng bài hy sinh một slot
đăng. Ví dụ acc `C_Home` nghỉ 12p + chu kỳ nuôi 150p, khung 05:00–23:00 cho ra
83 phiên comment + 7 phiên nuôi (`06:33 · 09:09 · 11:45 · 14:21 · 16:57 · 19:33
· 22:09`).

> **Thứ tự ba bước chuyển slot trong Gen lịch là mấu chốt**, đừng đảo:
> `1. nuôi nick → 2. comment theo chu kỳ → 3. quét nốt slot còn lại của acc C_*`
>
> Cả hai hàm `plan_*` chỉ đụng slot đang là `dang_bai`. Nếu quét bước 3 trước
> thì acc `C_*` bị khoá hết thành `comment` và **không bao giờ được nuôi** —
> hỏng im lặng, lịch trông vẫn bình thường. Có assertion canh riêng cái bẫy này.

> Lọc acc theo lịch phải so khớp **chính xác**, không dùng `in`: chuỗi `"C_Thuê"`
> chứa `"Thuê"` và `"C_Bán"` chứa `"Bán"`, so kiểu chuỗi con sẽ kéo acc chỉ
> comment vào nhóm đăng bài — hỏng im lặng, không báo lỗi gì.

### Phủ đều khung giờ — [xep_lich.py](xep_lich.py)
**Một phiên comment tính ngang một phiên đăng bài.** Cột *Nghỉ (p)* quyết định
nhịp: để 12 phút nghĩa là 5 phiên/giờ, dù phiên đó là đăng hay comment.

```
tổng lực = Σ (60 / nghỉ)     → số phiên mỗi giờ của cả đội
độ nén   = 60 / tổng lực     → khoảng cách lý tưởng giữa 2 phiên bất kỳ
```

Acc thứ *i* khởi điểm ở `start + i × độ_nén` (lệch pha), mỗi vòng chọn acc tới
lượt sớm nhất. Kết quả: đăng và comment **đan xen**, rải đều cả ngày.

> **Bắt buộc phải ép giãn cách tối thiểu.** Chỉ dựa vào "ai tới lượt sớm nhất"
> là chưa đủ: khi các acc có chu kỳ khác nhau (3 acc nghỉ 12p + 2 acc nghỉ 30p),
> sau vài vòng chúng trôi vào trùng pha và đẻ ra khoảng cách **0 phút** — hai
> phiên nổ cùng một phút, mở hai trình duyệt một lúc, rồi hở 6 phút phía sau.
>
> | hệ số ép | slot | gap nhỏ nhất | độ lệch chuẩn |
> |---|---|---|---|
> | (không ép) | 419 | **0** ❌ | 1.60 |
> | 0.70 | 415 | 2 | 1.33 |
> | **0.85** | 405 | 2 | **1.02** ← đang dùng |
> | 1.00 | 385 | 3 | 0.88 |
>
> Chọn 0.85: hết đụng độ, đều hơn hẳn, chỉ mất ~3% slot. Ép lên 1.00 đều nhất
> nhưng mất 8% slot và tạo nhịp **đều tăm tắp** — nhịp cố định lại chính là dấu
> hiệu máy, đúng thứ `utils.jitter_ms` sinh ra để tránh.

Form **Gen lịch** hiện sẵn số liệu trước khi bấm: lực đăng, lực comment, tổng
lực và trung bình bao nhiêu phút lại có một phiên nổ.

Nuôi nick chuyển slot trước, comment theo chu kỳ lấp vào slot đăng còn lại; hai
loại phiên không rơi sát nhau (dùng chung danh sách mốc giờ `da_dat`).

### Một phiên diễn ra thế nào
**Giống hệt luồng đăng bài bằng Page**, chỉ khác ở bước cuối: thay vì mở
composer để đăng thì vào từng link để comment.

1. Login acc cá nhân
2. Xem story cá nhân (~18s)
3. Lướt newsfeed cá nhân (~25s) — **không like**
4. **Chuyển sang Page được phân công** — bấm *Chuyển ngay* / *Dùng Trang* rồi
   inject `i_user`, tức là **chiếm quyền hoạt động của Page**. Từ đây mọi
   comment đi ra dưới danh nghĩa **Page**, không phải acc cá nhân. Lướt trong
   Page ~15s.
5. Vào từng link (bốc ngẫu nhiên) và **comment**, nghỉ 25–70 giây giữa hai bài
6. Lướt newsfeed ~20s và **like 1 bài** — chỗ duy nhất trong phiên có like
7. Kết thúc

Page lấy từ **cột Page của dòng lịch** (`ten_page`), giống hệt cách luồng đăng
bài Page xác định Page. Bước chuyển dùng lại `_switch_to_page()` của
[page_via_poster.py](page_via_poster.py) — **không chép lại**, vì selector nút
*Chuyển* / *Dùng Trang* đổi theo giao diện FB, chép ra hai bản là sau này sửa
sót một bản.

| Thông số | Mặc định | |
|---|---|---|
| Khởi động phiên | Bật | Story 18s + newsfeed 25s + Page 15s |
| Kết thúc phiên | Bật | Newsfeed 20s + like 1 bài |
| Số bài mỗi phiên | 10 | Bốc ngẫu nhiên trong danh sách của loại đó |
| Nghỉ giữa 2 bài | 25–70 giây | |

> **Slot không có Page** thì phiên vẫn chạy nhưng comment mang tên **acc cá
> nhân**. Chuyển Page thất bại cũng vậy — trường hợp này log ghi mức `ERROR`
> chứ không nuốt lặng lẽ, vì đó là khác hẳn ý định.

Story/newsfeed hỏng thì bỏ qua, vẫn đi comment — chúng chỉ để làm mềm hành vi.
Kết phiên chỉ chạy khi đã comment được ít nhất một bài: đang bị chặn mà còn nán
lại lướt + like là làm acc bị soi thêm.

> **Comment trùng nội dung là cách nhanh nhất mất luôn quyền comment** — và đó
> là đường cuối cùng của những acc đã bị dỡ bài. Thư viện câu càng nhiều càng
> tốt; code không bao giờ dùng lại một câu ở hai bài liền nhau
> (`pick_messages`). Acc bị chặn thì phiên **dừng ngay**, không cố comment
> tiếp, và trạng thái ghi rõ `BỊ CHẶN COMMENT`.
>
> **Không có cooldown** (bỏ theo yêu cầu): đến phiên là vào comment, mọi link
> trong danh sách đều hợp lệ mọi lúc. Số lần một bài bị comment mỗi ngày =
> `số slot comment × số bài mỗi phiên ÷ số link`. Muốn giãn ra thì **thêm link**
> hoặc giảm *Số bài mỗi phiên* / tăng *Nghỉ (p)* của acc comment — đẩy một bài
> quá dày thì admin nhóm đá acc ra, tệ hơn bị dỡ bài.

Lỗi khi comment **không** đặt `lan_cuoi` / `so_lan`, để hai cột đó phản ánh
đúng số comment đã lên thật.

### Link chết
Bài cũ bị xoá hoặc đổi phạm vi hiển thị là chuyện bình thường theo thời gian.
Hệ thống nhận ra và đánh dấu riêng — **không** gộp vào lỗi thường, vì link chết
thì xoá khỏi danh sách, còn selector hỏng thì phải sửa code.

Phát hiện lúc đang comment thì **xoá khỏi danh sách ngay**, log in ra đầy đủ URL.
Không có nút quét riêng: phiên comment vốn đã phải mở từng link, quét thêm một
lượt nữa chỉ là làm lại đúng việc đó bằng lượt truy cập thừa.

> Lỗi mạng/timeout **không** bị coi là link chết. Đánh dấu nhầm rồi xoá là mất
> link tốt, không lấy lại được.

Xác minh sau khi gửi: gõ xong không lỗi **không** có nghĩa comment đã lên. Code
kiểm ô nhập có được xoá trắng không (Facebook xoá trắng khi gửi thành công);
còn chữ trong ô là báo lỗi, tránh ghi ✅ cho lượt chẳng có comment nào rồi khoá
bài lại 6 tiếng.

Chạy tay để thử một phiên (hiện cửa sổ Chrome):
```
python comment_bai.py "Tên acc" homestay
```

### Thư viện câu — [comment_mau.txt](comment_mau.txt)
Trong **⚙️ Cài đặt comment** có hai nút:

- **➕ Thêm câu mẫu** — thêm câu còn thiếu vào cả 3 loại, giữ nguyên câu bạn tự
  viết. So khớp không phân biệt hoa thường nên bấm nhiều lần không sinh bản sao.
- **📥 Nạp lại từ đầu** — xoá sạch rồi thay bằng bộ mẫu 30 câu/loại. Có hỏi lại.

Cả hai chỉ đổi nội dung ô nhập, **phải bấm 💾 Lưu** mới ghi xuống DB.

Câu mẫu đi theo repo nên máy vệ tinh chỉ cần bấm nút thay vì gõ tay từng câu, và
mọi máy nạp ra cùng một bộ. Muốn sửa thì sửa `comment_mau.txt` rồi commit.

**Ba loại phải khác nhau.** Bộ 20 câu đời đầu dùng chung một danh sách cho cả ba
— cùng một chuỗi ký tự xuất hiện ở bài homestay, bài thuê lẫn bài bán, trong cùng
cụm nhóm, từ cùng một hệ thống Page. Đó đúng là kiểu trùng lặp dễ bị quét nhất.
Test kiểm điều này, ba bộ giao nhau bằng 0.

## Biến thể ảnh
Bật ở tab **Content → 🎲 Biến thể ảnh**. Mỗi lượt đăng sinh một bản sao trong
temp rồi đăng bản sao đó; **ảnh gốc không bao giờ bị sửa**, bản sao xoá ngay sau
khi đăng. Hai nick đăng cùng content vẫn ra hai bộ ảnh khác nhau. Không có thư
viện ảnh song song nào phải đồng bộ hay dọn dẹp.

Bản sao khác ảnh gốc ở 3 điểm: lệch nhẹ **độ sáng**, lệch nhẹ **độ tương phản**,
và một **mã 8 ký tự** vàng nhạt ở một trong 4 góc chọn ngẫu nhiên. Mã ghi vào
log (`🔖 tên_file → mã XXXXXXXX`) nên tra ngược được bài nào dùng ảnh nào. EXIF
gốc bị xoá sạch khi ghi lại.

### ⚠️ Hiệu quả né hash của bộ hiện tại rất thấp — số đo thật
```
python anh_bien_the.py data/media/content/homestay --manh
```
In ra khoảng cách Hamming gốc↔biến thể (0–64) trên chính ảnh của bạn. Facebook
coi **dưới 8 bit là cùng một ảnh**, dưới 16 vẫn trong ngưỡng khớp lỏng. (Đừng
lấy 32 làm mốc — 32/64 là mức của hai ảnh hoàn toàn không liên quan.)

| Thành phần | Dịch được |
|---|---|
| Mã 8 ký tự ở góc | **~0/64** |
| Sáng + tương phản | ~0,4/64 |
| **Cả bộ hiện tại (mạnh)** | **0,2–0,4/64** — dưới ngưỡng khớp rất xa |
| Lật ngang (tuỳ chọn) | ~33/64 |

Nói thẳng: bộ hiện tại đổi được byte file và xoá EXIF, nhưng **gần như không né
được perceptual hash**. Lý do mã ở góc vô hiệu: pHash hạ ảnh về lưới 32×32 rồi
chỉ đọc 8×8 hệ số DCT tần số thấp nhất — vài chục pixel ở một góc bị làm nhoè
gần hết ở bước đó. **Tăng cỡ chữ mã không giúp gì.**

Muốn né thật thì hoặc bật **lật ngang**, hoặc lấy lại từ git các phép đã bị bỏ:
crop mép + xoay + **trường sáng tần số thấp** (`_truong_sang()`, ~15/64 bit — nó
nhắm đúng dải hệ số mà hash đọc). Sửa tham số thì **đo lại**, đừng đoán.

> **Kể cả khi đo đẹp cũng chưa phải viên đạn bạc.** Đây chỉ là so khớp mức
> *pixel*. Facebook còn có mô hình nhúng ảnh (SimSearchNet++) so khớp theo *nội
> dung*, cố ý thiết kế để chịu được crop/xoay/đổi màu. Và cờ spam là đa tín
> hiệu: **caption lặp lại**, tần suất đăng, số nhóm trên một nick thường nặng
> hơn ảnh.
>
> Muốn biết thật sự có tác dụng: chạy **một nhóm nick có bật, một nhóm không**
> trong 1–2 tuần rồi so tỉ lệ bị gắn cờ. Cách chắc chắn nhất vẫn là có **nhiều
> ảnh gốc khác nhau** để xoay vòng.

Pillow là dependency **tuỳ chọn**: thiếu nó thì tính năng tự tắt và bài vẫn đăng
bằng ảnh gốc, có cảnh báo trong log.

## Sức khoẻ acc — tự tắt acc chết ([suc_khoe_acc.py](suc_khoe_acc.py))

Đo trên 3 ngày log thật (766 phiên, 10 acc) thấy **một acc chết chiếm 71/110 lỗi
của cả hệ thống** mà không ai biết, vì nó chỉ lộ ra khi ngồi bới log. Đây là thứ
phát hiện chuyện đó tự động.

Có đúng **hai kiểu hỏng**, và chúng đòi hai cách xử lý ngược nhau:

| Kiểu | Dấu hiệu thật đã gặp | Xử lý |
|---|---|---|
| **Bị chặn tạm** | `The Anh Nguyen` hỏng 29 phiên liên tiếp rồi tự hồi, hôm sau chạy 29/34 | 😴 nghỉ 3h, tự chạy lại |
| **Chết hẳn** | `Thao Ngan` chạy 9/9, rồi hỏng 71 phiên liên tiếp, không bao giờ hồi | ❌ tắt hẳn, chờ người |

Chuỗi lỗi liên tiếp **không** phân biệt được hai ca này (29 và 71 đều dài), nên
dùng hai tín hiệu tách rời:

- **Tầng 1** — 5 lỗi liên tiếp → cho nghỉ 3 giờ. Sai cũng không hại, acc tự quay lại.
- **Tầng 2** — 20 phiên gần nhất hỏng ≥80% → tắt hẳn. Chỉ acc không hồi mới tụt tới mức này.

Chạy lại đúng 766 phiên đó: tắt 1 acc (đúng acc đã chết), cho nghỉ 2 acc rồi cả
hai chạy tiếp, không đụng 7 acc khoẻ, cứu 86/766 slot (11%). **Sửa ngưỡng thì nên
chạy lại phép đo đó trước.**

### Thấy ở đâu
- Cột **Trạng thái** tab Tài khoản: `😴 Nghỉ tới 14:20` (cam) / `❌ Hỏng` (đỏ).
  Rê chuột hiện chi tiết. Bấm vào ra dropdown — chọn `Active` là **bật lại**.
- Thanh tóm tắt: ô `Nghỉ tạm` và `⚠️ Hỏng`, chỉ hiện khi thực sự có acc dính.
- **Toast** bắn ngay lúc máy quyết định, hiện một lần rồi thôi.

### Vài điểm dễ hiểu nhầm
- **Nghỉ tạm không đổi `trang_thai`** — acc vẫn `Active`, chỉ bị chặn ở khâu giao
  phiên. Đổi thì Gen lịch lần sau loại acc đó vĩnh viễn.
- **Nghỉ tạm vẫn cho nuôi nick chạy** — xem story / lướt feed là thứ có cơ gỡ acc
  ra. **Tắt hẳn thì chặn tất**, vì `trang_thai='Hỏng'` làm `get_account_by_name`
  không tìm ra acc nữa, cho nuôi chạy tiếp chỉ đổ lỗi vô nghĩa vào log.
- **Slot bị bỏ qua ghi `😴` chứ không ghi `❌`** — đếm nó là lỗi thì bộ theo dõi tự
  bơm phồng chính mình: acc nghỉ đẻ ra thêm "lỗi", thêm lỗi lại kéo dài nghỉ.
- **Cookie hết hạn không tính vào sức khoẻ** — nó có cách xử lý riêng (đăng nhập
  lại), không phải dấu hiệu bị Facebook chặn.
- **Bật lại về `Active` xoá sạch lịch sử phiên** — không thì phiên hỏng kế tiếp
  chạm lại ngưỡng ngay, nhìn như nút bật không ăn.

## Mã lỗi trạng thái lịch
- **Cookie hết hạn** → tài khoản bị đăng xuất, cần lấy lại `xs` (account tự bị đánh dấu).
- **Lỗi mạng/tạm thời** → đã tự thử lại 3 lần (cách nhau ~30s rồi ~60s) mà vẫn hỏng.
- **Bị giới hạn — thử lại sau** → Facebook đang chặn. Cố ý **không** tự thử lại,
  vì đăng dồn lúc này là cách nhanh nhất để acc bị khoá. Nên giãn lịch ra.
- **Không thấy nút (FB đổi giao diện?)** → cần cập nhật selector.

## Bảo mật
- Bảng Tài khoản **che** password / `xs` / 2FA / thông tin khôi phục. Máy tại chỗ
  bấm vào ô là hiện giá trị thật để sửa; phiên **truy cập từ xa không xem được**
  credential (cố ý — mật khẩu Facebook không nên đi qua mạng chỉ để hiển thị).
- `data/`, `cookies/`, `profiles/` không bao giờ được commit. Nếu sửa `.gitignore`,
  nhớ rằng **git không hỗ trợ comment ở cuối dòng** — ghi chú phải nằm trên dòng
  riêng, nếu không pattern hỏng và dữ liệu nhạy cảm lọt vào lịch sử git.
- Kiểm tra nhanh trước khi commit: `git check-ignore -q data/app.db && echo OK`

## Test
```
python test_basic.py   # 381 assertion, chạy trên DB tạm — không đụng data thật
```
