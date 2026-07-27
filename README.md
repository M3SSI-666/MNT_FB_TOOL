# MNT FB AutoPost

Công cụ tự động đăng bài Facebook (nhóm + tường Page) bằng Playwright, có bảng
điều khiển web chạy trong cửa sổ app desktop, và điều khiển được từ xa qua Tailscale.

## Yêu cầu
- Windows 10/11
- Python 3.11+ (nhớ tick **Add Python to PATH** khi cài)

## Cài đặt (máy mới)
Chạy **`INSTALL.bat`** — tự cài:
1. Python packages (`flask`, `playwright`)
2. Chromium cho Playwright
3. Tailscale (để điều khiển từ xa)

Sau đó (làm tay 1 lần):
- Mở **Tailscale** → đăng nhập Google (cùng tài khoản với các máy/điện thoại khác).
- Chạy `RUN_APP.bat` → vào tab **Hành động** → đặt **mật khẩu truy cập từ xa**.

## Chạy
| File | Công dụng |
|------|-----------|
| `RUN_APP.bat` | Mở app dạng **cửa sổ** (pywebview). Nhấn **X** = tắt sạch (server + runner nền). |
| `START_BACKGROUND.bat` | Chạy **ẩn**, không cửa sổ — chỉ có server, điều khiển qua trình duyệt. |
| `RESTART.bat` | Tắt hết rồi mở lại cửa sổ (dùng sau khi sửa code Python). |
| `INSTALL_AUTOSTART.bat` | Đăng ký tự chạy nền khi mở máy. |
| `UNINSTALL_AUTOSTART.bat` | Gỡ tự chạy. |

Bảng điều khiển: `http://localhost:8080`

## Điều khiển từ xa (Tailscale)
1. Máy đích: cài Tailscale + đăng nhập, app đang chạy, **không để máy ngủ**.
2. Máy/điện thoại điều khiển: cài Tailscale, đăng nhập **cùng tài khoản**.
3. Mở trình duyệt → `http://<ten-hoac-ip-may-dich>:8080` → nhập mật khẩu.

> Máy tại chỗ (cửa sổ app / localhost) không cần mật khẩu; chỉ truy cập từ xa
> mới yêu cầu đăng nhập. **Không bật "exit node"** trên máy đăng bài để giữ IP.

## Cấu trúc
| File | Vai trò |
|------|---------|
| `server.py` | Flask backend + login + mở cửa sổ app |
| `scheduler.py` | Vòng lặp đọc lịch, chạy đăng bài đúng giờ |
| `via_poster.py` / `page_via_poster.py` | Đăng bài bằng Playwright (Via / Hybrid / tường Page) |
| `fb_common.py` | Helper Playwright dùng chung cho 2 file poster ở trên |
| `nuoi_nick.py` | Tính năng nuôi nick (ramp-up + phiên hoạt động giống người) |
| `cookie_exporter.py` | Đọc/refresh cookie từ profile trình duyệt |
| `db.py` | Lớp dữ liệu SQLite (`data/app.db`) |
| `utils.py` | Logger, jitter (chống nhịp cố định), phân loại lỗi |
| `static/` `templates/` | Giao diện web |

> Sửa selector Facebook: nếu hàm nằm trong `fb_common.py` thì chỉ sửa một chỗ,
> cả hai poster cùng nhận. Đừng copy hàm ngược lại vào từng file.

## Page nào được đăng?
Cột **UID Page** ở bảng Tài khoản (danh sách chọn, lấy từ bảng Page) mới là thứ
**quyết định page đăng thật**. Cột *Tên Page* chỉ để bạn gợi nhớ.

Lý do: tra theo tên không đáng tin — nhiều page **trùng tên** thì hệ thống lấy đại
một cái, và so tên còn **phân biệt hoa/thường** (`HomeStay` ≠ `Homestay` → tra ra
rỗng, lỗi "Không có Page UID").

> Acc chưa gán UID vẫn chạy được (tự dò theo tên như cũ), nhưng **nên gán UID cho
> mọi acc** — đó là cách duy nhất chắc chắn đăng đúng page.

## Nuôi nick
Bật bằng cách tick cột **Nuôi** ở bảng Tài khoản. Cột **Chu kỳ (p)** cạnh nó quyết
định bao lâu nuôi một lần — mặc định **150 phút (2h30)**, sửa được từng nick.

| Cột "Loại đăng" | Nick làm gì |
|---|---|
| Có (Homestay/Thuê/Bán) | Đăng bài bình thường; cứ mỗi *chu kỳ*, **một slot đăng biến thành phiên nuôi** (badge 🌱). Không thêm slot mới nên lịch không dày lên, và một slot chỉ đăng **hoặc** nuôi → không đụng nhau. |
| **Để trống** | **Chỉ nuôi, không đăng gì.** Vào tab **Lịch Nuôi nick** → *Gen lịch* để xếp phiên mỗi *chu kỳ* phút. Dùng cho nick yếu thời gian đầu; khi nick khỏe thì điền Loại đăng để chuyển sang vừa đăng vừa nuôi. |

Các phiên nuôi được **giãn cách tối thiểu 10 phút** với nhau nên không có chuyện
nhiều nick cùng mở trình duyệt một lúc. Tới giờ, phiên nuôi kéo dài 5–8 phút, làm
các hành động **bốc ngẫu nhiên tập con + xáo thứ tự**: lướt feed, xem story, like,
xác nhận lời mời kết bạn.

> Nick "chỉ nuôi" chạy bằng **runner Nuôi nick** riêng — nhớ bật nó ở tab
> **Hành động** (giống các runner khác).

> **Mặc định an toàn:** phần *gửi* lời mời kết bạn và *nhắn tin* **TẮT sẵn**
> (`nuoi_enable_addfriend`, `nuoi_enable_message` trong bảng `settings`). Gửi kết
> bạn hàng loạt là hành động dễ khóa nick nhất — chỉ bật khi đã chạy thử
> non-headless và chấp nhận rủi ro. Nhắn tin cần thư viện câu (`nuoi_msg_pool`) +
> nhóm chat nội bộ (`nuoi_msg_group_url`), xây sau.
>
> Chỉnh thông số nuôi (số like, số/tốc độ kết bạn, độ dài phiên, bật/tắt hành động)
> qua bảng `settings` — xem mặc định ở `DEFAULTS` trong [nuoi_nick.py](nuoi_nick.py).

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
python test_basic.py   # 36 assertion, chạy trên DB tạm — không đụng data thật
```
