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

# ── nuôi nick: xếp phiên theo CHU KỲ (logic thuần) ─────────────────────────
import nuoi_nick

# normalize_interval: mặc định 150 (2h30), chặn giá trị rác / quá dày
check("interval mặc định 150",         nuoi_nick.normalize_interval(None) == 150)
check("interval rỗng -> mặc định",     nuoi_nick.normalize_interval("") == 150)
check("interval 0 -> mặc định",        nuoi_nick.normalize_interval(0) == 150)
check("interval hợp lệ giữ nguyên",    nuoi_nick.normalize_interval(90) == 90)
check("interval quá nhỏ bị chặn",      nuoi_nick.normalize_interval(5) == nuoi_nick.MIN_INTERVAL_MIN)

# _unwrap_times: lịch xuyên đêm (02:00 phải SAU 23:00, không phải trước)
check("qua nửa đêm cộng 24h",          nuoi_nick._unwrap_times(["22:00","23:00","01:00"]) == [1320,1380,1500])

# plan_warming_conversion: cứ mỗi `chu kỳ` phút thì 1 slot thành nuôi
def _mkrows(acc, n, step=30, start=7*60):
    return [{"ten_acc":acc,
             "gio_dang":f"{((start+i*step)//60)%24:02d}:{(start+i*step)%60:02d}",
             "stt":i+1} for i in range(n)]

# A: 24 slot cách 30' (07:00→18:30 = 690'), chu kỳ 150' -> ~5 phiên nuôi
sched = _mkrows("A",24) + _mkrows("B",24)
n_conv = nuoi_nick.plan_warming_conversion(sched, {"A":150})
a_rows = [r for r in sched if r["ten_acc"]=="A"]
b_warm = sum(1 for r in sched if r["ten_acc"]=="B" and r["hoat_dong"]=="nuoi_nick")
a_warm_times = nuoi_nick._unwrap_times([r["gio_dang"] for r in a_rows if r["hoat_dong"]=="nuoi_nick"])
check("acc không bật nuôi: 0 slot",    b_warm == 0)
check("acc bật nuôi có phiên nuôi",    len(a_warm_times) >= 4)
check("tổng converted khớp",           n_conv == len(a_warm_times))
check("slot còn lại vẫn đăng bài",     any(r["hoat_dong"]=="dang_bai" for r in a_rows))
check("khoảng cách 2 phiên >= chu kỳ",
      all(b-a >= 150 for a,b in zip(a_warm_times, a_warm_times[1:])))

# Chu kỳ ngắn hơn -> nhiều phiên nuôi hơn
s2 = _mkrows("C",24); nuoi_nick.plan_warming_conversion(s2, {"C":60})
s3 = _mkrows("D",24); nuoi_nick.plan_warming_conversion(s3, {"D":240})
n60  = sum(1 for r in s2 if r["hoat_dong"]=="nuoi_nick")
n240 = sum(1 for r in s3 if r["hoat_dong"]=="nuoi_nick")
check("chu kỳ ngắn -> nhiều phiên hơn", n60 > n240)

# build_warming_schedule: acc CHỈ NUÔI, không có slot đăng nào
rows = nuoi_nick.build_warming_schedule(
    [{"ten":"N1","interval":150},{"ten":"N2","interval":150}], "07:00", "23:00")
check("lịch nuôi có dòng",             len(rows) > 0)
check("mọi dòng đều là nuôi_nick",     all(r["hoat_dong"]=="nuoi_nick" for r in rows))
check("mọi dòng thuộc loai='nuoi'",    all(r["loai"]=="nuoi" for r in rows))
check("không dòng nào có content",     all(r["ma_content"]=="" for r in rows))
check("stt đánh số liên tục",          [r["stt"] for r in rows] == list(range(1,len(rows)+1)))
n1 = nuoi_nick._unwrap_times([r["gio_dang"] for r in rows if r["ten_acc"]=="N1"])
check("mỗi acc cách nhau ~chu kỳ",      all(b-a >= 150 for a,b in zip(n1, n1[1:])))

# Chống trùng giờ: kể cả khi 2 acc có chu kỳ KHÁC nhau (150 vs 120 sẽ gặp nhau
# ở 12:00 nếu không giãn) — mọi phiên phải cách nhau >= MIN_GAP_MIN.
mix = nuoi_nick.build_warming_schedule(
    [{"ten":"M1","interval":150},{"ten":"M2","interval":120}], "07:00", "23:00")
mt = nuoi_nick._unwrap_times([r["gio_dang"] for r in mix])
check("không 2 phiên nào trùng giờ",    len(mt) == len(set(mt)))
check("mọi phiên cách nhau >= min gap",
      all(b-a >= nuoi_nick.MIN_GAP_MIN for a,b in zip(mt, mt[1:])))
check("lịch nuôi nằm trong khung giờ",
      all(7*60 <= t <= 23*60 for t in mt))

# pick_messages: bốc câu nhắn, không lặp 2 câu giống nhau liền nhau
import random as _r0
_pool = ["câu A", "câu B", "câu C"]
for _seed in range(50):
    _msgs = nuoi_nick.pick_messages(_pool, 3, _r0.Random(_seed))
    if len(_msgs) != 3 or any(a == b for a, b in zip(_msgs, _msgs[1:])):
        break
else:
    _msgs = None
check("bốc đủ số câu, không lặp liền kề", _msgs is None)
check("thư viện 1 câu vẫn chạy được",
      nuoi_nick.pick_messages(["chỉ 1 câu"], 3, _r0.Random(1)) == ["chỉ 1 câu"]*3)
check("thư viện rỗng -> không câu nào",   nuoi_nick.pick_messages([], 3, _r0.Random(1)) == [])
check("xin 0 câu -> rỗng",                nuoi_nick.pick_messages(_pool, 0, _r0.Random(1)) == [])
check("mọi câu đều lấy từ thư viện",
      set(nuoi_nick.pick_messages(_pool, 10, _r0.Random(7))) <= set(_pool))

# select_session_activities: chỉ lấy hành động đang bật, luôn ≥1, chỉ tên hợp lệ
import random as _rnd
_ALL_ON = {"nuoi_enable_feed":1,"nuoi_enable_story":1,"nuoi_enable_accept":1,
           "nuoi_enable_addfriend":1,"nuoi_enable_message":1}
_valid = set(nuoi_nick._ACTIVITY_FNS)
_samples = [nuoi_nick.select_session_activities(_ALL_ON, _rnd.Random(i)) for i in range(200)]
check("phiên nào cũng ≥1 hành động",   all(len(s) >= 1 for s in _samples))
check("chỉ chứa tên hành động hợp lệ",  all(set(s) <= _valid for s in _samples))
check("không lặp hành động trong phiên", all(len(s)==len(set(s)) for s in _samples))
check("có sự đa dạng giữa các phiên",   len({tuple(s) for s in _samples}) > 5)
# Hành động bị tắt thì không bao giờ xuất hiện
_only_feed = nuoi_nick.select_session_activities({"nuoi_enable_feed":1}, _rnd.Random(1))
check("tắt hết trừ feed -> chỉ feed",  _only_feed == ["feed"])
check("không bật gì -> rỗng",          nuoi_nick.select_session_activities({}, _rnd.Random(1)) == [])

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
