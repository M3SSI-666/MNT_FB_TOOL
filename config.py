"""
config.py — Cấu hình MNT_FB (không cần Google Cloud, không cần API key ngoài)
"""

import os
from pathlib import Path

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
MEDIA_DIR  = DATA_DIR / "media"
LOG_DIR    = BASE_DIR / "logs"
DB_PATH    = DATA_DIR / "app.db"

# Log files per runner
LOG_FILES = {
    "homestay": str(LOG_DIR / "autopost_homestay.log"),
    "thue":     str(LOG_DIR / "autopost_thue.log"),
    "ban":      str(LOG_DIR / "autopost_ban.log"),
    "page":     str(LOG_DIR / "autopost_page.log"),
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
for _d in [DATA_DIR, MEDIA_DIR, LOG_DIR,
           MEDIA_DIR / "content" / "homestay",
           MEDIA_DIR / "content" / "thue",
           MEDIA_DIR / "content" / "ban",
           MEDIA_DIR / "uploads"]:
    _d.mkdir(parents=True, exist_ok=True)
