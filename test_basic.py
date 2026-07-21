"""
test_basic.py — Smoke test cho logic thuần (không cần Playwright/Facebook).
Chạy:  python test_basic.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")   # cho phép in emoji ở mọi console
except Exception:
    pass

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}")


# ── utils: jitter (chống nhịp thời gian cố định) ───────────────────────────
from utils import jitter, jitter_ms, classify_error, CookieDeadError

vals = [jitter(3, pct=0.5, floor=1.5) for _ in range(500)]
check("jitter nằm trong ±50%",        all(1.5 <= v <= 4.5 for v in vals))
check("jitter tôn trọng floor",        all(v >= 1.5 for v in vals))
check("jitter thật sự ngẫu nhiên",     len({round(v, 3) for v in vals}) > 50)
check("jitter_ms trả về int",          isinstance(jitter_ms(1500), int))
check("jitter_ms có sàn tối thiểu",    all(jitter_ms(10, floor_ms=200) >= 200 for _ in range(100)))

# ── utils: phân loại lỗi ───────────────────────────────────────────────────
check("CookieDeadError -> cookie",     classify_error(CookieDeadError("x"))[0] == "cookie")
check("keyword login -> cookie",       classify_error(Exception("redirect to login"))[0] == "cookie")
check("timeout -> transient",          classify_error(Exception("Timeout 30000ms"))[0] == "transient")
check("rate limit -> ratelimit",       classify_error(Exception("rate limit hit"))[0] == "ratelimit")
check("nút không thấy -> selector",    classify_error(Exception("Không tìm thấy nút Đăng"))[0] == "selector")
check("lỗi lạ giữ nguyên message",     classify_error(Exception("abcxyz"))[1] == "abcxyz")

# ── db: reorder pages (DB tạm, KHÔNG đụng dữ liệu thật) ─────────────────────
import db

_tmp = Path(tempfile.gettempdir()) / "mnt_test.db"
if _tmp.exists():
    _tmp.unlink()
db.DB_PATH = _tmp
db.init_db()
ids = [db.upsert_page({"ten_page": f"P{i}"}) for i in range(3)]
db.reorder_pages(list(reversed(ids)))
got = [p["id"] for p in db.get_pages()]
check("reorder_pages lưu đúng thứ tự", got == list(reversed(ids)))
check("get_pages sắp theo order_idx",  got == list(reversed(ids)))
try:
    _tmp.unlink(missing_ok=True)   # best-effort; sqlite WAL có thể còn giữ file
except OSError:
    pass

print(f"\n{_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
