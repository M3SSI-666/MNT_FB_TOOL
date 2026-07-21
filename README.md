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
| `cookie_exporter.py` | Đọc/refresh cookie từ profile trình duyệt |
| `db.py` | Lớp dữ liệu SQLite (`data/app.db`) |
| `utils.py` | Logger, jitter (chống nhịp cố định), phân loại lỗi |
| `static/` `templates/` | Giao diện web |

## Mã lỗi trạng thái lịch
- **Cookie hết hạn** → tài khoản bị đăng xuất, cần lấy lại `xs` (account tự bị đánh dấu).
- **Lỗi mạng/tạm thời** → thử lại sau.
- **Không thấy nút (FB đổi giao diện?)** → cần cập nhật selector.

## Test
```
python test_basic.py
```
