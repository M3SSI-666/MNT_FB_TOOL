"""
test_basic.py — Smoke test cho logic thuần (không cần Playwright/Facebook).
Chạy:  python test_basic.py

Toàn bộ test chạy trên DB tạm — KHÔNG đụng vào data/app.db thật.
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

# ── DB tạm — phải set TRƯỚC khi import server (server gọi init_db lúc import) ──
import db

_tmp = Path(tempfile.gettempdir()) / "mnt_test.db"
for suffix in ("", "-wal", "-shm"):
    Path(str(_tmp) + suffix).unlink(missing_ok=True)
db.DB_PATH = _tmp
db.init_db()

# Scheduler cần env var này lúc import, nếu không sẽ sys.exit(1)
os.environ.setdefault("SCHEDULER_LOAI", "homestay")

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

# ── db: reorder pages ──────────────────────────────────────────────────────
ids = [db.upsert_page({"ten_page": f"P{i}"}) for i in range(3)]
db.reorder_pages(list(reversed(ids)))
got = [p["id"] for p in db.get_pages()]
check("reorder_pages lưu đúng thứ tự", got == list(reversed(ids)))
check("get_pages sắp theo order_idx",  got == list(reversed(ids)))

# ── db: busy_timeout được bật (tránh 'database is locked') ─────────────────
with db._conn() as _c:
    _bt = _c.execute("PRAGMA busy_timeout").fetchone()[0]
check("SQLite có busy_timeout > 0",    _bt >= 1000)

# ── db: lấy account theo id ────────────────────────────────────────────────
_acc_id = db.upsert_account({"ten_acc": "TestAcc", "password": "pw-that",
                             "xs": "xs-that", "twofa": "2fa-that"})
check("get_account_by_id trả đúng acc", (db.get_account_by_id(_acc_id) or {}).get("ten_acc") == "TestAcc")
check("get_account_by_id id lạ -> None", db.get_account_by_id(999999) is None)

# ── scheduler: chính sách retry ────────────────────────────────────────────
import scheduler

check("transient -> retry lần 1",      scheduler._should_retry("transient", 1) is True)
check("transient -> hết lượt thì dừng", scheduler._should_retry("transient", scheduler.MAX_ATTEMPTS) is False)
check("ratelimit KHÔNG retry",         scheduler._should_retry("ratelimit", 1) is False)
check("cookie KHÔNG retry",            scheduler._should_retry("cookie", 1) is False)
check("selector KHÔNG retry",          scheduler._should_retry("selector", 1) is False)
check("backoff tăng dần",              scheduler._retry_delay(2) > scheduler._retry_delay(1) * 0.9)

# ── scheduler: parse UID nhóm đầu ──────────────────────────────────────────
_pfg = scheduler._parse_first_group_uid
check("parse URL nhóm -> uid",         _pfg("https://facebook.com/groups/123456789/") == "123456789")
check("parse UID số thuần",            _pfg("123456789") == "123456789")
check("parse slug chữ",                _pfg("homestaytimescity") == "homestaytimescity")
check("chuỗi rỗng -> rỗng",            _pfg("") == "")

# ── server: KHÔNG rò rỉ credential qua /api/accounts ───────────────────────
import server

_client = server.app.test_client()
_res    = _client.get("/api/accounts")
_rows   = _res.get_json()["data"]
_row    = next((r for r in _rows if r["id"] == _acc_id), None)

check("/api/accounts trả về acc",      _row is not None)
if _row:
    check("password bị che",           _row["password"] == server.SECRET_MASK)
    check("xs bị che",                 _row["xs"] == server.SECRET_MASK)
    check("twofa bị che",              _row["twofa"] == server.SECRET_MASK)
    check("không lộ giá trị thật",     "pw-that" not in _res.get_data(as_text=True))
    check("trường thường vẫn hiện",    _row["ten_acc"] == "TestAcc")

# Lưu form với dấu che KHÔNG được ghi đè credential thật
_client.post("/api/accounts/save", json={"id": _acc_id, "ten_acc": "TestAcc2",
                                         "password": server.SECRET_MASK})
check("dấu che không ghi đè password", db.get_account_by_id(_acc_id)["password"] == "pw-that")
check("trường thường vẫn lưu được",    db.get_account_by_id(_acc_id)["ten_acc"] == "TestAcc2")

# Sửa inline bằng dấu che cũng phải bị bỏ qua
_client.post(f"/api/accounts/{_acc_id}/field", json={"field": "xs", "value": server.SECRET_MASK})
check("dấu che không ghi đè xs",       db.get_account_by_id(_acc_id)["xs"] == "xs-that")

# Nhưng giá trị thật thì vẫn sửa được bình thường
_client.post(f"/api/accounts/{_acc_id}/field", json={"field": "xs", "value": "xs-moi"})
check("sửa xs bằng giá trị thật OK",   db.get_account_by_id(_acc_id)["xs"] == "xs-moi")

# ── dọn dẹp ────────────────────────────────────────────────────────────────
for suffix in ("", "-wal", "-shm"):
    try:
        Path(str(_tmp) + suffix).unlink(missing_ok=True)
    except OSError:
        pass   # best-effort; sqlite WAL có thể còn giữ file

print(f"\n{_passed} passed, {_failed} failed")
sys.exit(1 if _failed else 0)
