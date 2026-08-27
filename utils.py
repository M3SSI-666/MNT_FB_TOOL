"""
utils.py — Utilities dùng chung
"""

import os
import logging
import sys
import random
from datetime import datetime
from config import LOG_FILE, LOG_DIR

# ── Ẩn cửa sổ console của child process trên Windows ─────────────────────────
# Scheduler chạy ẩn (CREATE_NO_WINDOW) nên khi Playwright spawn driver node.exe,
# Windows cấp console MỚI → cửa sổ cmd đen hiện lên cùng Chrome mỗi lần đăng.
# Patch asyncio.create_subprocess_exec để mọi child async cũng chạy ẩn.
if sys.platform == "win32":
    import asyncio
    import subprocess

    _orig_cse = asyncio.create_subprocess_exec

    def _cse_no_window(*args, **kwargs):
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        return _orig_cse(*args, **kwargs)

    asyncio.create_subprocess_exec = _cse_no_window

_EFFECTIVE_LOG_FILE = os.environ.get("SCHEDULER_LOG_FILE", LOG_FILE)


def setup_logger(name: str = "mnt_fb") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    # Console — bỏ qua khi chạy bằng pythonw (không có console, sys.stdout=None)
    if sys.stdout is not None:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    # File — XOAY VÒNG để log không phình vô hạn.
    # 4 runner ghi mức DEBUG suốt ngày đêm: từng để autopost_homestay.log lên
    # tới 24MB. Giữ 3MB × 3 file (bản mới nhất + 2 bản cũ) là đủ để soi lỗi.
    os.makedirs(LOG_DIR, exist_ok=True)
    from logging.handlers import RotatingFileHandler
    fh = RotatingFileHandler(_EFFECTIVE_LOG_FILE, maxBytes=3 * 1024 * 1024,
                             backupCount=2, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


logger = setup_logger()


# ── Phân loại lỗi để báo trạng thái rõ ràng ─────────────────────────────────
class PostError(Exception):
    """Lỗi cơ sở khi đăng bài."""


class CookieDeadError(PostError):
    """Cookie hết hạn / bị đăng xuất — cần refresh cookie thủ công."""


class ComposerBiChan(PostError):
    """Facebook chặn acc đăng bài: hộp thoại 'Tạo bài viết' mở ra nhưng RỖNG.

    KHÔNG phải lỗi kỹ thuật, dù nhìn giống. Đã đo bằng ba phép thử tách biến
    trên acc 'Ngân Nấm' ngày 27/08:

        acc đó + nhóm khác            → rỗng
        acc KHOẺ + đúng nhóm đó       → mở bình thường, 12 nút
        acc đó + PROFILE SẠCH hoàn toàn → vẫn rỗng

    Nên không phải do nhóm, không phải do cache, không phải do profile. Biến duy
    nhất còn lại là chính tài khoản. Facebook chặn bằng cách trả về hộp thoại
    trống: 0 nút, 0 ô soạn thảo, đúng 12 ký tự tiêu đề — và KHÔNG có lỗi console
    hay request hỏng nào, tức là không có gì tải trượt cả.

    Đây là cùng loại tín hiệu với "bài bị gỡ", nên xử lý bằng đúng đường Spam:
    nghỉ, chuyển slot sang nuôi nick, một tiếng sau nhử lại.
    """


def classify_error(exc) -> tuple:
    """
    Đoán loại lỗi từ exception → (category, nhãn tiếng Việt) để hiển thị.
    category: 'cookie' | 'ratelimit' | 'transient' | 'selector' | 'other'
    """
    if isinstance(exc, CookieDeadError):
        return ("cookie", "Cookie hết hạn")
    msg = str(exc).lower()
    if any(k in msg for k in ("cookie", "logged out", "log in", "checkpoint", "đăng nhập", "login")):
        return ("cookie", "Cookie hết hạn")
    if any(k in msg for k in ("rate", "too many", "spam", "try again later", "tạm thời bị")):
        return ("ratelimit", "Bị giới hạn — thử lại sau")
    if any(k in msg for k in ("timeout", "timed out", "net::", "connection", "econn", "reset", "unreachable")):
        return ("transient", "Lỗi mạng/tạm thời")
    if any(k in msg for k in ("selector", "not found", "no element", "không tìm thấy nút", "đổi giao diện")):
        return ("selector", "Không thấy nút (FB đổi giao diện?)")
    return ("other", str(exc)[:50])


def jitter(base: float, pct: float = 0.3, floor: float = 0.0) -> float:
    """
    Trả về giá trị dao động ngẫu nhiên quanh `base` ±`pct` (mặc định ±30%).
    Dùng để phá vỡ các khoảng chờ cố định (đăng tự động trông tự nhiên hơn).
    Ví dụ: jitter(3) → khoảng 2.1–3.9 | jitter(1500) → ~1050–1950
    `floor`: giá trị tối thiểu (không bao giờ nhỏ hơn).
    """
    val = base * random.uniform(1 - pct, 1 + pct)
    return max(val, floor)


def jitter_ms(base_ms: int, pct: float = 0.3, floor_ms: int = 200) -> int:
    """Như jitter() nhưng cho mili-giây (Playwright wait_for_timeout)."""
    return int(jitter(base_ms, pct, floor_ms))


def truncate_text(text: str, max_len: int = 60) -> str:
    return text[:max_len] + "..." if len(text) > max_len else text


def format_full_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_time_to_post(gio_dang: str, window_minutes: int = 3) -> bool:
    """Kiểm tra giờ đăng có trong cửa sổ ±window_minutes không."""
    try:
        h, m   = map(int, gio_dang.strip().split(":"))
        now    = datetime.now()
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        diff   = (now - target).total_seconds() / 60
        return 0 <= diff <= window_minutes
    except Exception:
        return False
