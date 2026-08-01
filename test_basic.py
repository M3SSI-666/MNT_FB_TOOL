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

# ── db: reorder content (order_idx có phạm vi từng loai) ───────────────────
_r1, _r2, _r3 = [db.upsert_content({"loai": "homestay", "ma_content": f"R{i}"}) for i in (1, 2, 3)]
_t1, _t2      = [db.upsert_content({"loai": "thue",     "ma_content": f"T{i}"}) for i in (1, 2)]
check("content mới xếp CUỐI danh sách",
      [c["id"] for c in db.get_content("homestay")][-3:] == [_r1, _r2, _r3])
db.reorder_content([_r3, _r1, _r2])
check("reorder_content lưu đúng thứ tự",
      [c["id"] for c in db.get_content("homestay")][-3:] == [_r3, _r1, _r2])
check("reorder_content không ảnh hưởng loai khác",
      [c["id"] for c in db.get_content("thue")][-2:] == [_t1, _t2])
check("thứ tự mới vẫn đúng khi lọc su_dung",
      [c["id"] for c in db.get_content("homestay", su_dung="Có")][-3:] == [_r3, _r1, _r2])
# Thêm dòng SAU khi đã kéo-thả thì vẫn phải xuống cuối, không chen lên đầu
_r4 = db.upsert_content({"loai": "homestay", "ma_content": "R4"})
check("content mới vẫn xuống cuối sau reorder",
      [c["id"] for c in db.get_content("homestay")][-4:] == [_r3, _r1, _r2, _r4])

# ── db: reorder uid_groups (chỉ nhóm trống, TIME1-7 phải nguyên vẹn) ──────
_g1 = db.upsert_uid_group({"ma_nhom": "",      "uid": "1110000", "ten_nhom": "G1"})
_g2 = db.upsert_uid_group({"ma_nhom": "",      "uid": "2220000", "ten_nhom": "G2"})
_gt = db.upsert_uid_group({"ma_nhom": "TIME1", "uid": "9990000"})
db.reorder_uid_groups([_g2, _g1])
_all = db.get_all_uid_groups()
check("reorder_uid_groups đổi thứ tự nhóm trống",
      [g["id"] for g in _all if g["ma_nhom"] == ""][-2:] == [_g2, _g1])
check("get_all_uid_groups vẫn gom theo ma_nhom",
      [g["ma_nhom"] for g in _all] == sorted(g["ma_nhom"] for g in _all))
check("nhóm TIME1 không bị ảnh hưởng",
      [g["id"] for g in db.get_uid_groups_by_code("TIME1")] == [_gt])

# ── db: migration idempotent — gọi lại init_db không được mất thứ tự ──────
# Đây là assert duy nhất thật sự chạy qua nhánh guard của _add_col, tức chỗ mà
# migration sai sẽ chỉ hại DB cũ của người dùng, không bao giờ hại máy cài mới.
db.init_db()
check("init_db chạy lại: thứ tự content còn nguyên",
      [c["id"] for c in db.get_content("homestay")][-4:] == [_r3, _r1, _r2, _r4])
check("init_db chạy lại: thứ tự uid nhóm còn nguyên",
      [g["id"] for g in db.get_all_uid_groups() if g["ma_nhom"] == ""][-2:] == [_g2, _g1])

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

# ── ảnh content: xóa content/bỏ ảnh thì file cũng đi theo ──────────────────
_u = db._tach_urls
check("tách URL bỏ khoảng trắng",      _u(" a.jpg , b.jpg ") == {"a.jpg", "b.jpg"})
check("tách URL bỏ chuỗi rỗng",        _u("", None, "a.jpg,,") == {"a.jpg"})
check("tách URL gộp nhiều chuỗi",      _u("a.jpg", "b.jpg") == {"a.jpg", "b.jpg"})

_c1 = db.upsert_content({"loai":"homestay","ma_content":"IMG1",
                         "link_anh_hook":"/m/h.jpg","link_anh":"/m/x.jpg, /m/chung.jpg"})
_c2 = db.upsert_content({"loai":"homestay","ma_content":"IMG2",
                         "link_anh":"/m/y.jpg, /m/chung.jpg"})
check("lấy đúng ảnh của 1 content",
      db.get_content_image_urls(_c1) == {"/m/h.jpg", "/m/x.jpg", "/m/chung.jpg"})
check("gom ảnh của MỌI content",
      {"/m/h.jpg","/m/x.jpg","/m/y.jpg","/m/chung.jpg"} <= db.get_all_content_image_urls())
check("content không tồn tại -> rỗng", db.get_content_image_urls(999999) == set())
# Ảnh dùng chung: xóa 1 content thì ảnh chung PHẢI còn (content kia vẫn dùng)
db.delete_content(_c1)
check("xóa content: ảnh riêng hết dùng",
      "/m/x.jpg" not in db.get_all_content_image_urls())
check("xóa content: ảnh CHUNG vẫn còn dùng",
      "/m/chung.jpg" in db.get_all_content_image_urls())
db.delete_content(_c2)
check("xóa nốt: ảnh chung mới hết dùng",
      "/m/chung.jpg" not in db.get_all_content_image_urls())

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

# Nhiều acc cùng bật nuôi: các phiên phải TÁCH GIÃN, không chụm một cục.
# (Lịch thật: 4 acc luân phiên mỗi 3 phút, 3 acc bật nuôi cùng chu kỳ 150.)
_accs4 = ["A1","A2","A3","A4"]
_sched4 = []
_t = 5*60
for _k in range(441):
    _sched4.append({"ten_acc":_accs4[_k%4],
                    "gio_dang":f"{(_t//60)%24:02d}:{_t%60:02d}","stt":_k+1})
    _t += 3
nuoi_nick.plan_warming_conversion(_sched4, {"A2":150,"A3":150,"A4":150})
_wrows = [(r["gio_dang"], r["ten_acc"]) for r in _sched4 if r["hoat_dong"]=="nuoi_nick"]
_wt = nuoi_nick._unwrap_times([g for g,_ in _wrows])
_wgaps = [b-a for a,b in zip(_wt,_wt[1:])]
check("nhiều acc: phiên nuôi không chụm",  min(_wgaps) >= nuoi_nick.MIN_GAP_MIN)
check("nhiều acc: giãn cách đáng kể",      min(_wgaps) >= 30)
check("3 acc đều có phiên nuôi",           len({a for _,a in _wrows}) == 3)
# Mỗi acc vẫn tôn trọng chu kỳ riêng của nó
for _a in ("A2","A3","A4"):
    _at = nuoi_nick._unwrap_times([g for g,x in _wrows if x==_a])
    if not all(b-a >= 150 for a,b in zip(_at,_at[1:])):
        break
else:
    _a = None
check("mỗi acc vẫn giữ đúng chu kỳ 150",   _a is None)
# Acc không bật nuôi không bị đụng
check("acc không bật nuôi vẫn đăng hết",
      all(r["hoat_dong"]=="dang_bai" for r in _sched4 if r["ten_acc"]=="A1"))

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

# parse_group_urls: nhiều nhóm chat, mỗi phiên bốc ngẫu nhiên 1 nhóm
_pg = nuoi_nick.parse_group_urls
check("1 nhóm — tương thích cài đặt cũ",
      _pg("https://www.facebook.com/messages/t/111") == ["https://www.facebook.com/messages/t/111"])
check("nhiều nhóm, mỗi dòng 1",
      _pg("https://a/1\nhttps://a/2\nhttps://a/3") == ["https://a/1","https://a/2","https://a/3"])
check("bỏ dòng rỗng và khoảng trắng thừa",
      _pg("  https://a/1  \n\n  https://a/2 ") == ["https://a/1","https://a/2"])
check("chấp nhận phân cách dấu phẩy",
      _pg("https://a/1, https://a/2") == ["https://a/1","https://a/2"])
check("bỏ link trùng",              _pg("https://a/1\nhttps://a/1") == ["https://a/1"])
check("bỏ dòng không phải link",    _pg("ghi chu\nhttps://a/1") == ["https://a/1"])
check("rỗng -> danh sách rỗng",     _pg("") == [])
check("giữ nguyên thứ tự nhập",
      _pg("https://z/9\nhttps://a/1") == ["https://z/9","https://a/1"])

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

# Acc bị FB chặn nhắn tin -> nhận ra để bỏ qua, không cố gửi
_restrict_real = ("Xác nhận danh tính để gửi tin nhắn "
                  "Một số hành động đã bị hạn chế do có hoạt động bất thường. "
                  "Tìm hiểu thêm Cách xác nhận")
check("nhận ra chặn (text thật của FB)", nuoi_nick.is_messaging_restricted(_restrict_real) is True)
check("nhận ra chặn tiếng Anh",
      nuoi_nick.is_messaging_restricted("Confirm your identity to send messages") is True)
check("chat bình thường KHÔNG bị nhầm",
      nuoi_nick.is_messaging_restricted("hello các anh em hahaha i am back") is False)
check("text rỗng -> không chặn",       nuoi_nick.is_messaging_restricted("") is False)
check("None -> không chặn",            nuoi_nick.is_messaging_restricted(None) is False)

# Messenger đòi mã PIN khôi phục chat -> nhận ra để bấm bỏ qua
_pin_real = ("Nhập mã PIN để khôi phục đoạn chat của bạn "
             "Một số tin nhắn còn thiếu. Hãy nhập mã PIN để khôi phục lịch sử chat của bạn.")
check("nhận ra hộp thoại PIN (text thật)", nuoi_nick.has_pin_dialog(_pin_real) is True)
check("nhận ra PIN tiếng Anh",
      nuoi_nick.has_pin_dialog("Enter your PIN to restore your chat") is True)
check("chat thường KHÔNG bị nhầm là PIN",
      nuoi_nick.has_pin_dialog("hôm nay trời đẹp nhỉ mọi người ăn cơm chưa") is False)
check("PIN: text rỗng -> False",       nuoi_nick.has_pin_dialog("") is False)

# Thư viện câu mẫu đi kèm
_mau_res = _client_mau = None
import server as _srv
_mau_res = _srv.app.test_client().get("/api/nuoi/msg-mau").get_json()
_mau_lines = (_mau_res.get("text") or "").split("\n")
check("thư viện mẫu đọc được",         _mau_res.get("ok") is True)
check("có ~500 câu mẫu",               _mau_res.get("total", 0) >= 500)
check("mẫu không lẫn dòng ghi chú",    not any(l.startswith("#") for l in _mau_lines))
check("mẫu không có dòng rỗng",        all(l.strip() for l in _mau_lines))
check("mẫu không trùng câu",           len(_mau_lines) == len(set(_mau_lines)))
check("câu mẫu đều ngắn gọn",          all(len(l) <= 60 for l in _mau_lines))

# select_session_activities: chỉ lấy hành động đang bật, luôn ≥1, chỉ tên hợp lệ
import random as _rnd
_ALL_ON = {"nuoi_enable_story":1,"nuoi_enable_feed":1,
           "nuoi_enable_like":1,"nuoi_enable_message":1}
# Nuôi nick CHỈ có 4 hành động: story, feed, like, message.
check("đúng 4 hành động nuôi",         set(nuoi_nick._ACTIVITY_FNS) == {"story","feed","like","message"})
check("đã gỡ hẳn tính năng kết bạn",
      not any(k in nuoi_nick.DEFAULTS for k in
              ("nuoi_enable_accept","nuoi_enable_addfriend","nuoi_friend_min")))
_valid = set(nuoi_nick._ACTIVITY_FNS)
_samples = [nuoi_nick.select_session_activities(_ALL_ON, _rnd.Random(i)) for i in range(200)]
check("MỖI phiên làm ĐỦ 4 hành động",   all(set(s) == _valid for s in _samples))
check("chỉ chứa tên hành động hợp lệ",  all(set(s) <= _valid for s in _samples))
check("không lặp hành động trong phiên", all(len(s)==len(set(s)) for s in _samples))
# Đủ 4 nhưng THỨ TỰ phải xáo, không rập khuôn
check("thứ tự đa dạng giữa các phiên",  len({tuple(s) for s in _samples}) > 10)
check("không phải lúc nào cũng 1 thứ tự", _samples[0] != _samples[1] or _samples[0] != _samples[2])
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
