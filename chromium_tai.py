"""Tải Chromium lần chạy đầu, có báo tiến độ.

Chromium nặng 683 MB nên không nhét vào file cài được — phải tải về lần đầu.
Trước đây việc này nằm trong INSTALL.bat: chạy `playwright install chromium`
rồi ngồi nhìn cửa sổ đen hàng chục phút, không biết nó đang làm gì hay đã treo.

Ở đây tách làm hai phần:
  - phần thuần tính toán (`doc_phan_tram`) — kiểm được bằng assertion
  - phần chạy tiến trình con — server gọi, giao diện hỏi tiến độ mỗi giây
"""

import os
import re
import subprocess
import sys
import threading
from pathlib import Path

# Playwright in tiến độ ra dạng:
#   |■■■■■■■■            | 42% of 139.2 MiB
# Bắt phần trăm ở bất kỳ đâu trong dòng. Dùng lastindex để lấy số cuối cùng:
# một dòng có thể chứa cả tên bản build lẫn phần trăm.
_PHAN_TRAM = re.compile(r"(\d{1,3})\s*%")


def doc_phan_tram(dong):
    """Một dòng playwright in ra → phần trăm, hoặc None nếu dòng đó không có."""
    cuoi = None
    for m in _PHAN_TRAM.finditer(dong or ""):
        n = int(m.group(1))
        if 0 <= n <= 100:
            cuoi = n
    return cuoi


def thu_muc_chromium():
    """Nơi playwright để trình duyệt. Tôn trọng biến môi trường nếu có."""
    tuy_chinh = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if tuy_chinh and tuy_chinh not in ("0", "1"):
        return Path(tuy_chinh)
    return Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"


def da_co():
    """Chromium đã tải chưa.

    Hỏi thẳng playwright đường dẫn nó CHỜ ĐỢI, thay vì tự đoán tên thư mục:
    mỗi bản playwright gắn với một số build chromium riêng, nên một chromium cũ
    nằm đó vẫn không dùng được. Hỏi được thì đó là câu trả lời đúng nhất.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            duong = p.chromium.executable_path
        return bool(duong) and Path(duong).exists()
    except Exception:
        # Không hỏi được playwright (chưa cài, hoặc đang chạy trong vòng lặp
        # async) → đoán theo thư mục. Thà đoán còn hơn chặn người dùng lại.
        goc = thu_muc_chromium()
        if not goc.exists():
            return False
        return any(goc.glob("chromium-*/chrome-win/chrome.exe"))


def _lenh_tai():
    """Câu lệnh tải Chromium.

    Cách cũ là `sys.executable -m playwright install chromium`. Nó chỉ đúng khi
    chạy thẳng từ mã nguồn: sau khi biên dịch, `sys.executable` là server.exe
    chứ không phải python.exe, và server.exe không hiểu cờ `-m`.

    Gọi thẳng driver của playwright thì đúng trong CẢ HAI trường hợp — đó cũng
    chính là thứ mà `-m playwright` chạy bên dưới. Driver đi kèm ngay trong gói
    nên luôn có mặt.
    """
    try:
        from playwright._impl._driver import compute_driver_executable
        d = compute_driver_executable()
        if isinstance(d, (list, tuple)) and len(d) >= 2:
            return [str(d[0]), str(d[1]), "install", "chromium"]
        return [str(d), "install", "chromium"]
    except Exception:
        # Không hỏi được driver thì quay về cách cũ; ít ra bản chạy thẳng từ mã
        # nguồn vẫn tải được.
        return [sys.executable, "-m", "playwright", "install", "chromium"]


class TienTrinh:
    """Trạng thái một lượt tải, để giao diện hỏi."""

    def __init__(self):
        self.dang_chay = False
        self.phan_tram = 0
        self.xong      = False
        self.loi       = ""
        self.dong_cuoi = ""
        self._khoa     = threading.Lock()

    def trang_thai(self):
        with self._khoa:
            return {"dang_chay": self.dang_chay, "phan_tram": self.phan_tram,
                    "xong": self.xong, "loi": self.loi, "dong_cuoi": self.dong_cuoi}

    def bat_dau(self, cwd=None):
        """Chạy `playwright install chromium` ở luồng nền."""
        with self._khoa:
            if self.dang_chay:
                return False
            self.dang_chay, self.phan_tram = True, 0
            self.xong, self.loi, self.dong_cuoi = False, "", ""
        threading.Thread(target=self._chay, args=(cwd,), daemon=True).start()
        return True

    def _chay(self, cwd):
        try:
            p = subprocess.Popen(
                _lenh_tai(),
                cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            for dong in p.stdout:
                dong = dong.strip()
                if not dong:
                    continue
                pt = doc_phan_tram(dong)
                with self._khoa:
                    self.dong_cuoi = dong[:200]
                    if pt is not None:
                        # Chỉ tiến, không lùi: playwright tải nhiều gói nối
                        # tiếp nhau và mỗi gói lại đếm từ 0%, nhìn như treo.
                        self.phan_tram = max(self.phan_tram, pt)
            ma = p.wait()
            with self._khoa:
                self.dang_chay = False
                if ma == 0:
                    self.xong, self.phan_tram = True, 100
                else:
                    self.loi = f"playwright install kết thúc với mã {ma}"
        except Exception as e:
            with self._khoa:
                self.dang_chay, self.loi = False, str(e)


# Một lượt tải cho cả tiến trình server.
tien_trinh = TienTrinh()
