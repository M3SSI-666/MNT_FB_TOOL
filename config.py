"""
config.py — Cấu hình MNT_FB (không cần Google Cloud, không cần API key ngoài)
"""

import os
from pathlib import Path

# BASE_DIR = nơi để MÃ NGUỒN. DATA_ROOT = nơi để DỮ LIỆU. Hai thứ này tách
# nhau ra được, và đó là điều kiện để đóng gói thành bộ cài:
#
#   chạy từ mã nguồn (như hiện nay)  → DATA_ROOT = BASE_DIR, y hệt trước
#   cài bằng setup.exe               → code ở Program Files (chỉ đọc),
#                                       MNT_DATA_DIR trỏ sang %LOCALAPPDATA%
#
# Bắt buộc phải tách vì `profiles/` là 2,1 GB ghi liên tục — Windows không cho
# ghi vào Program Files. Ngoài ra tách rồi thì xoá code cài lại cũng không mất
# dữ liệu, và sao lưu chỉ cần chép một thư mục.
BASE_DIR   = Path(__file__).parent
DATA_ROOT  = Path(os.environ.get("MNT_DATA_DIR", "").strip() or BASE_DIR)

DATA_DIR   = DATA_ROOT / "data"
MEDIA_DIR  = DATA_DIR / "media"
LOG_DIR    = DATA_ROOT / "logs"
DB_PATH    = DATA_DIR / "app.db"
# Cookie và profile trình duyệt — trước đây mỗi file tự tính từ __file__ của
# CHÍNH NÓ (7 chỗ, 4 file), nên không có cách nào dời chúng đi nơi khác.
COOKIES_DIR  = DATA_ROOT / "cookies"
PROFILES_DIR = DATA_ROOT / "profiles"

# Log files per runner
LOG_FILES = {
    "homestay": str(LOG_DIR / "autopost_homestay.log"),
    "thue":     str(LOG_DIR / "autopost_thue.log"),
    "ban":      str(LOG_DIR / "autopost_ban.log"),
    "page":     str(LOG_DIR / "autopost_page.log"),
    "nuoi":     str(LOG_DIR / "autopost_nuoi.log"),
}
LOG_FILE = str(LOG_DIR / "autopost.log")

# Headless browser
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

# Web server
PORT = int(os.environ.get("PORT", "8080"))

# Scheduler
CHECK_EVERY_SEC = 60
WINDOW_MINUTES  = 3
MAX_WORKERS     = 15

# Media subdirs per content type
CONTENT_MEDIA_DIRS = {
    "homestay": str(MEDIA_DIR / "content" / "homestay"),
    "thue":     str(MEDIA_DIR / "content" / "thue"),
    "ban":      str(MEDIA_DIR / "content" / "ban"),
}

# Đảm bảo tất cả thư mục tồn tại
for _d in [DATA_DIR, MEDIA_DIR, LOG_DIR, COOKIES_DIR, PROFILES_DIR,
           MEDIA_DIR / "content" / "homestay",
           MEDIA_DIR / "content" / "thue",
           MEDIA_DIR / "content" / "ban",
           MEDIA_DIR / "uploads"]:
    _d.mkdir(parents=True, exist_ok=True)
